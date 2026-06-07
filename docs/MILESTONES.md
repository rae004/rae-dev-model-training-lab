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
needs. The deferred decisions (ADR-017) come back to the table then.
