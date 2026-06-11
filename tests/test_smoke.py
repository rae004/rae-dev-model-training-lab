"""End-to-end checks that the package is importable and the CLI runs."""

import subprocess
import sys

from codereview import __version__
from codereview.__main__ import main


def test_version_is_a_string() -> None:
    assert isinstance(__version__, str)
    assert __version__


def test_main_returns_zero_with_no_args() -> None:
    assert main([]) == 0


def test_module_help_runs() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "codereview", "--help"],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert b"codereview" in result.stdout
    assert b"train" in result.stdout


def test_train_subcommand_help_runs() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "codereview", "train", "--help"],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert b"--config" in result.stdout
    assert b"--device" in result.stdout
    assert b"--resume" in result.stdout


def test_sample_subcommand_help_runs() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "codereview", "sample", "--help"],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert b"--checkpoint" in result.stdout
    assert b"--prompt" in result.stdout
    assert b"--max-new-tokens" in result.stdout
    assert b"--top-k" in result.stdout


def test_review_subcommand_help_runs() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "codereview", "review", "--help"],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert b"--config" in result.stdout
    assert b"--json" in result.stdout
    assert b"--threshold" in result.stdout
    assert b"--backend-url" in result.stdout
    assert b"--model" in result.stdout


def test_review_subcommand_empty_stdin_exits_2() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "codereview", "review"],
        input=b"",
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert b"no diff on stdin" in result.stderr
