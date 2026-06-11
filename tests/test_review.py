"""Tests for the review() composition: prompt building, output parsing,
config, and the end-to-end flow with an injected fake backend."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from codereview.review import (
    BackendConfig,
    Category,
    ReviewConfig,
    Severity,
    build_prompt,
    parse_model_output,
    parse_review_payload,
    review,
)


# ---------------------------------------------------------------------------
# Fake backend used to drive review() without touching the network
# ---------------------------------------------------------------------------


@dataclass
class _FakeBackend:
    response: str
    received: dict[str, str] = field(default_factory=dict)

    def generate(self, *, system: str, user: str) -> str:
        self.received = {"system": system, "user": user}
        return self.response


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def test_build_prompt_wraps_diff_in_fence() -> None:
    diff = "diff --git a/foo b/foo\n@@ -1 +1 @@\n-old\n+new\n"
    system, user = build_prompt(diff)
    assert "JSON" in system  # the model knows to return JSON
    assert "severity" in system
    assert "category" in system
    assert "test-gap" in system  # kebab-case value is listed verbatim
    assert user.startswith("```diff\n")
    assert user.endswith("\n```")
    assert "old" in user and "new" in user


# ---------------------------------------------------------------------------
# parse_model_output: lenient JSON extraction
# ---------------------------------------------------------------------------


def test_parse_model_output_plain_json() -> None:
    text = '{"summary": "ok", "findings": []}'
    assert parse_model_output(text) == {"summary": "ok", "findings": []}


def test_parse_model_output_with_markdown_fence() -> None:
    text = 'Here is the review:\n```json\n{"summary": "ok", "findings": []}\n```\n'
    assert parse_model_output(text) == {"summary": "ok", "findings": []}


def test_parse_model_output_with_unlabeled_fence() -> None:
    text = '```\n{"summary": "ok", "findings": []}\n```'
    assert parse_model_output(text) == {"summary": "ok", "findings": []}


def test_parse_model_output_with_surrounding_prose() -> None:
    text = 'Sure, here you go:\n{"summary": "ok", "findings": []}\nLet me know if you need more.'
    assert parse_model_output(text) == {"summary": "ok", "findings": []}


def test_parse_model_output_no_json_raises() -> None:
    with pytest.raises(ValueError, match="no JSON object"):
        parse_model_output("the model decided not to respond in JSON")


def test_parse_model_output_malformed_json_raises() -> None:
    # Braces present so the locator finds *something*, but the contents are
    # not valid JSON — drives the json.JSONDecodeError branch specifically.
    with pytest.raises(ValueError, match="malformed JSON"):
        parse_model_output('{"summary": unquoted, "findings": []}')


# ---------------------------------------------------------------------------
# parse_review_payload: schema validation
# ---------------------------------------------------------------------------


def test_parse_review_payload_full_finding() -> None:
    data = {
        "summary": "looks ok",
        "findings": [
            {
                "severity": "warning",
                "category": "test-gap",
                "message": "No tests for X.",
                "location": {"file": "x.py", "lineStart": 10, "lineEnd": 20},
                "suggestion": "Add a test.",
            }
        ],
    }
    summary, findings = parse_review_payload(data)
    assert summary == "looks ok"
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == Severity.WARNING
    assert f.category == Category.TEST_GAP
    assert f.location is not None
    assert f.location.file == "x.py"
    assert f.location.line_start == 10
    assert f.location.line_end == 20
    assert f.suggestion == "Add a test."


def test_parse_review_payload_clean_review() -> None:
    summary, findings = parse_review_payload({"summary": "looks good", "findings": []})
    assert findings == []


def test_parse_review_payload_missing_required_severity_raises() -> None:
    data = {"summary": "x", "findings": [{"category": "bug", "message": "x"}]}
    with pytest.raises(ValueError, match="severity"):
        parse_review_payload(data)


def test_parse_review_payload_invalid_severity_raises() -> None:
    data = {
        "summary": "x",
        "findings": [{"severity": "critical", "category": "bug", "message": "x"}],
    }
    with pytest.raises(ValueError, match="invalid severity"):
        parse_review_payload(data)


def test_parse_review_payload_invalid_category_raises() -> None:
    data = {
        "summary": "x",
        "findings": [{"severity": "error", "category": "style", "message": "x"}],
    }
    with pytest.raises(ValueError, match="invalid category"):
        parse_review_payload(data)


def test_parse_review_payload_location_without_file_raises() -> None:
    data = {
        "summary": "x",
        "findings": [
            {
                "severity": "info",
                "category": "design",
                "message": "x",
                "location": {"lineStart": 5},
            }
        ],
    }
    with pytest.raises(ValueError, match="location.file"):
        parse_review_payload(data)


def test_parse_review_payload_summary_default_when_absent() -> None:
    summary, findings = parse_review_payload({"findings": []})
    assert summary == ""
    assert findings == []


# ---------------------------------------------------------------------------
# ReviewConfig
# ---------------------------------------------------------------------------


def test_review_config_defaults_match_proposed_section_4_values() -> None:
    cfg = ReviewConfig.from_dict({})
    assert cfg.threshold == Severity.ERROR
    assert cfg.backend.type == "ollama"
    assert cfg.backend.base_url == "http://workhorse:11434"


def test_review_config_overrides_threshold() -> None:
    cfg = ReviewConfig.from_dict({"threshold": "warning"})
    assert cfg.threshold == Severity.WARNING


def test_review_config_invalid_threshold_raises() -> None:
    with pytest.raises(ValueError):
        ReviewConfig.from_dict({"threshold": "critical"})


def test_review_config_backend_overrides() -> None:
    cfg = ReviewConfig.from_dict(
        {
            "threshold": "warning",
            "backend": {
                "type": "ollama",
                "base_url": "http://localhost:11434",
                "model": "codellama",
                "timeout": 10.0,
                "temperature": 0.5,
            },
        }
    )
    assert cfg.backend.base_url == "http://localhost:11434"
    assert cfg.backend.model == "codellama"
    assert cfg.backend.timeout == 10.0
    assert cfg.backend.temperature == 0.5


# ---------------------------------------------------------------------------
# review() — the contract function, end-to-end with a fake backend
# ---------------------------------------------------------------------------


def test_review_e2e_with_findings_derives_fail_verdict() -> None:
    model_json = """{
        "summary": "Has a real bug.",
        "findings": [
            {
                "severity": "error",
                "category": "bug",
                "message": "off by one",
                "location": {"file": "x.py", "lineStart": 5}
            }
        ]
    }"""
    backend = _FakeBackend(model_json)
    cfg = ReviewConfig(threshold=Severity.ERROR)
    result = review("dummy diff", cfg, backend=backend)

    assert result.summary == "Has a real bug."
    assert len(result.findings) == 1
    assert result.findings[0].severity == Severity.ERROR
    assert result.verdict is not None
    assert result.verdict.passed is False
    assert result.verdict.threshold == Severity.ERROR

    # The diff arrived in the user prompt
    assert "dummy diff" in backend.received["user"]


def test_review_e2e_clean_review_passes() -> None:
    backend = _FakeBackend('{"summary": "lgtm", "findings": []}')
    cfg = ReviewConfig(threshold=Severity.ERROR)
    result = review("d", cfg, backend=backend)
    assert result.summary == "lgtm"
    assert result.findings == []
    assert result.verdict is not None
    assert result.verdict.passed is True


def test_review_e2e_threshold_warning_makes_warnings_block() -> None:
    backend = _FakeBackend(
        '{"summary":"x","findings":[{"severity":"warning","category":"design","message":"x"}]}'
    )
    cfg = ReviewConfig(threshold=Severity.WARNING)
    result = review("d", cfg, backend=backend)
    assert result.verdict is not None
    assert result.verdict.passed is False
    assert result.verdict.threshold == Severity.WARNING


def test_review_e2e_handles_fenced_model_output() -> None:
    backend = _FakeBackend('```json\n{"summary":"ok","findings":[]}\n```')
    cfg = ReviewConfig(threshold=Severity.ERROR)
    result = review("d", cfg, backend=backend)
    assert result.summary == "ok"


def test_review_e2e_malformed_model_output_raises() -> None:
    backend = _FakeBackend("not json at all")
    cfg = ReviewConfig(threshold=Severity.ERROR)
    with pytest.raises(ValueError):
        review("d", cfg, backend=backend)


def test_review_passes_config_temperature_through_build_backend() -> None:
    cfg = ReviewConfig(
        threshold=Severity.ERROR,
        backend=BackendConfig(temperature=0.42, base_url="http://example:11434"),
    )
    # We don't run the network, just confirm build_backend produces a backend
    # carrying the config values.
    from codereview.backend import OllamaBackend
    from codereview.review import build_backend

    backend = build_backend(cfg.backend)
    assert isinstance(backend, OllamaBackend)
    assert backend.temperature == 0.42
    assert backend.base_url == "http://example:11434"


def test_build_backend_rejects_unknown_type() -> None:
    from codereview.review import build_backend

    with pytest.raises(ValueError, match="unknown backend type"):
        build_backend(BackendConfig(type="cohere"))
