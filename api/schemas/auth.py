from pydantic import BaseModel


class DevLoginRequest(BaseModel):
    """Schema for developer login request payload."""

    email: str
    password: str


class DevLoginResponse(BaseModel):
    """Schema for developer login response containing token."""

    token: str


class LoginResponse(BaseModel):
    """Schema for login response containing team information."""

    team: str
