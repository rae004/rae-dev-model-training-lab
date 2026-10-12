# CLAUDE.md — Agent Guide

You are working on a learning-first project: a small language model for Python
and TypeScript code review. Read this file every session. The human owner makes
all design decisions; your job is implementation within them.

## Read before structural work

- `docs/ARCHITECTURE.md` — the system design. Authoritative.
- `docs/DECISIONS.md` — 27 ADRs. **Append-only.** Never edit, renumber, or
  contradict an ADR. If implementation reveals a decision should change,
  propose a new superseding ADR and stop for human approval.
- `docs/MILESTONES.md` — the work plan. Implement one milestone at a time, in
  order, unless told otherwise.
- `docs/SETUP.md` — per-machine environment. If a step there disagrees with
  reality, fix the doc in the same branch as the fix.

## Hard rules

1. **`uv` only.** Never bare `pip`, never `pip install` into the system. All
   dependencies go through `pyproject.toml` + `uv.lock` (`uv add`, `uv sync`).
   The shared lockfile is CPU-only — training planes that need CUDA/ROCm
   rent GPUs per ADR-003 and install torch in a container, not in this
   lockfile. (Earlier ADR-014/ADR-021 called for a workhorse-local pinned
   torch venv; superseded by ADR-027 — workhorse's current 7900 XTX serves
   via Ollama's Vulkan backend, no PyTorch locally.)
2. **Never commit:** anything under `data/` except `data/sample/`,
   `data/scripts/`, and `data/SOURCES.md`; anything under `checkpoints/`;
   `.env`; model weights or `*.gguf` anywhere. The `.gitignore` encodes this —
   do not weaken it.
3. **Frozen contracts.** The `review(diff) -> Review` interface and the output
   schema (findings + summary + **derived** verdict — see `ARCHITECTURE.md` §4)
   are design decisions, not implementation details. Implement them exactly;
   propose changes via ADR, don't drift.
4. **Training code is fp32 and device-agnostic** (`cpu`/`cuda` selected by
   config/flag, never hardcoded). No mixed precision in Phase 1 (ADR-016).
   The fp32-everywhere rule is independent of what GPU is in which
   machine — it's simplicity over speed for the disposable Phase 1 model.
   Phase 2 training runs on rented NVIDIA GPUs (ADR-003/ADR-026), not
   locally.
5. **Decided vs. proposed.** Items marked *(proposed)* in the architecture doc
   (severity levels, category taxonomy, verdict threshold) should be
   implemented as defaults in config — easy to change, never silently changed.
6. **Reproducibility.** Every training run gets a config file in `configs/` and
   a fixed seed. A checkpoint must be regenerable from its config + commit.
7. **Don't touch the serving plane** (`serving/`, anything on
   `rae-dev-workhorse`) unless the milestone explicitly covers it.

## Workflow

- Branch per milestone (`m3-training-loop`), small commits, PR to main. A human
  reviews every diff before merge — write PR descriptions that make review easy
  (what, why, how verified).
- CI (ruff + pytest) must be green. Add tests with the code they test; the
  verdict-derivation logic and tokenizer round-trips especially.
- Each milestone has a "done means" in `MILESTONES.md` — meet it literally
  before declaring done.

## Context that saves you time

- The Phase 1 model is a **disposable teaching artifact**. Optimize for
  clarity of code and fast iteration, not model quality or cleverness.
- Phase 1 success = train/val loss + generated samples. The eval harness
  (milestone 8) scores *structured reviews* and is validated against an
  off-the-shelf Ollama model at `http://workhorse:11434` — never against the
  from-scratch model.
- Machines: `command` (build, CPU), `workhorse` (serving + the only CUDA box),
  `alpha` (data prep/eval). LAN-only, SSH + rsync between them (ADR-015).
- Style: follow `ruff` defaults at line-length 100; prefer plain, readable
  code over abstraction — a human is learning from this codebase.
