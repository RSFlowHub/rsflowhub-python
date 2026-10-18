# RSFlowHub Python SDK

[![PyPI](https://img.shields.io/pypi/v/rsflowhub.svg)](https://pypi.org/project/rsflowhub/)
[![Python](https://img.shields.io/pypi/pyversions/rsflowhub.svg)](https://pypi.org/project/rsflowhub/)
[![Tests](https://github.com/RSFlowHub/rsflowhub-python/actions/workflows/tests.yml/badge.svg)](https://github.com/RSFlowHub/rsflowhub-python/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

The official Python library for the [RSFlowHub AI API](https://rsflowhub.com). Add sentiment analysis, translation, AI chat, PII redaction, spam and comment moderation, review and support-ticket AI, knowledge-base search (RAG) and chatbots to **Django, FastAPI, Flask, Celery jobs, scripts and notebooks** with one API key.

- **Never out of date.** Methods are not hard-coded. A new RSFlowHub API works the day it ships: `client.ai.new_endpoint_name(...)`. No SDK upgrade needed.
- **Sync and async.** `RSFlowHub` and `AsyncRSFlowHub` share one API, built on [httpx](https://www.python-httpx.org/).
- **Typed.** Every method has typed keyword arguments (with `Literal` choices and limits in the docstring), generated from the [RSFlowHub OpenAPI spec](https://rsflowhub.com/api/v1/openapi.json). Works with mypy, Pyright and your IDE.
- **Typed errors.** `ValidationError`, `InsufficientCreditsError`, `RateLimitError` and more, each with the API's error code, message and request id.
- **Retries built in.** 429 and temporary 5xx answers are retried with backoff, respecting `Retry-After`. Those answers never charge credits.

Python 3.9+. Other languages: [Node.js / TypeScript](https://github.com/RSFlowHub/rsflowhub-node) · [PHP](https://github.com/RSFlowHub/rsflowhub-php) · [Examples](https://github.com/RSFlowHub/rsflowhub-examples)

## Install

```bash
pip install rsflowhub
```

`poetry add rsflowhub` · `uv add rsflowhub`

Get an API key from the [RSFlowHub dashboard](https://rsflowhub.com/dashboard) (free credits included).

## Quick start

```python
from rsflowhub import RSFlowHub

client = RSFlowHub()  # reads RSFLOWHUB_API_KEY; or RSFlowHub(api_key="rfh_...")

res = client.ai.sentiment_analysis(text="Setup took two minutes and support answered right away.")

print(res.result["sentiment"])  # "positive"
print(res.request_id)           # "req_..." quote it when you contact support
```

Every API answer is the envelope `{success, request_id, data, meta}`; AI endpoints put their output in `data.result`. A call returns a read-only `rsflowhub.Response`:

| | |
| --- | --- |
| `res.result` | the AI output (`data.result`), or `data` when there is none |
| `res.data`, `res["key"]`, `dict(res)` | everything under `data` |
| `res.get_path("result.aspects.0.name")` | dot-path read with an optional default |
| `res.request_id`, `res.meta`, `res.status_code`, `res.headers` | envelope and HTTP details |
| `res.rate_limit` | `{"limit", "remaining", "reset"}` from the `X-RateLimit-*` headers |

## Async (FastAPI, aiohttp, Django async views)

```python
from fastapi import FastAPI
from rsflowhub import AsyncRSFlowHub

app = FastAPI()
client = AsyncRSFlowHub()

@app.post("/moderate")
async def moderate(comment: str):
    res = await client.ai.comment_moderate(comment=comment)
    return res.result
```

`async with AsyncRSFlowHub() as client:` closes connections for you; in a long-running app create one client and reuse it.

## Calling any API

The method name is the endpoint slug in snake_case (camelCase works too):

| API | Call |
| --- | --- |
| `POST /ai/sentiment-analysis` | `client.ai.sentiment_analysis(text=...)` |
| `POST /ai/translation` | `client.ai.translation(text="Hello", target_language="French")` |
| `POST /ai/chat` | `client.ai.chat(message="Hi!")` |
| `POST /ai/pii-redaction` | `client.ai.pii_redaction(text="Call me on 555-0100")` |
| `POST /ai/ticket-analyze` | `client.ai.ticket_analyze(ticket="My order never arrived")` |
| `POST /ai/any-new-api` | `client.ai.any_new_api(...)` (works without an SDK update) |

All methods with their parameters: [docs/ENDPOINTS.md](docs/ENDPOINTS.md). API docs: [rsflowhub.com/docs](https://rsflowhub.com/docs).

The body can be keyword arguments or one dict: `client.ai.chat({"message": "Hi!"})`.

### Knowledge bases (RAG) and chatbots

Ids in the URL come first:

```python
from pathlib import Path

kb = client.knowledge_bases.create(name="Help center")
kb_id = kb.get_path("knowledge_base.id")

client.knowledge_bases.create_document(kb_id, file=Path("refund-policy.pdf"))

answer = client.knowledge_bases.ask(kb_id, question="Can I get a refund after 30 days?")

reply = client.chatbots.send_message(chatbot_id, message="Where is my order?")
```

A `pathlib.Path`, `bytes` or open binary file turns the request into a file upload.

### Any route

```python
usage = client.request("GET", "/account/usage", query={"page": 2})
```

## Errors

```python
import rsflowhub

try:
    client.ai.text_summarize(text=article)
except rsflowhub.ValidationError as e:
    print(e.errors)                                   # {"text": ["The text field is required."]}
except rsflowhub.InsufficientCreditsError as e:
    print(e.required_credits, e.available_credits)
except rsflowhub.RateLimitError as e:
    print(e.retry_after)                              # already retried max_retries times
except rsflowhub.APIError as e:
    print(e.status_code, e.code, e.message, e.request_id)
except rsflowhub.APIConnectionError:
    print("network problem or timeout")
```

| Error | When | Error codes |
| --- | --- | --- |
| `AuthenticationError` | 401 | `API_KEY_MISSING`, `INVALID_API_KEY` |
| `InsufficientCreditsError` | 402 | `INSUFFICIENT_CREDITS` |
| `PermissionDeniedError` | 403 | `SPENDING_LIMIT_REACHED`, `USER_INACTIVE` |
| `NotFoundError` | 404 | `ENDPOINT_NOT_FOUND` |
| `ValidationError` | 422 | `VALIDATION_ERROR` |
| `RateLimitError` | 429 | `RATE_LIMIT_EXCEEDED` |
| `InternalServerError` | 500 | `INTERNAL_SERVER_ERROR` |
| `ServiceUnavailableError` | 502 / 503 | `PROVIDER_UNAVAILABLE`, `AI_PROVIDER_ERROR` |
| `APIConnectionError` / `APITimeoutError` | no answer / too slow | |

All of them extend `rsflowhub.RSFlowHubError`.

## Options

```python
client = RSFlowHub(
    api_key="rfh_...",                       # default: RSFLOWHUB_API_KEY
    base_url="https://rsflowhub.com/api/v1", # default: RSFLOWHUB_BASE_URL
    timeout=60.0,                            # seconds
    max_retries=2,                           # for 429, 502, 503, 504 and network errors
    default_headers={},                      # extra headers on every request
    http_client=None,                        # your own httpx.Client (proxies, event hooks, tests)
    live_spec=True,                          # look up unknown non-AI methods in the live OpenAPI spec
)

# per call
client.ai.chat(message="Hi", timeout=10, max_retries=0, extra_headers={"X-Trace": "abc"})
```

## Django, Flask and Celery

Create the client once (module level or app startup) and reuse it; it is thread-safe. See [examples/](examples): [Django view](examples/django_view.py), [Flask](examples/flask_app.py), [FastAPI](examples/fastapi_app.py), [script](examples/quickstart.py).

## How it stays up to date

RSFlowHub publishes a machine-readable [OpenAPI document](https://rsflowhub.com/api/v1/openapi.json) generated from the API's own routes and validation rules. This SDK uses it in three ways:

1. **AI endpoints** are called by name, so new ones work at once.
2. **Other new routes** (for example a new knowledge-base action) are looked up in the live document the first time you call them.
3. **Types and docs** (`src/rsflowhub/_generated`, `docs/ENDPOINTS.md`) are regenerated every week by a GitHub workflow that opens a pull request when the API changed.

To regenerate by hand: `python scripts/generate.py [url-or-file]`.

## Contributing

Issues and pull requests are welcome: `pip install -e ".[dev]"`, then `pytest` and `mypy`. Do not edit generated files (`src/rsflowhub/_generated`, `docs/ENDPOINTS.md`); change `scripts/generate.py` instead.

## License

MIT. See [LICENSE](LICENSE).
