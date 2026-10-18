from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Union

import httpx
import pytest

from rsflowhub import AsyncRSFlowHub, RSFlowHub

Queued = Union[httpx.Response, Exception]


def ok(data: Any = None, headers: Optional[Dict[str, str]] = None) -> httpx.Response:
    body = {"success": True, "request_id": "req_123", "data": {} if data is None else data, "meta": {"version": "v1"}}
    return httpx.Response(200, json=body, headers=headers or {})


def api_error(status: int, code: str, message: str, details: Any = None, headers: Optional[Dict[str, str]] = None) -> httpx.Response:
    body = {"success": False, "request_id": "req_err", "error": {"code": code, "message": message, "details": details or {}}, "meta": {}}
    return httpx.Response(status, json=body, headers=headers or {})


class Mock:
    """Answers requests from a queue and records them."""

    def __init__(self) -> None:
        self.queue: List[Queued] = []
        self.requests: List[httpx.Request] = []
        self.sleeps: List[float] = []

    def add(self, *responses: Queued) -> None:
        self.queue.extend(responses)

    def handler(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        if not self.queue:
            raise AssertionError("no response queued")
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    def last_json(self) -> Any:
        return json.loads(self.last.content)

    def client(self, **options: Any) -> RSFlowHub:
        return RSFlowHub(
            "rfh_test1234_secret",
            base_url="https://api.test/api/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(self.handler)),
            _sleep=self.sleeps.append,
            **options,
        )

    def async_client(self, **options: Any) -> AsyncRSFlowHub:
        async def sleep(seconds: float) -> None:
            self.sleeps.append(seconds)

        return AsyncRSFlowHub(
            "rfh_test1234_secret",
            base_url="https://api.test/api/v1",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(self.handler)),
            _sleep=sleep,
            **options,
        )


@pytest.fixture
def mock() -> Mock:
    return Mock()


@pytest.fixture
def no_env(monkeypatch: pytest.MonkeyPatch) -> Callable[[], None]:
    def clear() -> None:
        monkeypatch.delenv("RSFLOWHUB_API_KEY", raising=False)
        monkeypatch.delenv("RSFLOWHUB_BASE_URL", raising=False)

    return clear
