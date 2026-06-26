"""Common tokenizer dispatch for `train` and `sample`.

The two concrete tokenizers (`CharTokenizer`, `BPETokenizer`) already share
the same external contract (`encode`, `decode`, `vocab_size`). This module
adds two more pieces: building one from a TrainConfig + corpus, and
(de)serializing one into the checkpoint payload.

Checkpoint format (forwards-compatible):

```
{
    "tokenizer_type": "char" | "bpe",
    "tokenizer_state": {...},
    # Legacy compat (older char-only checkpoints, before M6 prep):
    "vocab": [...],                     # also still written for char today
}
```

Older char-only checkpoints have only `vocab` — `restore_tokenizer_from_state`
treats a missing `tokenizer_type` as `"char"` and rebuilds from `vocab`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .bpe_tokenizer import BPETokenizer
from .tokenizer import CharTokenizer


@runtime_checkable
class Tokenizer(Protocol):
    """Minimal contract — shared by CharTokenizer and BPETokenizer."""

    @property
    def vocab_size(self) -> int: ...

    def encode(self, text: str) -> list[int]: ...

    def decode(self, ids: list[int]) -> str: ...


def build_tokenizer(
    tokenizer_type: str,
    text: str,
    *,
    bpe_vocab_size: int | None = None,
    bpe_path: Path | str | None = None,
) -> Tokenizer:
    """Train (or load) a tokenizer per `tokenizer_type`.

    For "char": vocab is the sorted set of unique characters in `text`.
    For "bpe":
      - If `bpe_path` is given, load the saved BPE from disk and ignore
        `bpe_vocab_size` and `text`. This is the M6 path — train BPE
        once per corpus with `data/scripts/pretrain_bpe.py`, commit
        the artifact, then load it for each subsequent model run.
      - Otherwise, train BPE up to `bpe_vocab_size` (required) on `text`.
    """
    if tokenizer_type == "char":
        return CharTokenizer.from_text(text)
    if tokenizer_type == "bpe":
        if bpe_path is not None:
            return BPETokenizer.load(bpe_path)
        if bpe_vocab_size is None:
            raise ValueError(
                "tokenizer_type='bpe' requires either bpe_path or bpe_vocab_size"
            )
        return BPETokenizer.train_from_text(text, vocab_size=bpe_vocab_size)
    raise ValueError(f"unknown tokenizer_type: {tokenizer_type!r}")


def tokenizer_to_state(tok: Tokenizer) -> tuple[str, dict[str, Any]]:
    """Return (tokenizer_type, tokenizer_state) suitable for save_checkpoint."""
    if isinstance(tok, CharTokenizer):
        return "char", {"vocab": tok.vocab}
    if isinstance(tok, BPETokenizer):
        # Serialize each pair as a list for JSON-friendliness (torch.save uses
        # pickle so tuples work too, but lists make the saved state explicit).
        return "bpe", {"merges": [list(pair) for pair in tok.merges]}
    raise TypeError(f"unknown tokenizer concrete type: {type(tok).__name__}")


def restore_tokenizer_from_state(ckpt: dict[str, Any]) -> Tokenizer:
    """Rebuild the tokenizer from a checkpoint dict.

    Handles:
    - New format with `tokenizer_type` + `tokenizer_state`
    - Legacy format with only `vocab` (assumed char-level)
    """
    tokenizer_type = ckpt.get("tokenizer_type")
    if tokenizer_type is None:
        # Legacy: pre-M6 char-only checkpoints have just `vocab`.
        legacy_vocab = ckpt.get("vocab")
        if legacy_vocab is None:
            raise ValueError(
                "checkpoint has neither 'tokenizer_type' nor legacy 'vocab' key"
            )
        return CharTokenizer(legacy_vocab)

    state = ckpt.get("tokenizer_state", {})
    if tokenizer_type == "char":
        return CharTokenizer(state["vocab"])
    if tokenizer_type == "bpe":
        merges = [tuple(pair) for pair in state["merges"]]
        return BPETokenizer(merges)
    raise ValueError(f"unknown tokenizer_type in checkpoint: {tokenizer_type!r}")
