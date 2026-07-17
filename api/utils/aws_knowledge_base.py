import asyncio
import logging
import os
import time
from datetime import datetime

import boto3
from jinja2 import Environment, FileSystemLoader

from api import args
from api.exceptions.custom_exceptions import APIException
from api.exceptions.error_codes import ErrorCode
from api.schemas.emails import EmailRequest
from api.utils.email_utils import send_email
from api.utils.opensearch_util import OpenSearchUtil

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s - %(message)s", "%Y-%m-%d %H:%M:%S")
console_handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(console_handler)


opensearch_client = OpenSearchUtil()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))


class AWSKnowledgeBaseUtils:
    """Utilities for collections based on AWS Knowledge Bases."""

    def __init__(self):
        if not all([args.knowledge_base_id, args.data_source_id]):
            raise ValueError("Missing Data Source ID or Knowledge Base ID in args")
        if not args.aws_region:
            raise ValueError("Missing AWS region in args")

        self.bedrock_agent_client = boto3.client("bedrock-agent", region_name=args.aws_region)

    def index_and_update_status(self, files, user_email: str, max_retries: int = 10, is_private: bool = False):
        """Run ingestion job and update sync status once indexing completes."""
        failure_status = ["FAILED", "STOPPING", "STOPPED"]

        # Try starting ingestion job safely with retry
        start_retries = 0
        ingestion_job = None

        while start_retries < max_retries:
            try:
                ingestion_job = self.bedrock_agent_client.start_ingestion_job(
                    dataSourceId=args.data_source_id,
                    description=(
                        f"Ingestion job for data source: {args.data_source_id} and KB: {args.knowledge_base_id}"
                    ),
                    knowledgeBaseId=args.knowledge_base_id,
                )
                break

            except self.bedrock_agent_client.exceptions.ConflictException:
                logger.warning(f"Another ingestion job is running; retrying in 10s ({start_retries + 1}/{max_retries})")
                time.sleep(20)
                start_retries += 1
                continue

        if ingestion_job is None:
            logger.error("Failed to start ingestion job after max retries.")
            self._send_failure_email(user_email, "CONFLICT")
            return {"error": "Failed to start ingestion job due to ongoing job conflict."}

        ingestion_job_id = ingestion_job.get("ingestionJob", {}).get("ingestionJobId")
        logger.info(f"Started ingestion job: {ingestion_job_id}")

        # Poll job status
        retries = 0
        job = None

        while True:
            job = self.bedrock_agent_client.get_ingestion_job(
                dataSourceId=args.data_source_id,
                knowledgeBaseId=args.knowledge_base_id,
                ingestionJobId=ingestion_job_id,
            )

            status = job.get("ingestionJob", {}).get("status")

            if status == "COMPLETE":
                self.update_indexing_status(job, files, user_email, is_private=is_private)
                logger.info(f"Ingestion job {ingestion_job_id} completed and document statuses updated.")
                break

            elif status in failure_status:
                logger.warning(f"Ingestion job failed or stopped: {status}")

                self._send_failure_email(user_email, status)

                try:
                    template = env.get_template("sync_notification_template.html")
                    html_body = template.render(
                        sender_name=args.email_sender_name,
                        documents=[],
                        additional_message=(
                            f"The ingestion job failed with status: {status}. No documents were indexed or synced."
                        ),
                    )

                    email_request = EmailRequest(
                        to_emails=[user_email],
                        subject=f"Document Ingestion Failed ({status})",
                        html_body=html_body,
                    )

                    asyncio.run(send_email(email_request))
                except Exception as e:
                    logger.error(f"Failed to send ingestion failure email: {e}")

                return job

            retries += 1
            time.sleep(10)

        logger.info(f"Ingestion job ended after {retries} retries.")
        return job

    def _send_failure_email(self, user_email: str, status: str):
        """Send failure email if ingestion job fails."""
        try:
            template = env.get_template("sync_notification_template.html")
            html_body = template.render(
                sender_name="Aether Agent",
                documents=[],
                additional_message=f"The ingestion job failed with status: {status}. No documents were indexed.",
            )
            email_request = EmailRequest(
                to_emails=[user_email],
                subject=f"Document Ingestion Failed ({status})",
                html_body=html_body,
            )

            asyncio.run(send_email(email_request))
            logger.info(f"Failure notification email sent to {user_email}")

        except Exception as e:
            logger.error(f"Failed to send ingestion failure email: {e}")

    def update_indexing_status(self, ingestion_job, files, user_email: str, is_private: bool = False):
        """Batch update document sync_status in OpenSearch after KB indexing completes."""
        target_index = args.aos_private_documents_index if is_private else args.aos_documents_index
        try:
            document_identifiers = []
            file_name_map = {}

            for file in files:
                s3_path = file["s3_path"]
                original_name = file.get("document_name")
                file_ext = os.path.splitext(original_name)[-1].lower()
                file_name_map[s3_path] = original_name

                if file_ext in [".docx", ".pptx"]:
                    final_path = (
                        s3_path.replace("/uploads/", "/docs/")
                        .replace("/originals/", "/docs/")
                        .replace(file_ext, ".pdf")
                    )
                    logger.info(f"Using converted PDF path for KB check: {final_path}")
                else:
                    # PDFs are already in /docs/
                    final_path = s3_path.replace("/uploads/", "/docs/")
                    logger.info(f"Using PDF path for KB check: {final_path}")

                document_identifiers.append({"dataSourceType": "S3", "s3": {"uri": final_path}})

            try:
                docs_response = self.bedrock_agent_client.get_knowledge_base_documents(
                    knowledgeBaseId=args.knowledge_base_id,
                    dataSourceId=args.data_source_id,
                    documentIdentifiers=document_identifiers,
                )
                document_details = docs_response.get("documentDetails", [])
            except Exception as e:
                logger.warning(f"Could not fetch KB document statuses: {e}")
                document_details = []

            document_results = []

            for detail in document_details:
                identifier = detail.get("identifier", {})
                s3_uri = identifier.get("s3", {}).get("uri")
                doc_status = detail.get("status", "NOT_FOUND")

                document_name = None
                for _orig_path, name in file_name_map.items():
                    if name.replace(os.path.splitext(name)[-1], ".pdf") in s3_uri:
                        document_name = name
                        break
                document_name = document_name or os.path.basename(s3_uri or "unknown")

                logger.info(f"Document {document_name} ({s3_uri}) indexing status: {doc_status}")

                search_query = {"query": {"match_phrase": {"object_store.converted": s3_uri}}}
                search_result = opensearch_client.client.search(index=target_index, body=search_query)
                hits = search_result.get("hits", {}).get("hits", [])

                if not hits:
                    logger.warning(f"[OS-MISS] No OpenSearch document found for {s3_uri}")
                    document_results.append({"document_name": document_name, "sync_status": "Failed (Not Found In OS)"})
                    continue

                doc_id = hits[0]["_id"]

                # Determine final sync status
                if doc_status == "INDEXED":
                    new_status = "synced"
                    result_label = "Success"
                else:
                    new_status = doc_status.lower()
                    result_label = f"Failed ({doc_status})"

                # Update in OpenSearch
                try:
                    opensearch_client.client.update(
                        index=target_index,
                        id=doc_id,
                        body={
                            "doc": {
                                "sync_status": new_status,
                                "last_synced_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                            }
                        },
                    )
                    document_results.append({"document_name": document_name, "sync_status": result_label})

                    logger.info(f"[OS-UPDATE] {document_name}({s3_uri}) → {new_status}")

                except Exception as e:
                    logger.error(f"[OS-UPDATE-FAIL] {document_name}({s3_uri}): {e}")
                    document_results.append({"document_name": document_name, "sync_status": f"Failed ({str(e)})"})

            template = env.get_template("sync_notification_template.html")
            html_body = template.render(
                sender_name=args.email_sender_name,
                documents=document_results,
                additional_message="You can now start querying with the uploaded documents.",
            )

            email_request = EmailRequest(
                to_emails=[user_email],
                subject="Document Sync Summary",
                html_body=html_body,
            )
            asyncio.run(send_email(email_request))

        except Exception as e:
            logger.error(f"Error updating KB document statuses: {e}")
            raise APIException(
                status_code=500,
                error_code=ErrorCode.EMAIL_SEND_FAILED,
                message=f"Failed to send sync results email: {str(e)}",
            ) from e
