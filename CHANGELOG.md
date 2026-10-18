# Changelog

## 1.0.0

- First release: dynamic sync (`RSFlowHub`) and async (`AsyncRSFlowHub`) clients for every RSFlowHub API (`client.ai.<slug>`), knowledge bases, chatbots, FAQ collections and account.
- Typed method stubs generated from the OpenAPI spec (mypy / Pyright / IDE autocomplete).
- Typed errors from the API error code; retries with backoff for 429/502/503/504 and network errors; timeouts.
- Live OpenAPI lookup for methods newer than the SDK; file uploads from `Path`, `bytes` or open files.
