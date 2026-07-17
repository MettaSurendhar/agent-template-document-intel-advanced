from pydantic import BaseModel, Field


class UserCreateRequest(BaseModel):
    """Schema for creating a new user."""

    email: str = Field(..., description="User email")
    name: str = Field(..., description="User name")
    team_id: str = Field(..., description="Team ID the user belongs to")
