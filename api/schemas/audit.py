from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLog(BaseModel):
    """Represents a single audit log entry."""

    id: str
    timestamp: datetime
    user_id: str
    user_name: str
    team_id: str
    event_type: str
    description: str
    metadata: dict[str, Any] = {}


class AuditLogListResponse(BaseModel):
    """Response schema for a paginated list of audit logs."""

    logs: list[AuditLog]
    page: int
    page_size: int
    total_records: int


class AuditUser(BaseModel):
    """Represents a user in the audit logs."""

    name: str
    email: str


class AuditUserListResponse(BaseModel):
    """Response model for a list of users from audit logs."""

    users: list[AuditUser]
    total_users: int
