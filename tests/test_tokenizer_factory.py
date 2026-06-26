import pytest

from codereview.bpe_tokenizer import BPETokenizer
from codereview.tokenizer import CharTokenizer
from codereview.tokenizer_factory import (
    build_tokenizer,
    restore_tokenizer_from_state,
    tokenizer_to_state,
)


def test_build_char_tokenizer() -> None:
    tok = build_tokenizer("char", "the quick brown fox")
    assert isinstance(tok, CharTokenizer)
    # Vocab is the sorted set of unique chars
    assert tok.vocab_size == len(set("the quick brown fox"))


def test_build_bpe_tokenizer() -> None:
    tok = build_tokenizer("bpe", "the the the the the the", bpe_vocab_size=270)
    assert isinstance(tok, BPETokenizer)
    # 256 bytes + some merges; exact count depends on text but should be >= 256
    assert tok.vocab_size >= 256
    assert tok.vocab_size <= 270


def test_build_bpe_requires_vocab_size_or_path() -> None:
    with pytest.raises(ValueError, match="requires either bpe_path or bpe_vocab_size"):
        build_tokenizer("bpe", "abc abc")


def test_build_bpe_loads_from_path(tmp_path) -> None:
    """When bpe_path is provided, build_tokenizer loads it instead of
    training. The corpus text is ignored entirely."""
    # Train a small BPE and save it
    saved = BPETokenizer.train_from_text("the the the cat sat" * 30, 300)
    p = tmp_path / "tok.json"
    saved.save(p)

    # Build via path — pass a deliberately bogus text and no vocab_size
    loaded = build_tokenizer("bpe", text="UNUSED", bpe_path=p)
    assert isinstance(loaded, BPETokenizer)
    assert loaded.merges == saved.merges


def test_build_bpe_path_takes_priority_over_vocab_size(tmp_path) -> None:
    """If both bpe_path and bpe_vocab_size are given, path wins (no
    training happens). Useful for the M6 config which always loads
    from disk but might still carry a vocab_size for documentation."""
    saved = BPETokenizer.train_from_text("hello world hello", 280)
    p = tmp_path / "tok.json"
    saved.save(p)

    loaded = build_tokenizer("bpe", text="UNRELATED", bpe_vocab_size=999, bpe_path=p)
    # Vocab matches the loaded one, NOT 999
    assert loaded.vocab_size == saved.vocab_size


def test_build_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="unknown tokenizer_type"):
        build_tokenizer("sentencepiece", "abc")


def test_char_round_trip_through_state() -> None:
    original = CharTokenizer.from_text("the quick brown fox jumps over the lazy dog")
    tokenizer_type, state = tokenizer_to_state(original)
    assert tokenizer_type == "char"

    restored = restore_tokenizer_from_state(
        {"tokenizer_type": tokenizer_type, "tokenizer_state": state}
    )
    assert isinstance(restored, CharTokenizer)
    text = "the lazy dog"
    assert restored.encode(text) == original.encode(text)


def test_bpe_round_trip_through_state() -> None:
    original = BPETokenizer.train_from_text("the the the cat sat on the mat" * 30, 300)
    tokenizer_type, state = tokenizer_to_state(original)
    assert tokenizer_type == "bpe"
    # JSON-friendly: merges should be lists of ints, not tuples
    assert all(isinstance(p, list) for p in state["merges"])

    restored = restore_tokenizer_from_state(
        {"tokenizer_type": tokenizer_type, "tokenizer_state": state}
    )
    assert isinstance(restored, BPETokenizer)
    text = "the cat sat"
    assert restored.encode(text) == original.encode(text)


def test_legacy_checkpoint_without_tokenizer_type_is_char() -> None:
    """Pre-M6 checkpoints have only 'vocab' (no 'tokenizer_type'/'tokenizer_state').
    Loader must treat them as char so existing artifacts keep working."""
    legacy_ckpt = {"vocab": ["a", "b", "c", "d"], "model": "unused-by-this-test"}
    restored = restore_tokenizer_from_state(legacy_ckpt)
    assert isinstance(restored, CharTokenizer)
    assert restored.vocab == ["a", "b", "c", "d"]
    assert restored.encode("bad") == [1, 0, 3]


def test_restore_rejects_corrupt_payload() -> None:
    with pytest.raises(ValueError, match="neither"):
        restore_tokenizer_from_state({})
