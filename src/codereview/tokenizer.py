"""Char-level tokenizer for Phase 1.

Vocabulary is the sorted set of unique characters in the training text. There
is no UNK token: by construction, every character seen at train time round-trips
exactly. Characters never seen at train time raise KeyError on encode — that's
deliberate, so silent data drift can't slip through.
"""

from __future__ import annotations

from collections.abc import Iterable


class CharTokenizer:
    def __init__(self, chars: Iterable[str]) -> None:
        unique = sorted(set(chars))
        if not unique:
            raise ValueError("cannot build a tokenizer from empty input")
        for c in unique:
            if len(c) != 1:
                raise ValueError(f"vocab entries must be single characters, got {c!r}")
        self._stoi: dict[str, int] = {c: i for i, c in enumerate(unique)}
        self._itos: dict[int, str] = {i: c for i, c in enumerate(unique)}

    @classmethod
    def from_text(cls, text: str) -> "CharTokenizer":
        return cls(text)

    @property
    def vocab_size(self) -> int:
        return len(self._stoi)

    @property
    def vocab(self) -> list[str]:
        return [self._itos[i] for i in range(self.vocab_size)]

    def encode(self, text: str) -> list[int]:
        return [self._stoi[c] for c in text]

    def decode(self, ids: Iterable[int]) -> str:
        return "".join(self._itos[i] for i in ids)
