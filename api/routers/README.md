# api/routers

[#api-routers](#api-routers)

One file per resource. Each router owns its HTTP surface and delegates persistence/retrieval to `utils/` or `client/` — routers should read like an orchestration script, not contain raw OpenSearch queries or boto3 calls inline (a few inline `opensearch_client.client.search` calls exist for simple one-off lookups; prefer adding a method to `OpenSearchUtil` for anything reused).

## What's here

| File | Resource | Key endpoints |
| --- | --- | --- |
| `auth.py` | Authentication | login, dev-login |
| `teams.py` | Teams | create, list, fetch |
| `users.py` | Users | create, list |
| `documents.py` | Document lifecycle | upload, list, sync status, delete |
| `agents.py` | The RAG agent itself | `/converse`, `/questions/recent`, `/questions/suggest`, `/languages` — see `CLAUDE.md` §5 for the `/converse` flow in detail |
| `emails.py` | Notifications | sync notifications, shared-summary emails |
| `audit.py` | Audit trail | query audit log events |
| `check_uploads_task.py` *(optional, not every fork needs this)* | Background sync status polling | |
| `private_search.py` *(optional, not every fork needs this)* | Search over a user's private (non-team) documents | |

Not every variant needs every router — `check_uploads_task.py` and `private_search.py` are examples of vertical-specific additions; don't feel obligated to keep them if your fork doesn't need per-user private document search.

## Conventions

- `router = APIRouter(prefix="/<resource>", tags=["<Resource>"])`, registered in `app.py`.
- Every endpoint wraps its body in `try/except`, raising `APIException` on failure (see `api/exceptions/README.md`) — never let a raw exception escape to the default FastAPI 500 handler.
- Read the current user/team via `getattr(request.state, "user", {})`, never re-derive auth here.
- Response models are always declared via `response_model=` on the route decorator, using a schema from `api/schemas` or `api/types`.
- Keep endpoint docstrings action-oriented — they show up in the auto-generated OpenAPI docs (`/docs`), so write them for someone browsing the API, not just future you.
- When adding a new router: create it here, add its schema file, register it in `app.py`, add a section to `usage.md`, and note it in this table.
