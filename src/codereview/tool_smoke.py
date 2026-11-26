"""Tool-calling smoke check (ADR-030; the ADR-029 tripwire).

Sends ~10 canned prompts with tool schemas to Ollama's /api/chat and
measures how often the model answers with a well-formed tool call. The
check is deliberately coarse — format and willingness, not tool-use
quality: a prompt passes when the response carries at least one tool
call whose name is in the offered schema and whose arguments parse as
an object. Two channels count, and the report says which fired:
Ollama's structured `tool_calls` field, or a content body that is
itself a single JSON tool invocation. The second exists because stock
qwen2.5-coder (measured M11, both 7b and 32b) names the right tool with
valid arguments but drops the `<tool_call>` tags its chat template
demands, so Ollama's parser leaves the call in `content`. Willingness
is intact, the wrapper is not; scoring only the structured channel
would flatten the base rate to 0 and leave the ADR-030 tripwire
nothing to compare against. ADR-030 gates the fine-tuned candidate on this rate not
being materially below the base model's (threshold set in
eval/tool_smoke.toml once the base rate was first measured).

Speaks /api/chat directly rather than through backend.py: the Backend
protocol is prose-in/prose-out on purpose, and tool schemas are only
this check's concern.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from codereview.backend import BackendError


@dataclass(frozen=True)
class SmokePrompt:
    name: str
    user: str


@dataclass(frozen=True)
class SmokeResult:
    name: str
    tool_called: bool
    detail: str  # tool name called, or why the prompt failed


def load_tool_smoke(path: Path) -> tuple[list[dict[str, Any]], list[SmokePrompt], float | None]:
    """Returns (tool schemas, prompts, pass-rate threshold or None if unset)."""
    with path.open("rb") as f:
        data = tomllib.load(f)
    prompts = [SmokePrompt(name=p["name"], user=p["user"]) for p in data["prompts"]]
    return data["tools"], prompts, data.get("threshold", {}).get("min_pass_rate")


def chat_with_tools(
    *,
    base_url: str,
    model: str,
    user: str,
    tools: list[dict[str, Any]],
    timeout: float,
    seed: int,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/chat"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": user}],
        "tools": tools,
        "stream": False,
        "options": {"temperature": 0.0, "seed": seed},
    }
    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as resp:
            payload = json.loads(resp.read())
    except URLError as e:
        raise BackendError(f"Ollama call to {url} failed: {e}") from e
    if not isinstance(payload, dict) or "message" not in payload:
        raise BackendError(f"Ollama chat response missing 'message': {payload!r}")
    return payload


def score_response(payload: dict[str, Any], tools: list[dict[str, Any]]) -> tuple[bool, str]:
    valid_names = {t["function"]["name"] for t in tools}
    calls = payload["message"].get("tool_calls") or []
    if calls:
        for call in calls:
            fn = call.get("function", {})
            name = fn.get("name")
            if name not in valid_names:
                return False, f"unknown tool {name!r}"
            if not isinstance(fn.get("arguments"), dict):
                return False, f"{name}: arguments not an object"
        return True, "structured: " + ", ".join(c["function"]["name"] for c in calls)
    return _score_content_call(payload["message"].get("content", ""), valid_names)


def _score_content_call(content: str, valid_names: set[str]) -> tuple[bool, str]:
    try:
        parsed = json.loads(content.strip())
    except json.JSONDecodeError:
        return False, "no tool call (answered in prose)"
    if not isinstance(parsed, dict):
        return False, "no tool call (answered in prose)"
    name = parsed.get("name")
    if name not in valid_names:
        return False, f"content JSON names unknown tool {name!r}"
    if not isinstance(parsed.get("arguments"), dict):
        return False, f"{name}: content JSON arguments not an object"
    return True, f"content JSON: {name} (missing <tool_call> tags)"


def run_tool_smoke(
    tools: list[dict[str, Any]],
    prompts: list[SmokePrompt],
    *,
    base_url: str,
    model: str,
    timeout: float,
    seed: int,
) -> list[SmokeResult]:
    results = []
    for prompt in prompts:
        payload = chat_with_tools(
            base_url=base_url,
            model=model,
            user=prompt.user,
            tools=tools,
            timeout=timeout,
            seed=seed,
        )
        ok, detail = score_response(payload, tools)
        results.append(SmokeResult(name=prompt.name, tool_called=ok, detail=detail))
    return results


def render_report(results: list[SmokeResult], *, model: str, threshold: float | None) -> str:
    total = len(results)
    passed = sum(r.tool_called for r in results)
    rate = passed / total
    lines = [
        "# Tool-calling smoke report",
        "",
        f"Model: **{model}**",
        "",
        f"Tool-call rate: **{passed}/{total}** ({rate:.1%})",
    ]
    if threshold is not None:
        verdict = "pass" if rate >= threshold else "**FAIL — tripwire fired (ADR-030)**"
        lines.append(f"Threshold: {threshold:.0%} — {verdict}")
    lines += ["", "| prompt | tool called | detail |", "| --- | --- | --- |"]
    for r in results:
        lines.append(f"| {r.name} | {'yes' if r.tool_called else '**no**'} | {r.detail} |")
    return "\n".join(lines) + "\n"
