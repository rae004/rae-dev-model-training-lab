#!/usr/bin/env python3
"""Train and save a BPE tokenizer on a corpus.

Run once per (corpus, vocab_size) pair. The saved JSON is small
(merge list only) and committed to `data/tokenizers/` so training
runs can load it instead of retraining each time.

Usage:
    uv run python data/scripts/pretrain_bpe.py \\
        --corpus data/corpus.txt \\
        --vocab-size 4096 \\
        --output data/tokenizers/bpe_4096.json
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from codereview.bpe_tokenizer import BPETokenizer  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--vocab-size", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    if not args.corpus.exists():
        parser.error(f"corpus not found: {args.corpus}")

    text = args.corpus.read_text(encoding="utf-8")
    n_bytes = len(text.encode("utf-8"))
    print(f"corpus: {args.corpus}  ({n_bytes:,} bytes)", file=sys.stderr)
    print(f"training BPE to vocab_size={args.vocab_size}...", file=sys.stderr)

    t0 = time.perf_counter()
    tok = BPETokenizer.train_from_text(text, vocab_size=args.vocab_size)
    train_dt = time.perf_counter() - t0
    print(
        f"trained vocab={tok.vocab_size} ({len(tok.merges)} merges) in {train_dt:.1f}s",
        file=sys.stderr,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    tok.save(args.output)
    out_bytes = args.output.stat().st_size
    print(f"wrote {args.output}  ({out_bytes:,} bytes)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
