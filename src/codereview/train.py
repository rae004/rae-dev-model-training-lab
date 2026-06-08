"""Device-agnostic training loop for the Phase 1 GPT.

Structured like minGPT/nanoGPT but kept verbose for learning value:
hyperparameters live in a TOML config (CLAUDE.md rule 6), the device is
resolved by string preference (CLAUDE.md rule 4), training is fp32
throughout, and every step writes to TensorBoard. Checkpoints carry the
model state, the optimizer state, the step count, the config that
produced them, and the tokenizer's vocabulary — the contract from
CLAUDE.md rule 6 ("regenerable from its config + commit").

Resume semantics: loading a checkpoint restores model + optimizer state
and the step counter; the batch RNG is *re-seeded* from the config seed,
so a resumed run is not byte-identical to a never-stopped run, but it
continues training from a faithful snapshot. The deterministic-trajectory
test exercises fresh-vs-fresh; the resume test exercises restore-and-continue.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import torch
from torch.utils.tensorboard import SummaryWriter

from codereview.config import load_config
from codereview.data import iter_batches, split_train_val
from codereview.model import GPT, GPTConfig
from codereview.tokenizer import CharTokenizer

log = logging.getLogger(__name__)

# Fixed per-split offset so eval batches are deterministic without depending
# on Python's randomized string hash.
_SPLIT_SEED_OFFSET = {"train": 0, "val": 1}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def resolve_device(pref: str) -> torch.device:
    if pref == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("device='cuda' requested but torch.cuda.is_available() is False")
        return torch.device("cuda")
    if pref == "cpu":
        return torch.device("cpu")
    if pref == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    raise ValueError(f"unknown device preference: {pref!r}")


def seed_everything(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def lr_at_step(
    step: int,
    *,
    warmup_steps: int,
    max_steps: int,
    max_lr: float,
    min_lr: float,
) -> float:
    """Linear warmup to max_lr, then cosine decay to min_lr at max_steps."""
    if step < warmup_steps:
        return max_lr * (step + 1) / max(warmup_steps, 1)
    if step >= max_steps:
        return min_lr
    progress = (step - warmup_steps) / max(max_steps - warmup_steps, 1)
    cosine = 0.5 * (1.0 + math.cos(math.pi * progress))
    return min_lr + (max_lr - min_lr) * cosine


def read_corpus(paths: list[Path]) -> str:
    return "".join(Path(p).read_text(encoding="utf-8") for p in paths)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class TrainConfig:
    # data
    corpus_paths: list[Path]
    val_fraction: float
    # model (vocab_size is derived from the tokenizer at runtime)
    block_size: int
    n_layer: int
    n_head: int
    d_model: int
    dropout: float
    # optim
    learning_rate: float
    min_learning_rate: float
    weight_decay: float
    beta1: float
    beta2: float
    grad_clip: float
    # schedule
    warmup_steps: int
    max_steps: int
    # loop
    batch_size: int
    eval_interval: int
    eval_iters: int
    log_interval: int
    # I/O
    out_dir: Path
    seed: int
    device: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TrainConfig":
        return cls(
            corpus_paths=[Path(p) for p in d["data"]["corpus_paths"]],
            val_fraction=d["data"]["val_fraction"],
            block_size=d["model"]["block_size"],
            n_layer=d["model"]["n_layer"],
            n_head=d["model"]["n_head"],
            d_model=d["model"]["d_model"],
            dropout=d["model"].get("dropout", 0.0),
            learning_rate=d["optim"]["learning_rate"],
            min_learning_rate=d["optim"]["min_learning_rate"],
            weight_decay=d["optim"]["weight_decay"],
            beta1=d["optim"]["beta1"],
            beta2=d["optim"]["beta2"],
            grad_clip=d["optim"]["grad_clip"],
            warmup_steps=d["schedule"]["warmup_steps"],
            max_steps=d["schedule"]["max_steps"],
            batch_size=d["loop"]["batch_size"],
            eval_interval=d["loop"]["eval_interval"],
            eval_iters=d["loop"]["eval_iters"],
            log_interval=d["loop"]["log_interval"],
            out_dir=Path(d["io"]["out_dir"]),
            seed=d["io"]["seed"],
            device=d["io"]["device"],
        )

    def to_serializable(self) -> dict[str, Any]:
        d = asdict(self)
        d["corpus_paths"] = [str(p) for p in self.corpus_paths]
        d["out_dir"] = str(self.out_dir)
        return d


# ---------------------------------------------------------------------------
# Eval and checkpoint
# ---------------------------------------------------------------------------


@torch.no_grad()
def estimate_loss(
    model: GPT,
    train_ids: list[int],
    val_ids: list[int],
    *,
    block_size: int,
    batch_size: int,
    eval_iters: int,
    device: torch.device,
    seed: int,
) -> dict[str, float]:
    """Return mean cross-entropy on a few batches from each split."""
    was_training = model.training
    model.eval()
    out: dict[str, float] = {}
    for name, ids in [("train", train_ids), ("val", val_ids)]:
        loader = iter_batches(
            ids, block_size, batch_size, seed=seed + _SPLIT_SEED_OFFSET[name]
        )
        losses: list[float] = []
        for _ in range(eval_iters):
            xs, ys = next(loader)
            x = torch.tensor(xs, dtype=torch.long, device=device)
            y = torch.tensor(ys, dtype=torch.long, device=device)
            _, loss = model(x, y)
            assert loss is not None
            losses.append(loss.item())
        out[name] = sum(losses) / len(losses)
    if was_training:
        model.train()
    return out


def save_checkpoint(
    path: Path,
    *,
    model: GPT,
    optimizer: torch.optim.Optimizer,
    step: int,
    train_cfg: TrainConfig,
    vocab: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "step": step,
            "config": train_cfg.to_serializable(),
            "vocab": vocab,
        },
        path,
    )


def load_checkpoint(path: Path, *, device: torch.device) -> dict[str, Any]:
    # weights_only=False because the payload includes the config dict and
    # the vocab list, not just tensors.
    return torch.load(path, map_location=device, weights_only=False)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def run_training(
    train_cfg: TrainConfig,
    *,
    override_device: str | None = None,
    resume_from: Path | None = None,
    writer_dir: Path | None = None,
) -> dict[str, Any]:
    """Train to completion. Returns a small summary suitable for tests/logs."""
    if override_device is not None:
        train_cfg.device = override_device

    seed_everything(train_cfg.seed)
    device = resolve_device(train_cfg.device)
    log.info("device=%s", device)

    text = read_corpus(train_cfg.corpus_paths)
    tok = CharTokenizer.from_text(text)
    ids = tok.encode(text)
    train_ids, val_ids = split_train_val(ids, train_cfg.val_fraction)
    log.info(
        "corpus chars=%d vocab=%d train=%d val=%d",
        len(text),
        tok.vocab_size,
        len(train_ids),
        len(val_ids),
    )

    model_cfg = GPTConfig(
        vocab_size=tok.vocab_size,
        block_size=train_cfg.block_size,
        n_layer=train_cfg.n_layer,
        n_head=train_cfg.n_head,
        d_model=train_cfg.d_model,
        dropout=train_cfg.dropout,
    )
    model = GPT(model_cfg).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=train_cfg.learning_rate,
        betas=(train_cfg.beta1, train_cfg.beta2),
        weight_decay=train_cfg.weight_decay,
    )

    start_step = 0
    if resume_from is not None:
        ckpt = load_checkpoint(resume_from, device=device)
        model.load_state_dict(ckpt["model"])
        optimizer.load_state_dict(ckpt["optimizer"])
        start_step = ckpt["step"]
        log.info("resumed from %s at step %d", resume_from, start_step)

    out_dir = train_cfg.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    writer = SummaryWriter(str(writer_dir or out_dir))

    train_loader = iter_batches(
        train_ids, train_cfg.block_size, train_cfg.batch_size, seed=train_cfg.seed
    )

    eval_history: list[tuple[int, dict[str, float]]] = []

    def do_eval(at_step: int) -> dict[str, float]:
        losses = estimate_loss(
            model,
            train_ids,
            val_ids,
            block_size=train_cfg.block_size,
            batch_size=train_cfg.batch_size,
            eval_iters=train_cfg.eval_iters,
            device=device,
            seed=train_cfg.seed + at_step,
        )
        writer.add_scalar("eval/train_loss", losses["train"], at_step)
        writer.add_scalar("eval/val_loss", losses["val"], at_step)
        log.info("step %d  eval train=%.4f val=%.4f", at_step, losses["train"], losses["val"])
        eval_history.append((at_step, losses))
        save_checkpoint(
            out_dir / "ckpt.pt",
            model=model,
            optimizer=optimizer,
            step=at_step,
            train_cfg=train_cfg,
            vocab=tok.vocab,
        )
        return losses

    do_eval(start_step)

    for step in range(start_step, train_cfg.max_steps):
        lr = lr_at_step(
            step,
            warmup_steps=train_cfg.warmup_steps,
            max_steps=train_cfg.max_steps,
            max_lr=train_cfg.learning_rate,
            min_lr=train_cfg.min_learning_rate,
        )
        for pg in optimizer.param_groups:
            pg["lr"] = lr

        xs, ys = next(train_loader)
        x = torch.tensor(xs, dtype=torch.long, device=device)
        y = torch.tensor(ys, dtype=torch.long, device=device)
        _, loss = model(x, y)
        assert loss is not None

        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        if train_cfg.grad_clip > 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), train_cfg.grad_clip)
        optimizer.step()

        if step % train_cfg.log_interval == 0 or step == train_cfg.max_steps - 1:
            writer.add_scalar("train/loss_step", loss.item(), step)
            writer.add_scalar("train/lr", lr, step)
            log.info("step %d  lr=%.2e  loss=%.4f", step, lr, loss.item())

        completed = step + 1
        is_eval_step = completed % train_cfg.eval_interval == 0
        is_final_step = completed == train_cfg.max_steps
        if is_eval_step or is_final_step:
            do_eval(completed)

    writer.close()
    return {
        "device": str(device),
        "vocab_size": tok.vocab_size,
        "param_count": model.num_params(),
        "eval_history": eval_history,
        "initial_eval": eval_history[0][1] if eval_history else None,
        "final_eval": eval_history[-1][1] if eval_history else None,
        "checkpoint_path": str(out_dir / "ckpt.pt"),
    }


def train_from_config_path(
    config_path: Path,
    *,
    override_device: str | None = None,
    resume_from: Path | None = None,
) -> dict[str, Any]:
    train_cfg = TrainConfig.from_dict(load_config(config_path))
    return run_training(train_cfg, override_device=override_device, resume_from=resume_from)
