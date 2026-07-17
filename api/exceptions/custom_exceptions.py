from fastapi import Request
from fastapi.responses import JSONResponse

from .error_codes import ErrorCode


class APIException(Exception):
    """Custom API exception with HTTP status, error code, and optional details."""

    def __init__(self, status_code: int, error_code: ErrorCode, message: str, details: str | None = None):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.details = details


def api_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle APIException errors and return a JSON response."""
    if isinstance(exc, APIException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_code": exc.error_code.value,
                "message": exc.message,
                "details": exc.details,
            },
        )
    # Optional: fallback for unexpected exceptions
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "internal_error",
            "message": "An unexpected error occurred.",
            "details": None,
        },
    )
