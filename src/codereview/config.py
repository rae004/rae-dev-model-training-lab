import tomllib
from pathlib import Path
from typing import Any


def load_config(path: Path | str) -> dict[str, Any]:
    with Path(path).open("rb") as f:
        return tomllib.load(f)
