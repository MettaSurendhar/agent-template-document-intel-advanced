from pydantic import BaseModel


class S3PathWithTags(BaseModel):
    """Represent an S3 path with associated tags for document insertion."""

    s3_path: str
    tags: list[str]


class PrivateDocInsertRequest(BaseModel):
    """Request model for inserting private documents with S3 paths and tags."""

    files: list[S3PathWithTags]


class PrivateDocInsertResponse(BaseModel):
    """Response schema for private document insertion."""

    success: bool = True


class PrivateDocDeleteResponse(BaseModel):
    """Response schema for private document deletion."""

    success: bool
    deleted_s3_files: int
    deleted_documents: int
