from pathlib import Path

import pytest

from codereview.tokenizer import CharTokenizer

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_PY = REPO_ROOT / "data" / "sample" / "sample.py"
SAMPLE_TS = REPO_ROOT / "data" / "sample" / "sample.ts"


def _sample_text() -> str:
    return SAMPLE_PY.read_text(encoding="utf-8") + SAMPLE_TS.read_text(encoding="utf-8")


def test_round_trip_on_sample_corpus() -> None:
    text = _sample_text()
    tok = CharTokenizer.from_text(text)
    assert tok.decode(tok.encode(text)) == text


def test_vocab_size_matches_unique_chars() -> None:
    text = _sample_text()
    tok = CharTokenizer.from_text(text)
    assert tok.vocab_size == len(set(text))


def test_vocab_is_sorted() -> None:
    tok = CharTokenizer.from_text("bca")
    assert tok.vocab == ["a", "b", "c"]


def test_encode_unknown_char_raises_keyerror() -> None:
    tok = CharTokenizer.from_text("abc")
    with pytest.raises(KeyError):
        tok.encode("abz")


def test_empty_input_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        CharTokenizer.from_text("")


def test_multichar_vocab_entry_rejected() -> None:
    with pytest.raises(ValueError, match="single characters"):
        CharTokenizer(["a", "bc"])
