# Quickstart

[#quickstart](#quickstart)

The fastest path to a running API on your machine. This gets you `/ping`, local JWT auth, and OpenSearch-backed endpoints working without a hosted cluster. **Bedrock retrieval/generation still needs real AWS credentials and a provisioned Knowledge Base** — that's not something worth faking with a toy vector store once you're using a real managed KB (see `setup.md` for that part).

## 1. Start a local OpenSearch (no cluster to provision)

```bash
docker compose up -d opensearch
```

Wait for it to report healthy (`docker compose ps`), or check directly:

```bash
curl http://localhost:9200/_cluster/health
```

## 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set:

```
OPENSEARCH_ENDPOINT=http://localhost:9200
OPENSEARCH_USE_SSL=false
OPENSEARCH_VERIFY_CERTS=false
JWT_SECRET=some-local-dev-secret
```

Leave `KNOWLEDGE_BASE_ID` / `MODEL_ID` / AWS vars blank for now — you can reach `/ping` and exercise auth without them; you'll need them the moment you call `/agents/converse`.

## 3. Install and run

```bash
make setup   # uv sync --locked + pre-commit install
make all      # uv run app.py
```

## 4. Verify

```bash
curl http://localhost:8000/api/ping
# {"status": "OK"}

curl -X POST http://localhost:8000/api/auth/dev-login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com"}'
# returns a bearer token you can use for the rest of the endpoints
```

## 5. Provision the indices you'll actually use

The app doesn't auto-create OpenSearch indices on first write in every case — for anything beyond quick manual testing, create the indices listed in `setup.md` §2 against your local cluster (a simple `PUT` per index with no special mapping is enough to get started; OpenSearch will infer field types dynamically for development).

## 6. When you're ready for the real thing

Follow `setup.md` in full to provision the Bedrock Knowledge Base, S3 bucket, and (optionally) Azure AD SSO — then point `OPENSEARCH_ENDPOINT` at a real cluster and flip `OPENSEARCH_USE_SSL`/`OPENSEARCH_VERIFY_CERTS` back to `true`.
