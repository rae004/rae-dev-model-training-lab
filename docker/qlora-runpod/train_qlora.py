"""QLoRA fine-tune entrypoint (ADR-025 / ADR-026 / ADR-029; M12-M13).

Runs inside the docker/qlora-runpod image on a RunPod pod. Flow:

1. Pull the ADR-029 dataset from HF Hub (dataset_repo in config).
2. Split the 10% held-out slice (seeded, before training).
3. QLoRA fine-tune per configs/qlora_baseline.toml (PEFT + TRL).
4. Push the LoRA adapter to HF Hub immediately (ADR-026: artifacts leave
   the pod before anything else can fail).
5. Merge adapter into the base, convert to GGUF (llama.cpp convert +
   llama-quantize), push the GGUF.
6. exit 0 -> the pod self-terminates.

Env: HF_TOKEN (pod secret, read+write), RUN_TAG (names the artifact repo
rae004/qlora-<RUN_TAG>), MAX_PAIRS / MAX_EPOCHS (smoke-slice overrides,
M12 only). Heavy imports happen after --dry-run handling so config and
data plumbing stay testable on CPU boxes without torch.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

LLAMA_CPP = Path("/opt/llama.cpp")
# The converter's deps conflict with the training stack (older
# transformers/hub pins), so the image gives them their own venv.
CONVERT_PYTHON = Path("/opt/convert-venv/bin/python")


def load_config(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def load_pairs(dataset_dir: Path) -> list[dict]:
    """Read the M10 dataset.jsonl; only `messages` feeds the trainer."""
    records = []
    with (dataset_dir / "dataset.jsonl").open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def split_holdout(records: list[dict], fraction: float, seed: int) -> tuple[list[dict], list[dict]]:
    """Seeded shuffle, then slice — same split for the same config."""
    pool = list(records)
    random.Random(seed).shuffle(pool)
    n_eval = int(len(pool) * fraction)
    return pool[n_eval:], pool[:n_eval]


def to_messages(records: list[dict]) -> list[dict]:
    return [{"messages": r["messages"]} for r in records]


def warmup_steps(n_train: int, train_cfg: dict, epochs: int) -> int:
    """ADR-025 specifies warmup as a ratio (3%); TRL 1.19's SFTConfig only
    accepts warmup_steps, so the ratio is translated here."""
    steps_per_epoch = math.ceil(n_train / (train_cfg["per_device_batch"] * train_cfg["grad_accum"]))
    return max(1, round(steps_per_epoch * epochs * train_cfg["warmup_ratio"]))


def resolve_run_plan(config: dict, env: dict[str, str]) -> dict:
    """Everything decided before torch loads, in one inspectable dict."""
    run_tag = env.get("RUN_TAG", "")
    max_pairs = int(env["MAX_PAIRS"]) if env.get("MAX_PAIRS") else None
    epochs = int(env["MAX_EPOCHS"]) if env.get("MAX_EPOCHS") else config["train"]["epochs"]
    return {
        "run_tag": run_tag,
        "max_pairs": max_pairs,
        "epochs": epochs,
        "artifact_repo": f"{config['output']['hf_repo_prefix']}-{run_tag}" if run_tag else "",
        "dataset_repo": config["run"]["dataset_repo"],
        "base_model": config["run"]["base_model"],
        "seed": config["run"]["seed"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/qlora_baseline.toml"))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the run plan and dataset counts, then exit (no torch, no GPU).",
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
        help="Use a local dataset directory instead of pulling from HF Hub.",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    plan = resolve_run_plan(config, dict(os.environ))
    if not plan["run_tag"] and not args.dry_run:
        print("RUN_TAG not set — refusing to train into an unnamed artifact repo.", file=sys.stderr)
        return 2
    if not os.environ.get("HF_TOKEN") and not args.dry_run:
        print("HF_TOKEN not set (pod secret, write scope).", file=sys.stderr)
        return 2

    if args.dataset_dir is not None:
        dataset_dir = args.dataset_dir
    else:
        from huggingface_hub import snapshot_download

        dataset_dir = Path(
            snapshot_download(repo_id=plan["dataset_repo"], repo_type="dataset")
        )

    records = load_pairs(dataset_dir)
    if plan["max_pairs"]:
        records = records[: plan["max_pairs"]]
    train_records, eval_records = split_holdout(
        records, config["train"]["holdout_fraction"], plan["seed"]
    )
    print(
        f"plan: {json.dumps(plan)}\n"
        f"pairs: {len(records)} total -> {len(train_records)} train / {len(eval_records)} eval"
    )
    if args.dry_run:
        return 0

    return _train(config, plan, train_records, eval_records)


def _train(config: dict, plan: dict, train_records: list[dict], eval_records: list[dict]) -> int:
    import torch
    from datasets import Dataset
    from huggingface_hub import HfApi
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    lora = config["lora"]
    quant = config["quant"]
    train = config["train"]
    out_dir = Path("/workspace/out")

    bnb = BitsAndBytesConfig(
        load_in_4bit=quant["load_in_4bit"],
        bnb_4bit_quant_type=quant["quant_type"],
        bnb_4bit_use_double_quant=quant["double_quant"],
        bnb_4bit_compute_dtype=getattr(torch, quant["compute_dtype"]),
    )
    model = AutoModelForCausalLM.from_pretrained(
        plan["base_model"], quantization_config=bnb, device_map="auto"
    )
    tokenizer = AutoTokenizer.from_pretrained(plan["base_model"])

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=Dataset.from_list(to_messages(train_records)),
        eval_dataset=Dataset.from_list(to_messages(eval_records)),
        peft_config=LoraConfig(
            r=lora["rank"],
            lora_alpha=lora["alpha"],
            lora_dropout=lora["dropout"],
            target_modules=lora["target_modules"],
            task_type="CAUSAL_LM",
        ),
        args=SFTConfig(
            output_dir=str(out_dir / "checkpoints"),
            seed=plan["seed"],
            num_train_epochs=plan["epochs"],
            learning_rate=train["learning_rate"],
            lr_scheduler_type=train["lr_scheduler"],
            warmup_steps=warmup_steps(len(train_records), train, plan["epochs"]),
            per_device_train_batch_size=train["per_device_batch"],
            gradient_accumulation_steps=train["grad_accum"],
            max_length=train["sequence_length"],
            optim=train["optimizer"],
            bf16=True,
            logging_steps=5,
            eval_strategy="epoch",
            save_strategy="epoch",
            report_to=[],
        ),
    )
    trainer.train()

    # Artifacts leave the pod in risk order (ADR-026): adapter first —
    # small, and the thing a rerun can resume from — then the GGUF.
    adapter_dir = out_dir / "adapter"
    trainer.save_model(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    api = HfApi(token=os.environ["HF_TOKEN"])
    api.create_repo(repo_id=plan["artifact_repo"], private=True, exist_ok=True)
    api.upload_folder(
        folder_path=str(adapter_dir), repo_id=plan["artifact_repo"], path_in_repo="adapter"
    )
    print(f"adapter -> {plan['artifact_repo']}/adapter")

    # The 46GB-RAM smoke pod OOM-killed when the merge phase held memory
    # alongside the converter subprocess; release the training objects first.
    del trainer, model
    gc.collect()
    torch.cuda.empty_cache()

    gguf = _export_gguf(plan, adapter_dir, out_dir, config["output"]["gguf_quant"])
    api.upload_file(
        path_or_fileobj=str(gguf), path_in_repo=gguf.name, repo_id=plan["artifact_repo"]
    )
    print(f"gguf -> {plan['artifact_repo']}/{gguf.name}")
    return 0


def _export_gguf(plan: dict, adapter_dir: Path, out_dir: Path, quant: str) -> Path:
    """Merge LoRA into the base, convert to GGUF, quantize."""
    import torch
    from huggingface_hub import snapshot_download
    from peft import PeftModel
    from transformers import AutoModelForCausalLM

    merged_dir = out_dir / "merged"
    base = AutoModelForCausalLM.from_pretrained(plan["base_model"], dtype=torch.bfloat16)
    merged = PeftModel.from_pretrained(base, str(adapter_dir)).merge_and_unload()
    merged.save_pretrained(str(merged_dir))
    # The converter venv's older transformers can't parse tokenizer configs
    # re-saved by the training stack's transformers 5.x (extra_special_tokens
    # became a list), so the merged dir gets the base model's original
    # tokenizer files verbatim — LoRA never changes the tokenizer.
    tok_snapshot = Path(
        snapshot_download(
            repo_id=plan["base_model"],
            allow_patterns=["tokenizer*", "vocab.json", "merges.txt", "special_tokens_map.json"],
        )
    )
    for f in tok_snapshot.iterdir():
        if f.is_file():
            shutil.copy(f, merged_dir / f.name)

    # Drop our 15GB in-memory copy before the converter subprocess loads
    # its own — holding both OOM-killed the 46GB smoke pod.
    del merged, base
    gc.collect()

    f16 = out_dir / f"qlora-{plan['run_tag']}-f16.gguf"
    subprocess.run(
        [
            str(CONVERT_PYTHON),
            str(LLAMA_CPP / "convert_hf_to_gguf.py"),
            str(merged_dir),
            "--outfile",
            str(f16),
            "--outtype",
            "f16",
        ],
        check=True,
    )
    final = out_dir / f"qlora-{plan['run_tag']}-{quant.lower()}.gguf"
    subprocess.run(
        [str(LLAMA_CPP / "build/bin/llama-quantize"), str(f16), str(final), quant],
        check=True,
    )
    return final


def _entry() -> int:
    """DEBUG_HOLD=1 freezes the pod on a crash instead of letting
    RunPod restart-loop it, so the traceback stays on screen."""
    try:
        return main()
    except BaseException:
        if os.environ.get("DEBUG_HOLD"):
            import time
            import traceback

            traceback.print_exc()
            print("DEBUG_HOLD set: sleeping 2h so the log stays up. Terminate the pod manually.")
            time.sleep(2 * 60 * 60)
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(_entry())
