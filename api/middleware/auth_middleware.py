import jwt
from fastapi.responses import JSONResponse
from jwt import PyJWKClient

from api import args
from api.exceptions.custom_exceptions import APIException
from api.exceptions.error_codes import ErrorCode
from api.utils.opensearch_util import OpenSearchUtil

opensearch_client = OpenSearchUtil()

PUBLIC_PATHS = [f"{args.subpath}/ping", f"{args.subpath}/auth/dev-login"]
LOGIN_PATH = f"{args.subpath}/auth/login"

JWKS_URL = f"https://login.microsoftonline.com/{args.tenant_id}/discovery/v2.0/keys"
jwks_client = PyJWKClient(JWKS_URL)


async def auth_middleware(request, call_next):
    """Validate authorization before passing the request to the next handler."""
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    if any(path.startswith(p) for p in PUBLIC_PATHS):
        return await call_next(request)

    if request.method == "POST" and (path == f"{args.subpath}/users/create" or path == f"{args.subpath}/teams/create"):
        return await call_next(request)

    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise APIException(
                status_code=401,
                error_code=ErrorCode.UNAUTHORIZED,
                message="Authentication credentials are missing or invalid.",
                details='No JWT token provided in the "Authorization" header',
            ) from None

        token = auth_header.split("Bearer ")[1].strip()
        payload = None
        is_sso_login = False

        try:
            header = jwt.get_unverified_header(token)
            alg = header.get("alg")

            if alg == args.jwt_algorithm:
                payload = jwt.decode(token, args.jwt_secret, algorithms=[args.jwt_algorithm])

            elif alg == "RS256":
                signing_key = jwks_client.get_signing_key_from_jwt(token)
                payload = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256"],
                    audience=args.client_id,
                    issuer=f"https://login.microsoftonline.com/{args.tenant_id}/v2.0",
                )
                is_sso_login = True

            else:
                raise APIException(
                    status_code=401,
                    error_code=ErrorCode.UNAUTHORIZED,
                    message=f"Unsupported token algorithm: {alg}",
                    details="Only HS256 (local) and RS256 (Azure AD) are supported",
                ) from None

        except jwt.ExpiredSignatureError as e:
            raise APIException(
                status_code=401,
                error_code=ErrorCode.UNAUTHORIZED,
                message="Token expired",
            ) from e
        except jwt.InvalidTokenError as e:
            raise APIException(
                status_code=401,
                error_code=ErrorCode.UNAUTHORIZED,
                message="Invalid token",
                details=str(e),
            ) from e

        email = payload.get("email") or payload.get("preferred_username") or payload.get("upn") or payload.get("oid")

        if not email:
            raise APIException(
                status_code=403,
                error_code=ErrorCode.USER_NOT_ONBOARDED,
                message="Email claim missing in token",
                details="The token does not contain an email/username claim",
            ) from None

        if not path.startswith(LOGIN_PATH):
            incoming_team_id = request.headers.get("X-DocIntel-Team-Id")
            if not incoming_team_id:
                raise APIException(
                    status_code=400,
                    error_code=ErrorCode.UNAUTHORIZED,
                    message="Missing required header: X-DocIntel-Team-Id",
                    details="The request must include the X-DocIntel-Team-Id header",
                ) from None

        query = {"query": {"match": {"email": email}}}

        try:
            results = opensearch_client.client.search(index=args.aos_user_index, body=query)
            hits = results.get("hits", {}).get("hits", [])

            if not hits:
                if is_sso_login:
                    team_id = args.default_team_id
                    doc = {"email": email, "team_id": team_id}
                    try:
                        opensearch_client.client.index(index=args.aos_user_index, body=doc)
                    except Exception as e:
                        raise APIException(
                            status_code=500,
                            error_code=ErrorCode.OPENSEARCH_INSERT_FAILED,
                            message="Failed to insert user into OpenSearch",
                            details=str(e),
                        ) from e
                else:
                    raise APIException(
                        status_code=403,
                        error_code=ErrorCode.USER_NOT_ONBOARDED,
                        message="User is not onboarded",
                        details="User does not exist in the user-team index and this is not an SSO login",
                    ) from None
            else:
                team_id = request.headers.get("X-DocIntel-Team-Id") or hits[0]["_source"].get("team_id")

        except APIException:
            raise
        except Exception as e:
            raise APIException(
                status_code=500,
                error_code=ErrorCode.OPENSEARCH_QUERY_FAILED,
                message="Failed to query user index",
                details=str(e),
            ) from e

        request.state.user = {"team": team_id, "email": email}
        return await call_next(request)

    except APIException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_code": exc.error_code.value,
                "message": exc.message,
                "details": exc.details,
            },
        )
