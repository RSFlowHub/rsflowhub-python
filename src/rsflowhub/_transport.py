from __future__ import annotations

import asyncio
import json
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

import httpx

from ._errors import APIConnectionError, APIError, APITimeoutError, RSFlowHubError
from ._response import Response
from ._version import __version__

RETRY_STATUSES = (429, 502, 503, 504)


@dataclass
class RequestOptions:
    """Per-call overrides: ``timeout``, ``max_retries``, ``extra_headers``."""

    timeout: Optional[float] = None
    max_retries: Optional[int] = None
    extra_headers: Optional[Mapping[str, str]] = None


@dataclass
class Settings:
    api_key: str
    base_url: str
    timeout: float
    max_retries: int
    headers: Dict[str, str] = field(default_factory=dict)


def build_request(
    settings: Settings,
    method: str,
    path: str,
    body: Optional[Mapping[str, Any]],
    query: Optional[Mapping[str, Any]],
    options: RequestOptions,
) -> Dict[str, Any]:
    """Keyword arguments for ``httpx.Client.request`` (shared by sync and async)."""
    method = method.upper()
    headers = {
        "X-API-Key": settings.api_key,
        "Accept": "application/json",
        "User-Agent": f"rsflowhub-python/{__version__}",
        **settings.headers,
        **(options.extra_headers or {}),
    }
    request: Dict[str, Any] = {
        "method": method,
        "url": settings.base_url.rstrip("/") + "/" + path.lstrip("/"),
        "headers": headers,
        "timeout": options.timeout if options.timeout is not None else settings.timeout,
    }
    if query:
        request["params"] = _flatten(query)
    if body and method != "GET":
        if _has_file(body):
            files, data = _multipart(body)
            request["files"] = files
            request["data"] = data
        else:
            request["content"] = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
    return request


def to_response(response: httpx.Response) -> Response:
    try:
        body = response.json() if response.content else {}
    except ValueError:
        body = None

    if not isinstance(body, dict):
        if response.status_code >= 400:
            raise APIError.from_response(response, {})
        raise RSFlowHubError(f"RSFlowHub returned a non-JSON response (HTTP {response.status_code}).")

    if response.status_code >= 400 or body.get("success") is False:
        raise APIError.from_response(response, body)

    return Response(body, response)


def backoff(attempt: int, response: Optional[httpx.Response]) -> float:
    """Seconds to wait: Retry-After when given (capped at 60), else 0.5, 1, 2 ... plus jitter."""
    retry_after = response.headers.get("retry-after") if response is not None else None
    if retry_after:
        try:
            return min(60.0, max(0.0, float(retry_after)))
        except ValueError:
            pass
    return min(8.0, 0.5 * (2.0**attempt)) + random.uniform(0, 0.25)


class SyncTransport:
    def __init__(self, settings: Settings, http: httpx.Client, sleep: Callable[[float], None] = time.sleep) -> None:
        self.settings = settings
        self.http = http
        self.sleep = sleep

    def send(
        self,
        method: str,
        path: str,
        body: Optional[Mapping[str, Any]] = None,
        query: Optional[Mapping[str, Any]] = None,
        options: Optional[RequestOptions] = None,
    ) -> Response:
        options = options or RequestOptions()
        request = build_request(self.settings, method, path, body, query, options)
        max_retries = options.max_retries if options.max_retries is not None else self.settings.max_retries

        attempt = 0
        while True:
            try:
                response = self.http.request(**request)
            except httpx.TimeoutException as e:
                if attempt < max_retries:
                    self.sleep(backoff(attempt, None))
                    attempt += 1
                    continue
                raise APITimeoutError(f"Request to RSFlowHub timed out after {request['timeout']} s.") from e
            except httpx.TransportError as e:
                if attempt < max_retries:
                    self.sleep(backoff(attempt, None))
                    attempt += 1
                    continue
                raise APIConnectionError(f"Could not reach RSFlowHub: {e}") from e

            if response.status_code in RETRY_STATUSES and attempt < max_retries:
                self.sleep(backoff(attempt, response))
                attempt += 1
                continue
            return to_response(response)


class AsyncTransport:
    def __init__(self, settings: Settings, http: httpx.AsyncClient, sleep: Optional[Callable[[float], Any]] = None) -> None:
        self.settings = settings
        self.http = http
        self.sleep = sleep or asyncio.sleep

    async def send(
        self,
        method: str,
        path: str,
        body: Optional[Mapping[str, Any]] = None,
        query: Optional[Mapping[str, Any]] = None,
        options: Optional[RequestOptions] = None,
    ) -> Response:
        options = options or RequestOptions()
        request = build_request(self.settings, method, path, body, query, options)
        max_retries = options.max_retries if options.max_retries is not None else self.settings.max_retries

        attempt = 0
        while True:
            try:
                response = await self.http.request(**request)
            except httpx.TimeoutException as e:
                if attempt < max_retries:
                    await self._sleep(backoff(attempt, None))
                    attempt += 1
                    continue
                raise APITimeoutError(f"Request to RSFlowHub timed out after {request['timeout']} s.") from e
            except httpx.TransportError as e:
                if attempt < max_retries:
                    await self._sleep(backoff(attempt, None))
                    attempt += 1
                    continue
                raise APIConnectionError(f"Could not reach RSFlowHub: {e}") from e

            if response.status_code in RETRY_STATUSES and attempt < max_retries:
                await self._sleep(backoff(attempt, response))
                attempt += 1
                continue
            return to_response(response)

    async def _sleep(self, seconds: float) -> None:
        result = self.sleep(seconds)
        if asyncio.iscoroutine(result):
            await result


# Files and form encoding -------------------------------------------------------

def _is_file(value: Any) -> bool:
    return isinstance(value, (bytes, bytearray, memoryview, Path)) or (hasattr(value, "read") and callable(value.read))


def _has_file(body: Mapping[str, Any]) -> bool:
    return any(_is_file(v) for v in body.values())


def _file_tuple(name: str, value: Any) -> Tuple[str, Any]:
    if isinstance(value, Path):
        return (value.name, value.read_bytes())
    if isinstance(value, (bytes, bytearray, memoryview)):
        return (name, bytes(value))
    # Read once so a retry sends the whole file again (uploads are capped at 20 MB).
    filename = os.path.basename(str(getattr(value, "name", "") or name))
    return (filename, value.read())


def _multipart(body: Mapping[str, Any]) -> Tuple[Dict[str, Tuple[str, Any]], Dict[str, Any]]:
    """multipart/form-data; nested values become name[key] (what Laravel's "array" rule reads)."""
    files: Dict[str, Tuple[str, Any]] = {}
    data: Dict[str, Any] = {}
    for name, value in body.items():
        if _is_file(value):
            files[name] = _file_tuple(name, value)
        elif value is not None:
            data.update(_flatten({name: value}))
    return files, data


def _flatten(values: Mapping[str, Any], prefix: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in values.items():
        name = f"{prefix}[{key}]" if prefix else str(key)
        if value is None:
            continue
        if isinstance(value, Mapping):
            out.update(_flatten(value, name))
        elif isinstance(value, (list, tuple)):
            out.update(_flatten({str(i): v for i, v in enumerate(value)}, name))
        elif isinstance(value, bool):
            out[name] = "1" if value else "0"
        else:
            out[name] = str(value)
    return out
