"""Tests for ADR-029 decline-pair derivation."""

from __future__ import annotations

import random

from codereview.finetune_decline import (
    SpecSource,
    TargetFile,
    derive_declines,
    is_non_applicable,
    spec_identifiers,
)


def test_spec_identifiers_intersects_spec_and_diff() -> None:
    spec = "Rename parse_header to read_header and update the docstring."
    changed = "def parse_header(raw):\n    read_header_impl(raw)\n"
    ids = spec_identifiers(spec, changed)
    assert "parse_header" in ids
    assert "docstring" not in ids  # not in the changed lines
    assert "update" not in ids  # stopword


def test_is_non_applicable_requires_identifiers() -> None:
    assert not is_non_applicable(set(), "anything")


def test_is_non_applicable_detects_presence() -> None:
    assert not is_non_applicable({"parse_header"}, "x = parse_header(y)\n")
    assert is_non_applicable({"parse_header"}, "x = compute_total(y)\n")


def _specs() -> list[SpecSource]:
    return [
        SpecSource(
            spec="Rename parse_header to read_header in the HTTP module.",
            repo="repo-a",
            identifiers=frozenset({"parse_header"}),
        ),
        SpecSource(
            spec="A spec with no concrete names.",
            repo="repo-a",
            identifiers=frozenset(),
        ),
    ]


def _files() -> list[TargetFile]:
    return [
        TargetFile(repo="repo-a", path="math.py", text="def add(a, b):\n    return a + b\n"),
        TargetFile(repo="repo-b", path="io.py", text="x = parse_header(y)\n"),
    ]


def test_derive_declines_builds_verified_pairs() -> None:
    declines = derive_declines(_specs(), _files(), random.Random(1), count=1)
    assert len(declines) == 1
    d = declines[0]
    assert d.target_path == "math.py"  # io.py contains parse_header -> rejected
    assert "parse_header" in d.spec
    assert d.file_text == _files()[0].text


def test_derive_declines_skips_identifierless_specs() -> None:
    specs = [s for s in _specs() if not s.identifiers]
    assert derive_declines(specs, _files(), random.Random(1), count=5) == []


def test_derive_declines_is_deterministic() -> None:
    a = derive_declines(_specs(), _files(), random.Random(42), count=3)
    b = derive_declines(_specs(), _files(), random.Random(42), count=3)
    assert a == b


def test_derive_declines_does_not_duplicate() -> None:
    declines = derive_declines(_specs(), _files(), random.Random(3), count=10)
    keys = [(d.spec, d.target_path) for d in declines]
    assert len(keys) == len(set(keys))
