"""Direct Ollama provider protocol tests using mocked HTTP responses."""

from __future__ import annotations

import json
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from ai.providers import ollama
from ai.providers.ollama import OllamaProvider, OllamaProviderError


class _HttpResponse:
    def __init__(self, payload: str):
        self.payload = payload.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return self.payload


def test_valid_ollama_response_and_request_configuration(monkeypatch):
    response = {
        "message": {
            "content": '{"status":"AVERAGE","summary":"OK","evidence":["e"],"caveat":"c"}',
            "thinking": "this must never be exposed",
        }
    }
    calls = {}

    def fake_urlopen(request, timeout):
        calls["request"] = request
        calls["timeout"] = timeout
        return _HttpResponse(json.dumps(response))

    monkeypatch.setattr(ollama, "urlopen", fake_urlopen)
    provider = OllamaProvider(
        base_url="http://localhost:11434/",
        model="qwen3:4b",
        timeout_seconds=17,
    )
    content = provider.generate("system", "user")
    body = json.loads(calls["request"].data)

    assert content == response["message"]["content"]
    assert "thinking" not in content
    assert calls["request"].full_url == "http://localhost:11434/api/chat"
    assert calls["timeout"] == 17
    assert body["model"] == "qwen3:4b"
    assert body["stream"] is False
    assert body["format"] == "json"
    assert body["think"] is False


def test_tagged_thinking_block_is_removed(monkeypatch):
    payload = {
        "message": {
            "content": '<think>private chain of thought</think>{"status":"AVERAGE"}'
        }
    }
    monkeypatch.setattr(
        ollama, "urlopen", lambda request, timeout: _HttpResponse(json.dumps(payload))
    )
    content = OllamaProvider().generate("system", "user")
    assert content == '{"status":"AVERAGE"}'
    assert "private chain" not in content


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (URLError(ConnectionRefusedError("refused")), "connect"),
        (TimeoutError("timed out"), "timed out"),
    ],
)
def test_connection_and_timeout_failures_are_reported(monkeypatch, failure, message):
    def raise_failure(request, timeout):
        raise failure

    monkeypatch.setattr(ollama, "urlopen", raise_failure)
    with pytest.raises(OllamaProviderError, match=message):
        OllamaProvider().generate("system", "user")


def test_http_error_is_reported_as_provider_error(monkeypatch):
    def raise_http_error(request, timeout):
        raise HTTPError(
            url=request.full_url,
            code=500,
            msg="server error",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(ollama, "urlopen", raise_http_error)
    with pytest.raises(OllamaProviderError, match="HTTP 500"):
        OllamaProvider().generate("system", "user")


def test_missing_model_http_error_is_reported(monkeypatch):
    def raise_http_error(request, timeout):
        raise HTTPError(
            url=request.full_url,
            code=404,
            msg="not found",
            hdrs=None,
            fp=BytesIO(b'{"error":"model not found"}'),
        )

    monkeypatch.setattr(ollama, "urlopen", raise_http_error)
    with pytest.raises(OllamaProviderError, match="model.*unavailable"):
        OllamaProvider().generate("system", "user")


def test_non_utf8_response_is_reported(monkeypatch):
    class BinaryResponse(_HttpResponse):
        def read(self):
            return b"\xff\xfe"

    monkeypatch.setattr(
        ollama, "urlopen", lambda request, timeout: BinaryResponse("")
    )
    with pytest.raises(OllamaProviderError, match="UTF-8"):
        OllamaProvider().generate("system", "user")


@pytest.mark.parametrize(
    "payload",
    [
        "not JSON",
        "{}",
        '{"message":{"content":""}}',
        '{"message":{"content":"<think>only thoughts</think>"}}',
    ],
)
def test_malformed_or_incomplete_provider_response_is_rejected(monkeypatch, payload):
    monkeypatch.setattr(
        ollama, "urlopen", lambda request, timeout: _HttpResponse(payload)
    )
    with pytest.raises(OllamaProviderError):
        OllamaProvider().generate("system", "user")
