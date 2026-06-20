"""Tests for the Ollama HTTP backend.

We mock urlopen so the suite never touches the network. The integration
verification (`workhorse:11434` actually serving a code model) is the
user-side step after this PR merges.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch
from urllib.error import URLError

import pytest

from codereview.backend import BackendError, OllamaBackend


class _FakeResponse:
    """Minimal stand-in for what urlopen() returns inside a `with` block."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_: object) -> bool:
        return False


def _fake_urlopen_factory(payload: dict[str, Any], captured: dict[str, Any]):
    def fake(req, timeout=None):  # type: ignore[no-untyped-def]
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    return fake


def test_ollama_sends_expected_request_shape() -> None:
    captured: dict[str, Any] = {}
    fake = _fake_urlopen_factory({"response": "hello"}, captured)
    backend = OllamaBackend(
        base_url="http://workhorse:11434",
        model="qwen2.5-coder",
        timeout=30.0,
        temperature=0.2,
    )

    with patch("codereview.backend.urlopen", fake):
        out = backend.generate(system="you are a reviewer", user="review this")

    assert out == "hello"
    assert captured["url"] == "http://workhorse:11434/api/generate"
    assert captured["method"] == "POST"
    assert captured["headers"]["Content-type"] == "application/json"
    assert captured["timeout"] == 30.0
    body = captured["body"]
    assert body["model"] == "qwen2.5-coder"
    assert body["system"] == "you are a reviewer"
    assert body["prompt"] == "review this"
    assert body["stream"] is False
    assert body["options"]["temperature"] == 0.2


def test_ollama_default_options_omit_num_thread() -> None:
    captured: dict[str, Any] = {}
    fake = _fake_urlopen_factory({"response": "ok"}, captured)
    backend = OllamaBackend()  # num_thread defaults to None
    with patch("codereview.backend.urlopen", fake):
        backend.generate(system="s", user="u")
    options = captured["body"]["options"]
    assert "temperature" in options
    assert "num_thread" not in options


def test_ollama_num_thread_is_passed_through_options_when_set() -> None:
    captured: dict[str, Any] = {}
    fake = _fake_urlopen_factory({"response": "ok"}, captured)
    backend = OllamaBackend(num_thread=8)
    with patch("codereview.backend.urlopen", fake):
        backend.generate(system="s", user="u")
    assert captured["body"]["options"]["num_thread"] == 8


def test_ollama_trailing_slash_in_base_url_is_normalized() -> None:
    captured: dict[str, Any] = {}
    fake = _fake_urlopen_factory({"response": "ok"}, captured)
    backend = OllamaBackend(base_url="http://workhorse:11434/")
    with patch("codereview.backend.urlopen", fake):
        backend.generate(system="s", user="u")
    assert captured["url"] == "http://workhorse:11434/api/generate"


def test_ollama_network_error_raises_backend_error() -> None:
    def fake_urlopen(req, timeout=None):  # type: ignore[no-untyped-def]
        raise URLError("connection refused")

    backend = OllamaBackend()
    with patch("codereview.backend.urlopen", fake_urlopen):
        with pytest.raises(BackendError, match="Ollama call to .* failed"):
            backend.generate(system="s", user="u")


def test_ollama_non_json_response_raises_backend_error() -> None:
    def fake_urlopen(req, timeout=None):  # type: ignore[no-untyped-def]
        return _FakeResponse(b"<html>not json</html>")

    backend = OllamaBackend()
    with patch("codereview.backend.urlopen", fake_urlopen):
        with pytest.raises(BackendError, match="non-JSON"):
            backend.generate(system="s", user="u")


def test_ollama_missing_response_field_raises_backend_error() -> None:
    captured: dict[str, Any] = {}
    fake = _fake_urlopen_factory({"error": "model not found"}, captured)
    backend = OllamaBackend()
    with patch("codereview.backend.urlopen", fake):
        with pytest.raises(BackendError, match="missing 'response'"):
            backend.generate(system="s", user="u")
