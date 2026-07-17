import asyncio
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Request

from api import args
from api.client.amazon_bedrock import AmazonBedrockClient
from api.exceptions.custom_exceptions import APIException
from api.exceptions.error_codes import ErrorCode
from api.schemas.agents import (
    ConverseRequest,
    ConverseResponse,
    Language,
    LanguageListResponse,
    QuestionSuggestionRequest,
    QuestionSuggestionResponse,
    RecentQuestion,
    RecentQuestionsResponse,
)
from api.utils.opensearch_util import OpenSearchUtil

router = APIRouter(prefix="/agents", tags=["Agents"])
opensearch_client = OpenSearchUtil()
bedrock_client = AmazonBedrockClient()


@router.post("/converse", response_model=ConverseResponse)
async def converse(
    request: Request,
    body: ConverseRequest,
):
    """
    Converse API: search + summarize documents.

    - Stores user query + assistant response in OpenSearch only if chunks are found
    - Retrieves relevant chunks + citations from Bedrock KB
    - Enriches citations using team documents list (docintel_documents index)
    - Summarizes with LLM using retrieved chunks as context
    - Logs audit + stores conversation messages
    """
    try:
        message_id = f"msg-{uuid.uuid4().hex}"

        current_user = getattr(request.state, "user", {})
        user_email = current_user.get("email", "unknown")
        team_id = current_user.get("team", "")

        all_team_uris = opensearch_client.get_team_document_uris(team_id)

        selected_uris = body.documentUris or []
        excluded_uris_input = body.excludedDocumentUris or []

        uris_to_use = []

        if selected_uris:
            selected_set = set(selected_uris)
            uris_to_use = [u for u in all_team_uris if u in selected_set]

        elif excluded_uris_input:
            excluded_set = set(excluded_uris_input)
            uris_to_use = [u for u in all_team_uris if u not in excluded_set]

        else:
            uris_to_use = all_team_uris

        if not uris_to_use:
            chunks, citations = [], []
        else:
            chunks, citations = bedrock_client.retrieve(body.userQuery, s3_uri_filters=uris_to_use)

        citation_uris = []
        enriched_citations = []

        for c in citations or []:
            if hasattr(c, "model_dump"):
                data = c.model_dump()
            elif isinstance(c, dict):
                data = c.copy()
            else:
                data = vars(c)

            uri = data.get("uri") or data.get("documentUri")
            if uri:
                citation_uris.append(uri)

            enriched_citations.append(data)

        citation_uris = list(dict.fromkeys([u for u in citation_uris if u]))

        must_queries = [
            {"match": {"team_id": team_id}},
            {"term": {"sync_status": "synced"}},
        ]

        query_body = {
            "query": {"bool": {"must": must_queries}},
            "_source": [
                "document_name",
                "document_id",
                "object_store.location",
                "object_store.converted",
                "uploaded_timestamp",
                "tags",
            ],
            "size": 5000,
        }

        try:
            docs_resp = opensearch_client.client.search(index=args.aos_documents_index, body=query_body)
            hits = docs_resp.get("hits", {}).get("hits", [])

            uri_to_doc = {}
            for hit in hits:
                src = hit.get("_source")
                if not src:
                    continue

                loc = src.get("object_store", {}).get("location")
                conv = src.get("object_store", {}).get("converted")

                if loc:
                    uri_to_doc[loc] = src
                if conv:
                    uri_to_doc[conv] = src

        except Exception as e:
            print(f"Error fetching team documents for enrichment: {e}")
            uri_to_doc = {}

        for c in enriched_citations:
            uri = c.get("uri") or c.get("documentUri")
            if uri and uri in uri_to_doc:
                src = uri_to_doc[uri]

                original_location = src.get("object_store", {}).get("location")
                final_uri = uri

                if original_location and not original_location.lower().endswith(".pdf"):
                    final_uri = original_location

                c.update(
                    {
                        "uri": final_uri,
                        "document_name": src.get("document_name"),
                        "tags": src.get("tags", []),
                        "uploaded_timestamp": src.get("uploaded_timestamp"),
                        "document_id": src.get("document_id"),
                        "converted_uri": src.get("object_store", {}).get("converted"),
                    }
                )

        if not chunks:
            summary = (
                "Sorry, I could not find any data sources related to your question, and therefore cannot answer it."
            )
            reason = "No relevant chunks found for the query."
            enriched_citations = []
        else:
            response_text = bedrock_client.generate(body.userQuery, chunks=chunks, citations=citations)
            try:
                response = json.loads(response_text)
                summary = response.get("answer", "")
                reason = response.get("reason", "")
            except json.JSONDecodeError:
                summary = response_text
                reason = response_text

            if "__NO_CONTEXT__" in summary:
                summary = (
                    "Sorry, I could not find any data sources related to your question, and therefore cannot answer it."
                )

            enriched_citations = []

        now = datetime.now()

        await asyncio.gather(
            asyncio.to_thread(
                opensearch_client.insert_document,
                index=args.aos_message_index,
                body={
                    "message_id": message_id,
                    "message": body.userQuery,
                    "text": body.userQuery,
                    "citations": [],
                    "user_id": user_email,
                    "team_id": team_id,
                    "role": "user",
                    "timestamp": now,
                },
            ),
            asyncio.to_thread(
                opensearch_client.insert_document,
                index=args.aos_message_index,
                body={
                    "message_id": message_id,
                    "message": summary,
                    "text": summary,
                    "citations": enriched_citations,
                    "user_id": "system",
                    "team_id": team_id,
                    "role": "assistant",
                    "timestamp": now,
                },
            ),
            asyncio.to_thread(
                opensearch_client.log_audit_event,
                user_id=user_email,
                team_id=team_id,
                event_type="QUERY",
                description=(f"Query executed and response generated for: {body.userQuery}"),
                metadata={
                    "message_id": message_id,
                    "user_message": body.userQuery,
                    "assistant_message": summary,
                    "citations": enriched_citations,
                },
            ),
        )

        return ConverseResponse(
            message_id=message_id,
            userQuery=body.userQuery,
            summary=summary,
            reason=reason,
            references=enriched_citations,
            timestamp=now,
        )
    except Exception as e:
        raise APIException(
            status_code=500,
            error_code=ErrorCode.AGENTS_CONVERSE_FAILED,
            message="Failed to process conversation request.",
            details=str(e),
        ) from e


@router.get("/questions/recent", response_model=RecentQuestionsResponse)
async def get_recent_questions(request: Request):
    """Get recent questions from team members, excluding the logged-in user."""
    try:
        current_user = getattr(request.state, "user", {})
        user_email = current_user.get("email", "unknown")
        team_id = current_user.get("team")

        messages_query = {
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"team_id": team_id}},
                        {"term": {"role": "user"}},
                        {"bool": {"must_not": {"term": {"user_id": user_email}}}},
                    ]
                }
            },
            "collapse": {"field": "message.keyword"},
            "sort": [{"timestamp": {"order": "desc"}}],
            "size": 4,
        }
        messages_results = opensearch_client.client.search(index=args.aos_message_index, body=messages_query)

        recent_questions = [
            RecentQuestion(message_id=hit["_source"]["message_id"], message=hit["_source"]["message"])
            for hit in messages_results.get("hits", {}).get("hits", [])
        ]

        return RecentQuestionsResponse(recent_questions=recent_questions)
    except Exception as e:
        raise APIException(
            status_code=500,
            error_code=ErrorCode.OPENSEARCH_QUERY_FAILED,
            message="Failed to fetch recent questions.",
            details=str(e),
        ) from e


@router.get("/languages", response_model=LanguageListResponse)
async def get_languages():
    """Return all languages from the languages index."""
    try:
        response = opensearch_client.client.search(index=args.aos_languages_index, body={"query": {"match_all": {}}})
        hits = response.get("hits", {}).get("hits", [])

        languages = [
            Language(language_code=hit["_source"]["language_code"], language_name=hit["_source"]["language_name"])
            for hit in hits
        ]

        return LanguageListResponse(languages=languages)
    except Exception as e:
        raise APIException(
            status_code=500,
            error_code=ErrorCode.OPENSEARCH_QUERY_FAILED,
            message="Failed to fetch languages.",
            details=str(e),
        ) from e


@router.post("/questions/suggest", response_model=QuestionSuggestionResponse)
async def suggest_questions(request: Request, body: QuestionSuggestionRequest):
    """
    Generate follow-up questions directly from retrieved document chunks (faster).

    - Uses only one Bedrock LLM call instead of multiple KD lookups.
    - Still filters by team documents for context relevance.
    """
    try:
        team_id = request.state.user["team"]

        all_team_uris = opensearch_client.get_team_document_uris(team_id)
        all_team_uris_set = set(all_team_uris)

        selected_uris = body.documentUris or []
        excluded_uris_input = body.excludedDocumentUris or []

        uris_to_use = []

        if selected_uris:
            uris_to_use = list(all_team_uris_set.intersection(selected_uris))
        elif excluded_uris_input:
            uris_to_use = list(all_team_uris_set.difference(excluded_uris_input))
        else:
            uris_to_use = all_team_uris

        user_query = (body.userQuery or "").strip()
        if not user_query:
            return QuestionSuggestionResponse(suggestions=[])

        if not uris_to_use:
            return QuestionSuggestionResponse(suggestions=[])

        relevant_chunks, _ = bedrock_client.retrieve(user_query, s3_uri_filters=uris_to_use)
        if not relevant_chunks:
            return QuestionSuggestionResponse(suggestions=[])

        suggestions = bedrock_client.suggest_questions(
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
