"""Tests for the eval harness.

All scoring logic is unit-tested without a live backend by injecting a
canned `review_fn` into `run_eval`.
"""

from pathlib import Path

import pytest

from codereview.eval import (
    CaseScore,
    EvalCase,
    ReferenceFinding,
    aggregate,
    load_eval_set,
    render_report,
    run_eval,
    score_case,
)
from codereview.review import (
    Category,
    Finding,
    Review,
    ReviewConfig,
    Severity,
    derive_verdict,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ref(severity: Severity, category: Category) -> ReferenceFinding:
    return ReferenceFinding(severity=severity, category=category)


def _finding(severity: Severity, category: Category) -> Finding:
    return Finding(severity=severity, category=category, message="x")


def _review(findings: list[Finding], threshold: Severity = Severity.ERROR) -> Review:
    r = Review(summary="", findings=findings)
    r.verdict = derive_verdict(findings, threshold)
    return r


# ---------------------------------------------------------------------------
# Per-case scoring
# ---------------------------------------------------------------------------


def test_score_perfect_match() -> None:
    case = EvalCase(
        name="x",
        description="",
        diff="",
        reference_findings=[
            _ref(Severity.ERROR, Category.BUG),
            _ref(Severity.WARNING, Category.TEST_GAP),
        ],
        expected_verdict_passed=False,
    )
    review = _review(
        [_finding(Severity.ERROR, Category.BUG), _finding(Severity.WARNING, Category.TEST_GAP)]
    )
    score = score_case(case, review)
    assert score.n_matched == 2
    assert score.precision == pytest.approx(1.0)
    assert score.recall == pytest.approx(1.0)
    assert score.f1 == pytest.approx(1.0)
    assert score.verdict_correct is True


def test_score_partial_match_one_correct_one_missed() -> None:
    case = EvalCase(
        name="x",
        description="",
        diff="",
        reference_findings=[
            _ref(Severity.ERROR, Category.BUG),
            _ref(Severity.ERROR, Category.SECURITY),
        ],
        expected_verdict_passed=False,
    )
    review = _review([_finding(Severity.ERROR, Category.BUG)])
    score = score_case(case, review)
    assert score.n_matched == 1
    assert score.precision == pytest.approx(1.0)  # 1 of 1 model finding was right
    assert score.recall == pytest.approx(0.5)  # 1 of 2 reference findings caught
    assert score.f1 == pytest.approx(2 / 3, abs=1e-6)


def test_score_partial_match_one_correct_one_spurious() -> None:
    case = EvalCase(
        name="x",
        description="",
        diff="",
        reference_findings=[_ref(Severity.ERROR, Category.BUG)],
        expected_verdict_passed=False,
    )
    review = _review(
        [_finding(Severity.ERROR, Category.BUG), _finding(Severity.WARNING, Category.READABILITY)]
    )
    score = score_case(case, review)
    assert score.n_matched == 1
    assert score.precision == pytest.approx(0.5)  # 1 of 2 model findings was right
    assert score.recall == pytest.approx(1.0)


def test_score_severity_mismatch_does_not_count() -> None:
    """An error reported as a warning is not a match — severity matters."""
    case = EvalCase(
        name="x",
        description="",
        diff="",
        reference_findings=[_ref(Severity.ERROR, Category.BUG)],
        expected_verdict_passed=False,
    )
    review = _review([_finding(Severity.WARNING, Category.BUG)])
    score = score_case(case, review)
    assert score.n_matched == 0
    assert score.precision == pytest.approx(0.0)
    assert score.recall == pytest.approx(0.0)


def test_score_lgtm_case_with_no_findings() -> None:
    """Clean review against clean reference is a perfect score (precision=recall=1)."""
    case = EvalCase(
        name="x",
        description="",
        diff="",
        reference_findings=[],
        expected_verdict_passed=True,
    )
    review = _review([])
    score = score_case(case, review)
    assert score.n_matched == 0
    assert score.n_reference == 0
    assert score.n_model == 0
    assert score.precision == pytest.approx(1.0)
    assert score.recall == pytest.approx(1.0)
    assert score.verdict_correct is True


def test_score_lgtm_case_with_spurious_finding() -> None:
    case = EvalCase(
        name="x",
        description="",
        diff="",
        reference_findings=[],
        expected_verdict_passed=True,
    )
    review = _review([_finding(Severity.ERROR, Category.BUG)])
    score = score_case(case, review)
    assert score.n_matched == 0
    assert score.precision == pytest.approx(0.0)  # 0 of 1 was right
    assert score.recall == pytest.approx(0.0)  # division-by-zero LGTM doesn't apply (n_model > 0)
    assert score.verdict_correct is False  # model failed something the reference said is clean


def test_score_verdict_wrong_but_findings_partial() -> None:
    """Verdict accuracy is separate from precision/recall."""
    case = EvalCase(
        name="x",
        description="",
        diff="",
        reference_findings=[_ref(Severity.WARNING, Category.DESIGN)],
        expected_verdict_passed=True,  # warning doesn't block at default threshold
    )
    # Model reports the warning + spuriously escalates to error
    review = _review(
        [_finding(Severity.WARNING, Category.DESIGN), _finding(Severity.ERROR, Category.BUG)]
    )
    score = score_case(case, review)
    assert score.n_matched == 1
    assert score.verdict_correct is False  # model says fail, reference says pass


def test_score_duplicate_model_findings_dont_double_count() -> None:
    """Two model findings claiming the same reference get one match."""
    case = EvalCase(
        name="x",
        description="",
        diff="",
        reference_findings=[_ref(Severity.ERROR, Category.BUG)],
        expected_verdict_passed=False,
    )
    review = _review(
        [_finding(Severity.ERROR, Category.BUG), _finding(Severity.ERROR, Category.BUG)]
    )
    score = score_case(case, review)
    assert score.n_matched == 1
    assert score.precision == pytest.approx(0.5)  # 1 of 2 model findings genuinely useful
    assert score.recall == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _case_score(p: float, r: float, f1: float, verdict_correct: bool = True) -> CaseScore:
    return CaseScore(
        case_name="x",
        n_reference=1,
        n_model=1,
        n_matched=1,
        precision=p,
        recall=r,
        f1=f1,
        verdict_correct=verdict_correct,
    )


def test_aggregate_empty_returns_zeros() -> None:
    rep = aggregate([])
    assert rep.macro_precision == 0.0
    assert rep.macro_recall == 0.0
    assert rep.verdict_accuracy == 0.0
    assert rep.category_recall == {}


def test_aggregate_macro_averages() -> None:
    rep = aggregate([
        _case_score(1.0, 1.0, 1.0, True),
        _case_score(0.5, 0.5, 0.5, False),
        _case_score(0.0, 0.0, 0.0, True),
    ])
    assert rep.macro_precision == pytest.approx(0.5)
    assert rep.macro_recall == pytest.approx(0.5)
    assert rep.macro_f1 == pytest.approx(0.5)
    assert rep.verdict_accuracy == pytest.approx(2 / 3)


def test_aggregate_category_recall_pools_across_cases() -> None:
    """category_recall = total matched / total reference, summed across cases."""
    s1 = CaseScore(
        case_name="a",
        n_reference=2, n_model=2, n_matched=2,
        precision=1.0, recall=1.0, f1=1.0, verdict_correct=True,
        matched_by_category={Category.BUG: 2},
        reference_by_category={Category.BUG: 2},
    )
    s2 = CaseScore(
        case_name="b",
        n_reference=2, n_model=1, n_matched=1,
        precision=1.0, recall=0.5, f1=2 / 3, verdict_correct=False,
        matched_by_category={Category.BUG: 1},
        reference_by_category={Category.BUG: 1, Category.SECURITY: 1},
    )
    rep = aggregate([s1, s2])
    # BUG: 3 matched / 3 reference = 1.0; SECURITY: 0 / 1 = 0.0
    assert rep.category_recall[Category.BUG] == pytest.approx(1.0)
    assert rep.category_recall[Category.SECURITY] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def test_render_report_contains_aggregate_and_per_case() -> None:
    s1 = _case_score(1.0, 1.0, 1.0, True)
    s1.case_name = "case-a"
    s1.matched_by_category = {Category.BUG: 1}
    s1.reference_by_category = {Category.BUG: 1}
    s2 = _case_score(0.5, 0.0, 0.0, False)
    s2.case_name = "case-b"
    s2.reference_by_category = {Category.SECURITY: 1}
    rep = aggregate([s1, s2])
    text = render_report(rep)
    assert "Macro precision" in text
    assert "case-a" in text
    assert "case-b" in text
    assert "bug" in text  # category recall row
    assert "security" in text
    # Verdict marks
    assert "✓" in text
    assert "✗" in text


# ---------------------------------------------------------------------------
# Runner — injected review_fn so no backend needed
# ---------------------------------------------------------------------------


def test_run_eval_invokes_review_fn_once_per_case() -> None:
    cases = [
        EvalCase(name="a", description="", diff="DIFF-A",
                 reference_findings=[_ref(Severity.ERROR, Category.BUG)],
                 expected_verdict_passed=False),
        EvalCase(name="b", description="", diff="DIFF-B",
                 reference_findings=[],
                 expected_verdict_passed=True),
    ]
    called: list[str] = []

    def fake_review(diff: str, cfg: ReviewConfig) -> Review:
        called.append(diff)
        if diff == "DIFF-A":
            return _review([_finding(Severity.ERROR, Category.BUG)])
        return _review([])

    cfg = ReviewConfig()
    rep = run_eval(cases, cfg, review_fn=fake_review)
    assert called == ["DIFF-A", "DIFF-B"]
    assert rep.macro_precision == pytest.approx(1.0)
    assert rep.macro_recall == pytest.approx(1.0)
    assert rep.verdict_accuracy == pytest.approx(1.0)


def test_run_eval_aggregates_across_cases() -> None:
    cases = [
        EvalCase(name="ok", description="", diff="x",
                 reference_findings=[], expected_verdict_passed=True),
        EvalCase(name="missed", description="", diff="y",
                 reference_findings=[_ref(Severity.ERROR, Category.SECURITY)],
                 expected_verdict_passed=False),
    ]

    def fake_review(diff: str, cfg: ReviewConfig) -> Review:
        return _review([])  # Always returns LGTM

    cfg = ReviewConfig()
    rep = run_eval(cases, cfg, review_fn=fake_review)
    # 1 case perfect (LGTM correct), 1 case fully missed
    assert rep.macro_precision == pytest.approx(0.5)  # (1.0 + 0.0) / 2
    assert rep.macro_recall == pytest.approx(0.5)
    assert rep.verdict_accuracy == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Eval set loading + the committed eval set
# ---------------------------------------------------------------------------


def test_load_eval_set_parses_committed_file() -> None:
    cases = load_eval_set(REPO_ROOT / "eval" / "eval_set.toml")
    assert len(cases) > 0
    names = {c.name for c in cases}
    assert "off-by-one-loop" in names
    assert "sql-injection" in names
    # At least one LGTM case
    lgtm = [c for c in cases if not c.reference_findings]
    assert len(lgtm) > 0


def test_committed_eval_set_uses_only_proposed_enum_values() -> None:
    """Reference findings must use valid Severity/Category enum values."""
    cases = load_eval_set(REPO_ROOT / "eval" / "eval_set.toml")
    for c in cases:
        for f in c.reference_findings:
            assert isinstance(f.severity, Severity)
            assert isinstance(f.category, Category)


def test_committed_eval_set_verdict_is_consistent_with_findings() -> None:
    """A case with any error-severity reference must expect verdict_passed=False
    at the default threshold; otherwise the eval set itself is inconsistent."""
    cases = load_eval_set(REPO_ROOT / "eval" / "eval_set.toml")
    for c in cases:
        has_error = any(f.severity == Severity.ERROR for f in c.reference_findings)
        if has_error:
            assert c.expected_verdict_passed is False, (
                f"case {c.name!r} has an error-severity finding but "
                f"expects verdict_passed=True"
            )
