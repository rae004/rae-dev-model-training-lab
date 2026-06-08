from pathlib import Path

import pytest

from codereview.sample import sample_from_checkpoint
from codereview.train import TrainConfig, run_training

REPO_ROOT = Path(__file__).resolve().parent.parent


def _smoke_train_cfg(out_dir: Path) -> TrainConfig:
    return TrainConfig(
        corpus_paths=[
            REPO_ROOT / "data" / "sample" / "sample.py",
            REPO_ROOT / "data" / "sample" / "sample.ts",
        ],
        val_fraction=0.1,
        block_size=32,
        n_layer=2,
        n_head=2,
        d_model=32,
        dropout=0.0,
        learning_rate=3e-3,
        min_learning_rate=3e-4,
        weight_decay=0.1,
        beta1=0.9,
        beta2=0.95,
        grad_clip=1.0,
        warmup_steps=5,
        max_steps=20,
        batch_size=8,
        eval_interval=20,
        eval_iters=2,
        log_interval=10,
        out_dir=out_dir,
        seed=1337,
        device="cpu",
    )


@pytest.fixture
def trained_checkpoint(tmp_path: Path) -> Path:
    run_training(_smoke_train_cfg(tmp_path / "run"))
    ckpt = tmp_path / "run" / "ckpt.pt"
    assert ckpt.exists()
    return ckpt


def test_sample_returns_prompt_plus_continuation(trained_checkpoint: Path) -> None:
    prompt = "def "
    out = sample_from_checkpoint(
        trained_checkpoint,
        prompt,
        max_new_tokens=20,
        temperature=0.8,
        top_k=10,
        device_pref="cpu",
        seed=42,
    )
    assert out.startswith(prompt)
    assert len(out) == len(prompt) + 20


def test_sample_is_deterministic_when_seeded(trained_checkpoint: Path) -> None:
    args = dict(
        prompt="class ",
        max_new_tokens=20,
        temperature=0.9,
        top_k=8,
        device_pref="cpu",
        seed=7,
    )
    a = sample_from_checkpoint(trained_checkpoint, **args)
    b = sample_from_checkpoint(trained_checkpoint, **args)
    assert a == b


def test_sample_empty_prompt_falls_back_to_first_vocab_char(trained_checkpoint: Path) -> None:
    out = sample_from_checkpoint(
        trained_checkpoint,
        "",
        max_new_tokens=10,
        device_pref="cpu",
        seed=0,
    )
    # Output is non-empty and exactly max_new_tokens + 1 (the seed char)
    assert len(out) == 11


def test_sample_rejects_unknown_prompt_char(trained_checkpoint: Path) -> None:
    # The sample data is ASCII Python/TS; a non-ASCII char won't be in vocab.
    with pytest.raises(KeyError):
        sample_from_checkpoint(
            trained_checkpoint,
            "héllo",  # é not in the corpus
            max_new_tokens=5,
            device_pref="cpu",
        )
