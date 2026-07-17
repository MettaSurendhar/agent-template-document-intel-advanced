import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from api import args
from api.schemas.emails import EmailRequest

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s - %(message)s", "%Y-%m-%d %H:%M:%S")
console_handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(console_handler)


async def send_email(request: EmailRequest) -> bool:
    """Send an email and log whether it succeeded or failed."""
    msg = MIMEMultipart()
    msg["From"] = args.smtp_user
    msg["To"] = ", ".join(request.to_emails)
    msg["Subject"] = request.subject
    msg.attach(MIMEText(request.html_body, "html"))

    ssl_context = ssl.create_default_context()

    try:
        with smtplib.SMTP_SSL(args.smtp_server, args.smtp_port, context=ssl_context) as server:
            server.login(args.smtp_user, args.smtp_password)
            server.sendmail(args.smtp_user, request.to_emails, msg.as_string())

        logger.info(f"Email successfully sent to: {request.to_emails}")
        return True

    except smtplib.SMTPException as e:
        logger.error(f"Failed to send email to {request.to_emails}: {e}")
        return False
