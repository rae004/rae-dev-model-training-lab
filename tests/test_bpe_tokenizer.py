from pathlib import Path

import pytest

from codereview.bpe_tokenizer import (
    BPETokenizer,
    _count_pairs,
    _merge_pair,
    _train_incremental,
    _train_reference,
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


# ---------------------------------------------------------------------------
# Incremental algorithm: must match the reference byte-for-byte
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,vocab_size",
    [
        # Single-char repeats — exercises the overlapping-pair edge case
        ("aaaa", 260),
        ("a" * 50, 280),
        # Two-character alphabet
        ("ababab" * 10, 270),
        # Real ASCII with diverse pairs
        ("the quick brown fox jumps over the lazy dog", 280),
        ("the quick brown fox jumps over the lazy dog" * 20, 320),
        # UTF-8 with multi-byte chars
        ("naïve café résumé 漢字 🎉", 270),
        ("naïve café résumé 漢字 🎉" * 30, 300),
        # Code-shaped text (closer to real corpus)
        ("def foo(x):\n    return x + 1\n" * 25, 300),
        ("function add(a: number, b: number): number {\n  return a + b;\n}\n" * 20, 320),
        # Pathological: 'aaab aaab aaab ...' (chained overlapping merges)
        ("aaab " * 50, 280),
        # Edge: vocab_size exactly = 256 (no merges)
        ("anything", 256),
        # Edge: empty pair counts hit early
        ("abc", 400),
    ],
)
def test_incremental_matches_reference(text: str, vocab_size: int) -> None:
    """The optimized algorithm must produce identical merges to the
    reference implementation for any input + vocab_size."""
    ids = list(text.encode("utf-8"))
    ref = _train_reference(list(ids), vocab_size)
    fast = _train_incremental(list(ids), vocab_size)
    assert fast == ref, (
        f"divergence at first mismatch: ref[:5]={ref[:5]} vs fast[:5]={fast[:5]}"
    )


def test_incremental_overlapping_same_pair_in_aaaa() -> None:
    """Direct test of the tricky 'aaaa' case: merging (a, a) at positions 0
    and 2 must work; position 1 (overlapping) must be skipped."""
    text = "aaaa"
    merges = _train_incremental(list(text.encode("utf-8")), vocab_size=257)
    # First merge is necessarily (97, 97) → token 256.
    # After it, "aaaa" → [256, 256], which we don't merge again at this vocab.
    assert merges == [(97, 97)]


def test_incremental_chained_merges_produce_compression() -> None:
    """Sanity: training to a generous vocab on a small text should produce
    one token covering common substrings (the whole point of BPE)."""
    text = "the the the the the"
    tok = BPETokenizer.train_from_text(text, vocab_size=400)
    # 'the' should encode as a single token after training
    ids = tok.encode("the")
    assert len(ids) == 1, f"expected 'the' to compress to 1 token, got {ids}"


# ---------------------------------------------------------------------------
# Incremental encode: must match the reference byte-for-byte
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "train_text,encode_text,vocab_size",
    [
        # Train and encode on the same text — typical training-pipeline case
        ("the the the cat sat on the mat" * 30, "the the the cat sat on the mat" * 30, 300),
        # Encode on text the tokenizer was never trained on
        ("the the the cat sat on the mat" * 30, "completely different text", 300),
        # Overlapping same-pair edge case in encode input
        ("aaaa" * 50, "aaaa", 260),
        ("aaaa" * 50, "aaaaaaaaaaaaaaaaaaaa", 270),
        # Unicode round-trip via byte fallback
        ("naïve café résumé 漢字 🎉" * 10, "novel ümläüt αβγ ✨", 280),
        # Code-shaped text with rich merge structure
        (
            "def foo(x):\n    return x + 1\n" * 30,
            "def bar(y):\n    return y * 2\n",
            320,
        ),
        # Pathological: chain of overlapping merges within encode input
        ("aaab " * 50, "aaaaab aab b", 280),
        # Single-byte input — no pairs, immediate return
        ("hello", "x", 300),
        # Empty input — edge case
        ("hello world hello", "", 280),
    ],
)
def test_encode_incremental_matches_reference(
    train_text: str, encode_text: str, vocab_size: int
) -> None:
    """The fast encode must produce identical output to the reference encode
    for any (trained tokenizer, input text) pair."""
    tok = BPETokenizer.train_from_text(train_text, vocab_size=vocab_size)
    ref = tok._encode_reference(encode_text)
    fast = tok.encode(encode_text)
    assert fast == ref, (
        f"divergence: ref={ref[:20]}{'...' if len(ref) > 20 else ''} "
        f"vs fast={fast[:20]}{'...' if len(fast) > 20 else ''}"
    )


def test_encode_incremental_handles_empty_input() -> None:
    """Edge case: empty string must encode to empty list (not crash on n<2)."""
    tok = BPETokenizer.train_from_text("hello world", vocab_size=280)
    assert tok.encode("") == []


def test_encode_incremental_handles_single_byte_input() -> None:
    """Edge case: single byte has no pairs to merge."""
    tok = BPETokenizer.train_from_text("aaaa", vocab_size=260)
    # 'a' is byte 97
    assert tok.encode("a") == [97]


def test_encode_incremental_overlapping_same_pair_left_to_right() -> None:
    """For overlapping (a, a) merges in 'aaaa', the heap must process
    positions left-to-right so output matches the reference's greedy
    non-overlapping left-to-right behavior."""
    tok = BPETokenizer.train_from_text("aaaa" * 30, vocab_size=257)
    # Single merge learned: (a, a) → 256.
    # Encoding 'aaaaa' (5 a's): positions 0+1 merge to 256, positions 2+3
    # merge to 256, position 4 left alone → [256, 256, 97]
    result = tok.encode("aaaaa")
    assert result == [256, 256, 97]
