#!/usr/bin/env python3
"""Thin entrypoint that delegates to codereview.corpus_prep:main.

Run with: `uv run python data/scripts/prep_corpus.py [--sources ...] [--output ...]`
"""

from codereview.corpus_prep import main

if __name__ == "__main__":
    raise SystemExit(main())
