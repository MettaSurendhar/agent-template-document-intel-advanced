from pydantic import BaseModel

from api.schemas.documents import S3PathWithTags


class TriggerKB(BaseModel):
    """Schema for triggering knowledge base ingestion."""

    files: list[S3PathWithTags]
    user_email: str
    team_id: str
    is_private: bool = False
