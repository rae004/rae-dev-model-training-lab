"""Tests for the torch-free plumbing of docker/qlora-runpod/train_qlora.py.

The entrypoint lives outside src/ (it is container-plane code; its heavy
deps are deliberately absent from the shared CPU-only lockfile), so it's
loaded here by path. Only the pure helpers run — no torch, no network.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location(
    "train_qlora", ROOT / "docker" / "qlora-runpod" / "train_qlora.py"
)
tq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tq)

CONFIG = tq.load_config(ROOT / "configs" / "qlora_baseline.toml")


def test_config_matches_adr_025_as_amended() -> None:
    assert CONFIG["lora"]["rank"] == 16
    assert CONFIG["lora"]["alpha"] == 32
    assert len(CONFIG["lora"]["target_modules"]) == 7  # all-linear
    assert CONFIG["quant"]["quant_type"] == "nf4"
    assert CONFIG["train"]["learning_rate"] == 2e-4
    assert CONFIG["train"]["per_device_batch"] * CONFIG["train"]["grad_accum"] == 32
    assert CONFIG["train"]["sequence_length"] == 8192  # ADR-029 amendment
    assert CONFIG["train"]["epochs"] == 3
    assert CONFIG["run"]["base_model"].startswith("Qwen/Qwen2.5-Coder-7B")


def test_holdout_split_is_seeded_and_sized() -> None:
    records = [{"messages": [], "i": i} for i in range(100)]
    train_a, eval_a = tq.split_holdout(records, 0.10, seed=7)
    train_b, eval_b = tq.split_holdout(records, 0.10, seed=7)
    assert (train_a, eval_a) == (train_b, eval_b)
    assert len(eval_a) == 10
    assert len(train_a) == 90
    assert {r["i"] for r in train_a} | {r["i"] for r in eval_a} == set(range(100))
    _, eval_c = tq.split_holdout(records, 0.10, seed=8)
    assert eval_c != eval_a


def test_to_messages_drops_everything_but_messages() -> None:
    records = [{"shape": "chat", "messages": [{"role": "user", "content": "q"}], "meta": {}}]
    assert tq.to_messages(records) == [{"messages": [{"role": "user", "content": "q"}]}]


def test_warmup_steps_translates_adr_ratio() -> None:
    # Full run: 1067 train pairs, batch 32, 3 epochs -> 34 steps/epoch,
    # 102 total, 3% ~= 3 steps. Smoke slice floors at 1.
    assert tq.warmup_steps(1067, CONFIG["train"], epochs=3) == 3
    assert tq.warmup_steps(45, CONFIG["train"], epochs=1) == 1


def test_run_plan_reads_env_overrides() -> None:
    plan = tq.resolve_run_plan(CONFIG, {"RUN_TAG": "smoke1", "MAX_PAIRS": "50", "MAX_EPOCHS": "1"})
    assert plan["artifact_repo"] == "rae004/qlora-smoke1"
    assert plan["max_pairs"] == 50
    assert plan["epochs"] == 1
    full = tq.resolve_run_plan(CONFIG, {"RUN_TAG": "run1"})
    assert full["epochs"] == 3
    assert full["max_pairs"] is None


def test_dry_run_prints_plan_without_heavy_imports(tmp_path: Path, capsys) -> None:
    data = tmp_path / "ds"
    data.mkdir()
    rows = [{"shape": "chat", "messages": [{"role": "user", "content": f"q{i}"}], "meta": {}}
            for i in range(20)]
    (data / "dataset.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    rc = tq.main(["--dry-run", "--dataset-dir", str(data),
                  "--config", str(ROOT / "configs" / "qlora_baseline.toml")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "20 total -> 18 train / 2 eval" in out
