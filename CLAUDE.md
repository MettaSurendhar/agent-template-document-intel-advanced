# CLAUDE.md

This file guides Claude (and Claude Code) when working in this repository. This repo is a **template**, generalized from two production POCs — `Document AI` and `RPG Document AI` — in [Agent-Catalog](https://github.com/MettaSurendhar/Agent-Catalog). Its job is to give anyone a working, opinionated starting point for building a **document-intelligence RAG agent** for a new vertical (legal docs, HR policies, SOPs, spec sheets, whatever), without re-deriving the retrieval/auth/audit plumbing from scratch.

If you (Claude) are asked to spin up a new agent from this template, or to extend this template itself, read this whole file first.

## 0. This is the advanced tier of a three-tier family

There are two lighter tiers of this same template concept: **POC** (ChromaDB, no auth, single-user) and **intermediate** (JWT auth, FAISS-or-Chroma choice, SQLite audit). If a task's actual requirements don't need multi-team isolation, SSO, or OpenSearch-scale audit, say so and suggest the lighter tier instead of implementing a stripped-down version of this one — the other tiers already exist and are simpler to reason about for that scope. Conversely, don't accept a task that asks this tier to drop its AWS/OpenSearch dependency to "be simpler" — that's what the other two tiers are for.

---

## 1. What this template actually is

A FastAPI backend that lets a team of users:

1. Upload documents (with format conversion) into an S3-backed knowledge base.
2. Have those documents indexed into an **AWS Bedrock Knowledge Base** (vector store) and mirrored into **OpenSearch** (for metadata, filtering, and audit).
3. Ask natural-language questions scoped to their team's documents via a `/agents/converse` endpoint that does retrieve → generate → persist.
4. Get follow-up question suggestions, browse supported languages, and have every query/response logged to an audit trail.

Auth supports two modes at once: local JWT (HS256, for dev/testing/service accounts) and Azure AD SSO (RS256, verified against the tenant's JWKS endpoint) — both validated by the same middleware.

This is **not** a generic chatbot scaffold. It is specifically a **team-scoped, citation-grounded, audit-logged document Q&A agent**. Keep that shape when adapting it.

## 2. Stack (do not casually swap these)

| Concern | Choice | Why it matters |
|---|---|---|
| Language/runtime | Python 3.12 | Pinned in `.python-version` and Dockerfile |
| Package manager | `uv` | Lockfile-driven (`uv.lock`); use `uv sync`, not raw pip |
| Web framework | FastAPI | Router-per-domain, Pydantic schemas |
| Vector retrieval | AWS Bedrock Knowledge Bases (`bedrock-agent-runtime.retrieve`) | Filtered by `x-amz-bedrock-kb-source-uri` metadata, not a custom vector DB |
| Generation | AWS Bedrock `converse` API | Strict system prompt forces JSON-only `{answer, reason}` output — see §5 |
| Metadata/search/audit store | OpenSearch | One index per concern: users/teams, documents, messages, languages, private documents, audit |
| Auth | JWT, dual-mode | HS256 local secret **or** RS256 via Azure AD JWKS — same middleware, same request |
| File storage | S3 | Raw uploads + converted PDFs |
| Doc conversion | LibreOffice (headless, in Docker image) + `unoconv`/`pdfminer.six` | Converts docx/pptx/ppt → PDF before ingestion |
| Email | SMTP (Jinja2 HTML templates) | Sync notifications, shared-summary emails |
| Lint/format/type-check | ruff, pyright, mdformat, sqlfluff, shellcheck, checkmake, gitleaks | All wired through pre-commit — do not bypass |
| Commit convention | Conventional Commits + gitmoji (commitizen) | Enforced by pre-commit hook |

If a task would require replacing one of these (e.g. swapping OpenSearch for Postgres, or Bedrock for a different model provider), treat that as an architectural decision to flag explicitly to the user, not something to do silently mid-task.

## 3. Directory map

```
.
├── app.py                     # FastAPI app, middleware wiring, router registration, uvicorn entrypoint
├── log_config.yaml            # Logging config
├── setup.sh                   # Self-signed SSL cert generation (used in Docker build)
├── Dockerfile                 # Multi-stage: uv builder -> slim runtime w/ LibreOffice
├── docker-compose.yml         # Local single-node OpenSearch for dev — see QUICKSTART.md
├── Makefile                   # setup / install / test / build / pre_commit targets
├── pyproject.toml             # Deps, ruff/pyright/pytest config
└── api/
    ├── __init__.py            # Args/config: env-driven, parsed via `datargs` at import time
    ├── client/                # Thin wrappers around external AI/infra services (Bedrock, etc.)
    ├── exceptions/            # APIException + ErrorCode enum — the ONLY error-raising pattern
    ├── middleware/            # auth_middleware — JWT/SSO verification, team resolution
    ├── routers/               # One file per resource: auth, teams, users, documents, agents, emails, audit
    ├── schemas/                # Pydantic request/response models, one file per resource
    ├── templates/              # Jinja2 HTML email templates
    ├── types/                  # Shared generic/request/response type building blocks per resource
    └── utils/                  # OpenSearch client, S3/KB helpers, email sending, logging setup
```

Each `api/` subfolder has its own `README.md` — read the relevant one before editing files in that folder.

## 4. Conventions (follow these exactly)

- **Errors**: every raised error is an `APIException(status_code, error_code, message, details)` where `error_code` comes from the `ErrorCode` enum in `api/exceptions/error_codes.py`. Never raise a bare `HTTPException` or return an ad-hoc error dict. If you need a new failure mode, add a new `ErrorCode` member first — don't stringify one inline.
- **Routers**: one router per resource, `APIRouter(prefix="/<resource>", tags=["<Resource>"])`, registered in `app.py` with `app.include_router(x.router, prefix=args.subpath)`. Keep business logic in the router or a helper in `utils/`, not scattered across schemas.
- **Schemas**: split by direction — request models, response models, and shared "generic" models live in `api/schemas/<resource>.py` (simple resources) or `api/types/<resource>/{generic,request,response}.py` (resources with SSO/complex auth-like shape). Follow whichever pattern the resource already uses; don't mix them.
- **Config**: all runtime config is a field on the `Args` class in `api/__init__.py`, sourced from an env var with a sane default via `os.getenv`. Never read `os.environ` directly elsewhere — import `args` from `api`.
- **Index/table naming**: OpenSearch indices are named `<agent_name>_<entity>` (e.g. `docintel_documents`, `docintel_messages`). When forking this template for a new vertical, rename the prefix consistently across every `aos_*_index` default **and** the actual index names you provision.
- **Auth header**: a custom header carries the active team scope (e.g. `X-DocIntel-Team-Id`). Rename this per-vertical but keep the pattern — it disambiguates which team's documents a multi-team user is querying.
- **Docstrings**: numpy convention, enforced by ruff's `D` rules. `D100` (module docstring) is ignored; everything else isn't.
- **Line length**: 120, enforced by ruff.
- **Never bypass pre-commit.** It runs gitleaks (secret scanning), ruff, pyright, mdformat, sqlfluff, shellcheck, checkmake, and commitizen. If a hook is inconvenient for a legitimate reason, fix the underlying issue rather than skipping the hook.

## 5. The core RAG flow — understand this before touching `agents.py`

`POST /agents/converse` is the heart of the template:

1. Resolve `team_id` from `request.state.user` (set by auth middleware).
2. Look up all document S3 URIs belonging to the team (OpenSearch).
3. Narrow to the URIs the user selected/excluded in the request body (or use the full team set).
4. Call `bedrock_client.retrieve(query, s3_uri_filters=...)` — Bedrock KB vector search, filtered by `x-amz-bedrock-kb-source-uri`, thresholded at relevance score > 0.4.
5. Enrich raw citations with document metadata from OpenSearch (name, tags, upload time).
6. Call `bedrock_client.generate(...)` — this uses a **strict system prompt** that forces the model to return only `{"answer": ..., "reason": ...}` as raw JSON, refuses to answer outside the provided context, and returns a sentinel `__NO_CONTEXT__` when it can't answer from the retrieved chunks. **Do not loosen this prompt casually** — it's what keeps the agent from hallucinating outside the team's documents, which is the whole point of a document-intelligence agent.
7. Persist both the user message and assistant message to OpenSearch, plus an audit log entry, concurrently via `asyncio.gather` + `asyncio.to_thread` (OpenSearch client is sync).
8. Return `ConverseResponse` with citations attached.

When adapting this for a new domain, the two things you'll actually want to change are: the **system prompt's domain framing** (still JSON-only, still context-bound) and the **document types/tags** relevant to that domain. The retrieve → generate → persist skeleton should not change.

## 6. Adapting this template for a new vertical — checklist

When asked to fork this into a new document-intelligence agent (e.g. "HR Policy AI", "Contracts AI"):

1. Rename the package/service (`pyproject.toml` name, Docker image tag in Makefile, README titles).
2. Rename all `AOS_*_INDEX` env defaults and the `X-<Agent>-Team-Id` header to match the new agent name.
3. Update the `docintel_*` → `<new_agent>_*` prefix everywhere it appears (search for it — it's not centralized).
4. Rewrite the Bedrock system prompt in `amazon_bedrock.py::generate` for the new domain's tone/scope, keeping the JSON-only contract and the `__NO_CONTEXT__` sentinel.
5. Update `allowed_extensions` / `conversion_extensions` if the new domain deals with different file types.
6. Update email templates in `api/templates/` for the new agent's branding/copy.
7. Re-provision: a new Bedrock Knowledge Base + Data Source, a new S3 bucket/prefix, new OpenSearch indices, and (if using SSO) a new/shared Azure AD app registration.
8. Update `setup.md` and `README.md` for the new agent (see those files' own guidance).
9. Do **not** copy env secrets between agents that share infra — each vertical should get its own KB ID, indices, and bucket prefix so team data doesn't cross-contaminate.

## 7. Commands

```bash
make setup          # uv sync + pre-commit install
make all             # uv run app.py (local dev server)
make test            # uv run pytest
make pre_commit       # run all hooks on demand
make build            # docker buildx build (linux/amd64)
```

## 8. What NOT to do

- Don't invent a new error-handling pattern alongside `APIException`.
- Don't call OpenSearch or Bedrock directly from a router — go through `utils/opensearch_util.py` or `client/amazon_bedrock.py`.
- Don't hardcode index names, bucket names, or model IDs — they must come from `args`.
- Don't loosen the Bedrock system prompt's "context-bound, JSON-only" contract without the user explicitly asking for that tradeoff.
- Don't skip writing a per-folder `README.md` when you add a new `api/` subfolder — this template's whole value is that every folder explains itself (see `good-readme.md`).
