"""Commit mining for the ADR-029 transform slice.

Walks a git repository's history for single-file modification commits and
extracts `(before, after, subject)` triples. The human-authored after-file is
the ground-truth output of a transform pair; the teacher model later writes
the task spec from the diff but never touches the code (ADR-029).

Determinism: mining is deterministic for a given HEAD — callers record
`head_sha()` in the composition report so a run is reproducible against the
same clone state. Branch refs in sources.toml drift over time; the recorded
SHA is the provenance anchor.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

ALLOWED_EXTENSIONS = frozenset({".py", ".ts", ".tsx"})

_RECORD_SEP = "\x01"
_FIELD_SEP = "\x1f"


def estimate_tokens(text: str) -> int:
    """~2 bytes per token for code (measured in data/scripts/tokens_per_kb.py)."""
    return len(text.encode("utf-8")) // 2


@dataclass(frozen=True)
class MinedCommit:
    repo: str
    sha: str
    path: str
    subject: str
    before: str
    after: str


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _show(repo: Path, ref: str, path: str) -> str | None:
    """Blob contents at `ref`, or None if missing or not valid UTF-8."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "show", f"{ref}:{path}"],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return None
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


def head_sha(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").strip()


def mine_repo(
    repo: Path,
    name: str,
    *,
    extensions: frozenset[str] = ALLOWED_EXTENSIONS,
    max_file_tokens: int,
    max_commits: int = 2000,
) -> list[MinedCommit]:
    """Mine up to `max_commits` of recent history for transform candidates.

    A candidate commit modifies exactly one file (status M — adds, deletes,
    and renames are not transforms) with an allowed extension, both blob
    versions decode as UTF-8, differ, and fit under `max_file_tokens`
    (ADR-029: spec + file + output must fit the 8192-token sequence).
    """
    log = _git(
        repo,
        "log",
        "--no-merges",
        "--name-status",
        f"--format={_RECORD_SEP}%H{_FIELD_SEP}%s",
        "-n",
        str(max_commits),
    )
    mined: list[MinedCommit] = []
    for record in log.split(_RECORD_SEP):
        record = record.strip("\n")
        if not record:
            continue
        header, _, rest = record.partition("\n")
        sha, _, subject = header.partition(_FIELD_SEP)
        changes = [line for line in rest.splitlines() if line.strip()]
        if len(changes) != 1:
            continue
        status, _, path = changes[0].partition("\t")
        if status != "M" or Path(path).suffix.lower() not in extensions:
            continue
        before = _show(repo, f"{sha}^", path)
        after = _show(repo, sha, path)
        if before is None or after is None or before == after:
            continue
        if max(estimate_tokens(before), estimate_tokens(after)) > max_file_tokens:
            continue
        mined.append(
            MinedCommit(repo=name, sha=sha, path=path, subject=subject, before=before, after=after)
        )
    return mined
