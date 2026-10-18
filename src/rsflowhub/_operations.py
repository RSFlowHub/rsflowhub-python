from __future__ import annotations

import re
from typing import Any, Dict, Mapping, Optional, Tuple

from ._generated.operations import OPERATIONS

Operation = Tuple[str, str]
OperationMap = Dict[str, Dict[str, Operation]]


class Operations:
    """Knows which HTTP call each SDK method makes.

    1. The bundled map (``_generated/operations.py``), generated from the live
       OpenAPI document by ``scripts/generate.py``.
    2. Not there, AI resource: ``POST /ai/{method-in-kebab-case}``. Every flat AI
       endpoint works this way, including ones released after this SDK version.
    3. Not there, other resource: the client reads ``GET /openapi.json`` once
       (``x-rsflowhub-sdk``) and looks again, so new routes work too.
    """

    def __init__(self) -> None:
        self.map: OperationMap = {resource: dict(methods) for resource, methods in OPERATIONS.items()}
        self.live_loaded = False

    def find(self, resource: str, method: str) -> Optional[Operation]:
        found = self.map.get(resource, {}).get(method)
        if found:
            return found
        if resource == "ai":
            return ("POST", f"/ai/{kebab(method)}")
        return None

    def merge_spec(self, spec: Mapping[str, Any]) -> None:
        self.live_loaded = True
        for resource, methods in from_spec(spec).items():
            self.map[resource] = {**methods, **self.map.get(resource, {})}

    def unknown(self, resource: str, method: str) -> AttributeError:
        known = sorted(self.map.get(resource, {}))
        hint = f"Known methods: {', '.join(snake(m) for m in known)}. " if known else "Unknown resource. "
        return AttributeError(
            f"Unknown RSFlowHub method {snake(resource)}.{snake(method)}(). {hint}Use client.request() for any other route."
        )


def from_spec(spec: Mapping[str, Any]) -> OperationMap:
    """Read x-rsflowhub-sdk names out of an OpenAPI document."""
    result: OperationMap = {}
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return result
    for path, operations in paths.items():
        if not isinstance(operations, dict):
            continue
        for http_method, op in operations.items():
            sdk = op.get("x-rsflowhub-sdk") if isinstance(op, dict) else None
            if isinstance(sdk, dict) and isinstance(sdk.get("resource"), str) and isinstance(sdk.get("method"), str):
                result.setdefault(sdk["resource"], {})[sdk["method"]] = (http_method.upper(), str(path))
    return result


def camel(name: str) -> str:
    """``sentiment_analysis`` -> ``sentimentAnalysis`` (camelCase input is kept)."""
    first, *rest = name.split("_")
    return first + "".join(part[:1].upper() + part[1:] for part in rest)


def _split(name: str, sep: str) -> str:
    # Two passes so one-letter words and acronyms survive:
    # askAQuestion -> ask-a-question, getHTMLPage -> get-html-page.
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1" + sep + r"\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1" + sep + r"\2", name).lower()


def snake(name: str) -> str:
    """``sentimentAnalysis`` -> ``sentiment_analysis``."""
    return _split(name, "_")


def kebab(name: str) -> str:
    """``sentimentAnalysis`` -> ``sentiment-analysis``."""
    return _split(name, "-")
