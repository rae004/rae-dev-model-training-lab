from pathlib import Path

import pytest

from codereview.bpe_tokenizer import (
    BPETokenizer,
    _count_pairs,
    _merge_pair,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_count_pairs_simple() -> None:
    # 'aaab' as bytes → [97, 97, 97, 98]
    # pairs: (97,97), (97,97), (97,98)
    counts = _count_pairs([97, 97, 97, 98])
    assert counts[(97, 97)] == 2
    assert counts[(97, 98)] == 1


def test_count_pairs_empty_and_singleton() -> None:
    assert _count_pairs([]) == {}
    assert _count_pairs([5]) == {}


def test_merge_pair_replaces_non_overlapping() -> None:
    # Merging (1, 1) in [1, 1, 1, 1] → [256, 256], NOT [256, 1, 1]
    assert _merge_pair([1, 1, 1, 1], (1, 1), 256) == [256, 256]


def test_merge_pair_replaces_only_matching() -> None:
    assert _merge_pair([1, 2, 3, 2, 1], (2, 3), 256) == [1, 256, 2, 1]


def test_merge_pair_no_match() -> None:
    assert _merge_pair([1, 2, 3], (4, 5), 256) == [1, 2, 3]


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def test_train_rejects_vocab_below_byte_floor() -> None:
    with pytest.raises(ValueError, match="at least 256"):
        BPETokenizer.train_from_text("aaa", vocab_size=200)


def test_train_rejects_empty_text() -> None:
    with pytest.raises(ValueError, match="empty"):
        BPETokenizer.train_from_text("", vocab_size=300)


def test_train_grows_to_target_vocab_when_text_supports_it() -> None:
    # 'abcabcabc...' has plenty of pairs to merge
    text = "abc" * 100
    tok = BPETokenizer.train_from_text(text, vocab_size=260)
    # 256 byte tokens + 4 merges = 260
    assert tok.vocab_size == 260
    assert len(tok.merges) == 4


def test_train_stops_early_when_no_repeated_pairs_remain() -> None:
    # Three distinct bytes, each appearing exactly once → zero merges possible
    text = "abc"
    tok = BPETokenizer.train_from_text(text, vocab_size=400)
    assert tok.vocab_size == 256  # no merges learned
    assert tok.merges == []


def test_train_is_deterministic() -> None:
    text = "the quick brown fox jumps over the lazy dog" * 50
    a = BPETokenizer.train_from_text(text, vocab_size=300)
    b = BPETokenizer.train_from_text(text, vocab_size=300)
    assert a.merges == b.merges


def test_train_learns_obvious_repeats_first() -> None:
    # 'th' appears very often in this text; should be among the first merges.
    text = "the th th the the th" * 100
    tok = BPETokenizer.train_from_text(text, vocab_size=260)
    # 't' is byte 116, 'h' is byte 104 — so we expect (116, 104) in merges
    assert (116, 104) in tok.merges


# ---------------------------------------------------------------------------
# Encode / decode round-trip
# ---------------------------------------------------------------------------


def test_round_trip_ascii() -> None:
    text = "def foo(x):\n    return x + 1\n"
    tok = BPETokenizer.train_from_text(text, vocab_size=280)
    assert tok.decode(tok.encode(text)) == text


def test_round_trip_unicode() -> None:
    # Non-ASCII chars: BPE on bytes must round-trip via UTF-8.
    text = "naïve café — résumé · 𝛼β + 中文 🎉"
    tok = BPETokenizer.train_from_text(text, vocab_size=280)
    assert tok.decode(tok.encode(text)) == text


def test_round_trip_on_unseen_text() -> None:
    # A BPE trained on one text must still round-trip ANY UTF-8 string —
    # bytes 0..255 are always in vocab.
    tok = BPETokenizer.train_from_text("aaaaaa", vocab_size=260)
    novel = "completely unseen text including ümläuts and 漢字"
    assert tok.decode(tok.encode(novel)) == novel


def test_encode_compresses_seen_corpus() -> None:
    """A trained BPE should produce *fewer* tokens than raw bytes for the
    text it was trained on (which is the whole point)."""
    text = "the the the the the the the the the the"
    raw_byte_count = len(text.encode("utf-8"))
    tok = BPETokenizer.train_from_text(text, vocab_size=270)
    encoded = tok.encode(text)
    assert len(encoded) < raw_byte_count


def test_decode_rejects_unknown_id() -> None:
    tok = BPETokenizer.train_from_text("abc", vocab_size=300)
    with pytest.raises(ValueError, match="unknown token id"):
        tok.decode([99999])


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_save_load_round_trip(tmp_path: Path) -> None:
    text = "function add(a: number, b: number): number { return a + b; }" * 20
    original = BPETokenizer.train_from_text(text, vocab_size=320)
    path = tmp_path / "tok.json"
    original.save(path)

    loaded = BPETokenizer.load(path)
    assert loaded.merges == original.merges
    assert loaded.vocab_size == original.vocab_size

    # And encoding produces the same ids
    assert loaded.encode(text) == original.encode(text)


def test_load_rejects_unknown_version(tmp_path: Path) -> None:
    path = tmp_path / "tok.json"
    path.write_text('{"version": 42, "merges": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="unknown BPE tokenizer format"):
        BPETokenizer.load(path)
