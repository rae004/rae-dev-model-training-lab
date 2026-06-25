"""Byte-pair encoding tokenizer for Phase 1.

Operates on **bytes** (UTF-8 encoded) rather than codepoints — there are
exactly 256 starting tokens and any UTF-8 text round-trips by construction,
so there is no UNK token. Same external contract as CharTokenizer:
`encode(text) -> list[int]` and `decode(ids) -> text`.

This is the from-scratch reference implementation called out in
ADR-016 / M5: it's deliberately simple and slow (O(N) per merge step over
the corpus) so the algorithm is legible. For Phase 2 we'd swap to a
performant tokenizer (tiktoken, sentencepiece, HuggingFace `tokenizers`).

Algorithm:
 1. Tokenize the training text into its raw byte ids (0–255).
 2. Repeatedly find the most frequent adjacent pair and merge it into
    a new token id (256, 257, ...) until vocab_size is reached or no
    pair occurs more than once.
 3. Save the ordered merge list. Encoding new text replays the merges
    in order; decoding looks each id back to its byte sequence.

The "ordered merge list" is the key data structure: token id 257 = the
merge of (a, b) where a and b are themselves tokens (possibly previously
merged), so the decode table is recursive — built once at construction.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


_BYTE_VOCAB_SIZE = 256
Pair = tuple[int, int]


class BPETokenizer:
    """A byte-level byte-pair encoding tokenizer.

    Construct with the ordered list of merges (or use `train_from_text`).
    Every byte 0..255 is always in the vocab; merges add ids 256, 257, ...
    """

    def __init__(self, merges: list[Pair]) -> None:
        # The merge list IS the model. Persisting just `merges` and rebuilding
        # the lookup tables on init keeps the on-disk format small and stable.
        self._merges: list[Pair] = list(merges)

        # rank[(a, b)] = order in which the merge was learned. Used in encode
        # to pick the lowest-rank applicable merge at each step.
        self._rank: dict[Pair, int] = {pair: i for i, pair in enumerate(merges)}

        # For decode: every token id maps to a tuple of raw bytes.
        self._id_to_bytes: dict[int, bytes] = {i: bytes([i]) for i in range(_BYTE_VOCAB_SIZE)}
        for i, (a, b) in enumerate(merges):
            self._id_to_bytes[_BYTE_VOCAB_SIZE + i] = self._id_to_bytes[a] + self._id_to_bytes[b]

    # ----- factories --------------------------------------------------

    @classmethod
    def train_from_text(cls, text: str, vocab_size: int) -> "BPETokenizer":
        """Train a BPE tokenizer on `text`, growing the vocab to `vocab_size`.

        Stops early if no remaining pair occurs more than once (no further
        information to gain from merging).
        """
        if vocab_size < _BYTE_VOCAB_SIZE:
            raise ValueError(
                f"vocab_size {vocab_size} must be at least {_BYTE_VOCAB_SIZE} (one per byte)"
            )
        if not text:
            raise ValueError("cannot train a tokenizer on empty text")

        ids: list[int] = list(text.encode("utf-8"))
        target_merges = vocab_size - _BYTE_VOCAB_SIZE
        merges: list[Pair] = []

        for _ in range(target_merges):
            counts = _count_pairs(ids)
            if not counts:
                break
            best_pair, best_count = max(
                counts.items(),
                # Tie-break by (count desc, pair asc) so training is deterministic.
                key=lambda item: (item[1], -item[0][0], -item[0][1]),
            )
            if best_count < 2:
                break
            new_id = _BYTE_VOCAB_SIZE + len(merges)
            ids = _merge_pair(ids, best_pair, new_id)
            merges.append(best_pair)

        return cls(merges)

    @classmethod
    def load(cls, path: Path | str) -> "BPETokenizer":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("version") != 1:
            raise ValueError(f"unknown BPE tokenizer format: {data.get('version')!r}")
        merges = [tuple(pair) for pair in data["merges"]]
        return cls(merges)

    # ----- public properties -----------------------------------------

    @property
    def vocab_size(self) -> int:
        return _BYTE_VOCAB_SIZE + len(self._merges)

    @property
    def merges(self) -> list[Pair]:
        return list(self._merges)

    # ----- encode / decode -------------------------------------------

    def encode(self, text: str) -> list[int]:
        """Greedy lowest-rank-first merging. Returns token ids."""
        ids: list[int] = list(text.encode("utf-8"))
        while len(ids) >= 2:
            # Pick the pair in ids with the lowest learned-merge rank.
            best_rank = None
            best_pair: Pair | None = None
            for pair in zip(ids, ids[1:]):
                rank = self._rank.get(pair)
                if rank is not None and (best_rank is None or rank < best_rank):
                    best_rank = rank
                    best_pair = pair
            if best_pair is None:
                break
            new_id = _BYTE_VOCAB_SIZE + best_rank  # type: ignore[operator]
            ids = _merge_pair(ids, best_pair, new_id)
        return ids

    def decode(self, ids: list[int]) -> str:
        out = bytearray()
        for token_id in ids:
            if token_id not in self._id_to_bytes:
                raise ValueError(
                    f"unknown token id {token_id}; vocab is 0..{self.vocab_size - 1}"
                )
            out.extend(self._id_to_bytes[token_id])
        return out.decode("utf-8", errors="strict")

    # ----- persistence -----------------------------------------------

    def save(self, path: Path | str) -> None:
        Path(path).write_text(
            json.dumps({"version": 1, "merges": [list(p) for p in self._merges]}),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# Pure helpers (top-level so they're easy to unit-test in isolation)
# ---------------------------------------------------------------------------


def _count_pairs(ids: list[int]) -> Counter[Pair]:
    """Count adjacent token pairs in `ids`."""
    counts: Counter[Pair] = Counter()
    for a, b in zip(ids, ids[1:]):
        counts[(a, b)] += 1
    return counts


def _merge_pair(ids: list[int], pair: Pair, new_id: int) -> list[int]:
    """Replace every non-overlapping occurrence of `pair` in `ids` with `new_id`."""
    out: list[int] = []
    i = 0
    n = len(ids)
    while i < n:
        if i + 1 < n and ids[i] == pair[0] and ids[i + 1] == pair[1]:
            out.append(new_id)
            i += 2
        else:
            out.append(ids[i])
            i += 1
    return out
