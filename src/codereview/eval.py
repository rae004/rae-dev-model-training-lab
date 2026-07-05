"""Eval harness — scores `review(diff)` output against a versioned eval set.

ADR-005 requires the harness in Phase 1. ADR-024 discharges the scoring-
methodology deferral from ADR-017 with a dual-metric approach.

Scoring model (ADR-024):
- For each case, run `review(diff, config)` against the configured backend
- Match each model finding against the reference findings under TWO rules:
  - **Strict**: `(severity, category)` must both agree. The primary metric.
    The M8 baseline (0.273 macro F1) is a strict-scoring number.
  - **Severity-only**: `severity` must agree; category is ignored for the
    match. The secondary metric. Rewards "found the right severity issue
    but disagreed with the taxonomy label" — a common cross-model case.
- Each reference can be matched at most once under each rule (independently).
- Precision = matched / total model findings (or 1.0 if model returned none
  and reference also has none — the LGTM/clean-review case)
- Recall    = matched / total reference findings (or 1.0 same way)
- F1        = harmonic mean

Verdict accuracy is per-case boolean, unchanged by ADR-024 (verdict derives
from severity threshold alone; category isn't involved).

Per-category recall stays strict-only per ADR-024: a severity-only view of
"recall on security" would collapse to "recall on any error-severity finding"
and stop being category-specific, erasing the model-personality signal the
category breakdown is there to surface.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .review import Category, Finding, Review, ReviewConfig, Severity, review


# ---------------------------------------------------------------------------
# Eval set data model
# ---------------------------------------------------------------------------


@dataclass
class ReferenceFinding:
    severity: Severity
    category: Category
    file: str | None = None
    message_keywords: list[str] = field(default_factory=list)


@dataclass
class EvalCase:
    name: str
    description: str
    diff: str
    reference_findings: list[ReferenceFinding]
    expected_verdict_passed: bool

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EvalCase":
        return cls(
            name=d["name"],
            description=d.get("description", ""),
            diff=d["diff"],
            reference_findings=[
                ReferenceFinding(
                    severity=Severity(f["severity"]),
                    category=Category(f["category"]),
                    file=f.get("file"),
                    message_keywords=list(f.get("message_keywords", [])),
                )
                for f in d.get("findings", [])
            ],
            expected_verdict_passed=bool(d["expected_verdict_passed"]),
        )


def load_eval_set(path: Path | str) -> list[EvalCase]:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return [EvalCase.from_dict(c) for c in data.get("cases", [])]


# ---------------------------------------------------------------------------
# Per-case scoring
# ---------------------------------------------------------------------------


@dataclass
class MatchScores:
    """Precision/recall/F1 under one matching rule (strict OR severity-only).

    Per ADR-024, every case produces two of these — one per rule. Isolating
    them in a sub-object keeps the CaseScore API readable when both are
    reported side-by-side.
    """

    n_matched: int
    precision: float
    recall: float
    f1: float

    @classmethod
    def zero(cls) -> "MatchScores":
        """All-zero scores, for errored cases."""
        return cls(n_matched=0, precision=0.0, recall=0.0, f1=0.0)


@dataclass
class CaseScore:
    case_name: str
    n_reference: int
    n_model: int
    # Strict: (severity, category) both agree. Primary metric — the M8 baseline
    # is a strict-scoring number and any Phase 2 candidate must beat it on
    # this rule (ADR-024).
    strict: MatchScores
    # Severity-only: severity agrees; category ignored for the match.
    # Secondary metric. Rewards "found the right severity, disagreed on label"
    # which the strict rule can't distinguish from "missed entirely."
    severity_only: MatchScores
    verdict_correct: bool
    # Per-category counts — kept strict-only per ADR-024. A severity-only view
    # would collapse to "recall on any error-severity finding" and erase the
    # model-personality signal this breakdown is here to surface.
    matched_by_category: dict[Category, int] = field(default_factory=dict)
    reference_by_category: dict[Category, int] = field(default_factory=dict)
    # Populated when the review call raised (e.g. model returned unparseable
    # output). Errored cases score both strict and severity-only as
    # P=R=F1=0 with verdict_correct=False, so they count against the aggregate
    # the same as a completely wrong review.
    error: str | None = None


def _match_findings_strict(
    model_findings: list[Finding], reference: list[ReferenceFinding]
) -> tuple[int, dict[Category, int]]:
    """Match on (severity, category) — the strict rule.

    Returns (n_matched, matched_by_category). Each reference matched at most
    once. matched_by_category is populated only under strict scoring (per
    ADR-024's category-breakdown-stays-strict rule).
    """
    used_ref_idx: set[int] = set()
    matched_by_category: dict[Category, int] = {}
    for mf in model_findings:
        for i, rf in enumerate(reference):
            if i in used_ref_idx:
                continue
            if mf.severity == rf.severity and mf.category == rf.category:
                used_ref_idx.add(i)
                matched_by_category[rf.category] = matched_by_category.get(rf.category, 0) + 1
                break
    return len(used_ref_idx), matched_by_category


def _match_findings_severity_only(
    model_findings: list[Finding], reference: list[ReferenceFinding]
) -> int:
    """Match on severity alone — the ADR-024 relaxed rule.

    Returns n_matched. Category is ignored for the match; each reference is
    still matched at most once. No per-category breakdown (see ADR-024:
    category-recall stays strict-only).
    """
    used_ref_idx: set[int] = set()
    for mf in model_findings:
        for i, rf in enumerate(reference):
            if i in used_ref_idx:
                continue
            if mf.severity == rf.severity:
                used_ref_idx.add(i)
                break
    return len(used_ref_idx)


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _scores_from_counts(n_matched: int, n_model: int, n_ref: int) -> MatchScores:
    """Compute (precision, recall, F1) with the LGTM convention.

    Both n_ref == 0 and n_model == 0 → LGTM agreement → both metrics 1.0.
    Otherwise: standard formulas with 0.0 fallbacks for the zero-denominator
    cases (n_model == 0 with n_ref > 0 = missed everything; n_ref == 0 with
    n_model > 0 = spuriously flagged a clean review).
    """
    if n_ref == 0 and n_model == 0:
        precision = recall = 1.0
    else:
        precision = (n_matched / n_model) if n_model > 0 else 0.0
        recall = (n_matched / n_ref) if n_ref > 0 else 0.0
    return MatchScores(
        n_matched=n_matched,
        precision=precision,
        recall=recall,
        f1=_f1(precision, recall),
    )


def score_case(case: EvalCase, review_result: Review) -> CaseScore:
    n_ref = len(case.reference_findings)
    n_model = len(review_result.findings)

    n_matched_strict, matched_by_cat = _match_findings_strict(
        review_result.findings, case.reference_findings
    )
    n_matched_severity = _match_findings_severity_only(
        review_result.findings, case.reference_findings
    )

    assert review_result.verdict is not None
    verdict_correct = review_result.verdict.passed == case.expected_verdict_passed

    ref_by_cat: dict[Category, int] = {}
    for rf in case.reference_findings:
        ref_by_cat[rf.category] = ref_by_cat.get(rf.category, 0) + 1

    return CaseScore(
        case_name=case.name,
        n_reference=n_ref,
        n_model=n_model,
        strict=_scores_from_counts(n_matched_strict, n_model, n_ref),
        severity_only=_scores_from_counts(n_matched_severity, n_model, n_ref),
        verdict_correct=verdict_correct,
        matched_by_category=matched_by_cat,
        reference_by_category=ref_by_cat,
    )


# ---------------------------------------------------------------------------
# Aggregate scoring + report
# ---------------------------------------------------------------------------


@dataclass
class AggregateScores:
    """Macro-averaged precision/recall/F1 across all cases, under one rule."""

    macro_precision: float
    macro_recall: float
    macro_f1: float

    @classmethod
    def zero(cls) -> "AggregateScores":
        return cls(macro_precision=0.0, macro_recall=0.0, macro_f1=0.0)


@dataclass
class EvalReport:
    cases: list[CaseScore]
    # Strict: primary metric per ADR-024. M8-baseline-comparable.
    strict: AggregateScores
    # Severity-only: secondary metric per ADR-024. The delta from strict
    # tells you how much of a model's score is "found real issues" vs
    # "agreed with our taxonomy labels".
    severity_only: AggregateScores
    verdict_accuracy: float
    category_recall: dict[Category, float]  # strict-only per ADR-024


def aggregate(case_scores: list[CaseScore]) -> EvalReport:
    if not case_scores:
        return EvalReport(
            cases=[],
            strict=AggregateScores.zero(),
            severity_only=AggregateScores.zero(),
            verdict_accuracy=0.0,
            category_recall={},
        )
    n = len(case_scores)

    strict = AggregateScores(
        macro_precision=sum(s.strict.precision for s in case_scores) / n,
        macro_recall=sum(s.strict.recall for s in case_scores) / n,
        macro_f1=sum(s.strict.f1 for s in case_scores) / n,
    )
    severity_only = AggregateScores(
        macro_precision=sum(s.severity_only.precision for s in case_scores) / n,
        macro_recall=sum(s.severity_only.recall for s in case_scores) / n,
        macro_f1=sum(s.severity_only.f1 for s in case_scores) / n,
    )
    verdict_acc = sum(1 for s in case_scores if s.verdict_correct) / n

    # Category recall: per category, sum matched / sum reference, across cases.
    # Uses strict matched_by_category only, per ADR-024.
    matched_total: dict[Category, int] = {}
    ref_total: dict[Category, int] = {}
    for s in case_scores:
        for cat, cnt in s.matched_by_category.items():
            matched_total[cat] = matched_total.get(cat, 0) + cnt
        for cat, cnt in s.reference_by_category.items():
            ref_total[cat] = ref_total.get(cat, 0) + cnt
    category_recall = {
        cat: matched_total.get(cat, 0) / ref_total[cat]
        for cat in ref_total
    }

    return EvalReport(
        cases=case_scores,
        strict=strict,
        severity_only=severity_only,
        verdict_accuracy=verdict_acc,
        category_recall=category_recall,
    )


def render_report(report: EvalReport) -> str:
    """Markdown-formatted summary suitable for `docs/results.md`.

    Follows ADR-024: strict aggregates and severity-only aggregates side-by-
    side; per-case table gains a strict / severity-only column pair;
    category-recall stays strict-only.
    """
    lines: list[str] = []
    n_correct = sum(1 for s in report.cases if s.verdict_correct)

    lines.append("## Aggregate")
    lines.append("")
    lines.append("| metric | strict | severity-only |")
    lines.append("| --- | ---:| ---:|")
    lines.append(
        f"| Macro precision | {report.strict.macro_precision:.3f} "
        f"| {report.severity_only.macro_precision:.3f} |"
    )
    lines.append(
        f"| Macro recall    | {report.strict.macro_recall:.3f} "
        f"| {report.severity_only.macro_recall:.3f} |"
    )
    lines.append(
        f"| Macro F1        | {report.strict.macro_f1:.3f} "
        f"| {report.severity_only.macro_f1:.3f} |"
    )
    lines.append("")
    lines.append(
        f"- **Verdict accuracy:** {report.verdict_accuracy:.3f}  "
        f"({n_correct} of {len(report.cases)})"
    )
    lines.append("")

    if report.category_recall:
        lines.append("### Recall by category (strict)")
        lines.append("")
        lines.append("| category | recall |")
        lines.append("| --- | ---:|")
        for cat in sorted(report.category_recall, key=lambda c: c.value):
            lines.append(f"| {cat.value} | {report.category_recall[cat]:.3f} |")
        lines.append("")

    lines.append("## Per-case")
    lines.append("")
    lines.append(
        "| case | ref | model | strict matched | strict P/R/F1 "
        "| sev-only matched | sev-only P/R/F1 | verdict |"
    )
    lines.append(
        "| --- | ---:| ---:| ---:| ---:| ---:| ---:| :---:|"
    )
    for s in report.cases:
        if s.error is not None:
            verdict_mark = "ERR"
        elif s.verdict_correct:
            verdict_mark = "✓"
        else:
            verdict_mark = "✗"
        strict_prf = f"{s.strict.precision:.2f}/{s.strict.recall:.2f}/{s.strict.f1:.2f}"
        sev_prf = (
            f"{s.severity_only.precision:.2f}/"
            f"{s.severity_only.recall:.2f}/"
            f"{s.severity_only.f1:.2f}"
        )
        lines.append(
            f"| {s.case_name} | {s.n_reference} | {s.n_model} "
            f"| {s.strict.n_matched} | {strict_prf} "
            f"| {s.severity_only.n_matched} | {sev_prf} "
            f"| {verdict_mark} |"
        )
    lines.append("")

    # If any case errored, list the errors in an appendix — the caller wants
    # to know whether it's "backend down" (uniform error) or "model won't emit
    # JSON on hard cases" (varied errors).
    errored = [s for s in report.cases if s.error is not None]
    if errored:
        lines.append("## Errored cases")
        lines.append("")
        for s in errored:
            lines.append(f"- **{s.case_name}**: {s.error}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Runner — ties together the eval set + the review() core
# ---------------------------------------------------------------------------


def run_eval(
    cases: list[EvalCase],
    review_config: ReviewConfig,
    *,
    review_fn: Callable[[str, ReviewConfig], Review] | None = None,
) -> EvalReport:
    """Run `review()` over every case and aggregate.

    `review_fn` is injectable for tests so the harness can be exercised
    without a live backend. In production it defaults to `codereview.review.review`.

    Per-case failures (e.g. the model returned unparseable output, or the
    backend was unreachable) score the case as P=R=F1=0 with verdict_correct
    =False and record the error message on the CaseScore. This is a genuine
    signal about the backend model: an off-the-shelf coder that can't produce
    the requested JSON on 8 of 11 cases isn't a harness bug, it's a real
    finding. Bailing on the first failure would hide that.
    """
    fn = review_fn if review_fn is not None else review
    case_scores: list[CaseScore] = []
    for case in cases:
        try:
            result = fn(case.diff, review_config)
            case_scores.append(score_case(case, result))
        except Exception as e:
            case_scores.append(
                CaseScore(
                    case_name=case.name,
                    n_reference=len(case.reference_findings),
                    n_model=0,
                    strict=MatchScores.zero(),
                    severity_only=MatchScores.zero(),
                    verdict_correct=False,
                    reference_by_category={
                        cat: sum(1 for f in case.reference_findings if f.category == cat)
                        for cat in {f.category for f in case.reference_findings}
                    },
                    error=str(e),
                )
            )
    return aggregate(case_scores)
