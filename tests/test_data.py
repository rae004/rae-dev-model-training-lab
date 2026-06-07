import itertools
from pathlib import Path

import pytest

from codereview.data import iter_batches, split_train_val
from codereview.tokenizer import CharTokenizer

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_PY = REPO_ROOT / "data" / "sample" / "sample.py"
SAMPLE_TS = REPO_ROOT / "data" / "sample" / "sample.ts"


def _sample_ids() -> list[int]:
    text = SAMPLE_PY.read_text(encoding="utf-8") + SAMPLE_TS.read_text(encoding="utf-8")
    return CharTokenizer.from_text(text).encode(text)


def test_split_90_10_lengths() -> None:
    ids = list(range(1000))
    train, val = split_train_val(ids, val_fraction=0.1)
    assert len(train) == 900
    assert len(val) == 100
    assert train + val == ids


def test_split_rejects_out_of_range_fraction() -> None:
    with pytest.raises(ValueError, match="val_fraction"):
        split_train_val([1, 2, 3], val_fraction=0.0)
    with pytest.raises(ValueError, match="val_fraction"):
        split_train_val([1, 2, 3], val_fraction=1.0)


def test_split_rejects_when_one_side_empty() -> None:
    # Short stream + high val_fraction floors the train side to zero.
    with pytest.raises(ValueError, match="empty"):
        split_train_val([1, 2], val_fraction=0.9)


def test_iter_batches_shape_from_sample() -> None:
    ids = _sample_ids()
    block_size = 64
    batch_size = 4
    batches = iter_batches(ids, block_size=block_size, batch_size=batch_size, seed=1337)
    xs, ys = next(batches)
    assert len(xs) == batch_size
    assert len(ys) == batch_size
    for x, y in zip(xs, ys, strict=True):
        assert len(x) == block_size
        assert len(y) == block_size


def test_iter_batches_targets_are_inputs_shifted_by_one() -> None:
    ids = _sample_ids()
    batches = iter_batches(ids, block_size=16, batch_size=2, seed=0)
    xs, ys = next(batches)
    for x, y in zip(xs, ys, strict=True):
        assert x[1:] == y[:-1]


def test_iter_batches_is_deterministic_for_fixed_seed() -> None:
    ids = _sample_ids()
    a = list(itertools.islice(iter_batches(ids, 32, 4, seed=42), 3))
    b = list(itertools.islice(iter_batches(ids, 32, 4, seed=42), 3))
    assert a == b


def test_iter_batches_rejects_short_stream() -> None:
    with pytest.raises(ValueError, match="too short"):
        next(iter_batches([1, 2, 3], block_size=8, batch_size=1, seed=0))
