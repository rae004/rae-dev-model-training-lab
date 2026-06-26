from pathlib import Path

import pytest
import torch

from codereview.train import (
    TrainConfig,
    estimate_loss,
    load_checkpoint,
    lr_at_step,
    resolve_device,
    run_training,
    seed_everything,
)
from codereview.model import GPT, GPTConfig
from codereview.tokenizer import CharTokenizer

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Helpers under test (pure)
# ---------------------------------------------------------------------------


def test_resolve_device_cpu() -> None:
    assert resolve_device("cpu") == torch.device("cpu")


def test_resolve_device_auto_falls_back_to_cpu_when_no_cuda() -> None:
    if torch.cuda.is_available():
        pytest.skip("CUDA is available; this test only meaningful on CPU-only hosts")
    assert resolve_device("auto") == torch.device("cpu")


def test_resolve_device_cuda_errors_when_unavailable() -> None:
    if torch.cuda.is_available():
        pytest.skip("CUDA is available; can't exercise the error path")
    with pytest.raises(RuntimeError, match="is_available"):
        resolve_device("cuda")


def test_resolve_device_rejects_unknown_preference() -> None:
    with pytest.raises(ValueError, match="unknown device"):
        resolve_device("tpu")


def test_lr_warmup_then_cosine_to_min() -> None:
    kwargs = dict(warmup_steps=10, max_steps=100, max_lr=1.0, min_lr=0.1)
    assert lr_at_step(0, **kwargs) == pytest.approx(0.1)
    assert lr_at_step(9, **kwargs) == pytest.approx(1.0)
    # Halfway through cosine decay → mean of max and min
    midpoint = lr_at_step(55, **kwargs)
    assert midpoint == pytest.approx(0.55, abs=1e-6)
    assert lr_at_step(99, **kwargs) == pytest.approx(0.1, abs=1e-3)
    # Past max_steps clamps to min
    assert lr_at_step(500, **kwargs) == pytest.approx(0.1)


def test_seed_everything_makes_torch_reproducible() -> None:
    seed_everything(7)
    a = torch.randn(3)
    seed_everything(7)
    b = torch.randn(3)
    torch.testing.assert_close(a, b)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def test_smoke_config_loads() -> None:
    cfg = TrainConfig.from_dict(_load_toml(REPO_ROOT / "configs" / "smoke.toml"))
    assert cfg.max_steps == 100
    assert cfg.seed == 1337
    assert cfg.device == "auto"


def test_spec_config_loads() -> None:
    cfg = TrainConfig.from_dict(_load_toml(REPO_ROOT / "configs" / "char_step1.toml"))
    assert cfg.n_layer == 4
    assert cfg.block_size == 128


def _load_toml(path: Path) -> dict:
    import tomllib

    return tomllib.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Eval
# ---------------------------------------------------------------------------


def test_estimate_loss_returns_train_and_val_means() -> None:
    seed_everything(0)
    text = (REPO_ROOT / "data" / "sample" / "sample.py").read_text(encoding="utf-8")
    tok = CharTokenizer.from_text(text)
    ids = tok.encode(text)
    train_ids, val_ids = ids[:1500], ids[1500:]

    model = GPT(
        GPTConfig(vocab_size=tok.vocab_size, block_size=16, n_layer=1, n_head=1, d_model=16)
    )
    losses = estimate_loss(
        model,
        train_ids,
        val_ids,
        block_size=16,
        batch_size=4,
        eval_iters=2,
        device=torch.device("cpu"),
        seed=42,
    )
    assert set(losses.keys()) == {"train", "val"}
    assert losses["train"] > 0
    assert losses["val"] > 0


# ---------------------------------------------------------------------------
# End-to-end smoke
# ---------------------------------------------------------------------------


def _smoke_train_cfg(out_dir: Path, *, max_steps: int = 100, seed: int = 1337) -> TrainConfig:
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
        warmup_steps=10,
        max_steps=max_steps,
        batch_size=8,
        eval_interval=50,
        eval_iters=5,
        log_interval=20,
        out_dir=out_dir,
        seed=seed,
        device="cpu",
    )


def test_smoke_loss_decreases(tmp_path: Path) -> None:
    cfg = _smoke_train_cfg(tmp_path / "run")
    result = run_training(cfg, writer_dir=tmp_path / "tb")

    initial = result["initial_eval"]["train"]
    final = result["final_eval"]["train"]
    assert final < initial, f"loss did not decrease: initial={initial:.4f} final={final:.4f}"
    assert (tmp_path / "run" / "ckpt.pt").exists()


def test_smoke_deterministic_for_same_seed(tmp_path: Path) -> None:
    cfg_a = _smoke_train_cfg(tmp_path / "a", max_steps=40, seed=42)
    cfg_b = _smoke_train_cfg(tmp_path / "b", max_steps=40, seed=42)
    a = run_training(cfg_a, writer_dir=tmp_path / "tba")
    b = run_training(cfg_b, writer_dir=tmp_path / "tbb")

    assert a["final_eval"]["train"] == pytest.approx(b["final_eval"]["train"], rel=1e-5)
    assert a["final_eval"]["val"] == pytest.approx(b["final_eval"]["val"], rel=1e-5)


def test_smoke_different_seeds_give_different_results(tmp_path: Path) -> None:
    a = run_training(_smoke_train_cfg(tmp_path / "a", max_steps=40, seed=1))
    b = run_training(_smoke_train_cfg(tmp_path / "b", max_steps=40, seed=2))
    assert a["final_eval"]["train"] != b["final_eval"]["train"]


# ---------------------------------------------------------------------------
# Checkpoint round-trip and resume
# ---------------------------------------------------------------------------


def test_checkpoint_contains_state_step_config_and_vocab(tmp_path: Path) -> None:
    cfg = _smoke_train_cfg(tmp_path / "run", max_steps=20)
    run_training(cfg)
    ckpt = load_checkpoint(tmp_path / "run" / "ckpt.pt", device=torch.device("cpu"))
    assert ckpt["step"] == 20
    assert "model" in ckpt and len(ckpt["model"]) > 0
    assert "optimizer" in ckpt
    assert ckpt["config"]["seed"] == cfg.seed
    assert len(ckpt["vocab"]) > 0


def test_resume_continues_training_and_loss_keeps_decreasing(tmp_path: Path) -> None:
    # Train initial chunk
    cfg_a = _smoke_train_cfg(tmp_path / "run", max_steps=30)
    first = run_training(cfg_a)
    mid_loss = first["final_eval"]["train"]

    # Resume from the checkpoint and train more
    cfg_b = _smoke_train_cfg(tmp_path / "run", max_steps=80)
    cont = run_training(cfg_b, resume_from=tmp_path / "run" / "ckpt.pt")

    # The resumed run should start near the checkpointed loss and end lower
    assert cont["initial_eval"]["train"] == pytest.approx(mid_loss, rel=0.5)
    assert cont["final_eval"]["train"] < mid_loss


# ---------------------------------------------------------------------------
# train_from_config_path entry
# ---------------------------------------------------------------------------


def test_train_from_config_path_with_smoke_config(tmp_path: Path) -> None:
    # Re-point out_dir into tmp_path so the test doesn't write into runs/.
    cfg_dict = _load_toml(REPO_ROOT / "configs" / "smoke.toml")
    cfg_dict["io"]["out_dir"] = str(tmp_path / "smoke")
    cfg_dict["io"]["device"] = "cpu"
    cfg_dict["schedule"]["max_steps"] = 30
    cfg_dict["loop"]["eval_interval"] = 15
    cfg = TrainConfig.from_dict(cfg_dict)

    result = run_training(cfg)
    assert result["device"] == "cpu"
    assert result["param_count"] > 0
    assert result["final_eval"]["train"] < result["initial_eval"]["train"]


# ---------------------------------------------------------------------------
# BPE-tokenizer end-to-end
# ---------------------------------------------------------------------------


def test_smoke_bpe_config_loads() -> None:
    cfg = TrainConfig.from_dict(_load_toml(REPO_ROOT / "configs" / "smoke_bpe.toml"))
    assert cfg.tokenizer_type == "bpe"
    assert cfg.tokenizer_vocab_size == 300


def test_default_tokenizer_is_char() -> None:
    """Configs without a [tokenizer] section must still load as char."""
    cfg = TrainConfig.from_dict(_load_toml(REPO_ROOT / "configs" / "smoke.toml"))
    assert cfg.tokenizer_type == "char"
    assert cfg.tokenizer_vocab_size is None


def test_smoke_bpe_loss_decreases(tmp_path: Path) -> None:
    cfg_dict = _load_toml(REPO_ROOT / "configs" / "smoke_bpe.toml")
    cfg_dict["io"]["out_dir"] = str(tmp_path / "smoke_bpe")
    cfg_dict["io"]["device"] = "cpu"
    cfg = TrainConfig.from_dict(cfg_dict)

    result = run_training(cfg)
    assert result["final_eval"]["train"] < result["initial_eval"]["train"], (
        f"BPE smoke loss did not decrease: "
        f"initial={result['initial_eval']['train']:.4f} "
        f"final={result['final_eval']['train']:.4f}"
    )
    assert (tmp_path / "smoke_bpe" / "ckpt.pt").exists()


def test_bpe_checkpoint_payload_carries_tokenizer_type_and_merges(tmp_path: Path) -> None:
    cfg_dict = _load_toml(REPO_ROOT / "configs" / "smoke_bpe.toml")
    cfg_dict["io"]["out_dir"] = str(tmp_path / "run")
    cfg_dict["io"]["device"] = "cpu"
    cfg_dict["schedule"]["max_steps"] = 20
    cfg = TrainConfig.from_dict(cfg_dict)
    run_training(cfg)

    ckpt = load_checkpoint(tmp_path / "run" / "ckpt.pt", device=torch.device("cpu"))
    assert ckpt["tokenizer_type"] == "bpe"
    assert "merges" in ckpt["tokenizer_state"]
    assert len(ckpt["tokenizer_state"]["merges"]) > 0
    # No legacy `vocab` key for BPE
    assert "vocab" not in ckpt


def test_char_checkpoint_still_writes_legacy_vocab_key(tmp_path: Path) -> None:
    """Existing scripts that read ckpt['vocab'] keep working for char models."""
    cfg = _smoke_train_cfg(tmp_path / "run", max_steps=20)
    run_training(cfg)
    ckpt = load_checkpoint(tmp_path / "run" / "ckpt.pt", device=torch.device("cpu"))
    assert ckpt["tokenizer_type"] == "char"
    assert "vocab" in ckpt
    assert ckpt["vocab"] == ckpt["tokenizer_state"]["vocab"]
