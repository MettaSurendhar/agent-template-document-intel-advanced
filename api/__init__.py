import os

from datargs import arg, argsclass, parse
from dotenv import load_dotenv

load_dotenv(override=True)


@argsclass(description="args")
class Args:
    """App-related arguments."""

    host: str = arg(default=os.getenv("APP_HOST", "0.0.0.0"), help="App host")
    port: int = arg(default=int(os.getenv("APP_PORT", "8000")), help="App port")
    subpath: str = arg(default=os.getenv("APP_API_SUBPATH", "/api"), help="API subpath")
    aos_username: str = arg(default=os.getenv("OPENSEARCH_USERNAME", ""), help="OpenSearch username")
    aos_password: str = arg(default=os.getenv("OPENSEARCH_PASSWORD", ""), help="OpenSearch password")
    aos_endpoint: str = arg(
        default=os.getenv("OPENSEARCH_ENDPOINT", "https://localhost:9200"), help="OpenSearch endpoint"
    )
    aos_use_ssl: bool = arg(
        default=os.getenv("OPENSEARCH_USE_SSL", "true").lower() == "true",
        help="Whether to use SSL for the OpenSearch connection (set false for local, unsecured dev clusters)",
    )
    aos_verify_certs: bool = arg(
        default=os.getenv("OPENSEARCH_VERIFY_CERTS", "true").lower() == "true",
        help="Whether to verify SSL certs for the OpenSearch connection (set false for local dev)",
    )
    jwt_secret: str = arg(default=os.getenv("JWT_SECRET", "docintelagent"), help="JWT secret key")
    jwt_algorithm: str = arg(default=os.getenv("JWT_ALGORITHM", "HS256"), help="JWT algorithm")

    aos_user_index: str = arg(
        default=os.getenv("AOS_USER_INDEX", "docintel_users_teams"), help="OpenSearch user index"
    )
    aos_team_index: str = arg(default=os.getenv("AOS_TEAM_INDEX", "docintel_teams"), help="OpenSearch team index")
    aos_documents_index: str = arg(
        default=os.getenv("AOS_DOCUMENTS_INDEX", "docintel_documents"), help="OpenSearch documents index"
    )
    aos_message_index: str = arg(
        default=os.getenv("AOS_MESSAGES_INDEX", "docintel_messages"), help="OpenSearch message index"
    )
    aos_languages_index: str = arg(
        default=os.getenv("AOS_LANGUAGES_INDEX", "docintel_languages"), help="OpenSearch languages index"
    )
    aos_private_documents_index: str = arg(
        default=os.getenv("AOS_PRIVATE_DOCUMENTS_INDEX", "docintel_private_documents"),
        help="OpenSearch private document index",
    )
    aos_audit_index: str = arg(
        default=os.getenv("AOS_AUDIT_INDEX", "docintel_audit_logs"), help="OpenSearch audit log index"
    )

    aws_region: str = arg(default=os.getenv("AWS_REGION", "us-east-1"), help="AWS region for Bedrock and S3")
    knowledge_base_id: str = arg(default=os.getenv("KNOWLEDGE_BASE_ID", ""), help="Bedrock knowledge base ID")
    data_source_id: str = arg(default=os.getenv("DATA_SOURCE_ID", ""), help="Bedrock data source ID")
    model_id: str = arg(default=os.getenv("MODEL_ID", ""), help="Bedrock model ID")

    tenant_id: str = arg(default=os.getenv("AZURE_TENANT_ID", ""), help="Azure AD tenant ID")
    client_id: str = arg(default=os.getenv("AZURE_CLIENT_ID", ""), help="Azure AD application (client) ID")

    smtp_server: str = arg(default=os.getenv("SMTP_SERVER", "smtp.gmail.com"), help="SMTP server")
    smtp_port: int = arg(default=int(os.getenv("SMTP_PORT", 465)), help="SMTP port")
    smtp_user: str = arg(default=os.getenv("SMTP_USER", ""), help="SMTP user (email address)")
    smtp_password: str = arg(default=os.getenv("SMTP_PASSWORD", ""), help="SMTP password or app password")
    email_sender_name: str = arg(default=os.getenv("EMAIL_SENDER_NAME", ""), help="Email sender name")

    s3_bucket: str = arg(default=os.getenv("S3_BUCKET"), help="s3 bucket")
    s3_folder_prefix: str = arg(default=os.getenv("S3_FOLDER_PREFIX"), help="S3 prefix")

    s3_uploads_prefix: str = arg(default=os.getenv("S3_UPLOADS_PREFIX", "uploads/"), help="S3 uploads prefix")
    s3_docs_prefix: str = arg(default=os.getenv("S3_DOCS_PREFIX", "docs/"), help="S3 docs prefix")
    default_team_id: str = arg(
        default=os.getenv("DEFAULT_TEAM_ID", ""), help="Default team ID for new users without a team"
    )
    private_team_id: str = arg(default=os.getenv("PRIVATE_TEAM_ID", ""), help="Team ID used for private user documents")

    allowed_extensions: str = arg(
        default=os.getenv("ALLOWED_EXTENSIONS", ".pdf,.docx,.pptx,.ppt,.xlsx,.csv,.txt"),
        help="Comma-separated list of allowed file extensions",
    )
    conversion_extensions: str = arg(
        default=os.getenv("CONVERSION_EXTENSIONS", ".docx,.pptx,.ppt"),
        help="Comma-separated list of extensions that require conversion to PDF",
    )
    ssl_keyfile: str = arg(default=os.getenv("SSL_KEYFILE"), help="SSL private key path")
    ssl_certfile: str = arg(default=os.getenv("SSL_CERTFILE"), help="SSL certificate path")


args = parse(Args)

__all__ = ["args"]
