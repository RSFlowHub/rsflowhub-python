from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Type

import httpx

__all__ = [
    "RSFlowHubError",
    "APIConnectionError",
    "APITimeoutError",
    "APIError",
    "AuthenticationError",
    "InsufficientCreditsError",
    "PermissionDeniedError",
    "NotFoundError",
    "ValidationError",
    "RateLimitError",
    "InternalServerError",
    "ServiceUnavailableError",
]


class RSFlowHubError(Exception):
    """Base class of every error raised by the SDK."""


class APIConnectionError(RSFlowHubError):
    """The request never got an answer (DNS, TLS, connection refused)."""


class APITimeoutError(APIConnectionError):
    """The request took longer than the timeout."""


class APIError(RSFlowHubError):
    """The API answered with an error envelope:
    ``{"success": false, "request_id", "error": {"code", "message", "details"}}``.

    Catch this to handle every API error; catch a subclass for one kind.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        code: str,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        body: Optional[Dict[str, Any]] = None,
        response: Optional[httpx.Response] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        #: HTTP status, e.g. 422.
        self.status_code = status_code
        #: Machine-readable error code, e.g. "VALIDATION_ERROR".
        self.code = code
        #: Extra context from the API (for VALIDATION_ERROR: field -> messages).
        self.details: Dict[str, Any] = details or {}
        #: Server request id. Quote it when you contact support.
        self.request_id = request_id
        #: The decoded JSON body (empty when the server did not send JSON).
        self.body: Dict[str, Any] = body or {}
        self.response = response

    def __str__(self) -> str:
        suffix = f" (request {self.request_id})" if self.request_id else ""
        return f"{self.code}: {self.message}{suffix}"

    def __repr__(self) -> str:
        return f"{type(self).__name__}(status_code={self.status_code}, code={self.code!r}, message={self.message!r})"

    @classmethod
    def from_response(cls, response: httpx.Response, body: Mapping[str, Any]) -> "APIError":
        """Build the most specific error for an error response."""
        status = response.status_code
        error = body.get("error") if isinstance(body.get("error"), dict) else {}
        assert isinstance(error, dict)
        code = error.get("code") if isinstance(error.get("code"), str) else _code_for_status(status)
        message = error.get("message") or body.get("message") or f"HTTP {status} {response.reason_phrase}".strip()
        details = error.get("details") if isinstance(error.get("details"), dict) else {}
        request_id = body.get("request_id") if isinstance(body.get("request_id"), str) else response.headers.get("x-request-id")

        error_class = _error_class(status, str(code))
        return error_class(
            str(message),
            status_code=status,
            code=str(code),
            details=details,
            request_id=request_id,
            body=dict(body),
            response=response,
        )


class AuthenticationError(APIError):
    """401: the API key is missing, invalid or revoked (API_KEY_MISSING, INVALID_API_KEY, UNAUTHORIZED)."""


class InsufficientCreditsError(APIError):
    """402: your balance cannot cover this call (INSUFFICIENT_CREDITS). Nothing was charged."""

    @property
    def required_credits(self) -> Optional[int]:
        return _to_int(self.details.get("required_credits"))

    @property
    def available_credits(self) -> Optional[int]:
        return _to_int(self.details.get("available_credits"))


class PermissionDeniedError(APIError):
    """403: spending limit reached or account inactive (SPENDING_LIMIT_REACHED, USER_INACTIVE)."""


class NotFoundError(APIError):
    """404: the endpoint or resource does not exist (ENDPOINT_NOT_FOUND)."""


class ValidationError(APIError):
    """422: the request body failed validation (VALIDATION_ERROR)."""

    @property
    def errors(self) -> Dict[str, List[str]]:
        """Field -> list of messages, e.g. ``{"text": ["The text field is required."]}``."""
        return {
            str(field): [str(m) for m in (messages if isinstance(messages, list) else [messages])]
            for field, messages in self.details.items()
        }


class RateLimitError(APIError):
    """429: too many requests (RATE_LIMIT_EXCEEDED). Retried automatically up to max_retries."""

    @property
    def retry_after(self) -> Optional[int]:
        """Seconds to wait before the next call, from the Retry-After header."""
        return _to_int(self.response.headers.get("retry-after")) if self.response is not None else None


class InternalServerError(APIError):
    """500: unexpected server error (INTERNAL_SERVER_ERROR)."""


class ServiceUnavailableError(APIError):
    """502 / 503 / 504: the AI is temporarily unavailable (PROVIDER_UNAVAILABLE, AI_PROVIDER_ERROR). Retried automatically."""


def _error_class(status: int, code: str) -> Type[APIError]:
    if code in ("API_KEY_MISSING", "INVALID_API_KEY", "UNAUTHORIZED") or status == 401:
        return AuthenticationError
    if code == "INSUFFICIENT_CREDITS" or status == 402:
        return InsufficientCreditsError
    if code in ("SPENDING_LIMIT_REACHED", "USER_INACTIVE") or status == 403:
        return PermissionDeniedError
    if code == "VALIDATION_ERROR" or status == 422:
        return ValidationError
    if code == "RATE_LIMIT_EXCEEDED" or status == 429:
        return RateLimitError
    if code in ("ENDPOINT_NOT_FOUND", "NOT_FOUND") or status == 404:
        return NotFoundError
    if status in (502, 503, 504):
        return ServiceUnavailableError
    if status >= 500:
        return InternalServerError
    return APIError


def _code_for_status(status: int) -> str:
    return {
        401: "UNAUTHORIZED",
        402: "INSUFFICIENT_CREDITS",
        404: "ENDPOINT_NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMIT_EXCEEDED",
        503: "PROVIDER_UNAVAILABLE",
    }.get(status, "INTERNAL_SERVER_ERROR" if status >= 500 else f"HTTP_{status}")


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
