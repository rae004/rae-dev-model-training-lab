"""Load a checkpoint and generate text from a prompt.

The checkpoint payload from `train.save_checkpoint` carries everything
needed to rebuild the model standalone: the model state, the config dict,
and the vocab list. We don't need to know which corpus was trained on —
the tokenizer is reconstructed from the saved vocab.
"""

from __future__ import annotations

import logging
from pathlib import Path

import torch

from .model import GPT, GPTConfig
from .tokenizer import CharTokenizer
from .train import load_checkpoint, resolve_device

log = logging.getLogger(__name__)


def sample_from_checkpoint(
    checkpoint_path: Path,
    prompt: str,
    *,
    max_new_tokens: int,
    temperature: float = 0.8,
    top_k: int | None = 40,
    device_pref: str = "auto",
    seed: int | None = None,
) -> str:
    """Return prompt + max_new_tokens characters of model-generated continuation."""
    device = resolve_device(device_pref)
    ckpt = load_checkpoint(checkpoint_path, device=device)

    cfg_dict = ckpt["config"]
    vocab: list[str] = ckpt["vocab"]

    tok = CharTokenizer(vocab)
    model_cfg = GPTConfig(
        vocab_size=tok.vocab_size,
        block_size=cfg_dict["block_size"],
        n_layer=cfg_dict["n_layer"],
        n_head=cfg_dict["n_head"],
        d_model=cfg_dict["d_model"],
        dropout=cfg_dict.get("dropout", 0.0),
    )
    model = GPT(model_cfg).to(device)
    model.load_state_dict(ckpt["model"])
    model.eval()

    if seed is not None:
        torch.manual_seed(seed)
        if device.type == "cuda":
            torch.cuda.manual_seed_all(seed)

    if prompt == "":
        # Empty prompt is awkward (generate() needs at least one token). Seed
        # the context with the first char of the vocab; the user sees that
        # char as the first output character.
        prompt = vocab[0]
    prompt_ids = torch.tensor([tok.encode(prompt)], dtype=torch.long, device=device)

    out = model.generate(
        prompt_ids,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        top_k=top_k,
    )
    return tok.decode(out[0].tolist())
