import uuid

from fastapi import APIRouter

from api import args
from api.exceptions.custom_exceptions import APIException
from api.exceptions.error_codes import ErrorCode
from api.schemas.team import Team, TeamCreateRequest, TeamListResponse
from api.utils.opensearch_util import OpenSearchUtil

router = APIRouter(prefix="/teams", tags=["Teams"])
opensearch_client = OpenSearchUtil()


@router.get("", response_model=TeamListResponse)
def list_all_teams():
    """List all teams from the OpenSearch index."""
    try:
        resp = opensearch_client.client.search(
            index=args.aos_team_index,
            body={
                "size": 1000,
                "query": {"match_all": {}},
            },
        )

        hits = resp.get("hits", {}).get("hits", [])
        teams = [
            Team(
                team_id=str(src.get("team_id", "")),
                team_name=src.get("team_name", ""),
            )
            for src in (hit.get("_source", {}) for hit in hits)
        ]

        return TeamListResponse(teams=teams)
    except Exception as e:
        raise APIException(
            status_code=500,
            error_code=ErrorCode.TEAMS_FETCH_FAILED,
            message="Failed to fetch teams.",
            details=str(e),
        ) from e


@router.post("/create", response_model=Team)
def create_team(body: TeamCreateRequest):
    """Create a new team."""
    try:
        query = {
            "query": {"match": {"team_name.keyword": body.team_name}},
        }
        resp = opensearch_client.client.search(index=args.aos_team_index, body=query)
        if resp["hits"]["total"]["value"] > 0:
            raise APIException(
                status_code=409,
                error_code=ErrorCode.TEAM_ALREADY_EXISTS,
                message=f"Team '{body.team_name}' already exists.",
            )

        team_id = str(uuid.uuid4())

        doc = {
            "team_id": team_id,
            "team_name": body.team_name,
        }
        opensearch_client.client.index(index=args.aos_team_index, body=doc)

        return Team(team_id=team_id, team_name=body.team_name)

    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=500,
            error_code=ErrorCode.TEAM_CREATION_FAILED,
            message="Failed to create team.",
            details=str(e),
        ) from e
