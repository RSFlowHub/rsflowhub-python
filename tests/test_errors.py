from __future__ import annotations

import asyncio
from typing import Any, Type

import httpx
import pytest

from rsflowhub import (
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
from tests.conftest import Mock, api_error, ok


def test_validation_error_exposes_code_message_request_id_and_fields(mock: Mock) -> None:
    client = mock.client()
    mock.add(api_error(422, "VALIDATION_ERROR", "The given data was invalid.", {"text": ["The text field is required."]}))

    with pytest.raises(ValidationError) as info:
        client.ai.sentiment_analysis()

    e = info.value
    assert isinstance(e, APIError) and isinstance(e, RSFlowHubError)
    assert e.code == "VALIDATION_ERROR"
    assert e.status_code == 422
    assert e.message == "The given data was invalid."
    assert e.request_id == "req_err"
    assert e.errors == {"text": ["The text field is required."]}
    assert str(e) == "VALIDATION_ERROR: The given data was invalid. (request req_err)"


def test_insufficient_credits(mock: Mock) -> None:
    client = mock.client()
    mock.add(api_error(402, "INSUFFICIENT_CREDITS", "Not enough credits.", {"required_credits": 3, "available_credits": 1}))

    with pytest.raises(InsufficientCreditsError) as info:
        client.ai.review_summary(reviews=["ok"])

    assert info.value.required_credits == 3
    assert info.value.available_credits == 1


@pytest.mark.parametrize("status,code,cls", [
    (401, "INVALID_API_KEY", AuthenticationError),
    (401, "API_KEY_MISSING", AuthenticationError),
    (403, "SPENDING_LIMIT_REACHED", PermissionDeniedError),
    (403, "USER_INACTIVE", PermissionDeniedError),
    (404, "ENDPOINT_NOT_FOUND", NotFoundError),
    (500, "INTERNAL_SERVER_ERROR", InternalServerError),
    (502, "AI_PROVIDER_ERROR", ServiceUnavailableError),
    (405, "METHOD_NOT_ALLOWED", APIError),
])
def test_error_codes_map_to_typed_errors(mock: Mock, status: int, code: str, cls: Type[APIError]) -> None:
    client = mock.client(max_retries=0)
    mock.add(api_error(status, code, "Nope"))

    with pytest.raises(APIError) as info:
        client.ai.chat(message="hi")

    assert type(info.value) is cls
    assert info.value.code == code


def test_non_json_error_pages_map_by_status(mock: Mock) -> None:
    client = mock.client(max_retries=0)
    mock.add(httpx.Response(503, text="<html>Bad gateway</html>"))

    with pytest.raises(ServiceUnavailableError) as info:
        client.ai.chat(message="hi")

    assert info.value.code == "PROVIDER_UNAVAILABLE"


def test_non_json_success_is_an_sdk_error(mock: Mock) -> None:
    client = mock.client()
    mock.add(httpx.Response(200, text="<html>maintenance</html>"))

    with pytest.raises(RSFlowHubError, match="non-JSON"):
        client.ai.chat(message="hi")


def test_retries_429_and_503_honouring_retry_after(mock: Mock) -> None:
    client = mock.client()
    mock.add(
        api_error(429, "RATE_LIMIT_EXCEEDED", "Slow down", headers={"Retry-After": "2"}),
        api_error(503, "PROVIDER_UNAVAILABLE", "Busy"),
        ok({"result": {"reply": "Hello"}}),
    )

    res = client.ai.chat(message="hi")

    assert res.result["reply"] == "Hello"
    assert len(mock.requests) == 3
    assert mock.sleeps[0] == 2.0
    assert mock.sleeps[1] >= 1.0


def test_gives_up_after_max_retries_and_exposes_retry_after(mock: Mock) -> None:
    client = mock.client(max_retries=1)
    mock.add(
        api_error(429, "RATE_LIMIT_EXCEEDED", "Slow down", headers={"Retry-After": "7"}),
        api_error(429, "RATE_LIMIT_EXCEEDED", "Slow down", headers={"Retry-After": "7"}),
    )

    with pytest.raises(RateLimitError) as info:
        client.ai.chat(message="hi")

    assert info.value.retry_after == 7
    assert len(mock.requests) == 2


def test_per_call_max_retries(mock: Mock) -> None:
    client = mock.client()
    mock.add(api_error(503, "PROVIDER_UNAVAILABLE", "Busy"))

    with pytest.raises(ServiceUnavailableError):
        client.ai.chat(message="hi", max_retries=0)

    assert len(mock.requests) == 1


def test_server_errors_are_not_retried(mock: Mock) -> None:
    client = mock.client()
    mock.add(api_error(500, "INTERNAL_SERVER_ERROR", "Oops"))

    with pytest.raises(InternalServerError):
        client.ai.chat(message="hi")

    assert len(mock.requests) == 1
    assert mock.sleeps == []


def test_connection_errors_retry_then_raise(mock: Mock) -> None:
    client = mock.client(max_retries=1)
    mock.add(httpx.ConnectError("refused"), httpx.ConnectError("refused"))

    with pytest.raises(APIConnectionError):
        client.ai.chat(message="hi")

    assert len(mock.sleeps) == 1


def test_timeouts_raise_api_timeout_error(mock: Mock) -> None:
    client = mock.client(max_retries=0)
    mock.add(httpx.ReadTimeout("slow"))

    with pytest.raises(APITimeoutError, match="timed out"):
        client.ai.chat(message="hi")


def test_async_errors_and_retries(mock: Mock) -> None:
    async def run() -> Any:
        client = mock.async_client()
        mock.add(
            api_error(503, "PROVIDER_UNAVAILABLE", "Busy"),
            api_error(422, "VALIDATION_ERROR", "Invalid", {"message": ["Required."]}),
        )
        with pytest.raises(ValidationError) as info:
            await client.ai.chat()
        await client.aclose()
        return info.value

    e = asyncio.run(run())
    assert e.errors == {"message": ["Required."]}
    assert len(mock.requests) == 2
    assert len(mock.sleeps) == 1
