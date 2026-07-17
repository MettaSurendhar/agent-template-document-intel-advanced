# api/exceptions

[#api-exceptions](#api-exceptions)

The single, mandatory error-handling pattern for this API. Every error raised anywhere in `routers/`, `utils/`, `client/`, or `middleware/` should be an `APIException`, not a bare `HTTPException`, a raw `Exception`, or an ad-hoc dict response.

## What's here

- **`custom_exceptions.py`**
  - `APIException(status_code, error_code, message, details=None)` — the exception class to raise.
  - `api_exception_handler(request, exc)` — the FastAPI exception handler, registered in `app.py` via `app.add_exception_handler(APIException, api_exception_handler)`. Converts any `APIException` into a consistent JSON body: `{"error_code", "message", "details"}`. Unexpected exceptions fall back to a generic 500 with `error_code: "internal_error"`.
- **`error_codes.py`**
  - `ErrorCode` — a `str, Enum` of every error code the API can return. Grouped loosely by domain (auth, OpenSearch, S3, email, agents, teams, users).

## Conventions

- **Never** invent a new error string inline (`error_code="something_failed"`). Add a new `ErrorCode` member first, then reference it. This keeps error codes stable and greppable for client-side error handling.
- Name new codes `<DOMAIN>_<FAILURE>` (e.g. `DOCUMENTS_SYNC_FAILED`), matching the existing pattern.
- Always set `status_code` to the correct HTTP semantics (401/403 for auth, 404 for not-found, 409 for conflicts like `TEAM_ALREADY_EXISTS`, 500 for infra failures) — don't default everything to 500.
- Use `details` for developer-facing diagnostic info (exception message, which field was missing); use `message` for something safe to show a user.
- When you catch a lower-level exception and re-raise as `APIException`, use `raise APIException(...) from e` to preserve the traceback chain.
