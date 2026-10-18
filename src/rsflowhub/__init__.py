"""Official Python SDK for the RSFlowHub AI API.

    from rsflowhub import RSFlowHub

    client = RSFlowHub()  # reads RSFLOWHUB_API_KEY
    res = client.ai.sentiment_analysis(text="Setup took two minutes.")
    print(res.result["sentiment"])

Docs: https://rsflowhub.com/docs · Source: https://github.com/RSFlowHub/rsflowhub-python
"""

from ._client import DEFAULT_BASE_URL, AsyncRSFlowHub, RSFlowHub
from ._errors import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    InsufficientCreditsError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    RSFlowHubError,
    ServiceUnavailableError,
    ValidationError,
)
from ._resource import AsyncResource, Resource
from ._response import RateLimit, Response
from ._version import __version__

__all__ = [
    "RSFlowHub",
    "AsyncRSFlowHub",
    "DEFAULT_BASE_URL",
    "Response",
    "RateLimit",
    "Resource",
    "AsyncResource",
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
    "__version__",
]
