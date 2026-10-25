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

Six reviewable increments turning ADRs 022–027 into a fine-tuned
`code-reviewer:v1` served on workhorse. Same discipline as Phase 1: one branch,
one PR, one human review, "Done means" is the acceptance bar. Phase 2 fans out
across machines — `command` for authoring + dataset generation (ADR-023), a
rented RunPod A100 40GB for training (ADR-026), and `workhorse` for serving +
evaluation (ADR-027).

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

## M10 — Fine-tune dataset build (ADR-023)
**Goal:** Generate ~500–1000 `(diff, Review-JSON)` pairs with the 70 / 15 / 15
split (synthetic / weakness-targeted / authentic voice). Pipeline code in
`data/scripts/`, dataset under `data/finetune/` (git-ignored per ADR-011,
regenerable from the committed recipe).
**Done means:** deterministic generator from a committed teacher-model tag;
every pair validates against the Review JSON schema; a composition report
shows actual proportions + weakness-axis coverage against M9's target list;
dataset uploaded to a HuggingFace Hub private dataset repo
`rae004/qlora-dataset-<run-tag>`.

## M11 — QLoRA training image + RunPod smoke test
**Goal:** `docker/qlora-runpod/Dockerfile` per ADR-026 with the ADR-025
dependency set; `train_qlora.py` wired to `configs/qlora_baseline.toml`;
image pushed to `ghcr.io/rae004/rae-dev-model-training-lab-qlora`. A **cheap
RunPod pod** (A4000-tier, 50-pair dataset slice, 1 epoch) validates the full
container → train → HF Hub push → auto-exit cycle before any A100 time is
bought. ADR-027 killed ADR-026's local-5060-Ti smoke-test path; the cheap
RunPod path is the replacement, and an amendment ADR formally retiring the
superseded clause lands at Phase 2 close (not in this milestone).
**Done means:** image builds reproducibly from a committed repo SHA; the
smoke run completes end-to-end on RunPod in ≤ 30 min for < $2; LoRA adapter
and merged GGUF both land in HF Hub; pod self-terminates on `exit 0`.
Smoke-run cost + wall time recorded in `docs/results.md`.

## M12 — First QLoRA fine-tune run (A100 40GB)
**Goal:** The real run per ADR-025: 3 epochs, full dataset, A100 40GB
on-demand, max-runtime 4 hr. LoRA checkpoints + merged GGUF pushed to a
HuggingFace Hub private repo `rae004/qlora-<run-tag>` before the container
exits.
**Done means:** training completes within max-runtime; held-out-10%-slice
loss curve recorded at each epoch; LoRA + merged GGUF live in HF Hub; a
`docs/results.md` entry links the run tag to the base-model + dataset +
config commit hashes; pod self-terminated; actual cost recorded.

## M13 — Serve candidate on workhorse + eval vs. baseline
**Goal:** `ollama create code-reviewer:<run-tag>` on workhorse from the HF Hub
GGUF (served via Vulkan per ADR-027); run the M8 eval harness per ADR-024's
dual-metric scoring; compare the candidate directly against the
`qwen2.5-coder:7b` baseline documented in `docs/baseline-eval.md`.
**Done means:** scored report in `docs/results.md` with strict and
severity-only macro F1 for candidate and baseline side by side, including a
weakness-category breakdown showing whether M9's targeted gaps actually
closed; verdict stated plainly ("candidate beat baseline on severity-only,
lost on strict" or similar).

## M14 — Iterate or close Phase 2 (conditional on M13)
**Goal:** If M13's candidate beats the baseline on at least one metric with no
major regression on the other — freeze the artifact, write a Phase 2 close-out
note, update the README, and land an amendment ADR formally retiring
ADR-026's superseded local-smoke-test clause. If it didn't — diagnose
(dataset shape? LR? under-trained? wrong rank?), make one targeted change,
re-run M12→M13 once, and record both runs.
**Done means:** either (i) Phase 2 shipped — `code-reviewer:v1` tagged in
Ollama on workhorse, README reflects the new default, retrospective note
committed, superseded-clause amendment ADR merged; or (ii) a second iteration
shipped with a one-paragraph delta ADR explaining the change and both run
outcomes recorded in `docs/results.md`.
