# api/client

[#api-client](#api-client)

Thin wrappers around external AI/infra services. If code in here starts doing business logic (team scoping, persistence, response shaping), that logic belongs in a router or `utils/` instead — keep this folder to "talk to the external service and return a plain result."

## What's here

- **`amazon_bedrock.py`** — `AmazonBedrockClient`, wrapping two Bedrock APIs:
  - `retrieve(prompt, s3_uri_filters)` — vector search against the Bedrock Knowledge Base, optionally filtered to specific document S3 URIs via the `x-amz-bedrock-kb-source-uri` metadata field. Filters out low-relevance results (score ≤ 0.4) and non-text content. Returns `(chunks, citations)`.
  - `generate(prompt, system_prompt, chunks, citations)` — calls Bedrock's `converse` API. Uses a strict, context-bound system prompt (see `CLAUDE.md` §5) that forces JSON-only `{"answer", "reason"}` output and a `__NO_CONTEXT__` sentinel when the answer isn't in the provided chunks. **This prompt is load-bearing for trust — don't loosen it without the user explicitly asking for that tradeoff.**
  - `suggest_questions(user_query, chunks, count)` — single LLM call to generate follow-up questions directly from retrieved chunks, avoiding extra KB round-trips.

## Conventions

- One class per external service (`AmazonBedrockClient`, and you'd add e.g. `AzureOpenAIClient` the same way if you ever swap providers).
- Constructor reads all config from `api.args` — never hardcode region, model ID, or KB ID here.
- Methods return plain Python types / Pydantic models from `api/schemas`, not raw boto3 response dicts — callers in `routers/` shouldn't need to know Bedrock's response shape.
- If you add a new external service client, give it the same three-part shape where applicable: a retrieval-like method, a generation-like method, and any narrow helper methods — and document the contract each method makes (like the JSON-only contract above) explicitly in its docstring, not just in code comments.
