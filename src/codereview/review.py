"""The frozen contract: `review(diff, config) -> Review`.

This module owns the **schema** (ARCHITECTURE.md §4, CLAUDE.md rule 3) and
the **derived-verdict** logic. Verdict is computed from findings against a
configurable severity threshold — the model is never asked separately.

Severity / Category enums and the threshold default are *(proposed)* per
ARCHITECTURE.md §4 — they live in config and are easy to change, never
silently changed (CLAUDE.md rule 5).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .backend import Backend


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


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class BackendConfig:
    type: str = "ollama"
    base_url: str = "http://workhorse:11434"
    model: str = "qwen2.5-coder"
    timeout: float = 60.0
    temperature: float = 0.2


@dataclass
class ReviewConfig:
    threshold: Severity = Severity.ERROR
    backend: BackendConfig = field(default_factory=BackendConfig)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ReviewConfig":
        b = d.get("backend", {})
        return cls(
            threshold=Severity(d.get("threshold", "error")),
            backend=BackendConfig(
                type=b.get("type", "ollama"),
                base_url=b.get("base_url", "http://workhorse:11434"),
                model=b.get("model", "qwen2.5-coder"),
                timeout=float(b.get("timeout", 60.0)),
                temperature=float(b.get("temperature", 0.2)),
            ),
        )


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


SYSTEM_PROMPT = """\
You are a senior software engineer reviewing a Python or TypeScript code diff.

Return a single JSON object exactly matching this schema, with no markdown \
fences or prose around it:

{
  "summary": "one-paragraph prose summary of the change",
  "findings": [
    {
      "severity": "error" | "warning" | "info",
      "category": "bug" | "security" | "performance" | "typing" | "test-gap" | "design" | "readability",
      "message": "what is wrong",
      "location": {"file": "path/to/file", "lineStart": 12, "lineEnd": 15},
      "suggestion": "how to fix it"
    }
  ]
}

Rules:
- `location` and `suggestion` are optional. Omit them if you can't tell precisely.
- `findings` may be empty — return [] if the diff looks good.
- Focus on judgment-level issues: bugs, security, missing tests, unclear design.
- Skip pure style or type errors — linters catch those.
- Output JSON only. No "Here is your review:" prose, no markdown fences.
"""


def build_prompt(diff: str) -> tuple[str, str]:
    """Return (system, user) prompt strings."""
    return SYSTEM_PROMPT, f"```diff\n{diff}\n```"


# ---------------------------------------------------------------------------
# Model output parsing
# ---------------------------------------------------------------------------


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def parse_model_output(text: str) -> dict[str, Any]:
    """Extract the first JSON object from model output.

    Tolerates markdown fences and leading/trailing prose. Raises ValueError
    if no JSON object can be located.
    """
    m = _FENCE_RE.search(text)
    if m:
        candidate = m.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("no JSON object found in model output")
        candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ValueError(f"malformed JSON in model output: {e}") from e


def parse_review_payload(data: dict[str, Any]) -> tuple[str, list[Finding]]:
    """Validate the parsed model output and convert to (summary, findings)."""
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object at top level, got {type(data).__name__}")

    summary = data.get("summary", "")
    if not isinstance(summary, str):
        raise ValueError(f"summary must be a string, got {type(summary).__name__}")

    findings_raw = data.get("findings", [])
    if not isinstance(findings_raw, list):
        raise ValueError(f"findings must be a list, got {type(findings_raw).__name__}")

    findings = [_parse_finding(f) for f in findings_raw]
    return summary, findings


def _parse_finding(d: Any) -> Finding:
    if not isinstance(d, dict):
        raise ValueError(f"finding must be a JSON object, got {type(d).__name__}")
    severity = _parse_enum(Severity, d.get("severity"), "severity")
    category = _parse_enum(Category, d.get("category"), "category")
    message = d.get("message", "")
    if not isinstance(message, str):
        raise ValueError("finding.message must be a string")
    suggestion = d.get("suggestion")
    if suggestion is not None and not isinstance(suggestion, str):
        raise ValueError("finding.suggestion must be a string or absent")
    return Finding(
        severity=severity,
        category=category,
        message=message,
        location=_parse_location(d.get("location")),
        suggestion=suggestion,
    )


def _parse_enum(enum_cls: type[Enum], value: Any, field_name: str) -> Any:
    if value is None:
        raise ValueError(f"missing required field: {field_name}")
    try:
        return enum_cls(value)
    except ValueError as e:
        valid = [m.value for m in enum_cls]
        raise ValueError(f"invalid {field_name} {value!r}; valid values: {valid}") from e


def _parse_location(d: Any) -> Location | None:
    if d is None:
        return None
    if not isinstance(d, dict):
        raise ValueError(f"location must be a JSON object, got {type(d).__name__}")
    file_field = d.get("file")
    if not isinstance(file_field, str) or not file_field:
        raise ValueError("location.file is required and must be a non-empty string")
    line_start = d.get("lineStart")
    line_end = d.get("lineEnd")
    if line_start is not None and not isinstance(line_start, int):
        raise ValueError("location.lineStart must be an integer or absent")
    if line_end is not None and not isinstance(line_end, int):
        raise ValueError("location.lineEnd must be an integer or absent")
    return Location(file=file_field, line_start=line_start, line_end=line_end)


# ---------------------------------------------------------------------------
# The frozen contract function
# ---------------------------------------------------------------------------


def build_backend(config: BackendConfig) -> "Backend":
    # Import here to keep review.py importable without urllib being loaded
    # by every test of pure-schema logic.
    from .backend import OllamaBackend

    if config.type == "ollama":
        return OllamaBackend(
            base_url=config.base_url,
            model=config.model,
            timeout=config.timeout,
            temperature=config.temperature,
        )
    raise ValueError(f"unknown backend type: {config.type!r}")


def review(diff: str, config: ReviewConfig, *, backend: "Backend | None" = None) -> Review:
    """The frozen contract — CLAUDE.md rule 3, ARCHITECTURE.md §3.

    Verdict is derived from findings; the model is never asked for it.
    A backend can be injected for tests; in production it's built from
    `config.backend`.
    """
    if backend is None:
        backend = build_backend(config.backend)
    system, user = build_prompt(diff)
    raw = backend.generate(system=system, user=user)
    data = parse_model_output(raw)
    summary, findings = parse_review_payload(data)
    return Review(
        summary=summary,
        findings=findings,
        verdict=derive_verdict(findings, config.threshold),
    )
