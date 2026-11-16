"""Unit tests for the tool-calling smoke check scoring (no network)."""

from __future__ import annotations

from pathlib import Path

from codereview.tool_smoke import SmokeResult, load_tool_smoke, render_report, score_response

SMOKE_SET = Path(__file__).parent.parent / "eval" / "tool_smoke.toml"


def _payload(tool_calls: list | None) -> dict:
    message: dict = {"role": "assistant", "content": ""}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {"message": message}


def test_committed_smoke_set_loads() -> None:
    tools, prompts, threshold = load_tool_smoke(SMOKE_SET)
    assert len(prompts) == 10
    assert {t["function"]["name"] for t in tools} == {
        "read_file",
        "write_file",
        "run_command",
        "search_code",
    }
    # Threshold stays unset until the base rate is measured (ADR-030).
    assert threshold is None


def test_wellformed_structured_call_passes() -> None:
    tools, _, _ = load_tool_smoke(SMOKE_SET)
    ok, detail = score_response(
        _payload([{"function": {"name": "read_file", "arguments": {"path": "README.md"}}}]),
        tools,
    )
    assert ok
    assert detail == "structured: read_file"


def test_content_json_call_passes() -> None:
    # Stock qwen2.5-coder drops the <tool_call> tags, leaving the call in
    # content; the coarse check still counts it as willingness + format.
    tools, _, _ = load_tool_smoke(SMOKE_SET)
    payload = _payload(None)
    payload["message"]["content"] = '{"name": "read_file", "arguments": {"path": "README.md"}}'
    ok, detail = score_response(payload, tools)
    assert ok
    assert "content JSON: read_file" in detail


def test_content_json_with_unknown_tool_fails() -> None:
    tools, _, _ = load_tool_smoke(SMOKE_SET)
    payload = _payload(None)
    payload["message"]["content"] = '{"name": "rm_rf", "arguments": {}}'
    ok, detail = score_response(payload, tools)
    assert not ok
    assert "rm_rf" in detail


def test_prose_answer_fails() -> None:
    tools, _, _ = load_tool_smoke(SMOKE_SET)
    ok, detail = score_response(_payload(None), tools)
    assert not ok
    assert "prose" in detail


def test_unknown_tool_fails() -> None:
    tools, _, _ = load_tool_smoke(SMOKE_SET)
    ok, detail = score_response(
        _payload([{"function": {"name": "delete_everything", "arguments": {}}}]), tools
    )
    assert not ok
    assert "delete_everything" in detail


def test_string_arguments_fail() -> None:
    tools, _, _ = load_tool_smoke(SMOKE_SET)
    ok, detail = score_response(
        _payload([{"function": {"name": "read_file", "arguments": '{"path": "x"}'}}]), tools
    )
    assert not ok
    assert "arguments" in detail


def test_report_includes_threshold_verdict() -> None:
    results = [
        SmokeResult(name="a", tool_called=True, detail="read_file"),
        SmokeResult(name="b", tool_called=False, detail="no tool call (answered in prose)"),
    ]
    report = render_report(results, model="m", threshold=0.9)
    assert "Tool-call rate: **1/2** (50.0%)" in report
    assert "tripwire fired" in report
    no_threshold = render_report(results, model="m", threshold=None)
    assert "Threshold" not in no_threshold
