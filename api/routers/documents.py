import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import PurePosixPath
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, BackgroundTasks, Query, Request

from api import args
from api.exceptions.custom_exceptions import APIException
from api.exceptions.error_codes import ErrorCode
from api.routers.check_uploads_task import check_uploads_task
from api.schemas.check_upload_task import TriggerKB
from api.schemas.documents import (
    DeleteDocumentResponse,
    Document,
    DocumentID,
    DocumentListResponse,
    DocumentTagUpdate,
    DocumentTagUpdateResponse,
    InsertDocsResponse,
    ObjectStore,
    PresignedPostUrlData,
    PresignedUrlResponse,
    S3PathRequest,
    TagsResponse,
    TranslateRequest,
    TranslateResponse,
    UploadPathsResponse,
)
from api.utils.opensearch_util import OpenSearchUtil

router = APIRouter(prefix="/documents", tags=["Documents"])
opensearch_client = OpenSearchUtil()
s3_client = boto3.client("s3")
translate_client = boto3.client(service_name="translate", region_name=args.aws_region)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s - %(message)s", "%Y-%m-%d %H:%M:%S")
console_handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(console_handler)


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    request: Request,
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="uploaded_timestamp"),
    sort_direction: str = Query(default="desc", regex="^(asc|desc)$"),
    search: str | None = Query(default=None),
    tags: str | None = Query(default=None),
):
    """List all documents from OpenSearch with optional filtering/search."""
    try:
        team_id = request.state.user.get("team")

        must_queries = [{"match": {"team_id": team_id}}]

        if start_time:
            must_queries.append({"range": {"uploaded_timestamp": {"gte": start_time}}})
        if end_time:
            must_queries.append({"range": {"uploaded_timestamp": {"lte": end_time}}})

        import re

        if search:
            search_term = search.strip()

            extension_match = re.match(r"^(\.?[a-zA-Z0-9]{2,5})$", search_term)

            should_queries = []

            if extension_match:
                ext = search_term if search_term.startswith(".") else f".{search_term}"
                wildcard_extension_pattern = f"*{ext}"

                should_queries.append({"wildcard": {"object_store.location": {"value": wildcard_extension_pattern}}})

            wildcard_general_pattern = f"{search_term}"

            should_queries.append(
                {"match_phrase_prefix": {"document_name": {"query": search_term, "max_expansions": 50}}}
            )

            should_queries.append({"wildcard": {"document_id": f"{search_term}*"}})
            should_queries.append({"wildcard": {"object_store.location": wildcard_general_pattern}})

            must_queries.append(
                {
                    "bool": {
                        "should": should_queries,
                        "minimum_should_match": 1,
                    }
                }
            )

        if tags:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            if tag_list:
                must_queries.append({"terms": {"tags.keyword": tag_list}})

        query_body = {
            "query": {"bool": {"must": must_queries}},
            "sort": [{sort_by: {"order": sort_direction}}],
            "from": (page - 1) * page_size,
            "size": page_size,
        }

        resp = opensearch_client.client.search(index=args.aos_documents_index, body=query_body)
        hits = resp.get("hits", {}).get("hits", [])
        total_records = resp.get("hits", {}).get("total", {}).get("value", 0)

        documents = [
            Document(
                document_id=src.get("document_id", ""),
                document_name=src.get("document_name", ""),
                object_store=src.get("object_store", {"type": "", "location": ""}),
                uploaded_timestamp=src.get("uploaded_timestamp", ""),
                tags=src.get("tags", []),
                sync_status=src.get("sync_status", ""),
                last_synced_at=src.get("last_synced_at", ""),
            )
            for hit in hits
            if (src := hit.get("_source"))
        ]

        return DocumentListResponse(documents=documents, page=page, page_size=page_size, total_records=total_records)

    except Exception as e:
        raise APIException(
            status_code=500,
            error_code=ErrorCode.OPENSEARCH_QUERY_FAILED,
            message="Failed to list documents.",
            details=str(e),
        ) from e


@router.get("/presigned-url", response_model=PresignedUrlResponse)
async def get_document_file_url(
    url: str = Query(..., description="S3 filepath"),
):
    """Return pre-signed URL for a provided S3 URL (with validation)."""
    if not url or url in ["undefined", "null", "None"]:
        raise APIException(
            status_code=400,
            error_code=ErrorCode.INVALID_URL,
            message="The provided S3 URL is invalid or undefined.",
            details=f"Received URL: {url}",
        )

    try:
        location = url
        parsed = urlparse(location)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        ext = key.split(".")[-1].lower()

        response_headers = {"ResponseContentDisposition": "attachment"}

        if ext == "pdf":
            response_headers = {
                "ResponseContentDisposition": "inline",
                "ResponseContentType": "application/pdf",
            }

        if not bucket or not key:
            raise APIException(
                status_code=400,
                error_code=ErrorCode.INVALID_S3_PATH,
                message="Malformed S3 URL. Expected format: s3://bucket-name/path/to/file",
                details=f"Received: {url}",
            )

        if not bucket or not key:
            raise APIException(
                status_code=400,
                error_code=ErrorCode.INVALID_S3_PATH,
                message="Malformed S3 URL. Expected format: s3://bucket-name/path/to/file",
                details=f"Received: {url}",
            )

        pre_signed_url = s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": bucket,
                "Key": key,
                **response_headers,
            },
            ExpiresIn=7200,
        )

        return PresignedUrlResponse(url=pre_signed_url)

    except ClientError as e:
        raise APIException(
            status_code=500,
            error_code=ErrorCode.PRESIGNED_URL_GENERATION_FAILED,
            message="Failed to generate pre-signed URL.",
            details=f"Error processing S3 URL '{url}': {str(e)}",
        ) from e


@router.get("/upload-paths", response_model=UploadPathsResponse)
async def get_upload_paths(
    request: Request, overwrite: bool = Query(default=False, description="Overwrite existing files")
) -> UploadPathsResponse:
    """Generate presigned upload URLs for files → always to /uploads/."""
    try:
        s3_client = boto3.client("s3", region_name=args.aws_region)
        files_to_upload = {k: v for k, v in dict(request.query_params).items() if k != "overwrite"}
        presigned_urls = {}
        existing_documents_map = {}

        is_private_team = request.headers.get("x-private-team", "false").lower() == "true"
        team_id = request.state.user.get("team")
        user_email = request.state.user.get("email")

        try:
            if team_id:
                team_docs = opensearch_client.get_existing_document_map(
                    scope="team",
                    value=team_id,
                )
                existing_documents_map.update(team_docs)

            if is_private_team and user_email:
                private_docs = opensearch_client.get_existing_document_map(
                    scope="user",
                    value=user_email,
                )
                existing_documents_map.update(private_docs)
        except Exception as e:
            logger.warning(f"Failed to fetch existing filenames for duplicate check: {e}")

        for file_key, file_name in files_to_upload.items():
            is_existing = file_name.lower() in existing_documents_map

            key = f"{args.s3_folder_prefix.strip('/')}/uploads/{file_name}"
            presigned_post = s3_client.generate_presigned_post(
                Bucket=args.s3_bucket,
                Key=key,
                ExpiresIn=600,
            )
            data = PresignedPostUrlData.model_validate(presigned_post)
            data.file_exists = is_existing
            presigned_urls[file_key] = data

        return UploadPathsResponse(presigned_urls=presigned_urls)

    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=500,
            error_code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="Failed to generate upload paths.",
            details=f"Something went wrong: {repr(e)}",
        ) from e


@router.get("/get-tags", response_model=TagsResponse)
async def get_all_tags(request: Request, team_id: bool | None = Query(default=None, description="team_id")):
    """Retrieve all unique tags from the documents index."""
    if team_id is True:
        team_id = request.state.user.get("team")
        query_filter = {"term": {"team_id": team_id}}
    else:
        query_filter = {"match_all": {}}

    query = {
        "size": 0,
        "query": query_filter,
        "aggs": {"unique_tags": {"terms": {"field": "tags.keyword", "size": 1000}}},
    }

    response = opensearch_client.client.search(index=args.aos_documents_index, body=query)

    buckets = response.get("aggregations", {}).get("unique_tags", {}).get("buckets", [])
    tags = [bucket["key"] for bucket in buckets]

    return TagsResponse(tags=tags)


@router.get("/{document_id}", response_model=Document)
async def get_document(request: Request, document_id: str):
    """Retrieve a document by its ID."""
    query = {"query": {"match": {"document_id": document_id}}}
    resp = opensearch_client.client.search(index=args.aos_documents_index, body=query)

    hits = resp.get("hits", {}).get("hits", [])
    if not hits:
        raise APIException(
            status_code=404,
            error_code=ErrorCode.DOCUMENT_NOT_FOUND,
            message="Document Not Found",
            details=f"Document with ID '{document_id}' not found in index '{args.aos_team_index}'",
        )

    document = hits[0].get("_source", {})
    return DocumentID(
        document_id=document.get("document_id", ""),
        document_name=document.get("document_name", ""),
        object_store=ObjectStore(
            type=document.get("object_store", {}).get("type"),
            converted=document.get("object_store", {}).get("converted"),
            location=document.get("object_store", {}).get("location"),
        ),
        uploaded_timestamp=document.get("uploaded_timestamp", 0.0),
    )


@router.post("/translate", response_model=TranslateResponse)
async def translate_passage(translate_request: TranslateRequest):
    """Translate a selected passage to the target language using AWS Translate."""
    try:
        response = translate_client.translate_text(
            Text=translate_request.passage,
            SourceLanguageCode="auto",
            TargetLanguageCode=translate_request.target_language,
        )
        translated_text = response.get("TranslatedText", "")
        return TranslateResponse(
            original_passage=translate_request.passage,
            translated_passage=translated_text,
            target_language=translate_request.target_language,
        )
    except ClientError as e:
        raise APIException(
            status_code=500,
            error_code=ErrorCode.TRANSLATION_ERROR,
            message="Failed to translate passage.",
            details=f"Error with AWS Translate: {str(e)}",
        ) from e


@router.post("/insert-docs", response_model=InsertDocsResponse)
async def insert_s3_docs(request: Request, s3_path_request: S3PathRequest, background_tasks: BackgroundTasks):
    """
    Insert uploaded document metadata into OpenSearch if not already present.

    Trigger background task to process uploads and ingestion.
    """
    results = []
    skipped = []
    uploaded_docs_metadata = []

    try:
        total_received = len(s3_path_request.files)

        existing_documents_map = {}
        try:
            existing_documents_map = opensearch_client.get_existing_document_map(
                scope="team", value=s3_path_request.team_id
            )

        except Exception as e:
            logger.warning(f"Failed to fetch existing URIs from OpenSearch: {e}")

        for item in s3_path_request.files:
            s3_path = item.s3_path
            incoming_filename = PurePosixPath(s3_path).name.lower()

            parsed = urlparse(s3_path)
            document_name = parsed.path.split("/")[-1]

            document_id = str(uuid.uuid4().hex)
            document_overwrite_flag = False

            if incoming_filename in existing_documents_map:
                existing_id = existing_documents_map.get(incoming_filename)
                if existing_id:
                    document_id = existing_id
                    document_overwrite_flag = True
                    logger.info(f"[INSERT_DOCS] Updating existing document {document_name} (ID: {document_id})")

            document_body = {
                "document_id": document_id,
                "document_name": document_name,
                "object_store": {"type": "s3", "converted": s3_path, "location": s3_path},
                "team_id": s3_path_request.team_id,
                "user_email": request.state.user.get("email"),
                "tags": item.tags,
                "uploaded_timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            }

            if document_overwrite_flag:
                document_body["overwrite"] = "true"

            try:
                opensearch_client.insert_document(
                    index=args.aos_documents_index,
                    body=document_body,
                    doc_id=document_id,
                    refresh="wait_for",
                    wait_for_active_shards="1",
                )
                results.append(s3_path)
                uploaded_docs_metadata.append(
                    {
                        "document_id": document_id,
                        "document_name": document_name,
                        "team_id": s3_path_request.team_id,
                        "tags": item.tags,
                        "s3_path": s3_path,
                    }
                )

            except Exception as e:
                logger.exception(f"Failed to insert {document_name} into OpenSearch: {e}")
                raise APIException(
                    status_code=500,
                    error_code=ErrorCode.OPENSEARCH_INSERT_FAILED,
                    message="Failed to insert document into OpenSearch.",
                    details=str(e),
                ) from e

        logger.debug(
            f"[INSERT_DOCS] Summary → Received: {total_received}, Inserted: {len(results)}, Skipped: {len(skipped)}"
        )

        if uploaded_docs_metadata:
            description = (
                f"Uploaded {len(uploaded_docs_metadata)} document(s)"
                if len(uploaded_docs_metadata) > 1
                else f"Uploaded document: {uploaded_docs_metadata[0]['document_name']}"
            )

            opensearch_client.log_audit_event(
                event_type="UPLOAD",
                description=description,
                user_id=request.state.user.get("email"),
                team_id=s3_path_request.team_id,
                metadata={"documents": uploaded_docs_metadata},
            )

        should_trigger_ingestion = False

        if results:
            expected_paths = set(results)

            try:
                found_uris = opensearch_client.get_existing_document_uris(
                    args.aos_documents_index, list(expected_paths)
                )
                missing_uris = expected_paths - found_uris

                if not missing_uris:
                    logger.info("[INSERT_DOCS] Consistency check passed. All files found. Triggering ingestion.")
                    should_trigger_ingestion = True
                else:
                    logger.error(
                        f"[INSERT_DOCS] Consistency check FAILED. Missing: {missing_uris}. SKIPPING Ingestion."
                    )
            except Exception as e:
                logger.error(f"[INSERT_DOCS] Error during consistency check: {e}. SKIPPING Ingestion.")

        if should_trigger_ingestion:
            user_email = request.state.user.get("email")
            triggering_payload = TriggerKB(
                files=s3_path_request.files, user_email=user_email, team_id=s3_path_request.team_id
            )
            background_tasks.add_task(check_uploads_task, triggering_payload)
        else:
            logger.warning(
                "[INSERT_DOCS] Ingestion task was NOT triggered due to consistency mismatch or empty results."
            )

        return InsertDocsResponse(success=True)

    except Exception as e:
        raise APIException(
            status_code=500,
            error_code=ErrorCode.OPENSEARCH_INSERT_FAILED,
            message="Failed to insert documents",
            details=str(e),
        ) from e


@router.patch("/tags/{document_id}", response_model=DocumentTagUpdateResponse)
async def update_tags(document_id: str, tag_update: DocumentTagUpdate):
    """Update tags for a document (add and/or remove)."""
    try:
        query = {"query": {"match": {"document_id": document_id}}}
        resp = opensearch_client.client.search(index=args.aos_documents_index, body=query)
        hits = resp.get("hits", {}).get("hits", [])
        if not hits:
            raise APIException(
                status_code=404,
                error_code=ErrorCode.DOCUMENT_NOT_FOUND,
                message="Document Not Found",
                details=f"Document with ID '{document_id}' not found.",
            )

        source = hits[0].get("_source", {})
        current_tags = set(source.get("tags", []))

        if tag_update.add_tags:
            current_tags.update(tag_update.add_tags)

        if tag_update.remove_tags:
            current_tags.difference_update(tag_update.remove_tags)

        updated_tags = list(current_tags)

        opensearch_client.update_document(
            index=args.aos_documents_index,
            doc_id=hits[0]["_id"],
            body={"doc": {"tags": updated_tags}},
        )

        return DocumentTagUpdateResponse(
            message="Tags updated successfully.",
            tags=updated_tags,
        )
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=500,
            error_code=ErrorCode.OPENSEARCH_UPDATE_FAILED,
            message="Failed to update tags.",
            details=str(e),
        ) from e


@router.delete("/delete-docs", response_model=DeleteDocumentResponse)
async def delete_documents_by_id(document_id: str = Query(..., description="Document ID to delete")):
    """
    Delete documents by document_id.

    - Fetch all documents with the given document_id from OpenSearch.
    - Delete corresponding files from S3 (both 'converted' and 'original').
    - Delete all matching OpenSearch records.
    """
    if not document_id:
        return DeleteDocumentResponse(status=False, message="Missing document_id")

    search_query = {
        "size": 1000,
        "query": {"term": {"document_id": document_id}},
    }

    try:
        search_result = opensearch_client.client.search(index=args.aos_documents_index, body=search_query)
    except Exception as e:
        raise APIException(
            status_code=500,
            error_code=ErrorCode.OPENSEARCH_QUERY_FAILED,
            message="Failed to search documents in OpenSearch.",
            details=str(e),
        ) from e

    hits = search_result.get("hits", {}).get("hits", [])
    if not hits:
        return DeleteDocumentResponse(status=False, message=f"No documents found for ID '{document_id}'")

    deleted_files = []
    failed_files = []
    loop = asyncio.get_running_loop()

    for hit in hits:
        obj = hit["_source"].get("object_store", {})
        converted_path = obj.get("converted")
        location_path = obj.get("location")

        s3_paths = set()
        if converted_path:
            s3_paths.add(converted_path)
        if location_path:
            s3_paths.add(location_path)

        for s3_path in s3_paths:
            parsed = urlparse(s3_path)
            bucket = parsed.netloc
            key = parsed.path.lstrip("/")

            try:
                s3_client.delete_object(Bucket=bucket, Key=key)

                def wait_until_deleted(bucket=bucket, key=key):
                    waiter = s3_client.get_waiter("object_not_exists")
                    waiter.wait(Bucket=bucket, Key=key, WaiterConfig={"Delay": 2, "MaxAttempts": 10})

                await asyncio.wait_for(loop.run_in_executor(None, wait_until_deleted), timeout=25)
                deleted_files.append(s3_path)

            except Exception as e:
                failed_files.append({"s3_path": s3_path, "error": str(e)})

    delete_query = {"query": {"term": {"document_id": document_id}}}
    try:
        delete_response = opensearch_client.client.delete_by_query(
            index=args.aos_documents_index, body=delete_query, params={"refresh": "true"}
        )
    except Exception as e:
        raise APIException(
            status_code=500,
            error_code=ErrorCode.OPENSEARCH_DELETE_FAILED,
            message="Failed to delete documents from OpenSearch.",
            details=str(e),
        ) from e

    deleted_count = delete_response.get("deleted", 0)

    message = f"Deleted {len(deleted_files)} S3 files and {deleted_count} OpenSearch record(s)."
    if failed_files:
        message += f" Failed to delete {len(failed_files)} files: {failed_files}"

    return DeleteDocumentResponse(status=len(failed_files) == 0, message=message)
