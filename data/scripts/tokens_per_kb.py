#!/usr/bin/env python3
"""Char-vs-BPE compression measurement on the Phase 1 corpus.

Trains a few BPE tokenizers at different vocab sizes and reports:
  - tokens-per-KB (the headline compression metric)
  - bytes-per-token (the inverse, useful when thinking about context length)
  - training time for the BPE

Run: `uv run python data/scripts/tokens_per_kb.py [--corpus data/corpus.txt]`

This is the "char-vs-BPE compression lesson, made concrete" half of
M5's done-means. Output is plain text on stdout — paste into the
docs/results.md when running for a particular corpus.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Make the package importable when this is run as a plain script.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from codereview.bpe_tokenizer import BPETokenizer  # noqa: E402
from codereview.tokenizer import CharTokenizer  # noqa: E402


VOCAB_SIZES = [512, 1024, 2048, 4096, 8192]


def _fmt_int(n: int) -> str:
    return f"{n:,}"


def measure(corpus_path: Path) -> None:
    text = corpus_path.read_text(encoding="utf-8")
    byte_count = len(text.encode("utf-8"))
    kb = byte_count / 1024
    print(f"corpus: {corpus_path}  ({_fmt_int(byte_count)} bytes, {kb:,.1f} KB)")
    print()

    # --- char-level baseline ---
    t0 = time.perf_counter()
    char_tok = CharTokenizer.from_text(text)
    char_ids = char_tok.encode(text)
    char_dt = time.perf_counter() - t0
    print(
        f"char-level: vocab={char_tok.vocab_size:5d}  tokens={_fmt_int(len(char_ids))}  "
        f"tokens/KB={len(char_ids) / kb:8.2f}  bytes/token={byte_count / len(char_ids):.3f}  "
        f"train+encode={char_dt:.2f}s"
    )
    print()

    # --- BPE at increasing vocab sizes ---
    print(f"{'vocab':>6}  {'tokens':>14}  {'tokens/KB':>10}  {'B/tok':>6}  "
          f"{'compression':>12}  {'train s':>8}  {'encode s':>9}")
    print("-" * 78)
    for vocab_size in VOCAB_SIZES:
        t0 = time.perf_counter()
        bpe = BPETokenizer.train_from_text(text, vocab_size=vocab_size)
        train_dt = time.perf_counter() - t0
        t0 = time.perf_counter()
        ids = bpe.encode(text)
        enc_dt = time.perf_counter() - t0

        compression = len(char_ids) / len(ids)
        print(
            f"{bpe.vocab_size:6d}  {_fmt_int(len(ids)):>14}  {len(ids) / kb:10.2f}  "
            f"{byte_count / len(ids):6.3f}  {compression:11.2f}x  "
            f"{train_dt:8.1f}  {enc_dt:9.1f}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--corpus",
        type=Path,
        default=_REPO_ROOT / "data" / "corpus.txt",
        help="Path to the corpus text file (default: data/corpus.txt).",
    )
    args = parser.parse_args(argv)
    if not args.corpus.exists():
        parser.error(f"corpus not found: {args.corpus}")
    measure(args.corpus)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
