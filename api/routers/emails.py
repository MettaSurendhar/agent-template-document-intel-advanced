import os

from fastapi import APIRouter
from jinja2 import Environment, FileSystemLoader

from api import args
from api.exceptions.custom_exceptions import APIException
from api.exceptions.error_codes import ErrorCode
from api.schemas.emails import EmailRequest, EmailSendResponse, ShareLLMEmailRequest
from api.utils.email_utils import send_email

router = APIRouter(prefix="/emails", tags=["Emails"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))


@router.post("/share-llm-summary", response_model=EmailSendResponse)
async def share_llm_summary(request: ShareLLMEmailRequest):
    """Send an LLM summary email."""
    try:
        template = env.get_template("share_llm_summary_template.html")
        html_body = template.render(sender_name=args.email_sender_name, passage=request.passage)

        email_request = EmailRequest(
            to_emails=request.recipients,
            subject=request.subject,
            html_body=html_body,
        )

        await send_email(email_request)

        return EmailSendResponse(
            status=True,
            message="LLM summary email sent.",
            recipients=request.recipients,
        )

    except Exception as e:
        raise APIException(
            status_code=500,
            error_code=ErrorCode.EMAIL_SEND_FAILED,
            message=f"Failed to send LLM summary email: {str(e)}",
        ) from e
