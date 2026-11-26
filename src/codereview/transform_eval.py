"""Mechanical transform-eval harness (ADR-030, M11).

Scores a model's single-file transform outputs against ~20 hand-authored
cases in `eval/transform_set.toml`. Prompts reuse the exact serving format
(finetune_serialize.TRANSFORM_SYSTEM_PROMPT + user-prompt shape), so the
harness measures what rae-local-agent would actually receive.

Scoring is three mechanical booleans per case plus a runaway guard — no
judgment calls, no teacher model, no API cost beyond the backend call:

1. clean_apply — the output yields a unified diff against the input that
   passes `git apply --check`; declines require byte-identical output.
2. preserved — every non-targeted input line survives byte-for-byte, in
   order. "Targeted" is defined per case by `may_change` regexes over
   input lines; everything else is protected.
3. targeted — the asked-for change is present: every `must_match` regex
   matches the output and no `must_not_match` regex does.

Runaway guard: output exceeding 2x the input's estimated tokens is an
automatic fail regardless of content.

The raw completion is normalized exactly the way rae-local-agent's
serving path normalizes it before writing the file (transform.py
`_strip_fences`: outer markdown fences and a leading `FILE:` label are
tolerated and removed), then scored as the full file. Measuring the
pre-strip raw output would fail stock models almost entirely on a mode
serving already absorbs; the four documented failure modes this harness
exists to catch (fabrication, forbidden edits, interface narrowing,
runaway) all live in what remains after the strip.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codereview.backend import Backend
from codereview.finetune_build import unified_diff
from codereview.finetune_mine import estimate_tokens
from codereview.finetune_serialize import TRANSFORM_SYSTEM_PROMPT, _transform_user_prompt

RUNAWAY_FACTOR = 2

CATEGORIES = ("decline", "preservation_trap", "philosophy_anchor", "straight_transform")

# ADR-030 names the categories and asks for minimum counts; the counts
# themselves are this harness's choice (an ADR-030 explicit non-decision).
MIN_PER_CATEGORY = {
    "decline": 4,
    "preservation_trap": 4,
    "philosophy_anchor": 6,  # one per ADR-028 anchor + the named narrowing case
    "straight_transform": 4,
}

# ADR-030 calls out interface narrowing as a known semantic regression and
# requires a named case for it.
REQUIRED_CASE_NAMES = ("interface-narrowing-regression",)


@dataclass(frozen=True)
class TransformCase:
    name: str
    category: str
    description: str
    spec: str
    path: str
    input_text: str
    may_change: tuple[str, ...]
    must_match: tuple[str, ...]
    must_not_match: tuple[str, ...]


@dataclass(frozen=True)
class CaseResult:
    name: str
    category: str
    clean_apply: bool
    preserved: bool
    targeted: bool
    runaway: bool
    input_tokens: int
    output_tokens: int

    @property
    def passed(self) -> bool:
        return self.clean_apply and self.preserved and self.targeted and not self.runaway


def load_transform_set(path: Path) -> list[TransformCase]:
    with path.open("rb") as f:
        data = tomllib.load(f)
    cases = [
        TransformCase(
            name=c["name"],
            category=c["category"],
            description=c["description"],
            spec=c["spec"],
            path=c["path"],
            input_text=c["input"],
            may_change=tuple(c.get("may_change", [])),
            must_match=tuple(c.get("must_match", [])),
            must_not_match=tuple(c.get("must_not_match", [])),
        )
        for c in data["cases"]
    ]
    _validate_set(cases)
    return cases


def _validate_set(cases: list[TransformCase]) -> None:
    names = [c.name for c in cases]
    if len(names) != len(set(names)):
        raise ValueError("duplicate case names in transform set")
    for case in cases:
        if case.category not in CATEGORIES:
            raise ValueError(f"case {case.name!r}: unknown category {case.category!r}")
        if case.category == "decline" and (case.may_change or case.must_match):
            raise ValueError(f"decline case {case.name!r} must not target any change")
        if case.category != "decline" and not case.must_match:
            raise ValueError(f"case {case.name!r} needs at least one must_match assertion")
        if not case.input_text.endswith("\n"):
            raise ValueError(f"case {case.name!r}: input must end with a newline")
    per_category = {cat: sum(c.category == cat for c in cases) for cat in CATEGORIES}
    for cat, minimum in MIN_PER_CATEGORY.items():
        if per_category[cat] < minimum:
            raise ValueError(f"category {cat!r} has {per_category[cat]} cases; minimum {minimum}")
    for required in REQUIRED_CASE_NAMES:
        if required not in names:
            raise ValueError(f"required case {required!r} missing from transform set")


def normalize_output(raw: str) -> str:
    """Mirror rae-local-agent's serve-time cleanup (transform.py
    `_strip_fences` — keep in sync with that repo), then restore the
    final newline the strip removes: source files end with one, and the
    byte-identical decline comparison needs it back.
    """
    s = raw.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines)
    first_nl = s.find("\n")
    if first_nl != -1 and s[:first_nl].strip().startswith("FILE:"):
        s = s[first_nl + 1 :]
    if s and not s.endswith("\n"):
        s += "\n"
    return s


def clean_apply(case: TransformCase, output: str) -> bool:
    if output == case.input_text:
        # Byte-identical: required for declines, trivially applicable else.
        return True
    if case.category == "decline" or not output:
        return False
    # Fence lines surviving the serve-time strip (interior fences, or a
    # second code block) would land in the written file. The preservation
    # check alone can't catch them — they are additions, and additions
    # are otherwise legitimate.
    if any(line.strip().startswith("```") for line in output.splitlines()):
        return False
    diff = unified_diff(case.path, case.input_text, output)
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / case.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(case.input_text, encoding="utf-8")
        patch = Path(tmp) / "candidate.patch"
        patch.write_text(diff, encoding="utf-8")
        proc = subprocess.run(
            ["git", "apply", "--check", str(patch)],
            cwd=tmp,
            capture_output=True,
        )
    return proc.returncode == 0


def preserved(case: TransformCase, output: str) -> bool:
    protected = [
        line
        for line in case.input_text.splitlines()
        if not any(re.search(p, line) for p in case.may_change)
    ]
    out_lines = iter(output.splitlines())
    # Protected lines must survive byte-for-byte as an ordered subsequence;
    # targeted edits and legitimate additions may appear between them.
    for want in protected:
        for got in out_lines:
            if got == want:
                break
        else:
            return False
    return True


def targeted(case: TransformCase, output: str) -> bool:
    if case.category == "decline":
        return output == case.input_text
    if any(not re.search(p, output) for p in case.must_match):
        return False
    return not any(re.search(p, output) for p in case.must_not_match)


def score_case(case: TransformCase, raw_output: str) -> CaseResult:
    output = normalize_output(raw_output)
    input_tokens = estimate_tokens(case.input_text)
    output_tokens = estimate_tokens(output)
    return CaseResult(
        name=case.name,
        category=case.category,
        clean_apply=clean_apply(case, output),
        preserved=preserved(case, output),
        targeted=targeted(case, output),
        runaway=output_tokens > RUNAWAY_FACTOR * input_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def run_transform_eval(cases: list[TransformCase], backend: Backend) -> list[CaseResult]:
    results = []
    for case in cases:
        output = backend.generate(
            system=TRANSFORM_SYSTEM_PROMPT,
            user=_transform_user_prompt(case.spec, case.path, case.input_text),
        )
        results.append(score_case(case, output))
    return results


def render_report(results: list[CaseResult], *, model: str) -> str:
    total = len(results)
    passed = sum(r.passed for r in results)
    lines = [
        "# Transform eval report",
        "",
        f"Model: **{model}**",
        "",
        f"Overall pass rate: **{passed}/{total}** ({passed / total:.1%})",
        "",
        "## Per category",
        "",
        "| category | passed | total | rate |",
        "| --- | --- | --- | --- |",
    ]
    for cat in CATEGORIES:
        in_cat = [r for r in results if r.category == cat]
        ok = sum(r.passed for r in in_cat)
        lines.append(f"| {cat} | {ok} | {len(in_cat)} | {ok / len(in_cat):.1%} |")
    lines += [
        "",
        "## Per case",
        "",
        "| case | category | clean apply | preserved | targeted | runaway | pass |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        lines.append(
            f"| {r.name} | {r.category} | {_yn(r.clean_apply)} | {_yn(r.preserved)} "
            f"| {_yn(r.targeted)} | {_yn(not r.runaway, invert=True)} | "
            f"{'**pass**' if r.passed else 'FAIL'} |"
        )
    return "\n".join(lines) + "\n"


def _yn(ok: bool, *, invert: bool = False) -> str:
    if invert:
        return "ok" if ok else "**RUNAWAY**"
    return "yes" if ok else "**no**"


def results_to_jsonable(results: list[CaseResult]) -> list[dict[str, Any]]:
    return [
        {
            "name": r.name,
            "category": r.category,
            "clean_apply": r.clean_apply,
            "preserved": r.preserved,
            "targeted": r.targeted,
            "runaway": r.runaway,
            "passed": r.passed,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
        }
        for r in results
    ]
