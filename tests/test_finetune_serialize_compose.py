"""Tests for ADR-029 serialization + validation gates + composition report."""

from __future__ import annotations

import json
import pathlib

from codereview.finetune_compose import compose_report, dedupe, validate_record
from codereview.finetune_serialize import (
    TRANSFORM_SYSTEM_PROMPT,
    chat_record,
    decline_record,
    read_jsonl,
    review_record,
    transform_record,
    write_jsonl,
)

GATES = {"max_file_tokens": 3500, "max_chat_answer_words": 150}

VALID_REVIEW_JSON = json.dumps(
    {
        "summary": "One bug.",
        "findings": [
            {
                "severity": "error",
                "category": "bug",
                "message": "Off-by-one in loop bound.",
            }
        ],
    }
)


def _transform() -> dict:
    return transform_record(
        "Rename x to y.", "a.py", "x = 1\n", "y = 1\n", {"repo": "r1", "rule": "noise_comments"}
    )


def test_transform_record_uses_serving_prompts() -> None:
    record = _transform()
    assert record["messages"][0]["content"] == TRANSFORM_SYSTEM_PROMPT
    assert "TRANSFORMATION SPEC:" in record["messages"][1]["content"]
    assert record["messages"][2]["content"] == "y = 1\n"


def test_chat_record_has_no_system_message() -> None:
    record = chat_record("What does add do?", "Adds two numbers.", {"repo": "r1"})
    assert [m["role"] for m in record["messages"]] == ["user", "assistant"]


def test_valid_records_pass_gates() -> None:
    records = [
        _transform(),
        decline_record("Rename q to r.", "b.py", "z = 2\n", {"repo": "r1"}),
        review_record("--- a/x\n+++ b/x\n", VALID_REVIEW_JSON, {"repo": "r1"}),
        chat_record("Q?", "A.", {"repo": "r1"}),
    ]
    assert [validate_record(r, **GATES) for r in records] == [None, None, None, None]


def test_gate_rejects_noop_transform() -> None:
    record = transform_record("Do nothing.", "a.py", "x = 1\n", "x = 1\n", {"repo": "r1"})
    assert "identical" in validate_record(record, **GATES)


def test_gate_rejects_tampered_decline() -> None:
    record = decline_record("Spec.", "a.py", "x = 1\n", {"repo": "r1"})
    record["messages"][-1]["content"] = "x = 2\n"
    assert "byte-identical" in validate_record(record, **GATES)


def test_gate_rejects_invalid_review_json() -> None:
    record = review_record("diff", "not json at all", {"repo": "r1"})
    assert "review JSON invalid" in validate_record(record, **GATES)


def test_gate_rejects_verbose_chat() -> None:
    record = chat_record("Q?", "word " * 200, {"repo": "r1"})
    assert "word cap" in validate_record(record, **GATES)


def test_dedupe_drops_same_shape_and_user() -> None:
    records = [_transform(), _transform(), chat_record("Q?", "A.", {"repo": "r1"})]
    assert len(dedupe(records)) == 2


def test_jsonl_round_trip(tmp_path: pathlib.Path) -> None:
    records = [_transform(), chat_record("Q?", "A.", {"repo": "r1"})]
    path = tmp_path / "out" / "data.jsonl"
    write_jsonl(records, path)
    assert read_jsonl(path) == records


def test_compose_report_shows_shapes_rules_repos() -> None:
    records = [
        _transform(),
        chat_record("Q?", "A.", {"repo": "r2"}),
    ]
    report = compose_report(records, min_pairs_per_rule=30)
    assert "| transform | 1 | 50.0% |" in report
    assert "| noise_comments | 1 | 30 | **NO** |" in report
    assert "| r2 | 1 |" in report
    assert "Token-length histogram" in report


def test_compose_report_honors_per_rule_minimum_overrides() -> None:
    report = compose_report(
        [_transform()], min_pairs_per_rule=30, min_overrides={"noise_comments": 1}
    )
    assert "| noise_comments | 1 | 1 | yes |" in report
