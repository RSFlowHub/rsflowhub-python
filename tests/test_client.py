from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Any

import httpx
import pytest

import rsflowhub
from rsflowhub import AsyncRSFlowHub, RSFlowHub, RSFlowHubError
from rsflowhub._generated.operations import OPERATIONS
from rsflowhub._generated.resources import AiResource, AsyncKnowledgeBasesResource, KnowledgeBasesResource
from rsflowhub._operations import camel, kebab, snake
from tests.conftest import Mock, ok


def test_ai_call_posts_json_with_the_key_and_returns_result(mock: Mock) -> None:
    client = mock.client()
    mock.add(ok({"result": {"sentiment": "positive", "aspects": [{"name": "billing"}]}}, {"X-RateLimit-Limit": "60", "X-RateLimit-Remaining": "59"}))

    res = client.ai.sentiment_analysis(text="Loved it")

    assert mock.last.method == "POST"
    assert str(mock.last.url) == "https://api.test/api/v1/ai/sentiment-analysis"
    assert mock.last.headers["X-API-Key"] == "rfh_test1234_secret"
    assert mock.last.headers["Content-Type"] == "application/json"
    assert mock.last.headers["User-Agent"] == f"rsflowhub-python/{rsflowhub.__version__}"
    assert mock.last_json() == {"text": "Loved it"}

    assert res.result["sentiment"] == "positive"
    assert res["result"]["sentiment"] == "positive"
    assert res.get_path("result.aspects.0.name") == "billing"
    assert res.get_path("result.missing", "none") == "none"
    assert res.request_id == "req_123"
    assert res.meta["version"] == "v1"
    assert res.rate_limit == {"limit": 60, "remaining": 59, "reset": None}
    assert dict(res) == res.data


def test_new_ai_endpoints_work_without_an_sdk_update(mock: Mock) -> None:
    client = mock.client()
    mock.add(ok(), ok())

    client.ai.speech_to_text_v2(audio_url="https://example.com/a.mp3")
    client.call("ai", "speechToTextV2", audio_url="x")

    assert [str(r.url) for r in mock.requests] == ["https://api.test/api/v1/ai/speech-to-text-v2"] * 2


def test_camel_case_method_names_work_too(mock: Mock) -> None:
    client = mock.client()
    mock.add(ok())
    client.ai.sentimentAnalysis(text="x")
    assert mock.last.url.path == "/api/v1/ai/sentiment-analysis"


def test_path_ids_by_position_by_name_and_dict_bodies(mock: Mock) -> None:
    client = mock.client()
    mock.add(ok(), ok(), ok(), ok())

    client.knowledge_bases.ask(12, question="Refunds?")
    assert mock.last.url.path == "/api/v1/knowledge-bases/12/ask"
    assert mock.last_json() == {"question": "Refunds?"}

    client.knowledge_bases.ask(id=7, question="Shipping?")
    assert mock.last.url.path == "/api/v1/knowledge-bases/7/ask"
    assert mock.last_json() == {"question": "Shipping?"}

    client.knowledge_bases.ask(5, {"question": "From a dict"})
    assert mock.last_json() == {"question": "From a dict"}

    client.chatbots.get_conversation(3, "conv/a b")
    assert mock.last.method == "GET"
    assert mock.last.url.raw_path == b"/api/v1/chatbots/3/conversations/conv%2Fa%20b"


def test_get_params_go_to_the_query_string(mock: Mock) -> None:
    client = mock.client()
    mock.add(ok({"items": []}))

    client.account.usage(page=2, filters={"endpoint": "chat"}, active=True)

    assert mock.last.url.params["page"] == "2"
    assert mock.last.url.params["filters[endpoint]"] == "chat"
    assert mock.last.url.params["active"] == "1"
    assert mock.last.content == b""


def test_per_call_options_are_not_sent_as_params(mock: Mock) -> None:
    client = mock.client()
    mock.add(ok())

    client.knowledge_bases.get(5, timeout=5, extra_headers={"X-Trace": "t1"})

    assert str(mock.last.url) == "https://api.test/api/v1/knowledge-bases/5"
    assert mock.last.headers["X-Trace"] == "t1"


def test_missing_path_id_is_a_clear_error(mock: Mock) -> None:
    client = mock.client()
    with pytest.raises(RSFlowHubError, match='needs the "id" path parameter'):
        client.knowledge_bases.ask(question="x")


def test_unknown_non_ai_methods_are_looked_up_in_the_live_spec_once(mock: Mock) -> None:
    client = mock.client()
    mock.add(
        httpx.Response(200, json={"openapi": "3.0.3", "paths": {
            "/knowledge-bases/{id}/reindex": {"post": {"x-rsflowhub-sdk": {"resource": "knowledgeBases", "method": "reindex"}}},
            "/webhooks": {"get": {"x-rsflowhub-sdk": {"resource": "webhooks", "method": "list"}}},
        }}),
        ok({"queued": True}),
        ok({"webhooks": []}),
    )

    res = client.knowledge_bases.reindex(5)
    client.webhooks.list()

    assert res["queued"] is True
    assert [r.url.path for r in mock.requests] == ["/api/v1/openapi.json", "/api/v1/knowledge-bases/5/reindex", "/api/v1/webhooks"]


def test_unknown_method_without_live_spec_explains_the_alternatives(mock: Mock) -> None:
    client = mock.client(live_spec=False)
    with pytest.raises(AttributeError, match=r"client\.request\(\)"):
        client.knowledge_bases.does_not_exist(1)


def test_request_reaches_any_route(mock: Mock) -> None:
    client = mock.client()
    mock.add(ok({"result": {"translated": "Bonjour"}}))

    res = client.request("POST", "/ai/translation", {"text": "Hello", "target_language": "French"})

    assert res.result["translated"] == "Bonjour"


@pytest.mark.parametrize("make_file", [
    lambda tmp: tmp / "refunds.txt",
    lambda tmp: open(tmp / "refunds.txt", "rb"),
    lambda tmp: (tmp / "refunds.txt").read_bytes(),
])
def test_files_upload_as_multipart_with_bracketed_fields(mock: Mock, tmp_path: Path, make_file: Any) -> None:
    (tmp_path / "refunds.txt").write_bytes(b"Refunds within 30 days.")
    client = mock.client()
    mock.add(ok({"document": {"id": 9}}))

    file = make_file(tmp_path)
    client.knowledge_bases.create_document(4, file=file, metadata={"source": "faq"})
    if isinstance(file, io.IOBase):
        file.close()

    body = mock.last.content
    assert mock.last.headers["Content-Type"].startswith("multipart/form-data")
    assert b'name="file"; filename="' in body
    assert b"Refunds within 30 days." in body
    assert b'name="metadata[source]"' in body


def test_resources_are_typed_and_cached(mock: Mock) -> None:
    client = mock.client()
    assert isinstance(client.ai, AiResource)
    assert isinstance(client.knowledge_bases, KnowledgeBasesResource)
    assert client.ai is client.ai
    assert client.resource("knowledgeBases") is client.knowledge_bases


def test_env_key_and_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RSFLOWHUB_API_KEY", "rfh_fromenv_x")
    monkeypatch.setenv("RSFLOWHUB_BASE_URL", "https://staging.test/api/v1/")
    assert RSFlowHub().base_url == "https://staging.test/api/v1"


def test_missing_key_fails_fast(no_env: Any) -> None:
    no_env()
    with pytest.raises(RSFlowHubError, match="No RSFlowHub API key"):
        RSFlowHub()


def test_context_manager_closes_its_own_http_client() -> None:
    with RSFlowHub("rfh_x") as client:
        http = client._http
    assert http.is_closed


def test_name_conversions() -> None:
    assert camel("sentiment_analysis") == "sentimentAnalysis"
    assert camel("sentimentAnalysis") == "sentimentAnalysis"
    assert snake("listDocuments") == "list_documents"
    assert kebab("piiRedaction") == "pii-redaction"
    assert kebab("textToSpeech2") == "text-to-speech2"
    assert kebab(camel("ask_a_question")) == "ask-a-question"
    assert snake(camel("not_a_real_method")) == "not_a_real_method"
    assert kebab("getHTMLPage") == "get-html-page"


def test_one_letter_words_reach_the_right_slug(mock: Mock) -> None:
    client = mock.client()
    mock.add(ok())
    client.ai.ask_a_question(text="x")
    assert mock.last.url.path == "/api/v1/ai/ask-a-question"


def test_bundled_map() -> None:
    assert OPERATIONS["ai"]["sentimentAnalysis"] == ("POST", "/ai/sentiment-analysis")
    assert OPERATIONS["knowledgeBases"]["ask"] == ("POST", "/knowledge-bases/{id}/ask")


def test_version_matches_package_metadata() -> None:
    from importlib.metadata import version

    assert version("rsflowhub") == rsflowhub.__version__


# Async ---------------------------------------------------------------------------

def test_async_client_works_the_same(mock: Mock) -> None:
    async def run() -> None:
        async with mock.async_client() as client:
            mock.add(ok({"result": {"sentiment": "positive"}}), ok(), ok())
            res = await client.ai.sentiment_analysis(text="Loved it")
            assert res.result["sentiment"] == "positive"

            assert isinstance(client.knowledge_bases, AsyncKnowledgeBasesResource)
            await client.knowledge_bases.ask(12, question="Refunds?")
            assert mock.last.url.path == "/api/v1/knowledge-bases/12/ask"

            await client.call("ai", "brand_new", x=1)
            assert mock.last.url.path == "/api/v1/ai/brand-new"

    asyncio.run(run())


def test_async_client_live_spec(mock: Mock) -> None:
    async def run() -> None:
        client: AsyncRSFlowHub = mock.async_client()
        mock.add(
            httpx.Response(200, json={"paths": {"/webhooks": {"get": {"x-rsflowhub-sdk": {"resource": "webhooks", "method": "list"}}}}}),
            ok({"webhooks": []}),
        )
        await client.webhooks.list()
        assert [r.url.path for r in mock.requests] == ["/api/v1/openapi.json", "/api/v1/webhooks"]
        await client.aclose()

    asyncio.run(run())
