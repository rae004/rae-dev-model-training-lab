"""Mechanical validation gates + composition report for the ADR-029 dataset.

Every pair must pass its shape's gate before it enters the dataset; the
composition report is the PR artifact a human reviews (shape proportions,
mutation-rule coverage, source-repo breakdown, token-length histogram).
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from codereview.finetune_mine import estimate_tokens
from codereview.review import parse_model_output, parse_review_payload


def validate_record(
    record: dict[str, Any],
    *,
    max_file_tokens: int,
    max_chat_answer_words: int,
) -> str | None:
    """Return None when the record passes its shape's gate, else the reason."""
    shape = record.get("shape")
    messages = record.get("messages", [])
    if not messages or messages[-1]["role"] != "assistant":
        return "missing assistant message"
    answer = messages[-1]["content"]
    user = next((m["content"] for m in messages if m["role"] == "user"), "")
    if not user:
        return "missing user message"

    if shape == "transform":
        if not answer.strip():
            return "empty transform output"
        if answer == _file_from_user_prompt(user):
            return "transform output identical to input (should be a decline)"
        if estimate_tokens(answer) > max_file_tokens:
            return "transform output over token cap"
    elif shape == "decline":
        if answer != _file_from_user_prompt(user):
            return "decline output not byte-identical to input"
    elif shape == "review":
        try:
            parse_review_payload(parse_model_output(answer))
        except Exception as e:  # noqa: BLE001 - any parse failure is the gate
            return f"review JSON invalid: {e}"
    elif shape == "chat":
        if len(answer.split()) > max_chat_answer_words:
            return "chat answer over word cap"
        if not answer.strip():
            return "empty chat answer"
    else:
        return f"unknown shape: {shape!r}"
    return None


def _file_from_user_prompt(user: str) -> str | None:
    """Extract the file content between the fences of the transform user prompt."""
    start = user.find("```\n")
    end = user.rfind("\n```")
    if start == -1 or end == -1 or end <= start:
        return None
    # The serving template is f"```\n{content}\n```" — the final "\n" belongs
    # to the template, not the file, so the slice excludes it.
    return user[start + 4 : end]


def dedupe(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop exact duplicates by (shape, user content), keeping first occurrence."""
    seen: set[tuple[str, str]] = set()
    kept: list[dict[str, Any]] = []
    for record in records:
        user = next((m["content"] for m in record["messages"] if m["role"] == "user"), "")
        key = (record["shape"], user)
        if key in seen:
            continue
        seen.add(key)
        kept.append(record)
    return kept


def compose_report(records: list[dict[str, Any]], *, min_pairs_per_rule: int) -> str:
    """Markdown composition report — the human-review artifact for the M10 PR."""
    shapes = Counter(r["shape"] for r in records)
    repos = Counter(r["meta"].get("repo", "?") for r in records)
    rules = Counter(
        r["meta"]["rule"] for r in records if r["shape"] == "transform" and "rule" in r["meta"]
    )
    total = len(records)

    lines = ["# Dataset composition report", "", f"Total pairs: **{total}**", ""]
    lines += ["## Shape proportions", "", "| shape | count | share |", "| --- | --- | --- |"]
    for shape, count in sorted(shapes.items()):
        lines.append(f"| {shape} | {count} | {count / total:.1%} |")

    lines += ["", "## Mutation-rule coverage", ""]
    lines += [f"Minimum per rule: {min_pairs_per_rule}", ""]
    lines += ["| rule | count | meets minimum |", "| --- | --- | --- |"]
    for rule, count in sorted(rules.items()):
        ok = "yes" if count >= min_pairs_per_rule else "**NO**"
        lines.append(f"| {rule} | {count} | {ok} |")

    lines += ["", "## Source repositories", "", "| repo | pairs |", "| --- | --- |"]
    for repo, count in repos.most_common():
        lines.append(f"| {repo} | {count} |")

    buckets = Counter(_token_bucket(r) for r in records)
    lines += ["", "## Token-length histogram (full record)", ""]
    lines += ["| bucket | records |", "| --- | --- |"]
    for bucket in sorted(buckets):
        lines.append(f"| {bucket} | {buckets[bucket]} |")
    return "\n".join(lines) + "\n"


def _token_bucket(record: dict[str, Any]) -> str:
    tokens = sum(estimate_tokens(m["content"]) for m in record["messages"])
    edges = [512, 1024, 2048, 4096, 8192]
    for edge in edges:
        if tokens <= edge:
            return f"<= {edge}"
    return "> 8192"
