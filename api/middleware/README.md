# api/middleware

[#api-middleware](#api-middleware)

Request-level middleware. Currently one concern: authentication and team-scope resolution, applied to every request before it reaches a router.

## What's here

- **`auth_middleware.py`** — `auth_middleware(request, call_next)`, registered in `app.py` via `app.middleware("http")(auth_middleware)`.

## What it does, in order

1. Passes through `OPTIONS` requests and anything in `PUBLIC_PATHS` (health check, dev-login) untouched.
2. Passes through account-creation POSTs (`/users/create`, `/teams/create`) untouched — these are the bootstrap paths before a user/team exists.
3. Requires a `Bearer` token in the `Authorization` header for everything else.
4. Inspects the token's `alg` header to decide the verification path:
   - `HS256` → verify against `args.jwt_secret` (local/dev tokens).
   - `RS256` → verify against the Azure AD tenant's JWKS endpoint, checking `audience`/`issuer` (SSO tokens).
   - Anything else → reject with `UNAUTHORIZED`.
5. Extracts an email/username claim (`email`, `preferred_username`, `upn`, or `oid`, in that order).
6. Requires a team-scope header (e.g. `X-DocIntel-Team-Id`) on every request except login itself.
7. Looks up the user's team in OpenSearch; auto-onboards first-time SSO users into `DEFAULT_TEAM_ID`; rejects unknown local-auth users as `USER_NOT_ONBOARDED`.
8. Attaches `request.state.user = {"team": team_id, "email": email}` for downstream routers to read.

## Conventions

- This middleware is intentionally the **only** place JWT verification happens — don't re-verify tokens in individual routers.
- If you rename the team-scope header for your fork, update it in exactly one place (`LOGIN_PATH`/header-check block here) and reflect the new name in every router README and in `usage.md`.
- Any new "always allow without auth" path must be added to `PUBLIC_PATHS` explicitly — don't special-case it by string-matching deeper in the function.
- Errors here should still be raised as `APIException` and caught in the local `try/except APIException` block that converts them to a `JSONResponse` — middleware runs outside the FastAPI exception-handler chain, so this local catch is necessary, not redundant.
