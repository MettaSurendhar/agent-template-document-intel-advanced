from fastapi import APIRouter

from api import args
from api.exceptions.custom_exceptions import APIException
from api.exceptions.error_codes import ErrorCode
from api.schemas.users import UserCreateRequest
from api.utils.opensearch_util import OpenSearchUtil

router = APIRouter(prefix="/users", tags=["Users"])
opensearch_client = OpenSearchUtil()


@router.post("/create", response_model=dict)
def create_user(body: UserCreateRequest):
    """Create a new user."""
    try:
        query = {"query": {"match": {"email": body.email}}}
        resp = opensearch_client.client.search(index=args.aos_user_index, body=query)

        if resp["hits"]["total"]["value"] > 0:
            raise APIException(
                status_code=409,
                error_code=ErrorCode.USER_ALREADY_EXISTS,
                message=f"User with email '{body.email}' already exists.",
            )

        doc = {
            "email": body.email,
            "name": body.name,
            "team_id": body.team_id,
        }
        opensearch_client.client.index(index=args.aos_user_index, body=doc)

        return {"status": "success", "message": "User created successfully"}

    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=500,
            error_code=ErrorCode.USER_CREATION_FAILED,
            message="Failed to create user.",
            details=str(e),
        ) from e
