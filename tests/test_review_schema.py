import json

import pytest

from codereview.review import (
    Category,
    Finding,
    Location,
    Review,
    Severity,
    derive_verdict,
    render_text,
    review_to_jsonable,
    severity_meets_threshold,
)


# ---------------------------------------------------------------------------
# Severity ordering
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sev,threshold,expected",
    [
        (Severity.ERROR, Severity.ERROR, True),
        (Severity.ERROR, Severity.WARNING, True),
        (Severity.ERROR, Severity.INFO, True),
        (Severity.WARNING, Severity.ERROR, False),
        (Severity.WARNING, Severity.WARNING, True),
        (Severity.WARNING, Severity.INFO, True),
        (Severity.INFO, Severity.ERROR, False),
        (Severity.INFO, Severity.WARNING, False),
        (Severity.INFO, Severity.INFO, True),
    ],
)
def test_severity_meets_threshold(sev: Severity, threshold: Severity, expected: bool) -> None:
    assert severity_meets_threshold(sev, threshold) is expected


# ---------------------------------------------------------------------------
# Verdict derivation — the heart of CLAUDE.md rule 3
# ---------------------------------------------------------------------------


def _finding(severity: Severity, category: Category = Category.BUG) -> Finding:
    return Finding(severity=severity, category=category, message="x")


def test_empty_findings_is_pass_at_any_threshold() -> None:
    # The LGTM path: clean review is a first-class result.
    for t in Severity:
        v = derive_verdict([], threshold=t)
        assert v.passed is True
        assert v.threshold == t


def test_one_error_fails_at_error_threshold() -> None:
    v = derive_verdict([_finding(Severity.ERROR)], threshold=Severity.ERROR)
    assert v.passed is False


def test_one_warning_passes_at_error_threshold() -> None:
    v = derive_verdict([_finding(Severity.WARNING)], threshold=Severity.ERROR)
    assert v.passed is True


def test_one_warning_fails_at_warning_threshold() -> None:
    v = derive_verdict([_finding(Severity.WARNING)], threshold=Severity.WARNING)
    assert v.passed is False


def test_one_info_passes_at_warning_threshold() -> None:
    v = derive_verdict([_finding(Severity.INFO)], threshold=Severity.WARNING)
    assert v.passed is True


def test_mixed_findings_fail_if_any_meets_threshold() -> None:
    findings = [_finding(Severity.INFO), _finding(Severity.ERROR), _finding(Severity.WARNING)]
    v = derive_verdict(findings, threshold=Severity.ERROR)
    assert v.passed is False


# ---------------------------------------------------------------------------
# JSON adapter — schema fields go out as camelCase to match the §4 contract
# ---------------------------------------------------------------------------


def test_jsonable_matches_architecture_section_4_example() -> None:
    review = Review(
        summary=(
            "Adds retry logic to the API client. Sound overall, but the retry "
            "loop can mask a permanent auth failure, and the exhausted-retries "
            "path is untested."
        ),
        findings=[
            Finding(
                severity=Severity.ERROR,
                category=Category.BUG,
                message=(
                    "Retries on 401 responses, so an invalid token retries until "
                    "timeout instead of failing fast."
                ),
                location=Location(file="src/client.ts", line_start=42, line_end=48),
                suggestion="Treat 401/403 as non-retryable and surface the error immediately.",
            ),
            Finding(
                severity=Severity.WARNING,
                category=Category.TEST_GAP,
                message="No test covers the path where all retries are exhausted.",
                location=Location(file="src/client.ts"),
            ),
        ],
    )
    review.verdict = derive_verdict(review.findings, threshold=Severity.ERROR)

    out = review_to_jsonable(review)

    # Schema-level shape
    assert set(out.keys()) == {"summary", "findings", "verdict"}
    assert out["verdict"] == {"passed": False, "threshold": "error"}

    # First finding has the full location with line_start + line_end
    f1 = out["findings"][0]
    assert f1["severity"] == "error"
    assert f1["category"] == "bug"
    assert f1["location"] == {"file": "src/client.ts", "lineStart": 42, "lineEnd": 48}
    assert "suggestion" in f1

    # Second finding has only the file (no line numbers, no suggestion)
    f2 = out["findings"][1]
    assert f2["category"] == "test-gap"  # kebab-case enum value
    assert f2["location"] == {"file": "src/client.ts"}
    assert "lineStart" not in f2["location"]
    assert "suggestion" not in f2

    # And the whole thing is valid JSON
    json.dumps(out)


def test_jsonable_omits_optional_location_when_absent() -> None:
    review = Review(
        summary="ok",
        findings=[
            Finding(severity=Severity.INFO, category=Category.READABILITY, message="hi"),
        ],
    )
    review.verdict = derive_verdict(review.findings, threshold=Severity.ERROR)
    out = review_to_jsonable(review)
    assert "location" not in out["findings"][0]
    assert "suggestion" not in out["findings"][0]


def test_jsonable_empty_findings_clean_review() -> None:
    review = Review(summary="Looks good.", findings=[])
    review.verdict = derive_verdict([], threshold=Severity.ERROR)
    out = review_to_jsonable(review)
    assert out == {
        "summary": "Looks good.",
        "findings": [],
        "verdict": {"passed": True, "threshold": "error"},
    }


# ---------------------------------------------------------------------------
# Text rendering
# ---------------------------------------------------------------------------


def test_render_text_includes_findings_summary_verdict() -> None:
    review = Review(
        summary="Has problems.",
        findings=[
            Finding(
                severity=Severity.ERROR,
                category=Category.BUG,
                message="Off by one.",
                location=Location(file="foo.py", line_start=10),
                suggestion="Use len(xs) instead.",
            )
        ],
    )
    review.verdict = derive_verdict(review.findings, threshold=Severity.ERROR)
    text = render_text(review)
    assert "[error/bug] foo.py:10" in text
    assert "Off by one." in text
    assert "→ Use len(xs) instead." in text
    assert "Summary: Has problems." in text
    assert "Verdict: FAIL (threshold: error)" in text


def test_render_text_clean_review_says_pass() -> None:
    review = Review(summary="Looks good.", findings=[])
    review.verdict = derive_verdict([], threshold=Severity.ERROR)
    text = render_text(review)
    assert "Summary: Looks good." in text
    assert "Verdict: PASS (threshold: error)" in text
    # No finding stanzas
    assert "/bug]" not in text
    assert "/error]" not in text


def test_render_text_line_range_when_end_differs() -> None:
    review = Review(
        summary="x",
        findings=[
            Finding(
                severity=Severity.WARNING,
                category=Category.DESIGN,
                message="Big function.",
                location=Location(file="a.py", line_start=10, line_end=120),
            )
        ],
    )
    review.verdict = derive_verdict(review.findings, threshold=Severity.ERROR)
    text = render_text(review)
    assert "a.py:10-120" in text
