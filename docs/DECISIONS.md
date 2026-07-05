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

## ADR-020 — Project license: Apache 2.0
**Status:** Accepted
**Context:** The README left the project license as "TBD." A choice was needed before any further code lands so contributions and downstream uses have unambiguous terms. The realistic candidates were the two permissive licenses already trusted on the *input* side by ADR-018 (MIT and Apache 2.0); copyleft (GPL/AGPL) and public-domain-equivalent options (CC0/Unlicense/0BSD) were not in scope — the former conflicts with the corp-friendly stance, the latter carry jurisdictional uncertainty corporate legal teams routinely flag.
**Decision:** License the project under **Apache License 2.0**. The canonical text is at `LICENSE` in the repo root; the README's "Project license: TBD" line is updated to point at it. The copyright line names `rae004` (the GitHub owner); a real legal name or org can be substituted later without a new ADR — it's a fill-in-the-blank, not a design change.
**Consequences:** Apache 2.0's explicit patent grant (§3) and defensive-termination clause are exactly what corp legal teams look for when evaluating whether to depend on or vendor an OSS tool — the main reason it was chosen over MIT, which is equivalently permissive but silent on patents. The trade: every source file *may* carry the Apache header (we're not requiring it for Phase 1's tiny tree — the root `LICENSE` is enough), and a `NOTICE` file becomes part of the contract if attribution requirements ever arise from incorporated third-party code (none today; defer until needed). Compatibility is unchanged with the Phase 1 corpus rule (ADR-018: MIT/Apache-2.0 inputs), since Apache 2.0 can include MIT-licensed code.

---

*Recorded 2026-06-26.*

## ADR-021 — Workhorse GPU swap: GTX 1050 → RTX 5060 Ti 16GB; PyTorch pin moves to cu128
**Status:** Accepted — supersedes ADR-014
**Context:** ADR-014 pinned an older cu126-line PyTorch on the workhorse because the GTX 1050 (Pascal `sm_61`) sat past current PyTorch builds' support line. Two things forced revisiting the choice. First, during the live M7 verification (PR #7) the 1050's 2 GB VRAM proved a hard ceiling: `qwen2.5-coder` runs ~95 % on the i7-8700 CPU because almost nothing fits in VRAM, and a typical PR-sized diff review takes 5–15 minutes — verified-working but not interactive (RUNBOOK §6c). Second, an attempt to reinstall `system76-driver-nvidia` for the 1050 during the M3 CUDA closure (2026-06-20 session) bricked Pop! boot, leaving the workhorse offline. The honest path forward — recover the bricked install, fight the 1050's age, and accept the same throughput — wasn't worth the time on hardware we were already planning to replace. An ASUS Dual RTX 5060 Ti 16GB OC (Blackwell, `sm_120`, GDDR7, 180 W TDP) was purchased on 2026-06-22 alongside a Corsair RM650e PSU swap; both land 2026-06-26.
**Decision:** Replace the GTX 1050 with the RTX 5060 Ti 16GB. Replace the aging 500 W EVGA PSU with a Corsair RM650e (650 W, Cybenetics Gold, 7-yr warranty) at the same time. Re-pin the workhorse's PyTorch from the **cu126** wheel line to the **cu128** wheel line (current generation, supports Blackwell `sm_120`). The workhorse's main lockfile stays CPU-only (build plane behavior, ADR-014 logic); the cu128 venv remains a separate environment per SETUP.md §2. Phase 2 fine-tuning still rents a GPU (re-affirms ADR-003) — 16 GB makes QLoRA on a 7 B base *viable* locally, but the rental remains the chosen path for the actual Phase 2 run; local QLoRA-on-7900-XTX-class hardware would be a *future* ADR if and when it makes sense.
**Consequences:**
- **M7 reviewer becomes interactive.** With 16 GB VRAM, `qwen2.5-coder` runs entirely on the GPU; PR-sized reviews drop from 5–15 min to seconds. The `timeout = 550` default in `configs/review.toml` is now wildly oversized for workhorse and `RUNBOOK.md §6c`'s "Realistic latency on the GTX 1050" section becomes a historical note. Both get updated in the rebuild PR, not this ADR.
- **M3's `--device cuda` clause closes** on the rebuild. CUDA-by-design Phase 1 training was always meant to use the workhorse as the only CUDA box; the swap honors that without changing the M3 done-means.
- **No code changes needed in the training loop.** ADR-016's "training code is fp32 and device-agnostic" rule was the right call — the loop will pick up the new card via `--device cuda` with no edits.
- **Smaller-than-it-looks ecosystem shift.** Going CUDA → CUDA, just newer wheels. No ROCm setup, no PyTorch API surface changes that affect us, no Ollama reconfiguration beyond confirming GPU offload. The runbook §3 cu126 install steps need replacing in lockstep (lands alongside the rebuild, in a separate PR).
- **Two-vintage gap reopens.** Same ADR-014 trade-off in reverse: workhorse now sits on a *newer* PyTorch than `command`'s main lockfile (CPU torch on the cu128 line could be added, but the build plane has no use for it). Accept the gap. The Phase 2 rental image targets *current* PyTorch/CUDA — the workhorse environment now matches that, which is a small but real win for the smoke-test-before-rental workflow.
- **Power and form-factor verified ahead of purchase.** Card is 2.5-slot, single 8-pin, fits the workhorse case; the 650 W PSU lands at ~50 % load at peak (efficiency sweet spot for Gold-tier). Both motherboard and i7-8700 stay; ADR-013's role assignment (workhorse = serving + CUDA) is unchanged.
- **The 2026-06-20 results entry** in `docs/results.md` correctly noted M3 CUDA was deferred to "the future GPU replacement"; this ADR is that replacement.

---

## ADR-022 — Phase 2 base model: `qwen2.5-coder:7b` (with `starcoder2:7b` as a trust-anchor cross-check)
**Status:** Accepted
**Context:** Phase 1 closed with an M8 baseline scored against **`qwen2.5-coder` (the default `:latest`, ~7B params)** served via Ollama on the workhorse (docs/results.md 2026-06-28 M8 entry + docs/baseline-eval.md): macro P/R/F1 = 0.273, verdict accuracy = 0.727 (8/11), recall 1.000 on `security`, 0.000 on every other category (miscategorization, not silence), with the three verdict failures all **false negatives** on real bugs. Phase 2 (ADR-001, ADR-003, ADR-017) is a QLoRA fine-tune of a small pretrained code model into the actual reviewer, so a base-model choice is now unavoidable. Realistic candidates evaluated: **qwen2.5-coder-7b** (the M8 baseline model — Alibaba, Apache-2.0, strong code benchmarks, instruction-tuned for JSON-shaped output), **starcoder2-7b** (BigCode collaboration with Hugging Face + ServiceNow + academic researchers — genuinely peer-reviewed paper, training data documented as *The Stack v2*, license-filtered, OpenRAIL-M license), **deepseek-coder-v2** (DeepSeek — top-tier code benchmarks, less training-process transparency), and **Codestral** (Mistral — EU origin, but the original release is *not* commercially open, disqualifying under ADR-020). Two axes matter: raw code-review quality (measurable against the M8 baseline) and provenance transparency (relevant for supply-chain trust even though ADR-015's LAN-only deployment blunts most of the concern). The two leading candidates trade against each other: Qwen wins on measurable-quality-vs-baseline; StarCoder2 wins on academic-transparency.
**Decision:** Fine-tune **`qwen2.5-coder:7b`** as the Phase 2 base model. In parallel, run the M8 eval harness against **`starcoder2:7b`** as a one-time **cross-vendor trust-anchor comparison**; the result gets recorded in `docs/results.md` alongside the Qwen baseline but *does not* become a training target — it exists so future readers can see whether an independent, more academically-transparent model agrees or disagrees with our Qwen-based numbers. The QLoRA hyperparameter direction (rank, alpha, target modules), the fine-tuning dataset choice, and the container/rented-GPU workflow are **out of scope for this ADR** and will land as their own ADRs when each is decided. This ADR locks in the base model only.
**Consequences:**
- **Phase 2 quality is directly comparable to Phase 1.** The M8 baseline is qwen2.5-coder:7b at zero-shot; a Qwen QLoRA gives an apples-to-apples "did fine-tuning help" number without a base-model-difference confound. That's the single most valuable property of this choice.
- **Instruction-tuning is already done.** The `-Coder-Instruct` variants know JSON-shaped structured output. StarCoder2 base needs its own instruct-tune before it behaves as a reviewer — additional work that's out of scope for us.
- **Fits the workhorse serving path.** 7B in q4_K_M is ~4-5 GB in Ollama's GGUF form, comfortably in the 5060 Ti's 16 GB with headroom for the KV cache. Consistent with ADR-021's "reviewer becomes interactive" outcome.
- **Provenance trade is accepted.** Qwen's training data process is less documented than StarCoder2's. ADR-015's LAN-only deployment means Qwen never sees our code (all inference is local), which blunts the most obvious supply-chain risk; the residual concern (a base model that memorized restrictively-licensed public code) is a **general-LLM problem, not a Qwen-specific problem**, and StarCoder2 is the only realistic escape hatch. The one-time cross-check clause in the Decision above is how we surface any material disagreement between the two.
- **The M8 baseline gets a companion measurement.** `docs/results.md` will grow a `starcoder2:7b` eval entry with the same scoring shape as the Qwen baseline. If StarCoder2 disagrees with Qwen on a case with high divergence, that's a signal about reviewer reliability worth investigating before spending fine-tuning cycles.
- **The false-negative bias from M8 is the specific fine-tuning target.** Qwen said "looks fine" on `off-by-one-loop`, `retry-on-auth-failure`, and `n-plus-one`. Whatever fine-tuning dataset gets chosen (separate ADR) must include *(diff-that-has-a-bug, review-that-catches-it)* pairs weighted toward these failure modes.
- **Re-affirms ADR-003.** QLoRA on a 7 B base is *viable* locally on the 5060 Ti (16 GB is enough for QLoRA training of a 7 B model at rank 16-32) but the Phase 2 training run still rents a GPU per ADR-003 for speed. Local capability is now the fallback / smoke-test path, not the primary workflow. ADR-021's parenthetical ("QLoRA on a 7 B base *viable* locally, but the rental remains the chosen path") stands unchanged.
- **Apache-2.0 license alignment.** Qwen2.5-Coder ships under Apache 2.0, which matches the project's own license (ADR-020) — no re-license complications for the fine-tuned artifact. StarCoder2's OpenRAIL-M is compatible with our use case but adds a `use-restrictions.md` obligation we'd have to honor; using it as a trust-anchor eval target (not a redistributed base) sidesteps that.

---

## ADR-024 — Eval scoring: dual-metric (strict + severity-only), reported together
**Status:** Accepted — discharges the "precision-aware eval scoring methodology" item deferred in ADR-017
**Context:** The M8 eval harness (PR #18, ADR-005) scores a model finding as a match iff both `severity` and `category` equal the reference. That strict rule was the *(proposed)* default from ARCHITECTURE.md §4 and worked well enough for a single-model baseline. The ADR-022 cross-check (docs/results.md 2026-07-05 entry) then produced data the harness wasn't designed to interpret cleanly: **qwen2.5-coder:7b** got recall 1.000 on `security` and 0.000 on every other category; **starcoder2:15b-instruct** got recall 1.000 on `performance` and 0.000 everywhere else. Neither model was *silent* on the missed categories — both flagged findings the reference expected, they just filed them under different (severity, category) buckets than the eval set. Concretely: on `n-plus-one`, Qwen produced 2 findings but neither hit `(warning, performance)`, so it scored 0; on `sql-injection`, StarCoder2-Instruct produced a finding but not at `(error, security)`, so it also scored 0. Under strict matching, "found the right issue with the wrong label" and "missed the issue entirely" look identical — a lossy collapse the aggregate numbers can't undo, and one that would cause a Phase 2 fine-tune to be credited (or penalized) for surface-level taxonomy alignment as much as underlying reviewer skill. The cross-check also demonstrated that **severity boundaries are more durable across models than category labels** — both models called security issues "error"-severity when they surfaced them at all, and disagreement was concentrated in the category axis. The methodology decision this ADR discharges was explicitly deferred by ADR-017 to the Phase 2 boundary; that boundary is here.
**Decision:** Score every case **twice** and report both. **Strict scoring** (existing: match on `(severity, category)`) stays the primary metric — the M8 baseline number (0.273 macro F1, 0.727 verdict accuracy against qwen2.5-coder:7b) remains directly comparable to any future entry. A new **severity-only scoring** (match on `severity` alone; category ignored for the *match* step but still recorded per-case for the category-recall breakdown) becomes the secondary metric — same math, looser match criterion. Aggregate reports show both sets of macro P/R/F1 side-by-side; per-case tables gain a second precision/recall/F1 triple; the "recall by category" section keeps the current strict-match interpretation (it's the only reading where a per-category recall > 0 means anything at all — under severity-only, "recall on security" would collapse to "recall on any error-severity finding" and stop being category-specific). Verdict accuracy is unchanged by this ADR (verdict derives from severity threshold alone; category isn't involved). Implementation is a follow-up code PR against `src/codereview/eval.py` — this ADR is decision-only.
**Consequences:**
- **The M8 baseline (0.273 strict) stands verbatim and stays load-bearing.** Any Phase 2 candidate must still beat it on the strict metric — that's the primary yardstick. The severity-only number is auxiliary signal, not a replacement floor.
- **The delta between the two metrics is itself a measurement.** A large gap (severity-only much higher than strict) means "model finds real issues but disagrees with the taxonomy"; a small gap means "model's misses are genuine misses." Both are useful to Phase 2 design. Expected values on the current cross-check data, once implemented: Qwen's strict-vs-severity-only gap is small (it already agrees with the taxonomy); StarCoder2-Instruct's gap is large (it finds the right severity issues but categorizes differently).
- **Category-recall breakdown stays valuable and stays strict.** The "personality difference" finding from the 2026-07-05 entry (Qwen catches security, StarCoder2-Instruct catches performance) is a strict-match observation; losing that in the severity-only view would erase the most actionable Phase-2 signal we have. Two views of the same data, each showing what the other can't.
- **Fine-tuning has a clearer target.** The 2026-07-05 entry's implication ("teach Qwen to catch performance patterns too") gets sharper: if fine-tuning moves the strict score without moving the severity-only score, we made the model comply with our taxonomy but didn't actually improve issue-detection; if both scores rise together, real reviewer capability improved.
- **Small implementation cost.** `_match_findings` is a private helper; adding a `_match_findings_severity_only` alongside is a few dozen lines. `CaseScore` gains a second set of P/R/F1 fields (or a `severity_only: CaseScore | None` sub-object — implementation detail). `render_report` gains a small table. `run_eval` calls both matchers per case. Tests parametrize across strict vs. severity-only. Estimate: one PR, one afternoon. Deliberately not doing it in this ADR so the decision stands independent of the implementation shape.
- **Report format is a breaking change for anyone parsing `docs/baseline-eval.md`.** Only consumer we know about is this project's own docs/results.md entries, which will be updated in the same follow-up PR. Not a real ecosystem concern.
- **Doesn't discharge every ADR-017 scoring question.** Message-similarity via embeddings, location-overlap bonuses, and per-severity weighting are all further-along scoring refinements this ADR explicitly leaves alone. The dual-metric baseline is the minimum viable improvement over strict-only — subsequent ADRs can layer on top if the fine-tuning results justify the added complexity.
- **Downstream ADR unblocked:** ADR-023 (fine-tuning dataset) can now proceed with a stable, dual-view yardstick to design against. Overweighting performance-category examples has a specific test: does the strict score on `n-plus-one` and similar rise, or does only the severity-only score rise? First case = real skill acquisition; second case = the model learned to file findings differently but didn't get sharper eyes.
