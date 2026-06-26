"""Eval harness — scores `review(diff)` output against a versioned eval set.

ADR-005 requires the harness in Phase 1. ARCHITECTURE.md §4 / ADR-017
defines the methodology as *(proposed)* — defaults here, easy to change.

Scoring model:
- For each case, run `review(diff, config)` against the configured backend
- Match each model finding against the reference findings on
  (severity, category). A match counts only once per reference.
- Precision = matched / total model findings (or 1.0 if model returned none
  and reference also has none — the LGTM/clean-review case)
- Recall    = matched / total reference findings (or 1.0 same way)
- F1        = harmonic mean
- Verdict accuracy is per-case boolean: model verdict matches expected
- Aggregates: macro-averaged precision/recall/F1 + verdict-accuracy fraction

Per-category breakdown captures *which kinds of issues* the model is
strong/weak on — more informative than a single score.
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
class CaseScore:
    case_name: str
    n_reference: int
    n_model: int
    n_matched: int
    precision: float
    recall: float
    f1: float
    verdict_correct: bool
    # Per-category counts (only for the categories that appear in this case)
    matched_by_category: dict[Category, int] = field(default_factory=dict)
    reference_by_category: dict[Category, int] = field(default_factory=dict)


def _match_findings(
    model_findings: list[Finding], reference: list[ReferenceFinding]
) -> tuple[int, dict[Category, int]]:
    """Return (n_matched, matched_by_category).

    A model finding matches a reference if (severity, category) agree.
    Each reference can be matched at most once.
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


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def score_case(case: EvalCase, review_result: Review) -> CaseScore:
    n_ref = len(case.reference_findings)
    n_model = len(review_result.findings)
    n_matched, matched_by_cat = _match_findings(
        review_result.findings, case.reference_findings
    )

    # Precision / recall with the clean-review (LGTM) convention:
    # if both sides agree "nothing wrong", both metrics are 1.0.
    if n_ref == 0 and n_model == 0:
        precision = recall = 1.0
    else:
        precision = (n_matched / n_model) if n_model > 0 else 0.0
        recall = (n_matched / n_ref) if n_ref > 0 else 0.0

    assert review_result.verdict is not None
    verdict_correct = review_result.verdict.passed == case.expected_verdict_passed

    ref_by_cat: dict[Category, int] = {}
    for rf in case.reference_findings:
        ref_by_cat[rf.category] = ref_by_cat.get(rf.category, 0) + 1

    return CaseScore(
        case_name=case.name,
        n_reference=n_ref,
        n_model=n_model,
        n_matched=n_matched,
        precision=precision,
        recall=recall,
        f1=_f1(precision, recall),
        verdict_correct=verdict_correct,
        matched_by_category=matched_by_cat,
        reference_by_category=ref_by_cat,
    )


# ---------------------------------------------------------------------------
# Aggregate scoring + report
# ---------------------------------------------------------------------------


@dataclass
class EvalReport:
    cases: list[CaseScore]
    macro_precision: float
    macro_recall: float
    macro_f1: float
    verdict_accuracy: float
    category_recall: dict[Category, float]


def aggregate(case_scores: list[CaseScore]) -> EvalReport:
    if not case_scores:
        return EvalReport(
            cases=[],
            macro_precision=0.0,
            macro_recall=0.0,
            macro_f1=0.0,
            verdict_accuracy=0.0,
            category_recall={},
        )
    n = len(case_scores)
    macro_p = sum(s.precision for s in case_scores) / n
    macro_r = sum(s.recall for s in case_scores) / n
    macro_f1 = sum(s.f1 for s in case_scores) / n
    verdict_acc = sum(1 for s in case_scores if s.verdict_correct) / n

    # Category recall: per category, sum matched / sum reference, across cases.
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
        macro_precision=macro_p,
        macro_recall=macro_r,
        macro_f1=macro_f1,
        verdict_accuracy=verdict_acc,
        category_recall=category_recall,
    )


def render_report(report: EvalReport) -> str:
    """Markdown-formatted summary suitable for `docs/results.md`."""
    lines: list[str] = []
    lines.append("## Aggregate")
    lines.append("")
    lines.append(f"- **Macro precision:** {report.macro_precision:.3f}")
    lines.append(f"- **Macro recall:**    {report.macro_recall:.3f}")
    lines.append(f"- **Macro F1:**        {report.macro_f1:.3f}")
    lines.append(f"- **Verdict accuracy:** {report.verdict_accuracy:.3f}  "
                 f"({sum(1 for s in report.cases if s.verdict_correct)} "
                 f"of {len(report.cases)})")
    lines.append("")

    if report.category_recall:
        lines.append("### Recall by category")
        lines.append("")
        lines.append("| category | recall |")
        lines.append("| --- | ---:|")
        for cat in sorted(report.category_recall, key=lambda c: c.value):
            lines.append(f"| {cat.value} | {report.category_recall[cat]:.3f} |")
        lines.append("")

    lines.append("## Per-case")
    lines.append("")
    lines.append(
        "| case | ref | model | matched | P | R | F1 | verdict |"
    )
    lines.append("| --- | ---:| ---:| ---:| ---:| ---:| ---:| :---:|")
    for s in report.cases:
        verdict_mark = "✓" if s.verdict_correct else "✗"
        lines.append(
            f"| {s.case_name} | {s.n_reference} | {s.n_model} | {s.n_matched} | "
            f"{s.precision:.2f} | {s.recall:.2f} | {s.f1:.2f} | {verdict_mark} |"
        )
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
    """
    fn = review_fn if review_fn is not None else review
    case_scores: list[CaseScore] = []
    for case in cases:
        result = fn(case.diff, review_config)
        case_scores.append(score_case(case, result))
    return aggregate(case_scores)
