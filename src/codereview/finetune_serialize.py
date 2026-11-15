"""Serialization of ADR-029 pairs into messages-format JSONL.

Records are `{"shape": ..., "messages": [...], "meta": {...}}`. TRL's
SFTTrainer applies the base model's chat template to `messages` at train
time, which guarantees the exact qwen2.5 template — we store roles and
content, not rendered template text.

Train-time formatting matches serve-time formatting (ADR-029):

- transform / decline pairs use rae-local-agent's serving prompts verbatim
  (TRANSFORM_SYSTEM_PROMPT and the user-prompt shape are copied from
  rae-local-agent transform.py; keep in sync with that repo).
- review pairs use the M7 serving prompt (imported from review.py).
- chat pairs carry NO system message on purpose: rae-local-chat does not
  send one, so the concise owner voice must be baked into the weights,
  not gated behind a prompt that serving never provides.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codereview.review import SYSTEM_PROMPT as REVIEW_SYSTEM_PROMPT

# Copied verbatim from rae-local-agent transform.py (its SYSTEM_PROMPT).
TRANSFORM_SYSTEM_PROMPT = """You are a code transformation worker. Given a transformation \
spec and the current contents of a file, produce the REWRITTEN contents of that \
file after applying the transformation.

Rules:
- Return ONLY the full file contents, as if you were overwriting the file.
- No prose, no explanation, no markdown fences, no `FILE:` labels, no diff.
- Preserve every line that isn't part of the transformation exactly as given, \
including whitespace, blank lines, imports, docstrings, and comments.
- If the spec has nothing to do in this file, return the file UNCHANGED \
(byte-for-byte identical to the input).
"""


def _transform_user_prompt(spec: str, rel: str, content: str) -> str:
    # Mirrors rae-local-agent transform.py `_build_user_prompt` exactly.
    return (
        f"TRANSFORMATION SPEC:\n{spec}\n\n"
        f"FILE: {rel}\n```\n{content}\n```\n\n"
        "Return the full file contents, rewritten."
    )


def transform_record(
    spec: str, rel: str, before: str, after: str, meta: dict[str, Any]
) -> dict[str, Any]:
    return {
        "shape": "transform",
        "messages": [
            {"role": "system", "content": TRANSFORM_SYSTEM_PROMPT},
            {"role": "user", "content": _transform_user_prompt(spec, rel, before)},
            {"role": "assistant", "content": after},
        ],
        "meta": meta,
    }


def decline_record(spec: str, rel: str, content: str, meta: dict[str, Any]) -> dict[str, Any]:
    record = transform_record(spec, rel, content, content, meta)
    record["shape"] = "decline"
    return record


def review_record(diff: str, review_json: str, meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "shape": "review",
        "messages": [
            {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": f"```diff\n{diff}\n```"},
            {"role": "assistant", "content": review_json},
        ],
        "meta": meta,
    }


def chat_record(question: str, answer: str, meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "shape": "chat",
        "messages": [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ],
        "meta": meta,
    }


def write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
