import logging
import os
import subprocess
import tempfile
import uuid
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError

from api import args
from api.schemas.check_upload_task import TriggerKB
from api.utils.aws_knowledge_base import AWSKnowledgeBaseUtils
from api.utils.opensearch_util import OpenSearchUtil

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s - %(message)s", "%Y-%m-%d %H:%M:%S")
console_handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(console_handler)

s3 = boto3.client("s3", region_name=args.aws_region)
opensearch_client = OpenSearchUtil()
kb_utils = AWSKnowledgeBaseUtils()


def check_uploads_task(trigger_kb: TriggerKB):
    """
    Scan S3 /uploads/ for new files.

    If PDF: move directly to /docs/.
    If DOCX/PPTX: convert → PDF → /docs/.
    Copies originals → /originals/.
    Updates OpenSearch entries.
    Triggers Knowledge Base ingestion for processed documents.
    """
    is_private = trigger_kb.is_private
    target_index = args.aos_private_documents_index if is_private else args.aos_documents_index

    bucket = args.s3_bucket
    base_prefix = args.s3_folder_prefix.rstrip("/")
    docs_prefix = f"{base_prefix}/{args.s3_docs_prefix.strip('/')}/"

    allowed_exts = [e.strip() for e in args.allowed_extensions.split(",")]
    conversion_exts = [e.strip() for e in args.conversion_extensions.split(",")]

    logger.info("Starting check_uploads_task…")
    logger.info(f"Processing only explicitly passed files: {len(trigger_kb.files)} file(s)")

    # Nothing to process
    if not trigger_kb.files:
        logger.info("TriggerKB.files is empty. Nothing to process.")
        return

    new_files_for_ingestion = []

    try:
        for item in trigger_kb.files:
            logger.info("--------------------------------------------------")
            logger.info(f"Processing item: {item.model_dump()}")
            logger.info("--------------------------------------------------")

            original_s3_path = item.s3_path  # full S3 URI
            parsed = urlparse(original_s3_path)
            key = parsed.path.lstrip("/")  # bucket key
            file_name = os.path.basename(key)
            file_ext = os.path.splitext(key)[-1].lower()
            base_name = os.path.splitext(file_name)[0]

            logger.info(f"Processing: {original_s3_path}")

            if file_ext not in allowed_exts:
                logger.info(f"Skipping {file_name}: extension {file_ext} not allowed.")
                continue

            with tempfile.TemporaryDirectory() as tmp_dir:
                local_file_path = os.path.join(tmp_dir, file_name)

                try:
                    s3.download_file(bucket, key, local_file_path)
                except ClientError as e:
                    logger.error(f"Failed to download {key} from S3: {e}")
                    continue

                orig_key = key.replace("uploads/", "originals/")

                # Determine doc_key based on whether conversion is needed
                if file_ext in conversion_exts:
                    doc_key = f"{docs_prefix}{base_name}.pdf"
                else:
                    doc_key = key.replace("uploads/", "docs/")

                # Copy original file to originals/
                if file_ext != ".pdf":
                    try:
                        s3.copy_object(
                            Bucket=bucket,
                            CopySource={"Bucket": bucket, "Key": key},
                            Key=orig_key,
                        )
                        logger.info(f"Copied original file to {orig_key}")
                    except Exception as e:
                        logger.warning(f"Failed to copy to originals/: {e}")

                try:
                    if file_ext in conversion_exts:
                        logger.info(f"Converting {file_name} → PDF using LibreOffice...")

                        pdf_output_dir = os.path.join(tmp_dir, "pdf-output")
                        os.makedirs(pdf_output_dir, exist_ok=True)

                        subprocess.run(
                            [
                                "libreoffice",
                                "--headless",
                                "--invisible",
                                "--norestore",
                                "--convert-to",
                                "pdf",
                                "--outdir",
                                pdf_output_dir,
                                os.path.abspath(local_file_path),
                            ],
                            check=True,
                        )

                        converted_pdf = os.path.join(pdf_output_dir, f"{base_name}.pdf")
                        if os.path.exists(converted_pdf) and os.path.getsize(converted_pdf) > 1000:
                            s3.upload_file(converted_pdf, bucket, doc_key)
                            logger.info(f"Uploaded converted PDF to {doc_key}")
                        else:
                            logger.warning(f"Conversion failed for the file: {file_name}, copying original instead")
                            s3.copy_object(
                                Bucket=bucket,
                                CopySource={"Bucket": bucket, "Key": key},
                                Key=doc_key,
                            )
                    else:
                        # Direct copy for PDF or other allowed extensions (e.g. .xlsx, .csv)
                        s3.copy_object(
                            Bucket=bucket,
                            CopySource={"Bucket": bucket, "Key": key},
                            Key=doc_key,
                        )
                        logger.info(f"Stored {file_ext} directly to {doc_key}")

                    # Delete uploaded file after processing
                    s3.delete_object(Bucket=bucket, Key=key)
                    logger.info(f"Deleted {file_name} from uploads/")

                    # Update OpenSearch entry
                    uploaded_s3_path = f"s3://{bucket}/{doc_key}"
                    original_location = f"s3://{bucket}/{orig_key}" if file_ext in conversion_exts else uploaded_s3_path

                    try:
                        query = {
                            "query": {
                                "bool": {
                                    "should": [
                                        {"term": {"object_store.converted.keyword": original_s3_path}},
                                        {"term": {"object_store.location.keyword": original_s3_path}},
                                    ],
                                    "minimum_should_match": 1,
                                }
                            },
                            "size": 1,
                        }

                        resp = opensearch_client.client.search(index=target_index, body=query)
                        hits = resp.get("hits", {}).get("hits", [])

                        if hits:
                            doc_hit = hits[0]
                            document_id = doc_hit["_source"].get("document_id", str(uuid.uuid4().hex))

                            opensearch_client.client.update(
                                index=target_index,
                                id=doc_hit["_id"],
                                body={
                                    "doc": {
                                        "document_name": file_name,
                                        "object_store": {
                                            "type": "s3",
                                            "converted": uploaded_s3_path,
                                            "location": original_location,
                                        },
                                        "sync_status": "pending",
                                        "last_synced_at": None,
                                    }
                                },
                            )

                            logger.info(f"Updated OpenSearch entry for {file_name}")

                            new_files_for_ingestion.append(
                                {
                                    "s3_path": uploaded_s3_path,
                                    "tags": item.tags or [],
                                    "document_id": document_id,
                                    "document_name": file_name,
                                }
                            )
                        else:
                            logger.warning(f"No matching OpenSearch entry for {original_s3_path}")

                    except Exception as e:
                        logger.exception(f"Failed to update OpenSearch for {file_name}: {e}")

                except subprocess.CalledProcessError as e:
                    logger.error(f"LibreOffice failed to convert {file_name}: {e}")
                except Exception as e:
                    logger.exception(f"Unexpected error while processing {file_name}: {e}")

        # Trigger Knowledge Base ingestion
        if new_files_for_ingestion:
            logger.info("Triggering Knowledge Base ingestion for new file(s)...")
            try:
                kb_utils.index_and_update_status(new_files_for_ingestion, trigger_kb.user_email, is_private=is_private)
                logger.info("Knowledge Base ingestion completed successfully.")

            except Exception as e:
                logger.exception(f"Error during Knowledge Base ingestion: {e}")
        else:
            logger.info("No files pending for ingestion.")

        logger.info("check_uploads_task execution completed successfully.")

    except ClientError as e:
        logger.error(f"S3 ClientError encountered: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error in check_uploads_task: {e}")
