"""Unit tests for the M11 transform harness scoring (no network).

The scoring functions are pure (plus a subprocess `git apply --check`),
so every ADR-030 boolean is tested directly: clean apply, byte-for-byte
preservation, targeted-change assertion, and the 2x runaway guard.
"""

from __future__ import annotations

from pathlib import Path

from codereview.transform_eval import (
    CATEGORIES,
    MIN_PER_CATEGORY,
    REQUIRED_CASE_NAMES,
    TransformCase,
    clean_apply,
    load_transform_set,
    normalize_output,
    preserved,
    render_report,
    run_transform_eval,
    score_case,
    targeted,
)

TRANSFORM_SET = Path(__file__).parent.parent / "eval" / "transform_set.toml"

RENAME_INPUT = """\
def compute_tax(amount: float) -> float:
    return amount * 0.2


def compute_total(amount: float) -> float:
    return amount + compute_tax(amount)
"""

RENAME_GOOD = RENAME_INPUT.replace("compute_tax", "calculate_tax")
RENAME_OVERREACH = RENAME_INPUT.replace("compute", "calculate")  # renames the sibling too


def _rename_case() -> TransformCase:
    return TransformCase(
        name="rename",
        category="preservation_trap",
        description="",
        spec="Rename compute_tax to calculate_tax.",
        path="src/billing.py",
        input_text=RENAME_INPUT,
        may_change=("compute_tax",),
        must_match=(r"def calculate_tax\(amount: float\) -> float:",),
        must_not_match=("compute_tax",),
    )


def _decline_case() -> TransformCase:
    return TransformCase(
        name="decline",
        category="decline",
        description="",
        spec="Rename a function this file does not have.",
        path="src/billing.py",
        input_text=RENAME_INPUT,
        may_change=(),
        must_match=(),
        must_not_match=(),
    )


def test_committed_set_loads_and_meets_category_minimums() -> None:
    cases = load_transform_set(TRANSFORM_SET)
    per_category = {cat: sum(c.category == cat for c in cases) for cat in CATEGORIES}
    for cat, minimum in MIN_PER_CATEGORY.items():
        assert per_category[cat] >= minimum, f"{cat} below minimum"
    names = {c.name for c in cases}
    for required in REQUIRED_CASE_NAMES:
        assert required in names


def test_good_rename_passes_all_booleans() -> None:
    result = score_case(_rename_case(), RENAME_GOOD)
    assert result.clean_apply and result.preserved and result.targeted
    assert not result.runaway
    assert result.passed


def test_sibling_rename_fails_preservation() -> None:
    assert preserved(_rename_case(), RENAME_GOOD)
    assert not preserved(_rename_case(), RENAME_OVERREACH)
    assert not score_case(_rename_case(), RENAME_OVERREACH).passed


def test_missing_target_fails_assertion() -> None:
    assert not targeted(_rename_case(), RENAME_INPUT)  # unchanged: no calculate_tax
    assert not score_case(_rename_case(), RENAME_INPUT).passed


def test_outer_fences_and_file_label_are_stripped_like_serving() -> None:
    # rae-local-agent strips outer fences and a FILE: label before writing;
    # the harness must tolerate exactly what serving tolerates.
    fenced = f"```python\n{RENAME_GOOD}```\n"
    assert score_case(_rename_case(), fenced).passed
    labeled = f"FILE: src/billing.py\n{RENAME_GOOD}"
    assert score_case(_rename_case(), labeled).passed


def test_interior_fences_still_fail_clean_apply() -> None:
    # A second code block survives the serve-time strip and would land in
    # the written file.
    two_blocks = f"```python\n{RENAME_GOOD}```\nAnd here is a test:\n```python\npass\n```\n"
    assert not clean_apply(_rename_case(), normalize_output(two_blocks))
    assert not score_case(_rename_case(), two_blocks).passed


def test_decline_passes_only_byte_identical() -> None:
    case = _decline_case()
    good = score_case(case, RENAME_INPUT)
    assert good.passed and good.clean_apply and good.targeted
    helpful = score_case(case, RENAME_INPUT + "\n# NOTE: nothing to do\n")
    assert not helpful.clean_apply
    assert not helpful.passed


def test_runaway_guard_fails_even_when_content_is_right() -> None:
    bloated = RENAME_GOOD + "\n" + ("# padding line that doubles the file\n" * 40)
    case = _rename_case()
    result = score_case(case, bloated)
    assert result.runaway
    assert not result.passed


def test_empty_output_fails_clean_apply() -> None:
    assert not clean_apply(_rename_case(), "")


def test_normalize_mirrors_serving_strip() -> None:
    assert normalize_output("x") == "x\n"
    assert normalize_output("x\n") == "x\n"
    assert normalize_output("") == ""
    assert normalize_output("```python\nx\n```") == "x\n"
    assert normalize_output("```\nx\n\n```\n") == "x\n"
    assert normalize_output("FILE: a.py\nx\n") == "x\n"


class StubBackend:
    def generate(self, *, system: str, user: str) -> str:
        # Echo the file back unchanged: declines pass, transforms fail.
        start = user.find("```\n")
        end = user.rfind("\n```")
        return user[start + 4 : end]


def test_run_transform_eval_over_committed_set_with_echo_stub() -> None:
    cases = load_transform_set(TRANSFORM_SET)
    results = run_transform_eval(cases, StubBackend())
    by_name = {r.name: r for r in results}
    assert all(by_name[c.name].passed for c in cases if c.category == "decline")
    assert all(not by_name[c.name].passed for c in cases if c.category != "decline")
    report = render_report(results, model="stub")
    assert "# Transform eval report" in report
    assert "| decline |" in report
