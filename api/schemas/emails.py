from pydantic import BaseModel, EmailStr


class EmailSendResponse(BaseModel):
    """Response schema returned after sending an email."""

    status: bool
    message: str
    recipients: list[EmailStr]


class ShareLLMEmailRequest(BaseModel):
    """Request schema for sending LLM summary email."""

    recipients: list[EmailStr]
    subject: str
    passage: str


class EmailRequest(BaseModel):
    """Base schema for email requests."""

    to_emails: list[EmailStr]
    subject: str
    html_body: str
