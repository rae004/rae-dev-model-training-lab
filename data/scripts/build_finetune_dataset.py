#!/usr/bin/env python3
"""Thin entrypoint that delegates to codereview.finetune_cli:main.

Run with: `uv run python data/scripts/build_finetune_dataset.py [--config ...]`
Requires TEACHER_API_KEY in the environment and a pinned [teacher] table in
configs/finetune_dataset.toml (ADR-029).
"""

from codereview.finetune_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
