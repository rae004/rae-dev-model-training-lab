"""Decline-pair derivation for the ADR-029 anti-fabrication slice.

A decline pair is `(spec, file) -> file unchanged byte-for-byte`: the spec
genuinely does not apply to the file, and the correct output is the input.
It exists because the stock model has no learned "do nothing" response —
the fabricated no-op failure mode documented on rae-local-agent.

Only commit-mined specs qualify. Mutation-rule specs are generic ("remove
noise comments") and could legitimately apply to almost any file; a decline
built from one would teach the model to ignore applicable specs. A
commit-mined spec names concrete identifiers, which makes non-applicability
checkable: if none of the identifiers the spec shares with its source diff
occur in the target file, the spec has nothing to do there.

Targets from the same repo are preferred — the vocabulary is close but the
named identifiers are genuinely absent, which is exactly the near-miss hard
negative ADR-029 asks for.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")

# Words that appear in prose and code alike; useless as applicability evidence.
_STOPWORDS = frozenset(
    """
    the and for not with this that from into are was were has have had can
    could should would will when where which while whose after before return
    returns function functions method methods class classes file files line
    lines code change changes changed add adds added remove removes removed
    rename renamed update updates updated use uses used instead value values
    type types test tests import imports def const let var new old all one
    """.split()
)


@dataclass(frozen=True)
class DeclinePair:
    spec: str
    file_text: str  # the ground-truth output is this exact text
    source_repo: str
    target_repo: str
    target_path: str


def spec_identifiers(spec: str, changed_text: str) -> set[str]:
    """Identifiers the spec shares with its source diff's changed lines.

    These are the concrete names that make the spec *about* its source file;
    their absence elsewhere is the non-applicability evidence.
    """
    spec_words = {w for w in _WORD.findall(spec) if w.lower() not in _STOPWORDS}
    changed_words = set(_WORD.findall(changed_text))
    return spec_words & changed_words


def is_non_applicable(identifiers: set[str], file_text: str) -> bool:
    """True when none of the spec's identifiers occur in the file."""
    if not identifiers:
        return False  # nothing concrete to check -> cannot verify; skip
    file_words = set(_WORD.findall(file_text))
    return not (identifiers & file_words)


@dataclass(frozen=True)
class SpecSource:
    spec: str
    repo: str
    identifiers: frozenset[str]


@dataclass(frozen=True)
class TargetFile:
    repo: str
    path: str
    text: str


def derive_declines(
    specs: list[SpecSource],
    files: list[TargetFile],
    rng: random.Random,
    count: int,
) -> list[DeclinePair]:
    """Build up to `count` verified decline pairs.

    For each sampled spec, same-repo target files are tried before
    cross-repo ones. A (spec source-repo, target path) combination is used
    at most once so the slice doesn't collapse into near-duplicates.
    """
    declines: list[DeclinePair] = []
    used: set[tuple[str, str, str]] = set()
    usable = [s for s in specs if s.identifiers]
    if not usable or not files:
        return declines
    attempts = 0
    max_attempts = count * 20
    while len(declines) < count and attempts < max_attempts:
        attempts += 1
        spec = rng.choice(usable)
        same_repo = [f for f in files if f.repo == spec.repo]
        pool = same_repo if same_repo and rng.random() < 0.7 else files
        target = rng.choice(pool)
        key = (spec.repo, spec.spec[:80], target.path)
        if key in used:
            continue
        if not is_non_applicable(set(spec.identifiers), target.text):
            continue
        used.add(key)
        declines.append(
            DeclinePair(
                spec=spec.spec,
                file_text=target.text,
                source_repo=spec.repo,
                target_repo=target.repo,
                target_path=target.path,
            )
        )
    return declines
