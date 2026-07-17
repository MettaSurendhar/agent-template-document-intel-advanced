# api/utils

[#api-utils](#api-utils)

Shared helpers used across routers and middleware. This is where persistence, cross-cutting infra calls, and setup logic live — anything a router shouldn't have to know the details of.

## What's here

- **`opensearch_util.py`** — `OpenSearchUtil`, the single OpenSearch client wrapper. Holds methods like `get_team_document_uris(team_id)`, `insert_document(index, body)`, `log_audit_event(...)`. All OpenSearch access should go through here, not through ad-hoc `opensearch_py` client instantiation elsewhere.
- **`aws_knowledge_base.py`** — helpers for managing the Bedrock Knowledge Base data source sync lifecycle (as distinct from `client/amazon_bedrock.py`, which handles retrieve/generate at query time — this handles ingestion-side sync).
- **`email_utils.py`** — renders `api/templates/*.html` with Jinja2 and sends via SMTP.
- **`logging_utils.py`** — `setup_logging()`, called once in `app.py` at startup; configures logging from `log_config.yaml`.

## Conventions

- Anything that talks to OpenSearch more than once across the codebase belongs as a method on `OpenSearchUtil`, not copy-pasted `client.search(...)` calls in multiple routers.
- Utils should raise `APIException` on failure just like routers do (see `api/exceptions/README.md`) — don't let a raw `opensearch_py` or `boto3` exception bubble up unwrapped.
- Keep `logging_utils.py`'s `setup_logging()` idempotent — it's called once at import time in `app.py`; don't add per-request logging setup here.
- If you add a new utils module, name it `<concern>_util.py` or `<concern>_utils.py` matching the existing pattern, and instantiate any client-like object once at module or router level (see `opensearch_client = OpenSearchUtil()` in routers) rather than per-request.
