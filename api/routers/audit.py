from fastapi import APIRouter, Query, Request

from api import args
from api.exceptions.custom_exceptions import APIException
from api.exceptions.error_codes import ErrorCode
from api.schemas.audit import AuditLog, AuditLogListResponse, AuditUser, AuditUserListResponse
from api.utils.opensearch_util import OpenSearchUtil

router = APIRouter(prefix="/audit", tags=["Audit Logs"])
os_util = OpenSearchUtil()


@router.get("/logs", response_model=AuditLogListResponse)
async def get_audit_logs(
    request: Request,
    team_id: str | None = Query(default=None, description="Filter by team ID"),
    user_id: str | None = Query(default=None, description="Filter by user ID"),
    event_type: str | None = Query(default=None, description="Filter by event type, e.g., UPLOAD or QUERY"),
    start_time: str | None = Query(default=None, description="Start timestamp in ISO format"),
    end_time: str | None = Query(default=None, description="End timestamp in ISO format"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """Retrieve simplified audit logs (handles QUERY and UPLOAD events) with user names."""
    try:
        user_resp = os_util.client.search(index=args.aos_user_index, body={"size": 1000, "_source": ["email", "name"]})
        user_map = {
            hit["_source"]["email"]: hit["_source"]["name"] for hit in user_resp.get("hits", {}).get("hits", [])
        }

        must_queries = []

        if team_id:
            must_queries.append({"term": {"team_id": team_id}})
        if user_id:
            must_queries.append({"term": {"user_id": user_id}})
        if event_type:
            must_queries.append({"term": {"event_type": event_type}})
        if start_time or end_time:
            range_query = {}
            if start_time:
                range_query["gte"] = start_time
            if end_time:
                range_query["lte"] = end_time
            must_queries.append({"range": {"timestamp": range_query}})

        query_body = {
            "query": {"bool": {"must": must_queries}} if must_queries else {"match_all": {}},
            "sort": [{"timestamp": {"order": "desc"}}],
            "from": (page - 1) * page_size,
            "size": page_size,
        }

        resp = os_util.client.search(index=args.aos_audit_index, body=query_body)
        hits = resp.get("hits", {}).get("hits", [])
        total_records = resp.get("hits", {}).get("total", {}).get("value", 0)

        merged_logs = {}

        for hit in hits:
            src = hit["_source"]
            etype = src.get("event_type")
            timestamp = src.get("timestamp")
            uid = src.get("user_id", "system")
            display_name = user_map.get(uid, uid)
            team_id = src.get("team_id")

            if etype == "QUERY":
                msg_id = src.get("metadata", {}).get("message_id") or hit["_id"]
                if msg_id not in merged_logs:
                    merged_logs[msg_id] = {
                        "id": hit["_id"],
                        "timestamp": timestamp,
                        "user_id": uid,
                        "user_name": display_name,
                        "team_id": team_id,
                        "event_type": "QUERY",
                        "description": src.get("description", "User query and assistant response"),
                        "metadata": {"message_id": msg_id, "conversation": [], "citations": []},
                    }

                meta = merged_logs[msg_id]["metadata"]
                md = src.get("metadata", {})

                citations = md.get("citations", [])
                for c in citations:
                    if c not in meta["citations"]:
                        meta["citations"].append(c)

                if "user_message" in md or "assistant_message" in md:
                    if md.get("user_message"):
                        meta["conversation"].append({"role": "user", "message": md["user_message"]})
                    if md.get("assistant_message"):
                        meta["conversation"].append({"role": "assistant", "message": md["assistant_message"]})

                elif "message" in md:
                    meta["conversation"].append({"role": md.get("role", "user"), "message": md.get("message", "")})

            elif etype == "UPLOAD":
                log_id = hit["_id"]
                merged_logs[log_id] = {
                    "id": log_id,
                    "timestamp": timestamp,
                    "user_id": uid,
                    "user_name": display_name,
                    "team_id": team_id,
                    "event_type": "UPLOAD",
                    "description": src.get("description", ""),
                    "metadata": {
                        "document": src.get("metadata", {}),
                        "conversation": [{"role": "user", "message": src.get("description", "")}],
                    },
                }

        for log in merged_logs.values():
            if log["event_type"] == "QUERY":
                conv = log["metadata"]["conversation"]
                log["metadata"]["conversation"] = [c for c in conv if c.get("message")]

        logs = [AuditLog(**log) for log in merged_logs.values()]

        logs.sort(key=lambda latest: latest.timestamp, reverse=True)

        return AuditLogListResponse(
            logs=logs,
            page=page,
            page_size=page_size,
            total_records=total_records,
        )

    except Exception as e:
        raise APIException(
            status_code=500,
            error_code=ErrorCode.AUDIT_LOG_FETCH_FAILED,
            message="Failed to fetch audit logs",
            details=str(e),
        ) from e


@router.get("/users", response_model=AuditUserListResponse)
async def get_audit_users(request: Request):
    """Return all distinct users (name + email) from the user_teams index."""
    try:
        query_body = {"size": 1000, "_source": ["email", "name"]}
        resp = os_util.client.search(index=args.aos_user_index, body=query_body)
        hits = resp.get("hits", {}).get("hits", [])

        users = []
        seen_emails = set()

        for hit in hits:
            source = hit["_source"]
            email = source.get("email")
            name = source.get("name", "")
            if email and email.lower() != "system" and email not in seen_emails:
                users.append(AuditUser(name=name, email=email))
                seen_emails.add(email)

        return AuditUserListResponse(users=users, total_users=len(users))

    except Exception as e:
        raise APIException(
            status_code=500,
            error_code=ErrorCode.AUDIT_USER_FETCH_FAILED,
            message="Failed to fetch audit users",
            details=str(e),
        ) from e
