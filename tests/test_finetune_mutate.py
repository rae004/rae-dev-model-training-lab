"""Tests for the ADR-029 reverse-mutation rules.

Every rule's contract: mutated text differs from the original, still parses
(for Python), the original rides along as ground truth, and the same seed
produces the same mutation.
"""

from __future__ import annotations

import ast
import random

import pytest

from codereview.finetune_mutate import RULES, Mutation

PY_FILE = '''\
from collections.abc import Sequence


def total(values: Sequence[int]) -> int:
    """Sum the values."""
    acc = 0
    for v in values:
        acc = acc + v
    return acc


def scale(values: Sequence[int], factor: int) -> list[int]:
    result = [v * factor for v in values]
    return result
'''

TS_FILE = """\
export function total(values: number[]): number {
  let acc = 0;
  for (const v of values) {
    acc = acc + v;
  }
  return acc;
}
"""


def _apply(rule_name: str, text: str, language: str, seed: int = 7) -> Mutation | None:
    return RULES[rule_name](text, random.Random(seed), language=language)


@pytest.mark.parametrize("rule_name", sorted(RULES))
def test_rule_contract_python(rule_name: str) -> None:
    mutation = _apply(rule_name, PY_FILE, "python")
    assert mutation is not None, f"{rule_name} should apply to the sample file"
    assert mutation.rule == rule_name
    assert mutation.original == PY_FILE
    assert mutation.mutated != PY_FILE
    ast.parse(mutation.mutated)
    assert mutation.spec


@pytest.mark.parametrize("rule_name", sorted(RULES))
def test_rules_are_deterministic(rule_name: str) -> None:
    assert _apply(rule_name, PY_FILE, "python") == _apply(rule_name, PY_FILE, "python")


@pytest.mark.parametrize("rule_name", ["noise_comments", "commented_out_code"])
def test_text_rules_apply_to_typescript(rule_name: str) -> None:
    mutation = _apply(rule_name, TS_FILE, "typescript")
    assert mutation is not None
    assert mutation.original == TS_FILE
    assert "//" in mutation.mutated


@pytest.mark.parametrize(
    "rule_name", ["defensive_validation", "backcompat_alias", "concrete_annotation"]
)
def test_python_only_rules_decline_typescript(rule_name: str) -> None:
    assert _apply(rule_name, TS_FILE, "typescript") is None


def test_noise_comments_needs_candidates() -> None:
    assert _apply("noise_comments", "x = 1\n", "python") is None


def test_defensive_validation_guards_after_docstring() -> None:
    mutation = _apply("defensive_validation", PY_FILE, "python")
    assert mutation is not None
    guarded = mutation.mutated
    # The docstring must still be the first statement of its function.
    tree = ast.parse(guarded)
    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    for func in funcs:
        if func.name == "total":
            assert ast.get_docstring(func) == "Sum the values."
    assert "is None:" in guarded


def test_backcompat_alias_appends_legacy_name() -> None:
    mutation = _apply("backcompat_alias", PY_FILE, "python")
    assert mutation is not None
    assert "legacy_" in mutation.mutated
    assert "backwards compatibility" in mutation.mutated


def test_concrete_annotation_narrows_one_annotation() -> None:
    mutation = _apply("concrete_annotation", PY_FILE, "python")
    assert mutation is not None
    assert mutation.mutated.count(": list[") == PY_FILE.count(": list[") + 1


def test_concrete_annotation_declines_without_abstract_types() -> None:
    assert _apply("concrete_annotation", "def f(x: list[int]):\n    return x\n", "python") is None
