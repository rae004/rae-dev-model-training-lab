import pytest
import torch

from codereview.model import GPT, GPTConfig


def _tiny_cfg(vocab_size: int = 32) -> GPTConfig:
    return GPTConfig(
        vocab_size=vocab_size,
        block_size=16,
        n_layer=2,
        n_head=2,
        d_model=32,
        dropout=0.0,
    )


def test_forward_shapes() -> None:
    cfg = _tiny_cfg()
    model = GPT(cfg)
    idx = torch.randint(0, cfg.vocab_size, (4, cfg.block_size))
    logits, loss = model(idx)
    assert logits.shape == (4, cfg.block_size, cfg.vocab_size)
    assert loss is None


def test_forward_with_targets_returns_scalar_loss() -> None:
    cfg = _tiny_cfg()
    model = GPT(cfg)
    idx = torch.randint(0, cfg.vocab_size, (3, cfg.block_size))
    targets = torch.randint(0, cfg.vocab_size, (3, cfg.block_size))
    logits, loss = model(idx, targets)
    assert logits.shape == (3, cfg.block_size, cfg.vocab_size)
    assert loss is not None
    assert loss.ndim == 0
    assert loss.item() > 0.0


def test_forward_rejects_overlong_sequence() -> None:
    cfg = _tiny_cfg()
    model = GPT(cfg)
    too_long = torch.randint(0, cfg.vocab_size, (1, cfg.block_size + 1))
    with pytest.raises(ValueError, match="exceeds block_size"):
        model(too_long)


def test_attention_is_causal() -> None:
    """Changing the last token's value must not change earlier-position logits."""
    cfg = _tiny_cfg()
    model = GPT(cfg).eval()
    a = torch.randint(0, cfg.vocab_size, (1, cfg.block_size))
    b = a.clone()
    b[0, -1] = (b[0, -1] + 1) % cfg.vocab_size
    with torch.no_grad():
        logits_a, _ = model(a)
        logits_b, _ = model(b)
    # All but the last position should be identical between runs.
    torch.testing.assert_close(logits_a[:, :-1, :], logits_b[:, :-1, :])
    # And the last position should differ (sanity that the change took effect).
    assert not torch.allclose(logits_a[:, -1, :], logits_b[:, -1, :])


def test_d_model_must_be_divisible_by_n_head() -> None:
    with pytest.raises(ValueError, match="divisible"):
        GPT(GPTConfig(vocab_size=8, block_size=4, n_layer=1, n_head=3, d_model=16))


def test_generate_returns_sequence_with_appended_tokens() -> None:
    cfg = _tiny_cfg()
    model = GPT(cfg)
    prompt = torch.randint(0, cfg.vocab_size, (2, 4))
    out = model.generate(prompt, max_new_tokens=8)
    assert out.shape == (2, 12)
    # Prompt portion is preserved verbatim.
    assert torch.equal(out[:, :4], prompt)


def test_generate_is_deterministic_when_seeded() -> None:
    cfg = _tiny_cfg()
    model = GPT(cfg)
    prompt = torch.randint(0, cfg.vocab_size, (1, 4))

    torch.manual_seed(0)
    a = model.generate(prompt, max_new_tokens=8)
    torch.manual_seed(0)
    b = model.generate(prompt, max_new_tokens=8)
    assert torch.equal(a, b)


def test_generate_top_k_constrains_per_step_choices() -> None:
    """top_k=k means each step samples from at most k tokens. Hold the
    prompt fixed and vary the seed: every draw must come from the same
    top-k set (same logits → same top-k slice)."""
    cfg = _tiny_cfg(vocab_size=32)
    model = GPT(cfg).eval()
    prompt = torch.randint(0, cfg.vocab_size, (1, 4))

    next_tokens: set[int] = set()
    for seed in range(50):
        torch.manual_seed(seed)
        out = model.generate(prompt, max_new_tokens=1, top_k=3)
        next_tokens.add(out[0, -1].item())
    assert len(next_tokens) <= 3, (
        f"top_k=3 should yield ≤3 distinct first tokens for a fixed prompt, saw {len(next_tokens)}"
    )


def test_generate_top_k_1_is_effectively_greedy() -> None:
    """With top_k=1, the sampling distribution collapses to a single token,
    so the output is deterministic without any seed."""
    cfg = _tiny_cfg()
    model = GPT(cfg).eval()
    prompt = torch.randint(0, cfg.vocab_size, (1, 4))
    a = model.generate(prompt, max_new_tokens=8, top_k=1)
    b = model.generate(prompt, max_new_tokens=8, top_k=1)
    assert torch.equal(a, b)


def test_generate_rejects_invalid_temperature() -> None:
    cfg = _tiny_cfg()
    model = GPT(cfg)
    prompt = torch.randint(0, cfg.vocab_size, (1, 2))
    with pytest.raises(ValueError, match="temperature"):
        model.generate(prompt, max_new_tokens=4, temperature=0.0)


def test_generate_handles_prompt_at_block_size_boundary() -> None:
    cfg = _tiny_cfg()
    model = GPT(cfg)
    # Start with a prompt that already fills block_size — generation must
    # crop on each step rather than crash.
    prompt = torch.randint(0, cfg.vocab_size, (1, cfg.block_size))
    out = model.generate(prompt, max_new_tokens=4)
    assert out.shape == (1, cfg.block_size + 4)


def test_param_count_order_of_magnitude_for_spec_config() -> None:
    """The ADR-016 step-1 shape (~4 layers / 4 heads / d_model 128 / context 128)
    at a realistic char-level vocab (~100) lands around 830k params — within
    the 'small enough to iterate in minutes' band the ADR set. The ADR's
    '~1-3M' was a slightly high estimate (it assumed a larger vocab); the
    order of magnitude is right. Loose bounds here guard against an
    accidental 10x change."""
    cfg = GPTConfig(vocab_size=100, block_size=128, n_layer=4, n_head=4, d_model=128)
    n = GPT(cfg).num_params()
    assert 500_000 <= n <= 3_000_000, f"out of expected order of magnitude: {n}"
