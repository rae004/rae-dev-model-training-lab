"""Tests for the eval harness.

All scoring logic is unit-tested without a live backend by injecting a
canned `review_fn` into `run_eval`.
"""

from pathlib import Path

import pytest

from codereview.eval import (
    CaseScore,
    EvalCase,
    MatchScores,
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
    # Perfect match — both strict and severity-only see 2/2.
    assert score.strict.n_matched == 2
    assert score.strict.precision == pytest.approx(1.0)
    assert score.strict.recall == pytest.approx(1.0)
    assert score.strict.f1 == pytest.approx(1.0)
    assert score.severity_only.n_matched == 2
    assert score.severity_only.precision == pytest.approx(1.0)
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
    # Strict: 1 model finding hits BUG only; 1/1 P, 1/2 R.
    # Severity-only: model finding (ERROR) also *could* be paired with the
    # ERROR-SECURITY reference under severity-only rules — but each reference
    # matches at most once, so the first match wins → still 1 matched.
    assert score.strict.n_matched == 1
    assert score.strict.precision == pytest.approx(1.0)
    assert score.strict.recall == pytest.approx(0.5)
    assert score.strict.f1 == pytest.approx(2 / 3, abs=1e-6)
    assert score.severity_only.n_matched == 1


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
    assert score.strict.n_matched == 1
    assert score.strict.precision == pytest.approx(0.5)  # 1 of 2 model findings was right
    assert score.strict.recall == pytest.approx(1.0)


def test_score_severity_mismatch_does_not_count_strict() -> None:
    """An error reported as a warning is not a match — severity matters even
    to strict scoring, and severity-only *definitely* fails on severity
    mismatch."""
    case = EvalCase(
        name="x",
        description="",
        diff="",
        reference_findings=[_ref(Severity.ERROR, Category.BUG)],
        expected_verdict_passed=False,
    )
    review = _review([_finding(Severity.WARNING, Category.BUG)])
    score = score_case(case, review)
    assert score.strict.n_matched == 0
    assert score.strict.precision == pytest.approx(0.0)
    # Severity-only also fails when severity doesn't match — the whole point
    # of "severity-only" is that severity is still required; only category is
    # ignored.
    assert score.severity_only.n_matched == 0
    assert score.severity_only.precision == pytest.approx(0.0)


def test_score_lgtm_case_with_no_findings() -> None:
    """Clean review against clean reference is a perfect score under both
    scoring rules (precision=recall=1)."""
    case = EvalCase(
        name="x",
        description="",
        diff="",
        reference_findings=[],
        expected_verdict_passed=True,
    )
    review = _review([])
    score = score_case(case, review)
    assert score.n_reference == 0
    assert score.n_model == 0
    assert score.strict.n_matched == 0
    assert score.strict.precision == pytest.approx(1.0)
    assert score.strict.recall == pytest.approx(1.0)
    assert score.severity_only.precision == pytest.approx(1.0)
    assert score.severity_only.recall == pytest.approx(1.0)
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
    assert score.strict.n_matched == 0
    assert score.strict.precision == pytest.approx(0.0)  # 0 of 1 was right
    assert score.strict.recall == pytest.approx(0.0)  # division-by-zero LGTM doesn't apply
    # Severity-only sees the same shape — nothing to match a reference against
    # since reference is empty.
    assert score.severity_only.precision == pytest.approx(0.0)
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
    assert score.strict.n_matched == 1
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
    assert score.strict.n_matched == 1
    assert score.strict.precision == pytest.approx(0.5)  # 1 of 2 model findings genuinely useful
    assert score.strict.recall == pytest.approx(1.0)
    # Severity-only shows the same shape — no double-counting under either rule.
    assert score.severity_only.n_matched == 1


# ---------------------------------------------------------------------------
# Severity-only rule — the ADR-024-specific behavior. These tests exercise the
# axis where strict and severity-only diverge.
# ---------------------------------------------------------------------------


def test_score_severity_only_matches_when_category_differs() -> None:
    """The load-bearing ADR-024 case: model found the right severity but filed
    it under a different category. Strict scores 0; severity-only scores 1.
    This is the qwen/starcoder2 personality-difference pattern from the
    2026-07-05 cross-check entry."""
    case = EvalCase(
        name="x",
        description="",
        diff="",
        reference_findings=[_ref(Severity.ERROR, Category.SECURITY)],
        expected_verdict_passed=False,
    )
    # Model correctly flagged an ERROR-severity issue but categorized it as BUG.
    review = _review([_finding(Severity.ERROR, Category.BUG)])
    score = score_case(case, review)

    # Strict fails on category mismatch.
    assert score.strict.n_matched == 0
    assert score.strict.precision == pytest.approx(0.0)
    assert score.strict.recall == pytest.approx(0.0)

    # Severity-only succeeds — severity matches.
    assert score.severity_only.n_matched == 1
    assert score.severity_only.precision == pytest.approx(1.0)
    assert score.severity_only.recall == pytest.approx(1.0)
    assert score.severity_only.f1 == pytest.approx(1.0)


def test_score_severity_only_still_respects_one_match_per_reference() -> None:
    """A single model finding at ERROR can match at most one ERROR reference
    under severity-only, even if two references share that severity."""
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
    review = _review([_finding(Severity.ERROR, Category.PERFORMANCE)])
    score = score_case(case, review)
    # Strict: 0 matched (PERFORMANCE doesn't match BUG or SECURITY).
    assert score.strict.n_matched == 0
    # Severity-only: 1 matched — the first ERROR reference, once.
    # Second reference isn't matched because the single model finding is
    # already consumed.
    assert score.severity_only.n_matched == 1
    assert score.severity_only.recall == pytest.approx(0.5)


def test_score_severity_only_gap_is_zero_when_categories_agree() -> None:
    """When the model uses our exact taxonomy, strict and severity-only agree.
    Qwen-like case: model always emits the reference's category label."""
    case = EvalCase(
        name="x",
        description="",
        diff="",
        reference_findings=[_ref(Severity.ERROR, Category.SECURITY)],
        expected_verdict_passed=False,
    )
    review = _review([_finding(Severity.ERROR, Category.SECURITY)])
    score = score_case(case, review)
    assert score.strict.n_matched == score.severity_only.n_matched
    assert score.strict.precision == score.severity_only.precision
    assert score.strict.recall == score.severity_only.recall
    assert score.strict.f1 == score.severity_only.f1


def test_score_severity_only_category_recall_still_uses_strict() -> None:
    """Per ADR-024, category-recall stays strict-only. A category-mismatched
    finding does NOT populate matched_by_category even if severity-only
    counts it as matched."""
    case = EvalCase(
        name="x",
        description="",
        diff="",
        reference_findings=[_ref(Severity.ERROR, Category.SECURITY)],
        expected_verdict_passed=False,
    )
    review = _review([_finding(Severity.ERROR, Category.BUG)])
    score = score_case(case, review)
    # Severity-only counts this as a match, but category-recall bookkeeping
    # doesn't credit SECURITY as caught — the model didn't call it SECURITY.
    assert score.severity_only.n_matched == 1
    assert Category.SECURITY not in score.matched_by_category


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _case_score(
    p: float,
    r: float,
    f1: float,
    verdict_correct: bool = True,
    *,
    sev_p: float | None = None,
    sev_r: float | None = None,
    sev_f1: float | None = None,
) -> CaseScore:
    """Build a CaseScore for aggregate tests.

    strict scores come from the positional args; severity-only defaults to the
    strict values unless explicitly overridden (so most aggregate tests can
    ignore the split and get consistent behavior)."""
    strict = MatchScores(n_matched=1, precision=p, recall=r, f1=f1)
    sev = MatchScores(
        n_matched=1,
        precision=p if sev_p is None else sev_p,
        recall=r if sev_r is None else sev_r,
        f1=f1 if sev_f1 is None else sev_f1,
    )
    return CaseScore(
        case_name="x",
        n_reference=1,
        n_model=1,
        strict=strict,
        severity_only=sev,
        verdict_correct=verdict_correct,
    )


def test_aggregate_empty_returns_zeros() -> None:
    rep = aggregate([])
    assert rep.strict.macro_precision == 0.0
    assert rep.strict.macro_recall == 0.0
    assert rep.severity_only.macro_precision == 0.0
    assert rep.severity_only.macro_recall == 0.0
    assert rep.verdict_accuracy == 0.0
    assert rep.category_recall == {}


def test_aggregate_macro_averages_strict() -> None:
    rep = aggregate([
        _case_score(1.0, 1.0, 1.0, True),
        _case_score(0.5, 0.5, 0.5, False),
        _case_score(0.0, 0.0, 0.0, True),
    ])
    assert rep.strict.macro_precision == pytest.approx(0.5)
    assert rep.strict.macro_recall == pytest.approx(0.5)
    assert rep.strict.macro_f1 == pytest.approx(0.5)
    assert rep.verdict_accuracy == pytest.approx(2 / 3)


def test_aggregate_macro_averages_severity_only_differs_when_split() -> None:
    """When strict and severity-only scores differ per case, the aggregate
    reflects each rule's macro-average independently."""
    rep = aggregate([
        _case_score(0.0, 0.0, 0.0, True, sev_p=1.0, sev_r=1.0, sev_f1=1.0),
        _case_score(0.0, 0.0, 0.0, False, sev_p=1.0, sev_r=1.0, sev_f1=1.0),
    ])
    # Strict: (0 + 0) / 2 = 0
    assert rep.strict.macro_precision == pytest.approx(0.0)
    # Severity-only: (1 + 1) / 2 = 1
    assert rep.severity_only.macro_precision == pytest.approx(1.0)
    assert rep.severity_only.macro_recall == pytest.approx(1.0)


def test_aggregate_category_recall_pools_across_cases_strict() -> None:
    """category_recall = total matched / total reference, summed across cases.
    Stays strict-only per ADR-024."""
    s1 = CaseScore(
        case_name="a",
        n_reference=2, n_model=2,
        strict=MatchScores(n_matched=2, precision=1.0, recall=1.0, f1=1.0),
        severity_only=MatchScores(n_matched=2, precision=1.0, recall=1.0, f1=1.0),
        verdict_correct=True,
        matched_by_category={Category.BUG: 2},
        reference_by_category={Category.BUG: 2},
    )
    s2 = CaseScore(
        case_name="b",
        n_reference=2, n_model=1,
        strict=MatchScores(n_matched=1, precision=1.0, recall=0.5, f1=2 / 3),
        severity_only=MatchScores(n_matched=1, precision=1.0, recall=0.5, f1=2 / 3),
        verdict_correct=False,
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


def test_render_report_shows_both_metric_columns() -> None:
    """The dual-metric requirement from ADR-024: aggregate shows both strict
    and severity-only side-by-side; per-case table has both P/R/F1 triples."""
    s = _case_score(0.0, 0.0, 0.0, True, sev_p=1.0, sev_r=1.0, sev_f1=1.0)
    rep = aggregate([s])
    text = render_report(rep)
    # Sanity: the aggregate reflects the split.
    assert rep.strict.macro_precision == pytest.approx(0.0)
    assert rep.severity_only.macro_precision == pytest.approx(1.0)
    # Aggregate table headers include both rules
    assert "strict" in text
    assert "severity-only" in text
    # Per-case table headers reflect the split
    assert "strict matched" in text
    assert "sev-only matched" in text
    # Category-recall header (when present) is separately verified below.


def test_render_report_category_recall_header_marked_strict() -> None:
    """The category-recall section stays strict-only per ADR-024, and the
    header explicitly labels itself as such so a reader isn't confused."""
    s = CaseScore(
        case_name="x",
        n_reference=1, n_model=1,
        strict=MatchScores(n_matched=1, precision=1.0, recall=1.0, f1=1.0),
        severity_only=MatchScores(n_matched=1, precision=1.0, recall=1.0, f1=1.0),
        verdict_correct=True,
        matched_by_category={Category.BUG: 1},
        reference_by_category={Category.BUG: 1},
    )
    rep = aggregate([s])
    text = render_report(rep)
    assert "Recall by category (strict)" in text


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
    assert rep.strict.macro_precision == pytest.approx(1.0)
    assert rep.strict.macro_recall == pytest.approx(1.0)
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
    assert rep.strict.macro_precision == pytest.approx(0.5)  # (1.0 + 0.0) / 2
    assert rep.strict.macro_recall == pytest.approx(0.5)
    assert rep.verdict_accuracy == pytest.approx(0.5)


def test_run_eval_records_case_errors_instead_of_bailing() -> None:
    """Per-case failures (unparseable model output, backend down, etc.)
    must record the error on the CaseScore and continue, not abort the
    whole eval. This was originally uncovered running StarCoder2 base
    against the M8 harness — the raw model doesn't reliably emit JSON,
    and the harness previously bailed on the first parse failure."""
    from codereview.review import Category

    cases = [
        EvalCase(name="ok", description="", diff="x",
                 reference_findings=[], expected_verdict_passed=True),
        EvalCase(name="broken", description="", diff="y",
                 reference_findings=[_ref(Severity.ERROR, Category.BUG)],
                 expected_verdict_passed=False),
        EvalCase(name="also-ok", description="", diff="z",
                 reference_findings=[], expected_verdict_passed=True),
    ]

    def flaky_review(diff: str, cfg: ReviewConfig) -> Review:
        if diff == "y":
            raise ValueError("no JSON object found in model output")
        return _review([])

    cfg = ReviewConfig()
    rep = run_eval(cases, cfg, review_fn=flaky_review)

    # All three cases scored, not just the first one that succeeded.
    assert len(rep.cases) == 3

    # The broken case has the error recorded and scores as complete miss
    # under BOTH strict and severity-only.
    broken = next(s for s in rep.cases if s.case_name == "broken")
    assert broken.error is not None
    assert "no JSON object" in broken.error
    assert broken.n_model == 0
    assert broken.strict.precision == 0.0
    assert broken.strict.recall == 0.0
    assert broken.severity_only.precision == 0.0
    assert broken.severity_only.recall == 0.0
    assert broken.verdict_correct is False
    # The reference-by-category counts are still populated so category
    # recall aggregation stays honest (bug category had 1 ref, 0 matched).
    assert broken.reference_by_category[Category.BUG] == 1

    # The successful cases still scored normally.
    ok = next(s for s in rep.cases if s.case_name == "ok")
    assert ok.error is None
    assert ok.verdict_correct is True


def test_render_report_shows_ERR_for_errored_cases() -> None:
    """Errored cases must render as ERR in the verdict column, not just ✗,
    and the report must include an appendix listing the errors."""
    from codereview.eval import CaseScore, aggregate

    ok = CaseScore(
        case_name="ok", n_reference=0, n_model=0,
        strict=MatchScores(n_matched=0, precision=1.0, recall=1.0, f1=1.0),
        severity_only=MatchScores(n_matched=0, precision=1.0, recall=1.0, f1=1.0),
        verdict_correct=True,
    )
    errored = CaseScore(
        case_name="broken", n_reference=1, n_model=0,
        strict=MatchScores.zero(),
        severity_only=MatchScores.zero(),
        verdict_correct=False,
        error="no JSON object found in model output",
    )
    rep = aggregate([ok, errored])
    text = render_report(rep)

    assert "| broken |" in text
    assert "| ERR |" in text
    assert "## Errored cases" in text
    assert "no JSON object found in model output" in text


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
