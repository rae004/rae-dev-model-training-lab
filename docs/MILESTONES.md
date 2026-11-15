# Phase 1 Milestones

Eight reviewable increments, in order. Each is one branch, one PR, one human
review. "Done means" is the acceptance bar — meet it literally. Machines are
noted where it matters; default is `rae-dev-command`.

## M1 — Repo and loop scaffolding
**Goal:** Turn the skeleton into a working project: package layout under
`src/`, config loading (per-run config files in `configs/`), logging setup, and
green CI.
**Done means:** `uv sync` then `uv run pytest` passes locally and in CI;
`uv run python -m <package> --help` runs; ruff is clean.

## M2 — Char-level tokenizer + data pipeline
**Goal:** Corpus prep per ADR-018 (owner's repos + permissive public slice;
every source recorded in `data/SOURCES.md`), a character-level
tokenizer, train/val split, and a batch loader. Committed: scripts and a small
sample; the full corpus stays git-ignored.
**Done means:** encode/decode round-trips exactly (tested); loader yields
batches of the configured shape from the sample data; prep script regenerates
the corpus deterministically.

## M3 — Model + device-agnostic training loop
**Goal:** The GPT (embeddings, attention blocks, LM head), AdamW with warmup +
cosine decay, fp32, `--device cpu|cuda|auto`, fixed seed, TensorBoard logging,
checkpoint save/resume.
**Done means:** a smoke-sized config shows decreasing loss in a short CI-safe
test; the identical config runs to completion with `--device cpu` and (on the
workhorse) `--device cuda`; resume from checkpoint reproduces.

## M4 — Char-level run (~1–3M params) on both machines
**Goal:** The first real training run: ~4 layers / 4 heads / d_model 128 /
context 128, on `command` (CPU) and `workhorse` (GTX 1050).
**Done means:** val-loss curves recorded for both devices; generated samples
saved; the run's config committed to `configs/` and outcomes noted in a results
log tied to the commit hash.

## M5 — BPE tokenizer (~4k–8k vocab)
**Goal:** Train a byte-pair tokenizer on the corpus; quantify the contrast
with char-level.
**Done means:** round-trip test passes; a short doc note reports tokens-per-KB
on the corpus for char vs. BPE (the compression lesson, made concrete).

## M6 — Baby-GPT run (~10M params) + CPU-vs-GPU benchmark
**Goal:** The main learning run: ~6 layers / 6 heads / d_model 384 / context
256 on the BPE corpus, on both machines, instrumented for throughput.
**Done means:** completed run with loss curves and samples; a benchmark table
(tokens/sec, time per step, CPU 24-thread vs. GTX 1050) added to the docs.

## M7 — `review()` core + CLI
**Goal:** The frozen contract made real: the Review schema (findings, summary,
derived verdict), a pluggable backend (Ollama-HTTP first, pointed at
`http://workhorse:11434` with an off-the-shelf code model), prompt construction
from a diff, and the thin CLI — stdin → stdout, `--json`, stderr diagnostics,
exit codes per the architecture doc.
**Done means:** `git diff | reviewer` returns a sensible review end-to-end;
`--json` output validates against the schema; verdict derivation is
unit-tested (including the empty-findings LGTM path); the CLI contains no
logic beyond argument handling.

## M8 — Eval harness + baseline
**Goal:** A small, versioned eval set in `eval/` (diffs with reference
findings), a runner that scores `review()` output against it using the
*(proposed)* precision-aware defaults, and a report format.
**Done means:** the harness produces a scored report for the off-the-shelf
Ollama model — recorded as the baseline any Phase 2 candidate must beat; the
eval set is committed; scoring logic is unit-tested.

---

After M8, Phase 1 is complete: the loop has been built and understood, and the
project holds a working CLI, a baseline, and a harness — everything Phase 2
needs. ADR-017's deferred decisions came back to the table and were resolved
across ADRs 022–027 (base model, dataset, scoring, QLoRA hyperparameters,
rented-GPU workflow, workhorse serving).

---

# Phase 2 Milestones

Seven reviewable increments turning ADRs 022–030 into a fine-tuned
multi-purpose coding agent served on workhorse. Same discipline as Phase 1:
one branch, one PR, one human review, "Done means" is the acceptance bar.
Phase 2 fans out across machines — `command` for authoring + dataset
generation (ADR-029), a rented RunPod A100 40GB for training (ADR-026), and
`workhorse` for serving + evaluation (ADR-027, ADR-030). The plan below
supersedes the reviewer-only M10–M14: after live rae-local-agent use showed
the stock model failing focused tasks, ADR-028 (goal), ADR-029 (dataset),
and ADR-030 (evaluation) pivoted the target.

## M9 — Weakness profile → dataset targeting plan
**Goal:** From the dual-metric baseline (ADR-024 impl, `docs/results.md`
2026-10-25 entry), produce a concrete weakness profile naming which
categories/patterns the fine-tune must fix, and what example-diff shapes the
dataset must contain. ADR-023 is the recipe; this milestone is the pre-work
that makes it executable.
**Done means:** `docs/weakness-profile.md` committed, listing: (i) categories
where baseline recall was 0 and whether each miss was miscategorization or
silence, (ii) the three false-negative verdicts from M8 with the shape of
each miss, (iii) a prioritized target list the ADR-023 pipeline will search
for. No code; just the sighting shot.
*(Complete before the pivot; its target list now feeds the review slice of
the ADR-029 dataset.)*

## M10 — Fine-tune dataset build (ADR-029)
**Goal:** ~1,000–1,500 pairs (floor 800) in four shapes — transforms ~45 %
(commit mining + reverse mutation), declines ~15 %, reviews ~20 % (targeted
per M9), chat ~20 % — serialized in the qwen2.5 instruct chat template with
the serving surfaces' actual system prompts. Pipeline code in
`data/scripts/`, dataset under `data/finetune/` (git-ignored per ADR-011,
regenerable from the committed recipe). The teacher writes specs, reviews,
and chat answers — never the code outputs the student trains on.
**Done means:** deterministic generator (fixed seed, pinned teacher-model
tag); every pair passes its shape's mechanical gate (clean `git apply` for
transforms, byte-identical declines, schema-valid reviews, length-capped
chat); a composition report shows shape proportions, philosophy-anchor
coverage, M9 weakness-axis coverage, source-repo breakdown, and a
token-length histogram; dataset uploaded to a HuggingFace Hub private
dataset repo `rae004/qlora-dataset-<run-tag>`.

## M11 — Transform eval harness + pre-training baselines (ADR-030)
**Goal:** The mechanical transform harness and its ~20 hand-authored cases
(decline / preservation-trap / philosophy-anchor / straight-transform
categories), plus the tool-calling smoke check. Both transform baselines are
measured before any candidate exists, so the gate is fixed in advance.
**Done means:** harness and cases committed in `eval/` with unit-tested
scoring (clean-apply, byte-for-byte preservation, targeted-change assertion,
2×-output runaway guard); stock `qwen2.5-coder:7b` and stock `:32b`
transform pass rates recorded in `docs/results.md`; the base model's
tool-calling rate measured and the "materially below" threshold set per
ADR-030; the harness runs deterministically against workhorse.

## M12 — QLoRA training image + RunPod smoke test
**Goal:** (Was M11.) `docker/qlora-runpod/Dockerfile` per ADR-026 with the
ADR-025 dependency set and ADR-029's sequence-length amendment (8192)
reflected in `configs/qlora_baseline.toml`; `train_qlora.py` wired to that
config; image pushed to `ghcr.io/rae004/rae-dev-model-training-lab-qlora`.
A **cheap RunPod pod** (A4000-tier, 50-pair dataset slice, 1 epoch)
validates the full container → train → HF Hub push → auto-exit cycle before
any A100 time is bought.
**Done means:** image builds reproducibly from a committed repo SHA; the
smoke run completes end-to-end on RunPod in ≤ 30 min for < $2; LoRA adapter
and merged GGUF both land in HF Hub; pod self-terminates on `exit 0`.
Smoke-run cost + wall time recorded in `docs/results.md`.

## M13 — First QLoRA fine-tune run (A100 40GB)
**Goal:** (Was M12.) The real run per ADR-025 as amended by ADR-029: 3
epochs, full dataset, sequence length 8192, effective batch 32, A100 40GB
on-demand, max-runtime 6 hr. LoRA checkpoints + merged GGUF pushed to a
HuggingFace Hub private repo `rae004/qlora-<run-tag>` before the container
exits.
**Done means:** training completes within max-runtime; held-out-slice loss
curve recorded at each epoch; LoRA + merged GGUF live in HF Hub; a
`docs/results.md` entry links the run tag to the base-model + dataset +
config commit hashes; pod self-terminated; actual cost recorded.

## M14 — Serve candidate + evaluate all four surfaces (ADR-030)
**Goal:** (Was M13.) `ollama create rae-agent:<run-tag>` on workhorse from
the HF Hub GGUF (served via Vulkan per ADR-027); run the full ADR-030
battery: review (M8 harness, ADR-024 dual-metric, vs. the existing
baseline), transform harness (vs. both M11 baselines), tool-calling smoke
check (vs. the M11 base rate), chat conciseness + qualitative review.
**Done means:** a `docs/results.md` entry reports all four surfaces with
candidate and baselines side by side, and states each ADR-030 promotion
gate plainly as pass/fail: transform pass rate beats stock-7b; review
metrics not regressed below the stock-7b baseline; tool calling not
degraded; chat reviewed.

## M15 — Iterate or close Phase 2 (conditional on M14)
**Goal:** (Was M14.) If all four gates pass — freeze the artifact, write
the Phase 2 close-out note, update the README, and land the amendment ADR
formally retiring ADR-026's superseded local-smoke-test clause. Adopting
the model in rae-local-agent / rae-local-chat is those repos' work, not
this one's. If a gate fails — diagnose (dataset shape? tool-smoke tripwire
→ ADR-029 amendment? LR? rank?), make one targeted change, re-run M13→M14
once, and record both runs.
**Done means:** either (i) Phase 2 shipped — `rae-agent:v1` tagged in
Ollama on workhorse, README reflects the new default, retrospective note +
superseded-clause amendment ADR merged; or (ii) a second iteration shipped
with a one-paragraph delta ADR explaining the change and both run outcomes
recorded in `docs/results.md`.
