# Usage

[#usage](#usage)

This walks through the API end-to-end: health check → auth → document upload → asking a question → follow-up suggestions.

All examples assume the API is running at `http://localhost:8000` with `APP_API_SUBPATH=/api`.

## 1. Health check

```bash
curl http://localhost:8000/api/ping
```

```json
{ "status": "OK" }
```

## 2. Authenticate

Local/dev token (HS256, no Azure AD needed):

```bash
curl -X POST http://localhost:8000/api/auth/dev-login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com"}'
```

Returns a bearer token. Every subsequent request needs:

```
Authorization: Bearer <token>
X-DocIntel-Team-Id: <your-team-id>
```

(Rename the `X-DocIntel-Team-Id` header to match your fork's naming — see the relevant router README.)

## 3. Upload a document

```bash
curl -X POST http://localhost:8000/api/documents/upload \
  -H "Authorization: Bearer <token>" \
  -H "X-DocIntel-Team-Id: team-123" \
  -F "file=@spec_sheet.pdf"
```

If the file type is in `CONVERSION_EXTENSIONS` (e.g. `.docx`), it's converted to PDF via LibreOffice before being stored in S3 and queued for Bedrock Knowledge Base sync.

## 4. Ask a question (the core RAG flow)

```bash
curl -X POST http://localhost:8000/api/agents/converse \
  -H "Authorization: Bearer <token>" \
  -H "X-DocIntel-Team-Id: team-123" \
  -H "Content-Type: application/json" \
  -d '{
    "userQuery": "What is the maximum operating temperature for the assembly?"
  }'
```

```json
{
  "message_id": "msg-3f9c1e2b...",
  "userQuery": "What is the maximum operating temperature for the assembly?",
  "summary": "The maximum operating temperature is 85°C.",
  "reason": "",
  "references": [
    {
      "title": "spec_sheet.pdf",
      "uri": "s3://bucket/docs/spec_sheet.pdf",
      "document_name": "spec_sheet.pdf",
      "tags": ["mechanical", "thermal"],
      "uploaded_timestamp": "2026-06-01T10:00:00Z"
    }
  ],
  "timestamp": "2026-07-17T09:00:00Z"
}
```

**Scoping the query to specific documents:**

```json
{
  "userQuery": "...",
  "documentUris": ["s3://bucket/docs/spec_sheet.pdf"]
}
```

**Excluding specific documents instead:**

```json
{
  "userQuery": "...",
  "excludedDocumentUris": ["s3://bucket/docs/old_draft.pdf"]
}
```

**When nothing relevant is found**, `summary` will read: *"Sorry, I could not find any data sources related to your question, and therefore cannot answer it."* — this is intentional (see `CLAUDE.md` §5 on the context-bound generation contract), not a bug.

## 5. Get follow-up question suggestions

```bash
curl -X POST http://localhost:8000/api/agents/questions/suggest \
  -H "Authorization: Bearer <token>" \
  -H "X-DocIntel-Team-Id: team-123" \
  -H "Content-Type: application/json" \
  -d '{"userQuery": "What is the maximum operating temperature?", "count": 3}'
```

```json
{
  "suggestions": [
    "What is the minimum operating temperature for the assembly?",
    "What cooling method is recommended above 70°C?",
    "How does temperature affect the warranty terms?"
  ]
}
```

## 6. Recent team questions

```bash
curl http://localhost:8000/api/agents/questions/recent \
  -H "Authorization: Bearer <token>" \
  -H "X-DocIntel-Team-Id: team-123"
```

Returns the last few distinct questions asked by *other* members of the team — useful for a "people also asked" UI element.

## 7. Supported languages

```bash
curl http://localhost:8000/api/agents/languages \
  -H "Authorization: Bearer <token>" \
  -H "X-DocIntel-Team-Id: team-123"
```

## Error format

Every error follows the same shape (see `api/exceptions/README.md`):

```json
{
  "error_code": "AGENTS_CONVERSE_FAILED",
  "message": "Failed to process conversation request.",
  "details": "..."
}
```

Check `error_code` programmatically — it's a stable enum value, not free text.
