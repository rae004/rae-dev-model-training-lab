"""The frozen contract: `review(diff, config) -> Review`.

This module owns the **schema** (ARCHITECTURE.md §4, CLAUDE.md rule 3) and
the **derived-verdict** logic. Verdict is computed from findings against a
configurable severity threshold — the model is never asked separately.

Severity / Category enums and the threshold default are *(proposed)* per
ARCHITECTURE.md §4 — they live in config and are easy to change, never
silently changed (CLAUDE.md rule 5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Category(str, Enum):
    BUG = "bug"
    SECURITY = "security"
    PERFORMANCE = "performance"
    TYPING = "typing"
    TEST_GAP = "test-gap"
    DESIGN = "design"
    READABILITY = "readability"


# More severe → lower index. Used by severity_meets_threshold.
_SEVERITY_ORDER: list[Severity] = [Severity.ERROR, Severity.WARNING, Severity.INFO]


def severity_meets_threshold(sev: Severity, threshold: Severity) -> bool:
    """True iff `sev` is at least as severe as `threshold`."""
    return _SEVERITY_ORDER.index(sev) <= _SEVERITY_ORDER.index(threshold)


@dataclass
class Location:
    file: str
    line_start: int | None = None
    line_end: int | None = None


@dataclass
class Finding:
    severity: Severity
    category: Category
    message: str
    location: Location | None = None
    suggestion: str | None = None


@dataclass
class Verdict:
    """Derived from findings; never asked of the model."""

    passed: bool
    threshold: Severity


@dataclass
class Review:
    summary: str
    findings: list[Finding] = field(default_factory=list)
    verdict: Verdict | None = None


def derive_verdict(findings: list[Finding], threshold: Severity) -> Verdict:
    """`passed=False` iff any finding meets-or-exceeds `threshold`."""
    has_blocking = any(severity_meets_threshold(f.severity, threshold) for f in findings)
    return Verdict(passed=not has_blocking, threshold=threshold)


# ---------------------------------------------------------------------------
# JSON adapter — emits the camelCase contract from ARCHITECTURE.md §4
# ---------------------------------------------------------------------------


def review_to_jsonable(review: Review) -> dict[str, Any]:
    """Map a Review to a JSON-ready dict matching the §4 contract.

    The Python field names use snake_case (`line_start`); the JSON uses
    camelCase (`lineStart`). This function is the only place the mapping
    lives.
    """
    return {
        "summary": review.summary,
        "findings": [_finding_to_jsonable(f) for f in review.findings],
        "verdict": _verdict_to_jsonable(review.verdict) if review.verdict else None,
    }


def _finding_to_jsonable(f: Finding) -> dict[str, Any]:
    out: dict[str, Any] = {
        "severity": f.severity.value,
        "category": f.category.value,
        "message": f.message,
    }
    if f.location is not None:
        out["location"] = _location_to_jsonable(f.location)
    if f.suggestion is not None:
        out["suggestion"] = f.suggestion
    return out


def _location_to_jsonable(loc: Location) -> dict[str, Any]:
    out: dict[str, Any] = {"file": loc.file}
    if loc.line_start is not None:
        out["lineStart"] = loc.line_start
    if loc.line_end is not None:
        out["lineEnd"] = loc.line_end
    return out


def _verdict_to_jsonable(v: Verdict) -> dict[str, Any]:
    return {"passed": v.passed, "threshold": v.threshold.value}


# ---------------------------------------------------------------------------
# Text rendering — human-readable view of a Review
# ---------------------------------------------------------------------------


def render_text(review: Review) -> str:
    """Human-readable rendering. The `--json` flag gets the raw dict instead."""
    parts: list[str] = []
    if review.findings:
        for f in review.findings:
            parts.append(_render_finding(f))
        parts.append("")
    parts.append(f"Summary: {review.summary}" if review.summary else "Summary: (none)")
    if review.verdict is not None:
        verdict_str = "PASS" if review.verdict.passed else "FAIL"
        parts.append(f"Verdict: {verdict_str} (threshold: {review.verdict.threshold.value})")
    return "\n".join(parts)


def _render_finding(f: Finding) -> str:
    head = f"[{f.severity.value}/{f.category.value}]"
    if f.location is not None:
        loc = f.location.file
        if f.location.line_start is not None:
            loc += f":{f.location.line_start}"
            if f.location.line_end is not None and f.location.line_end != f.location.line_start:
                loc += f"-{f.location.line_end}"
        head += f" {loc}"
    lines = [head, f"  {f.message}"]
    if f.suggestion is not None:
        lines.append(f"  → {f.suggestion}")
    return "\n".join(lines)
