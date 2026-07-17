from pydantic import BaseModel, Field


class ObjectStore(BaseModel):
    """Represents storage details for a document object."""

    type: str
    converted: str | None = None
    location: str | None = None


class Document(BaseModel):
    """Represents a document with metadata and storage details."""

    document_id: str
    document_name: str
    object_store: ObjectStore
    uploaded_timestamp: str
    tags: list[str]
    sync_status: str | None = None
    last_synced_at: str | None = None


class DocumentListResponse(BaseModel):
    """Response schema for a paginated list of documents."""

    documents: list[Document]
    page: int
    page_size: int
    total_records: int


class DocumentID(BaseModel):
    """Schema for documentId."""

    document_id: str
    document_name: str
    object_store: ObjectStore
    uploaded_timestamp: str


class DocumentTagUpdate(BaseModel):
    """Request schema for updating tags."""

    add_tags: list[str] = []
    remove_tags: list[str] = []


class DocumentTagUpdateResponse(BaseModel):
    """Response schema for updating tags."""

    message: str
    tags: list[str]


class TranslateRequest(BaseModel):
    """Request model for translating a passage."""

    passage: str
    target_language: str


class TranslateResponse(BaseModel):
    """schemas for translate response."""

    original_passage: str
    translated_passage: str
    target_language: str


class PresignedUrlResponse(BaseModel):
    """response schema for pre-signed url."""

    url: str


class DocumentsObjectStore(BaseModel):
    """Represent storage details for a document in S3."""

    type: str
    location: str


class S3PathWithTags(BaseModel):
    """Represent an S3 path with associated tags for document insertion."""

    s3_path: str
    tags: list[str]


class S3PathRequest(BaseModel):
    """Request model for inserting documents with S3 paths, tags, and a team ID."""

    files: list[S3PathWithTags]
    team_id: str


class PresignedPostFields(BaseModel):
    """schemas for pre-signed url fields.."""

    key: str
    AWSAccessKeyId: str
    policy: str
    signature: str
    x_amz_security_token: str = Field(..., alias="x-amz-security-token")
    model_config = {"extra": "allow"}


class PresignedPostUrlData(BaseModel):
    """schemas for url and fields."""

    url: str
    fields: PresignedPostFields
    file_exists: bool = False


class UploadPathsResponse(BaseModel):
    """Response schemas for pre-signed url for uploading documents."""

    presigned_urls: dict[str, PresignedPostUrlData]


class TagsResponse(BaseModel):
    """Represent a list of unique tags retrieved from the index."""

    tags: list[str]


class DeleteDocumentResponse(BaseModel):
    """Response schema for document deletion."""

    status: bool
    message: str


class SyncStatusUpdate(BaseModel):
    """Schema for updating document synchronization status."""

    file_path: str
    status: str
    job_id: str | None = None


class InsertDocsResponse(BaseModel):
    """Response schema for the /insert-docs API endpoint."""

    success: bool = True
