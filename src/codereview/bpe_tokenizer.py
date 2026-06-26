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

        Uses the incremental algorithm (`_train_incremental`); the result is
        byte-identical to the simple reference implementation
        (`_train_reference`) but ~100×+ faster for large corpora.
        """
        if vocab_size < _BYTE_VOCAB_SIZE:
            raise ValueError(
                f"vocab_size {vocab_size} must be at least {_BYTE_VOCAB_SIZE} (one per byte)"
            )
        if not text:
            raise ValueError("cannot train a tokenizer on empty text")

        merges = _train_incremental(list(text.encode("utf-8")), vocab_size)
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


def _best_pair(counts: dict[Pair, int]) -> tuple[Pair, int] | None:
    """Pick the highest-count pair with deterministic tie-break (pair asc)."""
    if not counts:
        return None
    best_pair: Pair | None = None
    best_key: tuple[int, int, int] | None = None
    for pair, cnt in counts.items():
        # Sort key: (count desc, then pair asc) — negate pair elements so
        # `max` picks the lexicographically smaller pair on count ties.
        key = (cnt, -pair[0], -pair[1])
        if best_key is None or key > best_key:
            best_key = key
            best_pair = pair
    assert best_pair is not None
    return best_pair, best_key[0]


def _train_reference(ids: list[int], vocab_size: int) -> list[Pair]:
    """Reference (slow) BPE training: O(N) per merge step.

    Kept as the authoritative correctness reference — `_train_incremental`'s
    output must equal this byte-identically for any input. Used in tests.
    """
    target_merges = vocab_size - _BYTE_VOCAB_SIZE
    merges: list[Pair] = []
    for _ in range(target_merges):
        counts = _count_pairs(ids)
        chosen = _best_pair(counts)
        if chosen is None:
            break
        best_pair, best_count = chosen
        if best_count < 2:
            break
        new_id = _BYTE_VOCAB_SIZE + len(merges)
        ids = _merge_pair(ids, best_pair, new_id)
        merges.append(best_pair)
    return merges


def _train_incremental(ids: list[int], vocab_size: int) -> list[Pair]:
    """Incremental BPE training: maintain pair counts and positions instead of
    re-scanning the whole token list per merge.

    Represents the working token stream as a doubly-linked list via parallel
    arrays (`next_idx`, `prev_idx`, `alive`) so a merge is O(1) per occurrence
    rather than O(N). Pair counts are updated only at the merge boundary —
    decrement the two adjacent pairs that contained the old tokens, increment
    the two new pairs that contain the merged id.

    Output is byte-identical to `_train_reference` for any input. The
    deterministic tie-break in `_best_pair` is what makes this guarantee hold.
    """
    target_merges = vocab_size - _BYTE_VOCAB_SIZE
    n = len(ids)

    # Linked-list representation:
    #   tokens[i] is the current token id at slot i
    #   alive[i] is False once slot i has been absorbed into a previous merge
    #   next_idx[i] / prev_idx[i] skip dead slots (treat n as the end sentinel)
    tokens = list(ids)
    alive = [True] * n
    next_idx = list(range(1, n + 1))  # next_idx[n-1] == n  (end of stream)
    prev_idx = [-1] + list(range(n - 1))  # prev_idx[0] == -1 (start of stream)

    # Initial counts and per-pair position sets (positions are LEFT-slot indices).
    pair_counts: dict[Pair, int] = {}
    pair_positions: dict[Pair, set[int]] = {}
    for i in range(n - 1):
        p = (tokens[i], tokens[i + 1])
        pair_counts[p] = pair_counts.get(p, 0) + 1
        pair_positions.setdefault(p, set()).add(i)

    def _decrement_pair(pair: Pair, pos: int) -> None:
        if pair not in pair_counts:
            return
        pair_counts[pair] -= 1
        positions = pair_positions.get(pair)
        if positions is not None:
            positions.discard(pos)
        if pair_counts[pair] <= 0:
            del pair_counts[pair]
            pair_positions.pop(pair, None)

    def _increment_pair(pair: Pair, pos: int) -> None:
        pair_counts[pair] = pair_counts.get(pair, 0) + 1
        pair_positions.setdefault(pair, set()).add(pos)

    merges: list[Pair] = []
    for _ in range(target_merges):
        chosen = _best_pair(pair_counts)
        if chosen is None:
            break
        best_pair, best_count = chosen
        if best_count < 2:
            break
        new_id = _BYTE_VOCAB_SIZE + len(merges)
        a, b = best_pair

        # Snapshot the positions because we mutate pair_positions during the loop.
        # Sorting makes the iteration order deterministic; overlapping same-pair
        # merges (e.g. (a,a) in "aaaa") MUST be processed left-to-right so each
        # one sees the correct surrounding context.
        positions = sorted(pair_positions.get(best_pair, ()))
        for left_i in positions:
            if not alive[left_i] or tokens[left_i] != a:
                continue
            right_i = next_idx[left_i]
            if right_i >= n or not alive[right_i] or tokens[right_i] != b:
                continue

            # Update the pair on the left boundary: (prev, a) → (prev, new_id)
            pi = prev_idx[left_i]
            if pi >= 0 and alive[pi]:
                _decrement_pair((tokens[pi], a), pi)
                _increment_pair((tokens[pi], new_id), pi)

            # Update the pair on the right boundary: (b, next) → (new_id, next)
            ni = next_idx[right_i]
            if ni < n and alive[ni]:
                _decrement_pair((b, tokens[ni]), right_i)
                _increment_pair((new_id, tokens[ni]), left_i)

            # Apply the merge: left slot becomes new_id, right slot dies.
            tokens[left_i] = new_id
            alive[right_i] = False
            next_idx[left_i] = ni
            if ni < n:
                prev_idx[ni] = left_i

        # The best_pair itself is fully consumed for this round.
        pair_counts.pop(best_pair, None)
        pair_positions.pop(best_pair, None)
        merges.append(best_pair)

    return merges
