from __future__ import annotations

import os
from typing import Any, Callable, Dict, Mapping, Optional, Type, TypeVar

import httpx

from ._errors import RSFlowHubError
from ._generated.resources import CLASSES, AsyncResourcesMixin, ResourcesMixin
from ._operations import Operation, Operations, camel
from ._resource import AsyncResource, Resource, bind
from ._response import Response
from ._transport import AsyncTransport, RequestOptions, Settings, SyncTransport

__all__ = ["RSFlowHub", "AsyncRSFlowHub", "DEFAULT_BASE_URL"]

DEFAULT_BASE_URL = "https://rsflowhub.com/api/v1"

_Self = TypeVar("_Self")


def _settings(
    api_key: Optional[str],
    base_url: Optional[str],
    timeout: float,
    max_retries: int,
    default_headers: Optional[Mapping[str, str]],
) -> Settings:
    key = api_key or os.environ.get("RSFLOWHUB_API_KEY") or ""
    if not key.strip():
        raise RSFlowHubError(
            "No RSFlowHub API key. Pass RSFlowHub(api_key='rfh_...') or set RSFLOWHUB_API_KEY. "
            "Create one at https://rsflowhub.com/dashboard."
        )
    if max_retries < 0:
        raise ValueError("max_retries cannot be negative.")
    return Settings(
        api_key=key,
        base_url=(base_url or os.environ.get("RSFLOWHUB_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
        timeout=timeout,
        max_retries=max_retries,
        headers=dict(default_headers or {}),
    )


class RSFlowHub(ResourcesMixin):
    """Official Python client for the RSFlowHub AI API.

    ::

        from rsflowhub import RSFlowHub

        client = RSFlowHub()  # reads RSFLOWHUB_API_KEY
        res = client.ai.sentiment_analysis(text="Loved it!")
        print(res.result["sentiment"])

    Methods are not hard-coded: any AI endpoint, including ones added after this
    release, is ``client.ai.<slug_in_snake_case>(...)``. Use it as a context
    manager (or call :meth:`close`) to release connections.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        default_headers: Optional[Mapping[str, str]] = None,
        http_client: Optional[httpx.Client] = None,
        live_spec: bool = True,
        _sleep: Optional[Callable[[float], None]] = None,
    ) -> None:
        self._settings = _settings(api_key, base_url, timeout, max_retries, default_headers)
        self._http = http_client or httpx.Client()
        self._owns_http = http_client is None
        self._transport = SyncTransport(self._settings, self._http, *([_sleep] if _sleep else []))
        self._operations = Operations()
        self._live_spec = live_spec
        self._resources: Dict[str, Resource] = {}

    @property
    def base_url(self) -> str:
        return self._settings.base_url

    def request(
        self,
        method: str,
        path: str,
        body: Optional[Mapping[str, Any]] = None,
        query: Optional[Mapping[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        extra_headers: Optional[Mapping[str, str]] = None,
    ) -> Response:
        """Call any route: ``client.request("POST", "/ai/translation", {"text": "Hello", "target_language": "French"})``.

        A ``bytes`` / ``pathlib.Path`` / open-file value turns the body into multipart/form-data.
        """
        return self._transport.send(method, path, body, query, RequestOptions(timeout, max_retries, extra_headers))

    def resource(self, name: str) -> Resource:
        """A resource by name, including ones newer than this SDK: ``client.resource("webhooks").list()``."""
        key = camel(name)
        if key not in self._resources:
            cls: Type[Resource] = CLASSES[key][0] if key in CLASSES else Resource
            self._resources[key] = cls(self, key)
        return self._resources[key]

    def call(self, resource: str, method: str, *args: Any, **kwargs: Any) -> Response:
        """Call a method by name: ``client.call("ai", "brand_new_endpoint", text="...")``."""
        return self._dispatch(camel(resource), camel(method), *args, **kwargs)

    def __getattr__(self, name: str) -> Resource:
        if name.startswith("_"):
            raise AttributeError(name)
        return self.resource(name)

    def _dispatch(self, resource: str, method: str, *args: Any, **kwargs: Any) -> Response:
        http_method, template = self._find(resource, method)
        path, params, options = bind(resource, method, template, args, kwargs)
        if http_method == "GET":
            return self._transport.send(http_method, path, None, params, options)
        return self._transport.send(http_method, path, params, None, options)

    def _find(self, resource: str, method: str) -> Operation:
        found = self._operations.find(resource, method)
        if found is None and self._live_spec and not self._operations.live_loaded:
            try:
                self._operations.merge_spec(self._transport.send("GET", "/openapi.json").body)
            except RSFlowHubError:
                self._operations.live_loaded = True  # offline or older server: keep the bundled map
            found = self._operations.find(resource, method)
        if found is None:
            raise self._operations.unknown(resource, method)
        return found

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self: _Self) -> _Self:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


class AsyncRSFlowHub(AsyncResourcesMixin):
    """Async client for asyncio apps (FastAPI, aiohttp, Django async views)::

        from rsflowhub import AsyncRSFlowHub

        async with AsyncRSFlowHub() as client:
            res = await client.ai.sentiment_analysis(text="Loved it!")
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        default_headers: Optional[Mapping[str, str]] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        live_spec: bool = True,
        _sleep: Optional[Callable[[float], Any]] = None,
    ) -> None:
        self._settings = _settings(api_key, base_url, timeout, max_retries, default_headers)
        self._http = http_client or httpx.AsyncClient()
        self._owns_http = http_client is None
        self._transport = AsyncTransport(self._settings, self._http, _sleep)
        self._operations = Operations()
        self._live_spec = live_spec
        self._resources: Dict[str, AsyncResource] = {}

    @property
    def base_url(self) -> str:
        return self._settings.base_url

    async def request(
        self,
        method: str,
        path: str,
        body: Optional[Mapping[str, Any]] = None,
        query: Optional[Mapping[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        extra_headers: Optional[Mapping[str, str]] = None,
    ) -> Response:
        """Call any route directly (see :meth:`RSFlowHub.request`)."""
        return await self._transport.send(method, path, body, query, RequestOptions(timeout, max_retries, extra_headers))

    def resource(self, name: str) -> AsyncResource:
        key = camel(name)
        if key not in self._resources:
            cls: Type[AsyncResource] = CLASSES[key][1] if key in CLASSES else AsyncResource
            self._resources[key] = cls(self, key)
        return self._resources[key]

    async def call(self, resource: str, method: str, *args: Any, **kwargs: Any) -> Response:
        return await self._dispatch(camel(resource), camel(method), *args, **kwargs)

    def __getattr__(self, name: str) -> AsyncResource:
        if name.startswith("_"):
            raise AttributeError(name)
        return self.resource(name)

    async def _dispatch(self, resource: str, method: str, *args: Any, **kwargs: Any) -> Response:
        http_method, template = await self._find(resource, method)
        path, params, options = bind(resource, method, template, args, kwargs)
        if http_method == "GET":
            return await self._transport.send(http_method, path, None, params, options)
        return await self._transport.send(http_method, path, params, None, options)

    async def _find(self, resource: str, method: str) -> Operation:
        found = self._operations.find(resource, method)
        if found is None and self._live_spec and not self._operations.live_loaded:
            try:
                self._operations.merge_spec((await self._transport.send("GET", "/openapi.json")).body)
            except RSFlowHubError:
                self._operations.live_loaded = True
            found = self._operations.find(resource, method)
        if found is None:
            raise self._operations.unknown(resource, method)
        return found

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self: _Self) -> _Self:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()
