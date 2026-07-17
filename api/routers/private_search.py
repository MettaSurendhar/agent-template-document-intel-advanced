import asyncio
import logging
import re
import uuid
from datetime import datetime
from pathlib import PurePosixPath
from urllib.parse import urlparse

import boto3
from fastapi import APIRouter, BackgroundTasks, Query, Request

from api import args
from api.client.amazon_bedrock import AmazonBedrockClient
from api.exceptions.custom_exceptions import APIException, ErrorCode
from api.routers.check_uploads_task import check_uploads_task
from api.schemas.agents import ConverseRequest, ConverseResponse, QuestionSuggestionRequest, QuestionSuggestionResponse
from api.schemas.check_upload_task import TriggerKB
from api.schemas.documents import DeleteDocumentResponse, DocumentListResponse, S3PathRequest
from api.schemas.private_search import PrivateDocDeleteResponse, PrivateDocInsertResponse
from api.utils.aws_knowledge_base import AWSKnowledgeBaseUtils
from api.utils.opensearch_util import OpenSearchUtil

bedrock = AmazonBedrockClient()
opensearch_client = OpenSearchUtil()
kb_utils = AWSKnowledgeBaseUtils()
s3_client = boto3.client("s3")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s - %(message)s", "%Y-%m-%d %H:%M:%S")
console_handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(console_handler)

router = APIRouter(prefix="/private-search", tags=["Private search"])


@router.get("/list-documents", response_model=DocumentListResponse)
async def list_private_documents(
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
    """List all private documents for the authenticated user."""
    try:
        user_email = request.state.user["email"]
        must_queries = [{"term": {"user_email.keyword": user_email}}]

        if start_time:
            must_queries.append({"range": {"uploaded_timestamp": {"gte": start_time}}})
        if end_time:
            must_queries.append({"range": {"uploaded_timestamp": {"lte": end_time}}})

        if search:
            search_term = search.strip()
            extension_match = re.match(r"^(\.?[a-zA-Z0-9]{2,5})$", search_term)

            should_queries = []

            if extension_match:
                ext = search_term if search_term.startswith(".") else f".{search_term}"
                should_queries.append({"wildcard": {"document_name": {"value": f"*{ext}"}}})

            should_queries.append(
                {
                    "match_phrase_prefix": {
                        "document_name": {"query": search_term, "max_expansions": 50},
                    },
                }
            )
            should_queries.append({"wildcard": {"document_name": {"value": f"*{search_term}*"}}})
            should_queries.append({"wildcard": {"object_store.location": {"value": f"*{search_term}*"}}})
            should_queries.append({"wildcard": {"document_id": {"value": f"{search_term}*"}}})
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
                must_queries.append(
                    {
                        "bool": {
                            "should": [{"prefix": {"tags.keyword": tag}} for tag in tag_list],
                            "minimum_should_match": 1,
                        }
                    }
                )

        query_body = {
            "query": {"bool": {"must": must_queries}},
            "sort": [{sort_by: {"order": sort_direction}}],
            "from": (page - 1) * page_size,
            "size": page_size,
        }

        resp = opensearch_client.client.search(index=args.aos_private_documents_index, body=query_body)
        hits = resp.get("hits", {}).get("hits", [])
        total = resp.get("hits", {}).get("total", {}).get("value", 0)

        documents = []
        for h in hits:
            src = h["_source"]

            documents.append(
                {
                    "document_id": src.get("document_id"),
                    "document_name": src.get("document_name"),
                    "object_store": src.get("object_store"),
                    "uploaded_timestamp": src.get("uploaded_timestamp", ""),
                    "tags": src.get("tags", []),
                    "sync_status": src.get("sync_status", ""),
                    "last_synced_at": src.get("last_synced_at", ""),
                }
            )

        return DocumentListResponse(
            documents=documents,
            total_records=total,
            page=page,
            page_size=page_size,
        )

    except Exception as e:
        raise APIException(
            status_code=500,
            error_code=ErrorCode.OPENSEARCH_QUERY_FAILED,
            message="Failed to list private documents",
            details=str(e),
        ) from e


@router.post("/insert-docs", response_model=PrivateDocInsertResponse)
async def insert_private_docs(request: Request, s3_path_request: S3PathRequest, background_tasks: BackgroundTasks):
    """Insert private documents for the authenticated user."""
    user_email = request.state.user["email"]
    result = []

    try:
        existing_filenames = {}
        try:
            existing_filenames = opensearch_client.get_existing_document_map(scope="user", value=user_email)
        except Exception as e:
            logger.warning(f"Failed to fetch existing private URIs: {e}")

        for item in s3_path_request.files:
            s3_path = item.s3_path
            incoming_filename = PurePosixPath(s3_path).name.lower()

            parsed = urlparse(s3_path)
            document_name = parsed.path.split("/")[-1]
            document_id = uuid.uuid4().hex
            overwrite_flag = False

            if incoming_filename in existing_filenames:
                existing_id = existing_filenames.get(incoming_filename)
                if existing_id:
                    document_id = existing_id
                    overwrite_flag = True

            document_body = {
                "document_id": document_id,
                "document_name": document_name,
                "object_store": {"type": "s3", "converted": s3_path, "location": s3_path},
                "user_email": user_email,
                "is_private": True,
                "tags": item.tags,
                "uploaded_timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            if overwrite_flag:
                document_body["overwrite"] = "true"

            opensearch_client.insert_document(
                index=args.aos_private_documents_index,
                body=document_body,
                doc_id=document_id,
                refresh="wait_for",
                wait_for_active_shards="1",
            )
            result.append(s3_path)

        should_trigger_ingestion = False

        if result:
            expected_paths = set(result)

            try:
                found_uris = opensearch_client.get_existing_document_uris(
                    args.aos_private_documents_index, list(expected_paths)
                )
                missing_uris = expected_paths - found_uris

                if not missing_uris:
                    logger.info("[INSERT_PRIVATE] Consistency check passed. Triggering ingestion.")
                    should_trigger_ingestion = True
                else:
                    logger.error(
                        f"[INSERT_PRIVATE] Consistency check FAILED. Missing: {missing_uris}. SKIPPING Ingestion."
                    )
            except Exception as e:
                logger.error(f"[INSERT_PRIVATE] Error during consistency check: {e}. SKIPPING Ingestion.")

        if should_trigger_ingestion:
            triggering_payload = TriggerKB(
                files=s3_path_request.files, user_email=user_email, team_id="t0", is_private=True
            )
            background_tasks.add_task(check_uploads_task, triggering_payload)
        else:
            logger.warning(
                "[INSERT_PRIVATE] Ingestion task was NOT triggered due to consistency mismatch or empty results."
            )

        return PrivateDocInsertResponse(success=True)

    except Exception as e:
        raise APIException(
            status_code=500,
            error_code=ErrorCode.OPENSEARCH_INSERT_FAILED,
            message="Failed to process private document insertion.",
            details=str(e),
        ) from e


@router.post("/converse", response_model=ConverseResponse)
async def converse(request: Request, body: ConverseRequest):
    """Handle private search converse requests."""
    message_id = f"assistant-{uuid.uuid4().hex}"
    user_email = request.state.user["email"]
    now = datetime.utcnow()

    try:
        query = {
            "query": {"term": {"user_email.keyword": user_email}},
            "_source": [
                "object_store.location",
                "object_store.converted",
                "document_name",
                "document_id",
                "uploaded_timestamp",
                "tags",
            ],
            "size": 5000,
        }

        resp = opensearch_client.client.search(index=args.aos_private_documents_index, body=query)
        hits = resp.get("hits", {}).get("hits", [])
        private_docs = [h["_source"] for h in hits]

        requested_uris = set(body.documentUris or [])
        if requested_uris:
            private_docs = [
                doc
                for doc in private_docs
                if (
                    doc.get("object_store", {}).get("location") in requested_uris
                    or doc.get("object_store", {}).get("converted") in requested_uris
                )
            ]

        private_uris = []

        for doc in private_docs:
            loc = doc.get("object_store", {}).get("location")
            conv = doc.get("object_store", {}).get("converted")

            if conv:
                private_uris.append(conv)
            else:
                private_uris.append(loc)

        if not private_uris:
            return ConverseResponse(
                message_id=message_id,
                userQuery=body.userQuery,
                summary="Sorry, there are no documents to refer to. Please upload the files.",
                references=[],
                timestamp=now,
            )

        chunks, citations = bedrock.retrieve(body.userQuery, s3_uri_filters=private_uris)
        citations = citations or []

        uri_to_doc = {}

        for doc in private_docs:
            loc = doc.get("object_store", {}).get("location")
            conv = doc.get("object_store", {}).get("converted")

            if loc:
                uri_to_doc[loc] = doc
            if conv:
                uri_to_doc[conv] = doc

        enriched_citations = []

        for c in citations:
            data = c.model_dump() if hasattr(c, "model_dump") else vars(c)
            uri = data.get("uri")
            if uri and uri in uri_to_doc:
                doc = uri_to_doc[uri]
                data.update(
                    {
                        "document_id": doc.get("document_id"),
                        "uploaded_timestamp": doc.get("uploaded_timestamp"),
                        "tags": doc.get("tags", []),
                        "document_name": doc.get("document_name", data.get("document_name")),
                        "converted_uri": doc["object_store"].get("converted"),
                        "uri": doc["object_store"].get("location"),
                    }
                )
                enriched_citations.append(data)

        if not chunks:
            summary = (
                "Sorry, I could not find any data sources related to your question, and therefore cannot answer it."
            )
            enriched_citations = []
        else:
            summary = bedrock.generate(body.userQuery, chunks=chunks, citations=citations)
            if not summary:
                summary = (
                    "Sorry, I could not find any data sources related to your question, and therefore cannot answer it."
                )
                enriched_citations = []

        return ConverseResponse(
            message_id=message_id,
            userQuery=body.userQuery,
            summary=summary,
            references=enriched_citations,
            timestamp=now,
        )

    except Exception as e:
        raise APIException(
            status_code=500,
            error_code=ErrorCode.OPENSEARCH_QUERY_FAILED,
            message="Failed to process private search converse request",
            details=str(e),
        ) from e


@router.post("/questions/suggest", response_model=QuestionSuggestionResponse)
async def suggest_questions(request: Request, body: QuestionSuggestionRequest):
    """Private question suggestion strictly based on user's documents (email-based)."""
    try:
        user_email = request.state.user["email"]
        if not user_email:
            return QuestionSuggestionResponse(suggestions=[])

        all_user_uris = opensearch_client.get_user_document_uris(user_email)
        all_user_uris_set = set(all_user_uris)

        selected_uris = body.documentUris or []
        excluded_uris = body.excludedDocumentUris or []

        if selected_uris:
            uris_to_use = list(all_user_uris_set.intersection(selected_uris))
        elif excluded_uris:
            uris_to_use = list(all_user_uris_set.difference(excluded_uris))
        else:
            uris_to_use = all_user_uris

        user_query = (body.userQuery or "").strip()
        if not user_query:
            return QuestionSuggestionResponse(suggestions=[])

        if not uris_to_use:
            return QuestionSuggestionResponse(suggestions=[])

        relevant_chunks, _ = bedrock.retrieve(user_query, s3_uri_filters=uris_to_use)

        if not relevant_chunks:
            return QuestionSuggestionResponse(suggestions=[])

        suggestions = bedrock.suggest_questions(
            user_query=user_query,
            chunks=relevant_chunks,
            count=body.count or 5,
        )

        return QuestionSuggestionResponse(suggestions=suggestions)

    except Exception as e:
        raise APIException(
            status_code=500,
            error_code=ErrorCode.AGENTS_SUGGESTION_FAILED,
            message="Failed to suggest questions.",
            details=str(e),
        ) from e


@router.delete("/delete-document", response_model=DeleteDocumentResponse)
async def delete_document(document_id: str = Query(..., description="Document ID to delete")):
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
        search_result = opensearch_client.client.search(index=args.aos_private_documents_index, body=search_query)
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
            index=args.aos_private_documents_index, body=delete_query, params={"refresh": "true"}
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


@router.delete("/exit-session", response_model=PrivateDocDeleteResponse)
async def exit_session(request: Request):
    """Delete all private documents for the authenticated user."""
    try:
        user_email = request.state.user["email"]
        search_query = {
            "size": 1000,
            "query": {"bool": {"must": [{"term": {"user_email.keyword": user_email}}]}},
        }

        search_result = opensearch_client.client.search(index=args.aos_private_documents_index, body=search_query)

        document_list = search_result.get("hits", {}).get("hits", [])
        if not document_list:
            return PrivateDocDeleteResponse(
                success=True,
                deleted_s3_files=0,
                deleted_documents=0,
            )

        s3_paths = set()

        for document in document_list:
            src = document.get("_source", {})
            obj = src.get("object_store", {})

            loc = obj.get("location")
            conv = obj.get("converted")

            if loc:
                s3_paths.add(loc)
            if conv:
                s3_paths.add(conv)

        deleted_s3 = 0
        for s3_url in s3_paths:
            try:
                parsed = urlparse(s3_url)
                bucket = parsed.netloc
                key = parsed.path.lstrip("/")

                s3_client.delete_object(Bucket=bucket, Key=key)
                deleted_s3 += 1

            except Exception as e:
                logger.warning(f"[WARN] Failed to delete S3 object {s3_url}: {e}")

        delete_query = {"query": {"bool": {"must": [{"term": {"user_email.keyword": user_email}}]}}}

        delete_response = opensearch_client.client.delete_by_query(
            index=args.aos_private_documents_index, body=delete_query, params={"refresh": "true"}
        )

        deleted_docs = delete_response.get("deleted", 0)
        return PrivateDocDeleteResponse(
            success=True,
            deleted_s3_files=deleted_s3,
            deleted_documents=deleted_docs,
        )

    except Exception as e:
        raise APIException(
            status_code=500,
            error_code=ErrorCode.OPENSEARCH_DELETE_FAILED,
            message="Failed to delete private documents.",
            details=str(e),
        ) from e
