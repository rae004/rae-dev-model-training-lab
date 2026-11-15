"""End-to-end assembly test with a stub teacher (no network, no code written
by the teacher — the stub returns prose and schema JSON only)."""

from __future__ import annotations

import json

from codereview.finetune_build import SourceFiles, build_dataset, unified_diff
from codereview.finetune_mine import MinedCommit
from codereview.finetune_teacher import CHAT_QUESTION_SYSTEM, SPEC_SYSTEM
from codereview.review import SYSTEM_PROMPT as REVIEW_SYSTEM_PROMPT

CONFIG = {
    "dataset": {"seed": 1, "target_total": 40, "floor_total": 8},
    "proportions": {"transform": 0.45, "decline": 0.15, "review": 0.20, "chat": 0.20},
    "limits": {"max_file_tokens": 3500, "max_chat_answer_words": 150},
    "mutations": {"min_pairs_per_rule": 1},
}

REVIEW_JSON = json.dumps(
    {
        "summary": "Looks fine.",
        "findings": [],
    }
)

PY_SAMPLE = '''\
from collections.abc import Sequence


def compute_total(values: Sequence[int]) -> int:
    """Sum the values."""
    acc = 0
    for v in values:
        acc = acc + v
    return acc
'''


class StubTeacher:
    def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> str:
        if system == SPEC_SYSTEM:
            return "Rename frobnicate_widget to spin_widget and keep behavior identical."
        if system == REVIEW_SYSTEM_PROMPT:
            return REVIEW_JSON
        if system == CHAT_QUESTION_SYSTEM:
            return "What does compute_total do?"
        return "It sums the values in the sequence and returns the total."


def _mined() -> list[MinedCommit]:
    return [
        MinedCommit(
            repo="repo-a",
            sha=f"{i:040d}",
            path="widget.py",
            subject="rename widget fn",
            before=f"def frobnicate_widget(n):\n    return n + {i}\n",
            after=f"def spin_widget(n):\n    return n + {i}\n",
        )
        for i in range(12)
    ]


def _sources() -> list[SourceFiles]:
    return [SourceFiles(repo="repo-a", files=[("calc.py", PY_SAMPLE)])]


def test_build_dataset_produces_all_four_shapes() -> None:
    records, report = build_dataset(_mined(), _sources(), StubTeacher(), CONFIG)
    shapes = {r["shape"] for r in records}
    assert shapes == {"transform", "decline", "review", "chat"}
    assert "# Dataset composition report" in report


def test_declines_are_byte_identical_and_verified() -> None:
    records, _ = build_dataset(_mined(), _sources(), StubTeacher(), CONFIG)
    declines = [r for r in records if r["shape"] == "decline"]
    assert declines, "expected decline pairs (spec names absent from calc.py)"
    for d in declines:
        assert d["messages"][-1]["content"] == PY_SAMPLE


def test_mutation_pairs_carry_rule_meta_and_original_ground_truth() -> None:
    records, _ = build_dataset(_mined(), _sources(), StubTeacher(), CONFIG)
    mutated = [r for r in records if r["shape"] == "transform" and "rule" in r["meta"]]
    assert mutated
    for r in mutated:
        assert r["messages"][-1]["content"] == PY_SAMPLE  # pristine original


def test_build_is_deterministic_given_seed_and_stub() -> None:
    a, _ = build_dataset(_mined(), _sources(), StubTeacher(), CONFIG)
    b, _ = build_dataset(_mined(), _sources(), StubTeacher(), CONFIG)
    assert a == b


def test_unified_diff_round_trips_shape() -> None:
    d = unified_diff("x.py", "a\n", "b\n")
    assert d.startswith("--- a/x.py")
    assert "+b" in d
