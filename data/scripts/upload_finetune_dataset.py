#!/usr/bin/env python3
"""Upload the built dataset to a HuggingFace Hub private dataset repo.

Run with:
    uv run python data/scripts/upload_finetune_dataset.py --run-tag <tag>

Requires HF_TOKEN in the environment (write scope). Uploads dataset.jsonl +
provenance.json from data/finetune/ to rae004/qlora-dataset-<run-tag>,
creating the private repo if needed (ADR-026 / ADR-029).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("data/finetune"))
    parser.add_argument("--repo-prefix", default="rae004/qlora-dataset")
    args = parser.parse_args(argv)

    token = os.environ.get("HF_TOKEN", "")
    if not token:
        print("HF_TOKEN not set (needs write scope).", file=sys.stderr)
        return 2
    dataset = args.data_dir / "dataset.jsonl"
    if not dataset.exists():
        print(f"{dataset} not found - run build_finetune_dataset.py first.", file=sys.stderr)
        return 2

    from huggingface_hub import HfApi

    api = HfApi(token=token)
    repo_id = f"{args.repo_prefix}-{args.run_tag}"
    api.create_repo(repo_id=repo_id, repo_type="dataset", private=True, exist_ok=True)
    for name in ("dataset.jsonl", "provenance.json"):
        path = args.data_dir / name
        if path.exists():
            api.upload_file(
                path_or_fileobj=str(path),
                path_in_repo=name,
                repo_id=repo_id,
                repo_type="dataset",
            )
            print(f"uploaded {name} -> {repo_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
