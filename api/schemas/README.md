# api/schemas

[#api-schemas](#api-schemas)

Pydantic models defining the request/response contract for each resource. One file per resource, matching the router of the same name.

## What's here

- `agents.py` — `ConverseRequest`/`ConverseResponse`, `Citation`, `QuestionSuggestionRequest`/`Response`, `Language`/`LanguageListResponse`, `RecentQuestion`/`RecentQuestionsResponse`.
- `documents.py` — upload/list/sync request and response shapes.
- `audit.py`, `auth.py`, `emails.py`, `team.py`, `users.py` — request/response shapes for their respective routers.
- `llm.py` — `GenerateResponse` (the JSON schema the Bedrock system prompt is told to conform to — see `api/client/README.md`).

## Conventions

- Field names in requests/responses use `camelCase` where the schema is consumed by a JS/TS frontend (e.g. `userQuery`, `documentUris`) — this is deliberate for frontend ergonomics, not an oversight. Keep it consistent within a resource; don't mix `camelCase` and `snake_case` in the same model.
- Every response model that returns a collection wraps it in a named container (`LanguageListResponse` wrapping `languages: list[Language]`), rather than returning a bare list — this leaves room to add pagination metadata later without a breaking change.
- Keep validation logic (field constraints, custom validators) in the schema itself, not in the router body.
- If a resource's request/response shapes get complex enough to need shared "generic" pieces reused across request and response (e.g. auth, documents, teams), promote them to `api/types/<resource>/` instead of duplicating fields across `schemas/`. Simple resources can stay flat in `schemas/`.
