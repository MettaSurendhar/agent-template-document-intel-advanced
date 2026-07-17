from pydantic import BaseModel, Field


class Team(BaseModel):
    """Represents a team with its ID and name."""

    team_id: str = Field(..., description="team id")
    team_name: str = Field(..., description="team name")


class TeamCreateRequest(BaseModel):
    """Schema for creating a new team."""

    team_name: str = Field(..., description="Team name")


class TeamListResponse(BaseModel):
    """Response model for listing teams."""

    teams: list[Team]
