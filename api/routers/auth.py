from datetime import datetime, timedelta

import jwt
from fastapi import APIRouter, Request

from api import args
from api.exceptions.custom_exceptions import APIException
from api.exceptions.error_codes import ErrorCode
from api.schemas.auth import DevLoginRequest, DevLoginResponse, LoginResponse
from api.utils.opensearch_util import OpenSearchUtil

router = APIRouter(prefix="/auth", tags=["Auth"])
opensearch_client = OpenSearchUtil()


def create_jwt_token(email: str) -> str:
    """Generate a JWT token with email claim and 2h expiration."""
    payload = {
        "email": email,
        "exp": datetime.utcnow() + timedelta(hours=2),
    }
    return jwt.encode(payload, args.jwt_secret, algorithm=args.jwt_algorithm)


@router.post("/dev-login", response_model=DevLoginResponse)
def dev_login(body: DevLoginRequest):
    """Dev login API that validates user from OpenSearch and returns a token."""
    query = {"query": {"match": {"email": body.email}}}
    resp = opensearch_client.client.search(index=args.aos_user_index, body=query)

    if resp["hits"]["total"]["value"] == 0:
        raise APIException(
            status_code=403,
            error_code=ErrorCode.USER_NOT_ONBOARDED,
            message="Your email is not registered with any team.",
            details=f'User with email "{body.email}" not found in "users_teams" index',
        )

    token = create_jwt_token(body.email)
    return DevLoginResponse(token=token)


@router.get("/login", response_model=LoginResponse)
async def login(request: Request):
    """Return the team ID of the authenticated user."""
    user_info = getattr(request.state, "user", None)

    if not user_info or "team" not in user_info:
        raise APIException(
            status_code=403,
            error_code=ErrorCode.USER_NOT_ONBOARDED,
            message="Your account is not linked to any team.",
            details="JWT token does not contain a valid 'team' claim",
        )

    return LoginResponse(team=user_info["team"])
