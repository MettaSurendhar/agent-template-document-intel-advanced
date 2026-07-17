from datetime import datetime

from pydantic import BaseModel


class ConverseRequest(BaseModel):
    """Schema for the converse API request body."""

    userQuery: str
    documentUris: list[str] | None = None
    excludedDocumentUris: list[str] | None = None


class Citation(BaseModel):
    """Represents a source citation with title and URI."""

    title: str
    document_id: str | None = None
    document_name: str | None = None
    uri: str
    converted_uri: str | None = None
    tags: list[str] | None = []
    uploaded_timestamp: str | None = None


class ConverseResponse(BaseModel):
    """Response schema for the /api/agents/converse endpoint."""

    message_id: str
    userQuery: str
    summary: str
    reason: str | None = None
    references: list[Citation]
    timestamp: datetime


class RecentQuestion(BaseModel):
    """Schema for a single recent question object."""

    message_id: str
    message: str


class RecentQuestionsResponse(BaseModel):
    """Response schema for the /api/agents/questions/recent endpoint."""

    recent_questions: list[RecentQuestion]


class Language(BaseModel):
    """schema for single language object."""

    language_code: str
    language_name: str


class LanguageListResponse(BaseModel):
    """response schema for /api/agents/languages endpoint."""

    languages: list[Language]


class QuestionSuggestionRequest(BaseModel):
    """Request schema for suggesting next questions."""

    documentUris: list[str] | None = None
    excludedDocumentUris: list[str] | None = None
    count: int = 5
    userQuery: str | None = None


class QuestionSuggestionResponse(BaseModel):
    """Response schema for /api/agents/questions/suggest endpoint."""

    suggestions: list[str]
