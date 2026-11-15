"""CLI for the ADR-029 dataset build.

Thin entrypoint lives at data/scripts/build_finetune_dataset.py. This module
loads the recipe + sources, clones/mines the repos, runs the teacher-backed
assembly, and writes three artifacts:

- <out>/dataset.jsonl          (git-ignored; the dataset itself)
- <out>/provenance.json        (git-ignored; head SHAs, teacher tag, seed)
- the composition report       (committed; the PR review artifact)

Teacher model + base_url must be pinned in the config's [teacher] table at
generation time (ADR-029); the API key comes from TEACHER_API_KEY.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

from codereview.finetune_build import SourceFiles, build_dataset
from codereview.finetune_mine import (
    ALLOWED_EXTENSIONS,
    MinedCommit,
    estimate_tokens,
    head_sha,
    mine_repo,
)
from codereview.finetune_serialize import write_jsonl
from codereview.finetune_teacher import Teacher, TeacherConfig

CHAT_EXTENSIONS = ALLOWED_EXTENSIONS | {".md"}
MAX_FILES_PER_REPO = 400
CLONE_DEPTH = 2000

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist", "build", ".next"}


def _resolve_repo(source: dict, cache_dir: Path) -> Path:
    if source["type"] == "path":
        return Path(source["path"]).expanduser()
    clone = cache_dir / source["name"]
    if not clone.exists():
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                str(CLONE_DEPTH),
                "--branch",
                source["ref"],
                source["url"],
                str(clone),
            ],
            check=True,
        )
    return clone


def _sample_files(repo: Path, max_file_tokens: int) -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    paths = sorted(
        p
        for p in repo.rglob("*")
        if p.is_file()
        and p.suffix.lower() in CHAT_EXTENSIONS
        and not any(part in _SKIP_DIRS for part in p.parts)
    )
    for p in paths[: MAX_FILES_PER_REPO * 3]:
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if not text.strip() or estimate_tokens(text) > max_file_tokens:
            continue
        files.append((str(p.relative_to(repo)), text))
        if len(files) >= MAX_FILES_PER_REPO:
            break
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the ADR-029 fine-tune dataset.")
    parser.add_argument("--config", type=Path, default=Path("configs/finetune_dataset.toml"))
    parser.add_argument("--sources", type=Path, default=Path("data/scripts/sources.toml"))
    parser.add_argument("--out", type=Path, default=Path("data/finetune"))
    parser.add_argument("--report", type=Path, default=Path("docs/finetune-composition-report.md"))
    parser.add_argument("--cache", type=Path, default=Path("data/finetune_cache"))
    args = parser.parse_args(argv)

    with args.config.open("rb") as f:
        config = tomllib.load(f)
    with args.sources.open("rb") as f:
        sources_toml = tomllib.load(f)

    teacher_cfg = config.get("teacher", {})
    api_key = os.environ.get("TEACHER_API_KEY", "")
    if not teacher_cfg.get("model") or not teacher_cfg.get("base_url") or not api_key:
        print(
            "teacher not pinned: set [teacher] model + base_url in the config "
            "and TEACHER_API_KEY in the environment (ADR-029).",
            file=sys.stderr,
        )
        return 2
    teacher = Teacher(
        TeacherConfig(
            base_url=teacher_cfg["base_url"],
            model=teacher_cfg["model"],
            api_key=api_key,
            temperature=teacher_cfg.get("temperature", 0.2),
        )
    )

    max_file_tokens = config["limits"]["max_file_tokens"]
    mined: list[MinedCommit] = []
    sources: list[SourceFiles] = []
    provenance: dict[str, str] = {}
    args.cache.mkdir(parents=True, exist_ok=True)
    for source in sources_toml["sources"]:
        repo = _resolve_repo(source, args.cache)
        name = source["name"]
        provenance[name] = head_sha(repo)
        mined += mine_repo(repo, name, max_file_tokens=max_file_tokens)
        sources.append(
            SourceFiles(
                repo=name,
                files=_sample_files(repo, max_file_tokens),
                owner=source.get("license") == "owner",
            )
        )
        print(f"{name}: {len(mined)} mined commits so far, HEAD {provenance[name][:12]}")

    records, report = build_dataset(mined, sources, teacher, config)
    floor = config["dataset"]["floor_total"]
    if len(records) < floor:
        print(f"only {len(records)} pairs survived the gates; floor is {floor}", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    write_jsonl(records, args.out / "dataset.jsonl")
    (args.out / "provenance.json").write_text(
        json.dumps(
            {
                "seed": config["dataset"]["seed"],
                "teacher_model": teacher_cfg["model"],
                "teacher_base_url": teacher_cfg["base_url"],
                "head_shas": provenance,
            },
            indent=2,
        )
        + "\n"
    )
    args.report.write_text(report)
    print(f"{len(records)} pairs -> {args.out / 'dataset.jsonl'}")
    print(f"composition report -> {args.report}")
    return 0
