"""Build the Phase 1 pretraining corpus from a sources.toml.

For a fixed sources.toml + fixed inputs, output bytes are byte-identical
across runs. The determinism contract is:
 - sources are sorted by `name`
 - files within a source are sorted by relative POSIX path
 - file content is concatenated with stable delimiters and a stable header
   identifying each file's origin

License enforcement is *out of scope*: the sources.toml records each
source's license per ADR-018, but the user is responsible for only listing
allowed-license sources. The script does not crawl or validate.

Source types:
 - `path`: copy from a local directory (recursive glob over `extensions`)
 - `git`:  shallow clone of `url` at `ref`, then treat like `path`
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_EXTENSIONS = [".py", ".ts", ".tsx"]
FILE_DELIMITER = "\n\n"

# Directory names pruned during corpus collection. Pruning is by name match
# at any depth (not by relative path), so a 'node_modules' inside a workspace
# package is also skipped. Override per-corpus via `ignore_dirs` in
# sources.toml when the default set is wrong for a given source.
DEFAULT_IGNORE_DIRS: frozenset[str] = frozenset({
    # Package / dependency directories
    "node_modules",
    ".venv", "venv", ".env", "env",
    # Build / generated output
    "dist", "build", "out", "target", "lib-cov",
    ".next", ".nuxt", ".turbo", ".cache", ".parcel-cache",
    # VCS internals
    ".git", ".hg", ".svn",
    # Tool caches
    "__pycache__",
    ".pytest_cache", ".ruff_cache", ".mypy_cache",
    # Test / coverage outputs
    "coverage", ".nyc_output", "htmlcov",
    # IDE / editor
    ".vscode", ".idea",
})


def _collect_files(
    root: Path, exts: list[str], ignore_dirs: frozenset[str] = DEFAULT_IGNORE_DIRS
) -> list[Path]:
    """Walk `root`, returning files matching `exts` sorted by relative path.

    Prunes any directory whose name matches `ignore_dirs` (e.g. node_modules,
    .venv, dist) so we don't descend into them at all.
    """
    ext_set = set(exts)
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune in-place — modifying dirnames stops os.walk from descending.
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs]
        for fname in filenames:
            if os.path.splitext(fname)[1] in ext_set:
                files.append(Path(dirpath) / fname)
    files.sort(key=lambda p: p.relative_to(root).as_posix())
    return files


def _render_source(
    source_name: str, root: Path, exts: list[str], ignore_dirs: frozenset[str]
) -> str:
    parts: list[str] = []
    for f in _collect_files(root, exts, ignore_dirs):
        rel = f.relative_to(root).as_posix()
        parts.append(f"# === {source_name}/{rel} ===\n")
        parts.append(f.read_text(encoding="utf-8", errors="replace"))
        parts.append(FILE_DELIMITER)
    return "".join(parts)


def _process_source(
    src: dict[str, Any], exts: list[str], ignore_dirs: frozenset[str]
) -> str:
    name = src["name"]
    kind = src["type"]
    if kind == "path":
        root = Path(src["path"]).expanduser().resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"source {name!r}: path {root} is not a directory")
        return _render_source(name, root, exts, ignore_dirs)
    if kind == "git":
        url = src["url"]
        ref = src.get("ref", "HEAD")
        with tempfile.TemporaryDirectory(prefix=f"corpus-{name}-") as tmp:
            subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", ref, url, tmp],
                check=True,
                capture_output=True,
            )
            return _render_source(name, Path(tmp), exts, ignore_dirs)
    raise ValueError(f"source {name!r}: unknown type {kind!r}")


def build_corpus(sources_toml: Path, output: Path) -> int:
    config = tomllib.loads(sources_toml.read_text(encoding="utf-8"))
    raw_sources = config.get("sources", [])
    sources = sorted(raw_sources, key=lambda s: s["name"])
    exts = config.get("extensions", DEFAULT_EXTENSIONS)
    ignore_override = config.get("ignore_dirs")
    ignore_dirs = (
        frozenset(ignore_override) if ignore_override is not None else DEFAULT_IGNORE_DIRS
    )

    chunks = [_process_source(src, exts, ignore_dirs) for src in sources]
    corpus = "".join(chunks)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(corpus, encoding="utf-8")
    return len(corpus)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="prep_corpus")
    parser.add_argument(
        "--sources",
        type=Path,
        default=Path("data/scripts/sources.toml"),
        help="Path to the sources.toml describing the corpus inputs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/corpus.txt"),
        help="Where to write the concatenated corpus.",
    )
    args = parser.parse_args(argv)
    size = build_corpus(args.sources, args.output)
    print(f"wrote {size} chars to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
