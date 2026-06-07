"""Train/val split and batch sampler for char-level pretraining.

Stays plain-Python: M2 doesn't need torch yet. The loader yields
(inputs, targets) as nested lists of ints; M3 will convert to tensors
at the model boundary.

Split is sequential (first 1-val_fraction of the token stream is train,
the rest is val). That's the convention for char-level pretraining —
no shuffling at the token level, since adjacency carries signal.
"""

from __future__ import annotations

import random
from collections.abc import Iterator


def split_train_val(token_ids: list[int], val_fraction: float) -> tuple[list[int], list[int]]:
    if not 0.0 < val_fraction < 1.0:
        raise ValueError(f"val_fraction must be in (0, 1); got {val_fraction}")
    n_train = int(len(token_ids) * (1.0 - val_fraction))
    if n_train == 0 or n_train == len(token_ids):
        raise ValueError(
            f"split leaves one side empty: len={len(token_ids)}, val_fraction={val_fraction}"
        )
    return token_ids[:n_train], token_ids[n_train:]


def iter_batches(
    token_ids: list[int],
    block_size: int,
    batch_size: int,
    seed: int,
) -> Iterator[tuple[list[list[int]], list[list[int]]]]:
    """Yield (x, y) batches forever, where each x[i] is a block_size window of
    token_ids and y[i] is the same window shifted by one (next-token targets).
    """
    if block_size <= 0:
        raise ValueError(f"block_size must be positive; got {block_size}")
    if batch_size <= 0:
        raise ValueError(f"batch_size must be positive; got {batch_size}")
    max_start = len(token_ids) - block_size - 1
    if max_start < 0:
        raise ValueError(
            f"token stream too short for block_size: len={len(token_ids)}, "
            f"block_size={block_size}"
        )

    rng = random.Random(seed)
    while True:
        xs: list[list[int]] = []
        ys: list[list[int]] = []
        for _ in range(batch_size):
            i = rng.randint(0, max_start)
            xs.append(token_ids[i : i + block_size])
            ys.append(token_ids[i + 1 : i + 1 + block_size])
        yield xs, ys
