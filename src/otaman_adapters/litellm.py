"""LiteLLM wire-call adapter for the Otaman LLM router (llm-router-backend 1.2).

otaman-core's ``ModelBackend`` seam resolves WHERE a routed call goes (a
:class:`BackendTarget`); the bridge decides WHETHER it may go there (the
sensitivity guard, 1.3). This module is the remaining piece: the WIRE CALL —
an OpenAI-compatible ``/chat/completions`` client that speaks to whatever the
target names, which per the research base is a LiteLLM proxy (100+ model
targets) or a local OpenAI-compatible server (Ollama, vLLM) directly.

All HTTP is stdlib ``urllib.request`` (repo convention, no external
dependencies — the ``litellm`` PyPI package is deliberately NOT imported; the
proxy is a deployment, not a library dependency).

The adapter never makes routing or guard decisions. It refuses a native
target (``base_url is None`` — that is the DefaultBackend's path, which does
not go through this adapter at all), and it reports the route it was given in
:meth:`ChatCompletion.telemetry` so routed calls are distinguishable per call
(the family-diversity evidence JTBD-59's policies consume).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

try:
    from otaman_core.llm_router import BackendTarget, Route
except ImportError:
    # otaman-core not installed in this environment: minimal stand-ins with
    # the same field shapes, replaced at runtime when the real package is
    # present (same pattern as easy8.py).

    @dataclass(frozen=True)
    class Route:  # type: ignore[no-redef]
        family: str
        model: str | None = None
        local: bool = False

    @dataclass(frozen=True)
    class BackendTarget:  # type: ignore[no-redef]
        family: str
        model: str | None
        base_url: str | None
        local: bool


class LiteLLMError(Exception):
    """Raised when the OpenAI-compatible endpoint returns a non-2xx response."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"LLM endpoint HTTP {status}: {body}")
        self.status = status
        self.body = body


@dataclass(frozen=True)
class ChatCompletion:
    """One completed routed call: the text, the usage, and the route it rode.

    ``model`` is the model id the server reports it served (which may differ
    from the requested one when the proxy aliases). Usage token counts are 0
    when the server omits the ``usage`` block (some local servers do under
    streaming configs).
    """

    text: str
    model: str
    target: BackendTarget
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    raw: dict = field(default_factory=dict)

    def telemetry(self) -> dict[str, Any]:
        """The per-call route + usage record for the existing usage telemetry.

        Carries the full route (family / model / base_url / local) so cost and
        latency per family are distinguishable per call — the observability
        clause of the llm-router-backend delta.
        """
        return {
            "route": {
                "family": self.target.family,
                "model": self.model,
                "base_url": self.target.base_url,
                "local": self.target.local,
            },
            "usage": {
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": self.total_tokens,
            },
            "latency_ms": self.latency_ms,
        }


def _endpoint(base_url: str) -> str:
    """The ``/v1/chat/completions`` URL for *base_url*.

    Accepts a base with or without the ``/v1`` suffix so one config key covers
    all three deployment shapes: a LiteLLM proxy root (``http://proxy:4000``),
    an Ollama root (``http://localhost:11434``), or a vLLM/OpenAI-style base
    that already ends in ``/v1``.
    """
    base = base_url.rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return f"{base}/chat/completions"


class LiteLLMAdapter:
    """OpenAI-compatible chat-completions client for one resolved :class:`BackendTarget`.

    The target comes from core's ``ModelBackend.resolve`` (use
    :meth:`from_backend` for that composition). ``api_key`` becomes a Bearer
    token when set — the LiteLLM proxy master key or a vLLM ``--api-key``;
    Ollama needs none.
    """

    def __init__(
        self,
        target: BackendTarget,
        *,
        api_key: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        if target.base_url is None:
            raise ValueError(
                "LiteLLMAdapter needs a proxy/local target (base_url set); a native "
                "target (base_url=None) is the DefaultBackend path and never goes "
                "through this adapter"
            )
        self._target = target
        self._api_key = api_key
        self._timeout = timeout

    @classmethod
    def from_backend(
        cls,
        backend: Any,
        route: Route | None,
        *,
        api_key: str | None = None,
        timeout: float = 120.0,
    ) -> LiteLLMAdapter:
        """Resolve *route* through *backend* (core's seam) and wrap the target."""
        return cls(backend.resolve(route), api_key=api_key, timeout=timeout)

    @property
    def target(self) -> BackendTarget:
        return self._target

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> ChatCompletion:
        """POST *messages* to the target's ``/v1/chat/completions`` endpoint.

        Model precedence: explicit *model* argument, then the target's model,
        then the target's family as a last resort (a family-only route lets
        the proxy pick its configured default for that family). *extra* merges
        additional OpenAI-compatible body fields verbatim (it cannot override
        ``model``/``messages``).
        """
        payload: dict[str, Any] = dict(extra or {})
        payload["model"] = model or self._target.model or self._target.family
        payload["messages"] = messages
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        req = urllib.request.Request(
            _endpoint(self._target.base_url),  # type: ignore[arg-type]  # checked in __init__
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise LiteLLMError(exc.code, body) from exc
        latency_ms = (time.monotonic() - started) * 1000.0

        choices = raw.get("choices") or []
        message = choices[0].get("message", {}) if choices else {}
        usage = raw.get("usage") or {}
        return ChatCompletion(
            text=str(message.get("content") or ""),
            model=str(raw.get("model") or payload["model"]),
            target=self._target,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            total_tokens=int(usage.get("total_tokens") or 0),
            latency_ms=latency_ms,
            raw=raw,
        )


__all__ = [
    "ChatCompletion",
    "LiteLLMAdapter",
    "LiteLLMError",
]
