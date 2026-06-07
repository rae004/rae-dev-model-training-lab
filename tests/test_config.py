from pathlib import Path

import pytest

from codereview.config import load_config

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_load_example_config() -> None:
    config = load_config(REPO_ROOT / "configs" / "example.toml")
    assert config["run"]["name"] == "example"
    assert config["run"]["seed"] == 1337
    assert config["device"]["preference"] == "auto"


def test_load_config_accepts_str_path() -> None:
    config = load_config(str(REPO_ROOT / "configs" / "example.toml"))
    assert "run" in config


def test_load_config_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_config(REPO_ROOT / "configs" / "does-not-exist.toml")
