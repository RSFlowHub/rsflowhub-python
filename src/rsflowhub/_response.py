from __future__ import annotations

from typing import Any, Dict, Iterator, Mapping, Optional

import httpx

__all__ = ["Response", "RateLimit"]


class RateLimit(Dict[str, Optional[int]]):
    """``{"limit": 60, "remaining": 59, "reset": None}`` from the X-RateLimit-* headers."""


class Response(Mapping[str, Any]):
    """A successful API answer: ``{"success": true, "request_id", "data", "meta"}``.

    AI endpoints put their output in ``data.result``; ``res.result`` returns it
    (or ``data`` itself for routes without a ``result``, like knowledge bases).
    The response is also a read-only mapping over ``data``: ``res["result"]``.
    """

    def __init__(self, body: Dict[str, Any], http: httpx.Response) -> None:
        #: The full decoded JSON body.
        self.body = body
        self.http_response = http
        data = body.get("data")
        #: Everything under ``data``.
        self.data: Dict[str, Any] = data if isinstance(data, dict) else {"value": data}
        #: ``{"version", "timestamp"}``
        self.meta: Dict[str, Any] = body["meta"] if isinstance(body.get("meta"), dict) else {}
        #: Server request id. Quote it when you contact support.
        self.request_id: Optional[str] = (
            body["request_id"] if isinstance(body.get("request_id"), str) else http.headers.get("x-request-id")
        )

    @property
    def result(self) -> Any:
        """The AI output (``data.result``), or ``data`` when there is no ``result``."""
        return self.data["result"] if "result" in self.data else self.data

    def get_path(self, path: str, default: Any = None) -> Any:
        """Read from ``data`` with dot notation: ``res.get_path("result.aspects.0.name")``."""
        value: Any = self.data
        for key in path.split("."):
            if isinstance(value, dict) and key in value:
                value = value[key]
            elif isinstance(value, list) and key.isdigit() and int(key) < len(value):
                value = value[int(key)]
            else:
                return default
        return value

    @property
    def status_code(self) -> int:
        return self.http_response.status_code

    @property
    def headers(self) -> httpx.Headers:
        return self.http_response.headers

    @property
    def rate_limit(self) -> RateLimit:
        """Your rate-limit state after this call (X-RateLimit-* headers)."""

        def num(name: str) -> Optional[int]:
            value = self.headers.get(name)
            try:
                return int(value) if value not in (None, "") else None
            except ValueError:
                return None

        return RateLimit(
            limit=num("x-ratelimit-limit"),
            remaining=num("x-ratelimit-remaining"),
            reset=num("x-ratelimit-reset"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return self.data

    # Mapping over data -------------------------------------------------------
    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.data)

    def __len__(self) -> int:
        return len(self.data)

    def __repr__(self) -> str:
        return f"Response(request_id={self.request_id!r}, data={self.data!r})"
