from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status


class AppError(HTTPException):
    """Base error producing the app's uniform error envelope.

    Subclasses set a default status and code but still accept an explicit
    ``code`` override, so call sites can distinguish cases the frontend needs
    to branch on (``invalid_credentials`` vs ``refresh_reused``, for example).
    """

    code = "error"
    status_code_default = status.HTTP_400_BAD_REQUEST

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        fields: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=status_code or self.status_code_default,
            detail={
                "code": code or self.code,
                "message": message,
                "fields": fields or {},
            },
        )


class BadRequest(AppError):
    code = "bad_request"
    status_code_default = status.HTTP_400_BAD_REQUEST


class NotFound(AppError):
    code = "not_found"
    status_code_default = status.HTTP_404_NOT_FOUND

    def __init__(self, message: str = "Not found", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)


class Unauthorized(AppError):
    code = "unauthorized"
    status_code_default = status.HTTP_401_UNAUTHORIZED

    def __init__(self, message: str = "Not authenticated", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)


class Forbidden(AppError):
    code = "forbidden"
    status_code_default = status.HTTP_403_FORBIDDEN


class Conflict(AppError):
    code = "conflict"
    status_code_default = status.HTTP_409_CONFLICT

    def __init__(self, message: str = "Already exists", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)


class TooManyRequests(AppError):
    code = "rate_limited"
    status_code_default = status.HTTP_429_TOO_MANY_REQUESTS

    def __init__(self, message: str = "Too many requests", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)


class UnprocessableUpload(AppError):
    code = "unprocessable_upload"
    status_code_default = status.HTTP_422_UNPROCESSABLE_ENTITY
