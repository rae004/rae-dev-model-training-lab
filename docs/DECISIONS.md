# Design Decisions

An append-only log of the significant decisions on this project, in lightweight
**ADR** (Architecture Decision Record) form. Each entry records the *context*
that forced the decision, *what* we chose, and the *consequences* — so the
reasoning stays legible later, which is itself part of the learning goal.
Decisions aren't edited away when they change; a superseding entry is added.

*Recorded as of 2026-05-31.*

---

## ADR-001 — Two-phase build: learn from scratch, then fine-tune
**Status:** Accepted
**Context:** A model small enough to pretrain from scratch on our hardware teaches the mechanics but can't review code well; a genuinely useful reviewer needs a pretrained base.
**Decision:** Phase 1 builds a tiny transformer from scratch purely to learn the lifecycle; Phase 2 fine-tunes a small pretrained code model into the actual reviewer.
**Consequences:** Both goals are served without compromise. The Phase 1 model is explicitly disposable — we don't try to make it good, and we never serve it.

## ADR-002 — `rae-dev-command` is primary; `rae-bot-alpha` is complementary
**Status:** Superseded by ADR-013
**Context:** Neither machine has a usable training GPU (both have only integrated AMD graphics). The 9900X (12c/24t) vastly outperforms the 3200G (4c) for CPU work and inference.
**Decision:** Run training, experiments, and heavier inference on `rae-dev-command`; use `rae-bot-alpha` as the always-on serving box plus dataset prep and eval runs. Do **not** pool the two into one distributed training job.
**Consequences:** Clear division of labor; neither machine blocks the other. Pooling was rejected — the coordination overhead and the speed mismatch would make it slower and more fragile than just using the fast machine.

## ADR-003 — Fine-tuning runs on a rented GPU, not locally
**Status:** Accepted
**Context:** No local CUDA GPU; the integrated AMD GPUs aren't supported by the fine-tuning stack (Unsloth targets discrete RX 6000–9000 / data-center cards), and CPU fine-tuning of a multi-billion-parameter model is impractical.
**Decision:** Offload Phase 2 QLoRA training to a rented/cloud GPU; keep everything else — Phase 1, inference, serving — local.
**Consequences:** A few dollars per training run, and the resulting GGUF must travel to the serving machine. Inference stays fully local.

## ADR-004 — A stable `review(diff) -> Review` interface is the invariant
**Status:** Accepted
**Context:** Models change across phases, and we want several ways to invoke the reviewer over time.
**Decision:** Define one core contract early. Keep invocation shells (CLI, later hooks/editor/CI) thin and put the logic in a reusable core; models sit behind a pluggable backend chosen by config.
**Consequences:** New integrations and new model backends are added without rewrites. This contract is the thing that must stay stable while everything behind it evolves.

## ADR-005 — Build the evaluation harness in Phase 1
**Status:** Accepted
**Context:** Understanding how a model is made requires being able to measure it, and the harness is reusable across both phases.
**Decision:** Include the eval harness and a small, versioned eval set in Phase 1 rather than deferring to Phase 2.
**Consequences:** A little upfront effort buys the learning value of measurement from day one and a consistent yardstick for whether the Phase 2 fine-tune actually helped. Eval rewards precision — correct "looks good" verdicts included — not just issues found.

## ADR-006 — CLI-first interaction model
**Status:** Accepted
**Context:** We want the simplest core that expands cleanly into hooks, an editor, and CI later.
**Decision:** Start with a Unix CLI — diff on stdin, review on stdout, diagnostics on stderr, meaningful exit code.
**Consequences:** It *is* the `review()` contract at the shell; `git diff | reviewer` works immediately, and every other integration becomes a thin wrapper. On slow models it later becomes a *client* of the warm serving plane rather than cold-loading a model each call.

## ADR-007 — Output is findings + summary + derived verdict
**Status:** Accepted
**Context:** A free-text review is hard to score, render, or gate on; asking the model for a separate pass/fail risks contradicting its own findings.
**Decision:** One canonical object — a list of findings (severity, category, message, optional location and suggestion), a prose summary, and a verdict *derived* from the findings' severities against a configurable threshold. Text rendering by default; `--json` exposes the raw object. A clean review is `passed: true` with empty findings.
**Consequences:** Slightly richer than the Phase 1 toy can fill, but cheap to define, and it unlocks the eval harness and every later integration. The verdict and findings can never disagree.

## ADR-008 — Don't rebuild the linter
**Status:** Accepted
**Context:** `ruff`/`mypy` and `eslint`/`tsc` already catch style, type, and syntax issues instantly and for free.
**Decision:** Bias the reviewer's categories — and what we train and evaluate for — toward judgment-level issues (bugs, security, tests, design, readability), and lean away from pure style nits.
**Consequences:** The reviewer earns its keep where deterministic tools can't reach, instead of duplicating them.

## ADR-009 — Treat the reviewer as an always-on service
**Status:** Accepted (working assumption, revisable)
**Context:** The likely day-to-day use is calling the reviewer from the editor on demand.
**Decision:** Architect for an always-on serving plane on `rae-bot-alpha` (Ollama plus the reviewer service), with model versioning and rollback via Ollama tags.
**Consequences:** Introduces the build-vs-serve split and an eval-gated model-promotion flow. If the always-on assumption changes, the promotion/versioning machinery can be simplified.

## ADR-010 — No containers for the Phase 1 learning loop; containerize at the seams
**Status:** Accepted
**Context:** Containers add indirection that distracts from learning; for pure-Python CPU work a lockfile captures most of the reproducibility; containers pay off mainly across machine boundaries.
**Decision:** Use `uv` + a lockfile for Phase 1. Containerize only the serving stack (Compose) and the rented-GPU training step (a CUDA image).
**Consequences:** Faster iteration while learning, with reproducibility and portability where they actually matter. Note that the CPU and CUDA images differ at the PyTorch layer, so they can't be byte-identical.

## ADR-011 — Single monorepo; reproducible core in Git, heavy/sensitive things out
**Status:** Accepted
**Context:** Tightly coupled solo project. Git handles code and text well and large binaries badly; GitHub's free Git LFS tier is too small for model weights.
**Decision:** One repo. Track code, configs, the lockfile, the eval set, container/Compose files, and docs. Git-ignore weights, the full dataset, and secrets — data and weights may sit in the working tree but stay ignored. Regenerate checkpoints from recipe or store them on Hugging Face / Releases. Track dataset provenance and licenses.
**Consequences:** Clean, fast history. The trade is a cross-machine transfer step for the GGUF and the discipline of keeping artifacts out of commits.

## ADR-012 — Documentation in Markdown with Mermaid diagrams
**Status:** Accepted
**Context:** Docs should live with the code, be diffable, and render where the repo is hosted.
**Decision:** Write documentation as Markdown files with Mermaid code-fenced diagrams.
**Consequences:** Diagrams version alongside the prose and render natively on GitHub; no separate diagramming tool or binary image assets to manage.

---

*Recorded 2026-06-07.*

## ADR-013 — Three-machine layout: serve from `rae-dev-workhorse`
**Status:** Accepted — supersedes ADR-002
**Context:** A third machine joined the fleet: `rae-dev-workhorse` (i7-8700, 6c/12t, 32 GB, GTX 1050 2 GB) — the only box with a CUDA GPU. Its CPU outclasses `rae-bot-alpha`'s 4-core 3200G, and llama.cpp can offload some inference layers to the GPU. The alternative (workhorse as a dedicated CUDA lab, alpha keeps serving) was considered and rejected in favor of the stronger machine carrying the daily workload.
**Decision:** `rae-dev-workhorse` becomes the always-on serving plane (Ollama + reviewer service, partial GPU offload). `rae-bot-alpha` narrows to a data plane: dataset prep, curation, and eval runs. `rae-dev-command` remains the build plane. The workhorse also doubles as the CUDA box — Phase 1's GPU training track and local smoke-testing of the Phase 2 training container — scheduled around serving, which is idle most of the time.
**Consequences:** Faster day-to-day review inference; every machine has one clear job. The 2 GB of VRAM changes nothing about Phase 2 — fine-tuning still rents a GPU (re-affirms ADR-003) — but it removes the main risk of that plan by letting the training container be debugged locally before paying for rental minutes. The trade: the serving appliance is also the experiment box, so heavier GPU experiments should respect its always-on duty.

## ADR-014 — Pin a cu126-line PyTorch on the GTX 1050
**Status:** Accepted
**Context:** The GTX 1050 is Pascal (`sm_61`). Current PyTorch builds dropped Pascal (CUDA 12.8/12.9 builds from PyTorch 2.8 onward reject it; CUDA 13 removed the architecture entirely), while the cu126 wheel line still supports it. Pascal consumer cards also have crippled fp16 throughput.
**Decision:** The workhorse's training environment pins an older PyTorch from the cu126 line, captured in its lockfile; training there is fp32. Inference via llama.cpp/Ollama is unaffected. The Phase 2 rental image targets *current* PyTorch/CUDA — the local smoke test validates the container workflow and scripts, not exact wheel versions.
**Consequences:** A second pinned environment to maintain, and an accepted gap between local-test and rental versions. In exchange, the only CUDA hardware we own stays usable. Revisit if the card is ever upgraded.

## ADR-015 — LAN-only communication: SSH + Git + rsync + HTTP, no shared filesystem
**Status:** Accepted
**Context:** Three machines need to exchange exactly four things: code, datasets, model artifacts (GGUFs), and live review traffic. The reviewer is local-only for now — no off-LAN access required. A shared filesystem (NFS/Syncthing) was considered as the general-purpose answer.
**Decision:** Match each flow to the simplest fitting tool. Cross-installed SSH keys with stable hostnames as the foundation; code moves only through the GitHub remote; artifacts move by explicit `rsync` over SSH (promotion `command -> workhorse`, data `alpha <-> command`); live review traffic is HTTP to Ollama on the workhorse. No shared filesystem, and no mesh VPN yet.
**Consequences:** Promotion remains a deliberate, scriptable act (`rsync` + `ssh ollama create`) — consistent with eval-gated promotion — and each machine's git-ignored heavy directories stay intentionally distinct. No always-on mount dependencies between boxes. The accepted limits: transfers are manual until scripted, and the reviewer is unreachable away from home. Tailscale is the designated upgrade path if off-LAN access is wanted; an NFS export from `alpha` is the shape if a shared scratch area ever proves necessary.

## ADR-016 — Phase 1 spec: char-level first, then a small-BPE baby-GPT
**Status:** Accepted
**Context:** The Phase 1 model is disposable, so its design optimizes for learning per hour and fast iteration, not quality. Tokenizer, model size, and training cost are interlinked (vocab size drives the embedding/head share of parameters; context length drives attention cost). Reusing a large pretrained vocabulary (~50k) was rejected — its embedding table would dwarf a tiny model. The new CUDA box also makes a CPU-vs-GPU comparison possible.
**Decision:** Two runs in sequence, sharing one device-agnostic training loop. **Step 1:** a char-level model (~1–3M params; on the order of 4 layers / 4 heads / d_model 128 / context 128) to prove the full loop end-to-end on both the 9900X (CPU) and the GTX 1050 (CUDA). **Step 2:** a small custom BPE tokenizer (~4k–8k vocab, trained on the Phase 1 corpus) feeding a ~10M-param baby-GPT (on the order of 6 layers / 6 heads / d_model 384 / context 256) as the main learning run, doubling as the CPU-vs-GPU benchmark. Training is fp32 on both devices (CPU norm; Pascal fp16 is crippled). Exact hyperparameters live in `configs/`, not here.
**Consequences:** The tokenizer lesson is taught by *contrast* — the same model family on char-level vs. BPE input makes sequence length, loss scale, and sample quality differences visible. Step 1 keeps iteration loops in minutes; only Step 2 pays for longer runs. Success in Phase 1 is measured by train/val loss and sampled generations — *not* the review eval harness, which this model cannot satisfy and never feeds.

## ADR-017 — Defer the reviewer-specific decisions to the Phase 2 boundary
**Status:** Accepted
**Decision:** The Phase 2 base-model choice, the fine-tuning dataset sourcing/curation/licensing plan, the final severity/category taxonomy, and the precision-aware eval-scoring methodology are deliberately deferred until Phase 1 is underway/complete. The eval harness is still *built* in Phase 1 using the proposed defaults from the architecture doc; only its final taxonomy and scoring design are deferred.
**Consequences:** Phase 1 starts unblocked. One item cannot be deferred with the rest: the Phase 1 **pretraining corpus** (raw Python/TS code for next-token prediction) is needed immediately — a low-stakes choice, distinct from the Phase 2 review dataset, but a near-term one.

## ADR-018 — Phase 1 corpus: own repos + a permissively licensed public slice
**Status:** Accepted
**Context:** The from-scratch model needs raw Python/TS code for next-token prediction (distinct from the Phase 2 review dataset). The choice is low-stakes for model quality but carries licensing/provenance implications, so it is made by the owner, not delegated.
**Decision:** A hybrid corpus: the owner's own repositories (meaningful, zero license questions) topped up with clearly permissively licensed public code (MIT/Apache-2.0 only) for volume. Every source is recorded in `data/SOURCES.md` with license and pull date. The corpus itself is git-ignored and regenerated by committed prep scripts.
**Consequences:** No license risk on the core; provenance is auditable; the corpus is reproducible from recipe rather than stored. The public slice must be filtered to the allowed licenses at prep time.

## ADR-019 — Implementation is agent-assisted, human-reviewed
**Status:** Accepted
**Context:** Implementation will be delegated to coding agents. Agents follow written rules well and unwritten ones poorly, and the owner must remain the decision-maker.
**Decision:** A root `CLAUDE.md` is the agents' operational authority (it distills, never overrides, the ADRs). Work proceeds as the eight milestone increments in `docs/MILESTONES.md`, one branch per milestone, with a human reviewing every diff before merge. A minimal CI (ruff + pytest) gates every push. Agents must not edit ADRs, alter frozen contracts (the `review()` interface and output schema), or commit ignored artifacts; when implementation argues for a design change, the agent proposes a superseding ADR and stops for approval.
**Consequences:** Work arrives in reviewable units with an explicit definition of done; design authority stays with the owner at the cost of review effort on every merge. Those reviews are themselves a future source of Phase 2 training examples.
