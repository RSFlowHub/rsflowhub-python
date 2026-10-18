from __future__ import annotations

import functools
import re
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Tuple, Union
from urllib.parse import quote

from ._errors import RSFlowHubError
from ._operations import camel, snake
from ._transport import RequestOptions

if TYPE_CHECKING:
    from ._client import AsyncRSFlowHub, RSFlowHub

Id = Union[int, str]
_OPTION_KEYS = ("timeout", "max_retries", "extra_headers")


class Resource:
    """A group of API methods, e.g. ``client.ai`` or ``client.knowledge_bases``.

    Call any method by name (snake_case or camelCase). Path ids come first, then
    the body as keyword arguments (or one dict); GET calls send them as the query::

        client.ai.sentiment_analysis(text="Great product!")
        client.knowledge_bases.ask(12, question="How do refunds work?")
        client.chatbots.get_conversation(3, "conv_abc")

    Per-call options: ``timeout=``, ``max_retries=``, ``extra_headers=``.
    """

    def __init__(self, client: "RSFlowHub", name: str) -> None:
        self._client = client
        self._name = name

    def __getattr__(self, method: str) -> Any:
        if method.startswith("_"):
            raise AttributeError(method)
        return functools.partial(self._client._dispatch, self._name, camel(method))

    def __repr__(self) -> str:
        return f"<rsflowhub resource {snake(self._name)}>"


class AsyncResource:
    """Async twin of :class:`Resource`: every method returns an awaitable."""

    def __init__(self, client: "AsyncRSFlowHub", name: str) -> None:
        self._client = client
        self._name = name

    def __getattr__(self, method: str) -> Any:
        if method.startswith("_"):
            raise AttributeError(method)
        return functools.partial(self._client._dispatch, self._name, camel(method))

    def __repr__(self) -> str:
        return f"<rsflowhub async resource {snake(self._name)}>"


def bind(
    resource: str, method: str, template: str, args: Tuple[Any, ...], kwargs: Dict[str, Any]
) -> Tuple[str, Dict[str, Any], RequestOptions]:
    """Fill path ids and split the arguments into (path, params, options)."""
    options = RequestOptions(**{k: kwargs.pop(k) for k in _OPTION_KEYS if k in kwargs})

    ids: List[Any] = []
    params: Dict[str, Any] = {}
    for arg in args:
        if isinstance(arg, Mapping):
            params.update(arg)
        elif params:
            raise TypeError(f"{snake(resource)}.{snake(method)}(): ids must come before the body.")
        else:
            ids.append(arg)
    params.update(kwargs)

    def fill(match: "re.Match[str]") -> str:
        name = match.group(1)
        if ids:
            value = ids.pop(0)
        elif name in params:
            value = params.pop(name)
        else:
            raise RSFlowHubError(f'{snake(resource)}.{snake(method)}() needs the "{name}" path parameter.')
        if isinstance(value, bool) or not isinstance(value, (int, str)) or str(value) == "":
            raise RSFlowHubError(f'{snake(resource)}.{snake(method)}(): "{name}" must be a non-empty id.')
        return quote(str(value), safe="")

    path = re.sub(r"\{([^}]+)\}", fill, template)
    if ids:
        raise RSFlowHubError(f"{snake(resource)}.{snake(method)}() got more ids than its path {template} takes.")
    return path, params, options
