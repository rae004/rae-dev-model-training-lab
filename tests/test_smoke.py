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
