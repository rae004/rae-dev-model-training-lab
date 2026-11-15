"""Tests for the teacher client (mocked urlopen) and prompt builders."""

from __future__ import annotations

import io
import json
from typing import Any

import pytest

from codereview import finetune_teacher
from codereview.finetune_teacher import (
    Teacher,
    TeacherConfig,
    TeacherError,
    build_chat_answer_system,
    build_spec_prompt,
)

CONFIG = TeacherConfig(
    base_url="https://api.example.test/v1", model="test-model", api_key="k", retries=2
)


class _FakeResponse(io.BytesIO):
    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def test_complete_posts_openai_shape_and_returns_content(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> _FakeResponse:
        captured["url"] = request.full_url
        captured["auth"] = request.get_header("Authorization")
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        body = {"choices": [{"message": {"content": "the spec"}}]}
        return _FakeResponse(json.dumps(body).encode("utf-8"))

    monkeypatch.setattr(finetune_teacher, "urlopen", fake_urlopen)

    result = Teacher(CONFIG).complete(system="sys", user="usr", max_tokens=99)

    assert result == "the spec"
    assert captured["url"] == "https://api.example.test/v1/chat/completions"
    assert captured["auth"] == "Bearer k"
    assert captured["payload"]["model"] == "test-model"
    assert captured["payload"]["max_tokens"] == 99
    assert captured["payload"]["messages"][0] == {"role": "system", "content": "sys"}


def test_complete_retries_then_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def failing_urlopen(request: Any, timeout: float) -> _FakeResponse:
        calls["n"] += 1
        raise TimeoutError("nope")

    monkeypatch.setattr(finetune_teacher, "urlopen", failing_urlopen)
    monkeypatch.setattr(finetune_teacher.time, "sleep", lambda s: None)

    with pytest.raises(TeacherError):
        Teacher(CONFIG).complete(system="s", user="u")
    assert calls["n"] == 2


def test_spec_prompt_includes_subject_and_diff() -> None:
    prompt = build_spec_prompt("fix parser", "--- a/x.py\n+++ b/x.py\n")
    assert "fix parser" in prompt
    assert "--- a/x.py" in prompt


def test_chat_answer_system_pins_word_cap() -> None:
    assert "150 words" in build_chat_answer_system(150)
