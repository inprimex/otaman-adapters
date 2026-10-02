"""Tests for the LiteLLM wire-call adapter (llm-router-backend 1.2).

Uses unittest.mock.patch on urllib.request.urlopen — no live network calls.
The local targets the task names (Ollama, vLLM) are exercised as resolved
BackendTargets against their real endpoint shapes.
"""

from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from otaman_adapters.litellm import (
    BackendTarget,
    ChatCompletion,
    LiteLLMAdapter,
    LiteLLMError,
    Route,
    _endpoint,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MESSAGES = [{"role": "user", "content": "ping"}]

OPENAI_RESPONSE = {
    "id": "chatcmpl-1",
    "model": "llama3.1:8b",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "pong"}}],
    "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
}


def _make_response(data: dict) -> MagicMock:
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cm)
    cm.__exit__ = MagicMock(return_value=False)
    cm.read = MagicMock(return_value=json.dumps(data).encode())
    return cm


def _ollama_target(model: str | None = "llama3.1:8b") -> BackendTarget:
    return BackendTarget(
        family="ollama", model=model, base_url="http://localhost:11434", local=True
    )


def _vllm_target() -> BackendTarget:
    return BackendTarget(
        family="vllm",
        model="mistralai/Mistral-7B-Instruct-v0.3",
        base_url="http://vllm.internal:8000/v1",
        local=True,
    )


def _proxy_target() -> BackendTarget:
    return BackendTarget(
        family="openai", model="gpt-4o-mini", base_url="http://litellm:4000", local=False
    )


# ---------------------------------------------------------------------------
# Endpoint normalization
# ---------------------------------------------------------------------------


class TestEndpoint:
    def test_root_base_gets_v1(self):
        assert _endpoint("http://localhost:11434") == "http://localhost:11434/v1/chat/completions"

    def test_v1_base_not_doubled(self):
        assert _endpoint("http://host:8000/v1") == "http://host:8000/v1/chat/completions"

    def test_trailing_slash_stripped(self):
        assert _endpoint("http://litellm:4000/") == "http://litellm:4000/v1/chat/completions"


# ---------------------------------------------------------------------------
# Construction rules
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_native_target_refused(self):
        native = BackendTarget(family="anthropic", model=None, base_url=None, local=False)
        with pytest.raises(ValueError, match="DefaultBackend path"):
            LiteLLMAdapter(native)

    def test_from_backend_resolves_route(self):
        class StubBackend:
            def resolve(self, route):
                assert route == Route(family="ollama", model="llama3.1:8b", local=True)
                return _ollama_target()

        adapter = LiteLLMAdapter.from_backend(
            StubBackend(), Route(family="ollama", model="llama3.1:8b", local=True)
        )
        assert adapter.target == _ollama_target()


# ---------------------------------------------------------------------------
# The wire call — local targets (Ollama, vLLM) and the proxy
# ---------------------------------------------------------------------------


class TestCompleteOllama:
    """A local Ollama target: root base_url, no auth, local=True."""

    @patch("otaman_adapters.litellm.urllib.request.urlopen")
    def test_url_payload_and_result(self, mock_urlopen):
        mock_urlopen.return_value = _make_response(OPENAI_RESPONSE)
        result = LiteLLMAdapter(_ollama_target()).complete(MESSAGES)

        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://localhost:11434/v1/chat/completions"
        body = json.loads(req.data)
        assert body["model"] == "llama3.1:8b"
        assert body["messages"] == MESSAGES
        assert not req.has_header("Authorization")

        assert isinstance(result, ChatCompletion)
        assert result.text == "pong"
        assert result.model == "llama3.1:8b"
        assert (result.prompt_tokens, result.completion_tokens, result.total_tokens) == (3, 2, 5)
        assert result.latency_ms >= 0.0

    @patch("otaman_adapters.litellm.urllib.request.urlopen")
    def test_family_only_route_falls_back_to_family_model(self, mock_urlopen):
        mock_urlopen.return_value = _make_response(OPENAI_RESPONSE)
        LiteLLMAdapter(_ollama_target(model=None)).complete(MESSAGES)
        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["model"] == "ollama"


class TestCompleteVllm:
    """A local vLLM target: /v1 base_url, api-key auth, local=True."""

    @patch("otaman_adapters.litellm.urllib.request.urlopen")
    def test_v1_base_and_bearer_auth(self, mock_urlopen):
        mock_urlopen.return_value = _make_response(OPENAI_RESPONSE)
        adapter = LiteLLMAdapter(_vllm_target(), api_key="vllm-key")
        result = adapter.complete(MESSAGES, temperature=0.0, max_tokens=64)

        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://vllm.internal:8000/v1/chat/completions"
        assert req.get_header("Authorization") == "Bearer vllm-key"
        body = json.loads(req.data)
        assert body["model"] == "mistralai/Mistral-7B-Instruct-v0.3"
        assert body["temperature"] == 0.0
        assert body["max_tokens"] == 64
        assert result.telemetry()["route"]["local"] is True


class TestCompleteProxy:
    """The LiteLLM proxy itself: cloud family through one OpenAI-compatible door."""

    @patch("otaman_adapters.litellm.urllib.request.urlopen")
    def test_explicit_model_overrides_target(self, mock_urlopen):
        mock_urlopen.return_value = _make_response(OPENAI_RESPONSE)
        LiteLLMAdapter(_proxy_target(), api_key="sk-master").complete(
            MESSAGES, model="claude-sonnet-5"
        )
        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["model"] == "claude-sonnet-5"

    @patch("otaman_adapters.litellm.urllib.request.urlopen")
    def test_extra_fields_merge_but_cannot_override(self, mock_urlopen):
        mock_urlopen.return_value = _make_response(OPENAI_RESPONSE)
        LiteLLMAdapter(_proxy_target()).complete(
            MESSAGES, extra={"stream": False, "model": "evil-override", "messages": []}
        )
        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["stream"] is False
        assert body["model"] == "gpt-4o-mini"
        assert body["messages"] == MESSAGES

    @patch("otaman_adapters.litellm.urllib.request.urlopen")
    def test_http_error_raises_litellm_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="http://litellm:4000/v1/chat/completions",
            code=401,
            msg="unauthorized",
            hdrs=None,  # type: ignore[arg-type]
            fp=io.BytesIO(b'{"error": "invalid key"}'),
        )
        with pytest.raises(LiteLLMError) as excinfo:
            LiteLLMAdapter(_proxy_target()).complete(MESSAGES)
        assert excinfo.value.status == 401
        assert "invalid key" in excinfo.value.body


# ---------------------------------------------------------------------------
# Telemetry — routes must be distinguishable per call
# ---------------------------------------------------------------------------


class TestTelemetry:
    @patch("otaman_adapters.litellm.urllib.request.urlopen")
    def test_two_families_distinguishable(self, mock_urlopen):
        mock_urlopen.return_value = _make_response(OPENAI_RESPONSE)
        local = LiteLLMAdapter(_ollama_target()).complete(MESSAGES).telemetry()
        mock_urlopen.return_value = _make_response({**OPENAI_RESPONSE, "model": "gpt-4o-mini"})
        cloud = LiteLLMAdapter(_proxy_target()).complete(MESSAGES).telemetry()

        assert local["route"]["family"] == "ollama"
        assert cloud["route"]["family"] == "openai"
        assert local["route"]["local"] is True
        assert cloud["route"]["local"] is False
        assert local["route"]["base_url"] != cloud["route"]["base_url"]
        for record in (local, cloud):
            assert record["usage"]["total_tokens"] == 5
            assert "latency_ms" in record

    @patch("otaman_adapters.litellm.urllib.request.urlopen")
    def test_missing_usage_block_yields_zeros(self, mock_urlopen):
        trimmed = {k: v for k, v in OPENAI_RESPONSE.items() if k != "usage"}
        mock_urlopen.return_value = _make_response(trimmed)
        result = LiteLLMAdapter(_ollama_target()).complete(MESSAGES)
        assert (result.prompt_tokens, result.completion_tokens, result.total_tokens) == (0, 0, 0)
