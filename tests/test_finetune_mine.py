"""Tests for the ADR-029 commit miner against a synthetic git history."""

from __future__ import annotations

import pathlib
import subprocess

import pytest

from codereview.finetune_mine import estimate_tokens, head_sha, mine_repo


def _run(repo: pathlib.Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _commit(repo: pathlib.Path, message: str, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        _run(repo, "add", rel)
    _run(repo, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path: pathlib.Path) -> pathlib.Path:
    _run(tmp_path, "init", "-q")
    _run(tmp_path, "config", "user.email", "t@t")
    _run(tmp_path, "config", "user.name", "t")
    _commit(tmp_path, "initial", {"a.py": "x = 1\n", "b.ts": "const b = 1;\n"})
    return tmp_path


def test_mines_single_file_modification(repo: pathlib.Path) -> None:
    _commit(repo, "fix a", {"a.py": "x = 2\n"})

    mined = mine_repo(repo, "r", max_file_tokens=3500)
    assert len(mined) == 1
    m = mined[0]
    assert (m.repo, m.path, m.subject) == ("r", "a.py", "fix a")
    assert m.before == "x = 1\n"
    assert m.after == "x = 2\n"


def test_skips_multi_file_commits(repo: pathlib.Path) -> None:
    _commit(repo, "touch both", {"a.py": "x = 3\n", "b.ts": "const b = 2;\n"})
    assert mine_repo(repo, "r", max_file_tokens=3500) == []


def test_skips_added_files(repo: pathlib.Path) -> None:
    _commit(repo, "add new", {"c.py": "y = 1\n"})
    assert mine_repo(repo, "r", max_file_tokens=3500) == []


def test_skips_disallowed_extension(repo: pathlib.Path) -> None:
    _commit(repo, "docs", {"README.md": "hello\n"})
    _commit(repo, "edit docs", {"README.md": "hello world\n"})
    assert mine_repo(repo, "r", max_file_tokens=3500) == []


def test_skips_oversized_files(repo: pathlib.Path) -> None:
    big = "x = 1\n" * 2000  # 12000 bytes -> ~6000 tokens
    _commit(repo, "add big", {"big.py": big})
    _commit(repo, "edit big", {"big.py": big + "y = 2\n"})
    assert mine_repo(repo, "r", max_file_tokens=3500) == []


def test_respects_max_commits(repo: pathlib.Path) -> None:
    _commit(repo, "first edit", {"a.py": "x = 2\n"})
    _commit(repo, "second edit", {"a.py": "x = 3\n"})

    mined = mine_repo(repo, "r", max_file_tokens=3500, max_commits=1)
    assert [m.subject for m in mined] == ["second edit"]


def test_mining_is_deterministic(repo: pathlib.Path) -> None:
    _commit(repo, "e1", {"a.py": "x = 2\n"})
    _commit(repo, "e2", {"a.py": "x = 3\n"})
    assert mine_repo(repo, "r", max_file_tokens=3500) == mine_repo(repo, "r", max_file_tokens=3500)


def test_head_sha_is_a_commit(repo: pathlib.Path) -> None:
    sha = head_sha(repo)
    assert len(sha) == 40


def test_estimate_tokens_is_bytes_halved() -> None:
    assert estimate_tokens("abcd") == 2
