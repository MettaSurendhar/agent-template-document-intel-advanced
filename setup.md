# Setup

[#setup](#setup)

This guide walks through everything needed to run this template locally or in Docker, and what needs to be provisioned in AWS/Azure before it'll actually work end-to-end.

## Prerequisites

- **Python 3.12** (pinned in `.python-version`)
- **[uv](https://docs.astral.sh/uv/)** — dependency + lockfile management
- **Docker** (optional, for containerized run/build)
- **An AWS account** with:
  - Bedrock model access enabled for your chosen model (e.g. Claude, Titan) in your target region
  - A **Bedrock Knowledge Base** created, pointed at an S3 data source
  - An **S3 bucket** for raw uploads + converted documents
- **An OpenSearch domain/cluster** (self-hosted or AWS OpenSearch Service)
- **(Optional) Azure AD app registration** if you want SSO login in addition to local JWT — you'll need a tenant ID and client ID
- **(Optional) SMTP credentials** if you want email notifications (sync status, shared summaries)

## 1. Provision AWS Bedrock Knowledge Base

1. In the Bedrock console, create a Knowledge Base backed by your S3 bucket/prefix.
2. Choose an embedding model and a vector store (OpenSearch Serverless is the common default; this template's own `OPENSEARCH_*` variables are separate from whatever vector store the KB itself uses).
3. Note the **Knowledge Base ID** and **Data Source ID** — you'll need both.
4. Choose a generation model and note its **Model ID** (used by the `converse` API call in `api/client/amazon_bedrock.py`).

## 2. Provision OpenSearch indices

This template expects the following indices to exist (names are configurable via env vars, defaults shown):

| Index | Default name | Purpose |
| --- | --- | --- |
| Users/teams | `docintel_users_teams` | Maps user email → team ID |
| Teams | `docintel_teams` | Team metadata |
| Documents | `docintel_documents` | Uploaded document metadata, S3 locations, sync status, tags |
| Messages | `docintel_messages` | Conversation history (user + assistant turns) |
| Languages | `docintel_languages` | Supported languages list |
| Private documents | `docintel_private_documents` | User-private (non-team) documents |
| Audit logs | `docintel_audit_logs` | Query/upload audit trail |

When forking this template for a new vertical, rename these consistently — see `CLAUDE.md` §6.

## 3. Environment variables

Copy these into a `.env` file at the repo root (the app loads it via `python-dotenv`).

| Variable | Default | Notes |
| --- | --- | --- |
| `APP_HOST` | `0.0.0.0` | Bind host |
| `APP_PORT` | `8000` | Bind port |
| `APP_API_SUBPATH` | `/api` | Prefix for all routes |
| `OPENSEARCH_ENDPOINT` | `https://localhost:9200` | OpenSearch cluster URL |
| `OPENSEARCH_USERNAME` / `OPENSEARCH_PASSWORD` | — | OpenSearch basic auth |
| `JWT_SECRET` | `docintelagent` | **Change this in any real deployment.** HS256 signing secret for local/dev tokens |
| `JWT_ALGORITHM` | `HS256` | Local token algorithm |
| `AWS_REGION` | `us-east-1` | Region for Bedrock + S3 |
| `KNOWLEDGE_BASE_ID` | — | From step 1 |
| `DATA_SOURCE_ID` | — | From step 1 |
| `MODEL_ID` | — | Bedrock generation model ID |
| `AZURE_TENANT_ID` / `AZURE_CLIENT_ID` | — | Required only if using Azure AD SSO |
| `SMTP_SERVER` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `EMAIL_SENDER_NAME` | — | Required only if email notifications are enabled |
| `S3_BUCKET` | — | Bucket for uploads/docs |
| `S3_FOLDER_PREFIX` / `S3_UPLOADS_PREFIX` / `S3_DOCS_PREFIX` | `uploads/`, `docs/` | Key prefixes within the bucket |
| `DEFAULT_TEAM_ID` | — | Team assigned to new SSO users with no existing team record |
| `PRIVATE_TEAM_ID` | — | Reserved team ID used for a user's private (non-shared) documents |
| `ALLOWED_EXTENSIONS` | `.pdf,.docx,.pptx,.ppt,.xlsx,.csv,.txt` | File types acceptable for upload |
| `CONVERSION_EXTENSIONS` | `.docx,.pptx,.ppt` | File types converted to PDF before indexing |
| `SSL_KEYFILE` / `SSL_CERTFILE` | — | Optional, enables HTTPS in `uvicorn` directly |

**Security note**: never commit a real `JWT_SECRET`, SMTP password, or AWS credentials. This template's pre-commit hooks run `gitleaks` to catch this, but don't rely on it as your only safety net.

## 4. Local run

```bash
make setup   # uv sync --locked + pre-commit install
make all      # uv run app.py
```

The API will be live at `http://localhost:8000/api/ping`.

## 5. Docker run

```bash
make build    # docker buildx build --platform linux/amd64 -t <image-name> .
docker run --env-file .env -p 8000:8000 <image-name>
```

The Docker image installs headless LibreOffice for document conversion — this is why the image is multi-stage and larger than a typical FastAPI container.

## 6. Auth modes

- **Local/dev**: issue an HS256 JWT signed with `JWT_SECRET`, containing an `email` claim. Useful for testing without wiring up Azure AD.
- **Azure AD SSO**: tokens are RS256, verified against `https://login.microsoftonline.com/{AZURE_TENANT_ID}/discovery/v2.0/keys`. First-time SSO users are auto-onboarded into `DEFAULT_TEAM_ID`.

Every authenticated request (except `/ping`, `/auth/dev-login`, and account-creation endpoints) must include the team-scope header — see the relevant router's README for the exact header name in your fork.
