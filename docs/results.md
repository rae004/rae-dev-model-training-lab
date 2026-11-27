# Training Results

Reverse-chronological log of training runs. Each entry records the commit
it was generated from, the config, devices used, loss outcomes, and a
representative sample — the M4 "done means" contract from
`docs/MILESTONES.md`.

## How to add an entry

1. Note the commit SHA you trained from (`git rev-parse --short HEAD`).
2. For each device the run was performed on, capture the
   `param_count` and the `initial_eval` / `final_eval` numbers printed
   by `codereview train` at the end of the run.
3. Generate a sample from the saved checkpoint:
   `codereview sample --checkpoint <run-dir>/ckpt.pt --prompt "<seed>" --seed 42`
4. Copy the template below into the **Runs** section, fill in, commit
   (the entry should live alongside the code at the commit it describes).

## Template

```
### YYYY-MM-DD — <short run name>

- **Commit:** `<short SHA>`
- **Config:** `configs/<name>.toml`
- **Corpus:** `<source(s)>`, `<N>` chars, vocab=`<V>`
- **Wall time:** command=`<Xs>`, workhorse=`<Ys>`

| device | param_count | initial train | initial val | final train | final val |
| --- | --- | --- | --- | --- | --- |
| cpu (command) | ... | ... | ... | ... | ... |
| cuda (workhorse, GTX 1050) | ... | ... | ... | ... | ... |

**Sample (`--prompt "<seed>" --temperature 0.8 --top-k 40 --seed 42`):**

\`\`\`
<paste sample here>
\`\`\`

**Notes:** <observations>
```

---

## Runs

### 2026-11-27 — M14 four-surface verdict: rae-agent-candidate:run2 (closes #69)

ADR-030's full battery against the M13 fine-tune, served on workhorse
(Vulkan) with the stock model's exact template/parameters (weights are
the only difference). Reports: `docs/candidate-run2-transform-eval.md`,
`docs/candidate-run2-review-eval.md`, `docs/candidate-run2-tool-smoke.md`,
owner chat verdict on #68. Seed 20261126, temperature 0 where supported.

**Promotion gates (ADR-030):**

| surface | candidate | stock-7b | stock-32b | gate | verdict |
| --- | --- | --- | --- | --- | :---: |
| transform pass rate | **17/22 (77.3%)** | 17/22 | 20/22 | beat stock-7b | **FAIL** (tie) |
| review (strict F1 / verdict acc) | **0.455 / 0.818** | 0.273 / 0.727 | — | no regression | **PASS** (improved) |
| tool-calling smoke | **10/10** | 10/10 | 10/10 | ≥ 0.9, not degraded | **PASS** |
| chat | owner verdict: fail with notes (#68) | — | — | reviewed qualitatively | **done** (non-gating) |

**One gate fails → M15 takes the iteration arm** (one targeted change,
re-run M13→M14 once, record both runs).

**What the surfaces say together:**

- **Review learned the most** — strict F1 up 67% relative, verdict
  accuracy 0.727 → 0.818, and the three LGTM cases stayed clean (the
  precision trap the M8 baseline flagged). The most structured output
  (Review JSON) moved furthest.
- **Transforms didn't move at all**: the candidate fails the *identical
  five cases* stock-7b fails (`decline-no-dead-code` + four
  `philosophy_anchor` cases) and passes everything both pass.
  45% of the dataset bought zero measured change on its own surface.
- **Tool calling is untouched** — 10/10 via the same
  content-JSON-without-tags channel as stock; ADR-029's tripwire does
  not fire.
- **Chat (#68, owner fail-with-notes)**: casual voice took (6/7 under
  the 150-word cap); technical questions collapse into generic
  listicles over the cap; zero closed-book repo knowledge (confident
  confabulation instead). Verified against the model directly
  (`/api/chat`, no system prompt, temp 0 — the training shape), so not
  a serving-harness artifact.

**Diagnosis seed for M15:** the pattern across surfaces is coherent —
structure transferred, knowledge/philosophy didn't. The transform and
chat slices taught formats the base model already had, while the
philosophy-anchor behaviors (the actual target, per ADR-028's four
live failure modes) appear in too few, too-indirect pairs to move a 7B
in 3 epochs. Candidate M15 levers, one to be chosen: philosophy-anchor
pair shape targeted at the five failing cases' categories, or chat
pairs that include context at train time to match serve time.

### 2026-11-27 — M13 QLoRA full run on A100 (closes #65)

The real fine-tune: full 1,186-pair ADR-029 dataset, 3 epochs, seed
20261126, on a rented A100 80 GB PCIe. The shipped artifact is **run2**
(`rae004/qlora-run2`): `adapter/` and `qlora-run2-q4_k_m.gguf`
(4.68 GB, 4.91 BPW). Quality judgment belongs to M14's eval harness
(ADR-024/030), not to these training-time numbers.

- **Commit:** main `334e792` (image `run-20261127-334e792`) for run1/
  run2's training; the final proven image is `run-20261127-b5db131`
  (all fixes below) — identical training path, fixed endgame
- **Config:** `configs/qlora_baseline.toml`, no env overrides
  (1,186 pairs -> 1,068 train / 118 eval, 102 optimizer steps)
- **GPU:** RunPod A100 80 GB PCIe (SXM was pricier; NVLink irrelevant
  single-GPU)
- **Wall time:** ~55 min per run — 49:48 train (29 s/step), ~8 min
  merge + f16 GGUF + Q4_K_M + upload, plus ~5 min image pull
- **Cost:** **$8.24 for the whole M13 day** ($8.19 GPU + $0.05
  storage): one productive ~55-min A100 run is roughly $2 of that; the
  rest bought run1's lost quantize, run2's two unwanted repeat
  trainings (restart loop, below), and two $0.10-class A40 stop-check
  pods. ADR-025's $3–10/run band holds.

Metrics are **run1's** — identical config/seed/data/hardware; run2's
own printed numbers died with its pod log (fixed forward: the
entrypoint now uploads `trainer_state.json` with the adapter). The
shipped GGUF is run2's; differences are GPU-nondeterminism noise.

| metric | epoch 1 | epoch 2 | epoch 3 |
| --- | ---:| ---:| ---:|
| eval_loss | 0.3701 | 0.3487 | 0.3463 |
| eval_mean_token_accuracy | 0.9030 | 0.9078 | 0.9085 |

Train loss fell 0.78 → 0.32, smooth, no spikes; eval still improving
but flattening at epoch 3 — ADR-025's 3 epochs looks right, no
under-fit case for the 5-epoch extension. Compare the smoke run's
0.6017 eval_loss: the full dataset matters.

**The M13-caught failures** (same pattern as M12 — each found by a pod,
each a cheap fix):

1. **`llama-quantize` SIGILL on the A100 host** (run1, after a perfect
   training). llama.cpp builds `-march=native` by default, so the
   binary carried command's instruction set; the M12 A40 host matched
   by luck, the A100 host didn't. Fixed with `GGML_NATIVE=OFF` (#85).
2. **Self-stop called a host that doesn't exist.** #82's
   `rest.runpod.io` returns NXDOMAIN from RunPod's own nameservers —
   everywhere. Run2 finished, failed to stop, and RunPod's
   restart-on-exit retrained it twice more before manual terminate
   (~$3 of the day's bill). Two fixes: never exit on a pod — retry,
   then idle under the 4 h max-runtime cap (#86, kept); and the real
   endpoint, `POST api.runpod.io/v2/pods/{id}/action`
   `{"action": "stop"}`, found via the v2 OpenAPI schema and verified
   live from a pod terminal with only the injected pod-scoped
   `RUNPOD_API_KEY` (#87). A misdiagnosis along the way (broken pod
   DNS + a DoH fallback, #86) was removed once the pod's own terminal
   disproved it.
3. **Metrics lived only in pod logs** — see above; `trainer_state.json`
   now ships with the adapter.

**Hands-off proof:** the final `stopcheck2` pod (image
`run-20261127-b5db131`, 50-pair slice) ran train → artifacts → upload
→ **stopped itself**, zero intervention. The babysitting era is over;
the 4 h max-runtime cap remains as the belt.

**Carry-forward for M14:** pull `qlora-run2-q4_k_m.gguf` on the
workhorse, `ollama create code-reviewer:run2`, eval per ADR-024/030
against the stock-7b baseline. HF repos `qlora-run1`/`qlora-stopcheck`/
`qlora-stopcheck2` are debugging byproducts, deletable; `qlora-run2`
is the artifact of record.

### 2026-11-26 — M12 QLoRA container smoke run (closes #63)

First GPU execution of the ADR-025/026/029 QLoRA pipeline: the
`docker/qlora-runpod` image ran end-to-end on a rented RunPod A40 —
train → adapter push → merge → GGUF convert → quantize → GGUF push.
A 50-pair smoke slice, not a quality run; the artifacts exist to prove
the plumbing, and the model itself is meaningless.

- **Commit:** `1105e9e` (image `run-20261126-1105e9e`; branch commit —
  squash-merged to main as `8eddf56`)
- **Config:** `configs/qlora_baseline.toml` + env `MAX_PAIRS=50`,
  `MAX_EPOCHS=1`, seed 20261126
- **GPU:** RunPod A40 48 GB, $0.59/hr (A4000 and RTX 4000 Ada were out
  of capacity)
- **Wall time:** ~10 min per successful cycle (~2 min image pull on a
  warm host, ~35 s dataset+weights, 2 min train, ~6 min merge + GGUF +
  upload)
- **Cost:** **$0.96 for the entire M12 smoke campaign** — seven pod
  deploys including every crash loop below ($0.93 GPU + $0.02 storage)

| metric | value |
| --- | ---:|
| train_loss (2 steps) | 0.7233 |
| eval_loss (5 held-out pairs) | 0.6017 |
| eval_mean_token_accuracy | 0.8714 |

**Artifacts:** `rae004/qlora-smoke1` on HF Hub — `adapter/` (LoRA +
tokenizer) and `qlora-smoke1-q4_k_m.gguf` (4.46 GB, 4.91 BPW, from a
14.5 GB f16 intermediate).

#### What the smoke run caught (the point of M12)

Five real failures, each invisible to the CPU-only tests, each fixed
for ~10 cents of GPU time instead of surfacing on a $2/hr A100:

1. **Dead HF token** — the saved token itself was revoked; rotated
   (crash loop 1, 401 on the private dataset).
2. **TRL 1.19 dropped `warmup_ratio`** from `SFTConfig` — ADR-025's
   ratio is now translated to `warmup_steps` in the entrypoint (#76).
3. **Triton's runtime JIT needs `python3-dev`** — first training step
   compiles a CUDA shim; added in a late image layer (#77).
4. **transformers 5.x re-saves tokenizer configs the converter venv's
   older transformers can't parse** — the merged dir now gets the base
   model's hub tokenizer files verbatim (#79).
5. **RunPod restarts the container on *any* exit, including success.**
   "exit 0 terminates the pod" (ADR-026 assumption) is false — a
   finished run re-executes forever until manually terminated. The
   reruns are idempotent (HF dedup skips unchanged uploads) but billed.
   An earlier "OOM" diagnosis of this behavior was wrong — the restarts
   after the memory-utilization warning were post-success loops, and
   the 95 % memory reading was page cache.

Also shipped for debuggability: `DEBUG_HOLD=1` pod env freezes the
container on a crash instead of letting RunPod wipe the log (#78);
the merge phase frees the training model before the converter runs
(#80 — written for the misdiagnosed OOM, kept as a correct hygiene
change).

#### Carry-forward for M13 (full A100 run)

- **The pod will not stop itself.** Either terminate manually when
  `gguf ->` prints, set the template's max-runtime cap (ADR-026's 4 h
  belt) as the backstop, or add a runpodctl self-stop (needs a RunPod
  API key as a pod secret). Decision deferred to M13 setup.
- Template needs: container disk 80 GB, no volume (never mount over
  `/workspace`), secret `HF_TOKEN`, env `RUN_TAG` (+ `DEBUG_HOLD=1`
  recommended); drop `MAX_PAIRS`/`MAX_EPOCHS` for the full run.
- A100 estimate unchanged: 1–3 h ≈ $2–6.

---

### 2026-11-16 — M11 transform + tool-smoke baselines (ADR-030)

The two pre-training transform baselines and the tool-calling base rate,
measured before any fine-tuned candidate exists so the Phase 2 promotion
gates are fixed in advance. Not a training run — these are the numbers
M13's candidate is judged against.

- **Commit:** `221c182` (harness + case sets in the same commit)
- **Harness:** `codereview transform-eval` / `codereview tool-smoke`,
  22 transform cases + 10 smoke prompts in `eval/`, temperature 0,
  seed 42 — two consecutive 7b runs produced byte-identical reports.
- **Backend:** Ollama on workhorse (7900 XTX / Vulkan).
- **Models:** `qwen2.5-coder:latest` (7.6B, Q4_K_M — the stock-7b gate)
  and `qwen2.5-coder:32b` (32.8B, Q4_K_M — the deployment signal;
  what rae-local-agent runs today).

**Transform pass rates (gate: the M13 candidate must beat stock-7b):**

| category | stock 7b | stock 32b |
| --- | --- | --- |
| decline | 4/5 | 4/5 |
| preservation_trap | 5/5 | 5/5 |
| philosophy_anchor | 3/7 | 6/7 |
| straight_transform | 5/5 | 5/5 |
| **overall** | **17/22 (77.3%)** | **20/22 (90.9%)** |

7b failures: `decline-no-dead-code`, `anchor-noise-comments`,
`anchor-dead-code`, `anchor-backcompat-alias`, `anchor-abstract-types`.
32b failures: `decline-no-dead-code`, `anchor-backcompat-alias`.

**Tool-calling smoke (the ADR-029 tripwire base rate):** both models
**10/10**, every call via the content-JSON channel — stock qwen2.5-coder
names the right tool with valid arguments but omits the `<tool_call>`
tags its own chat template demands, so Ollama's parser never populates
the structured `tool_calls` field. The smoke check counts both channels
(willingness + format, per ADR-030's deliberate coarseness).
**Threshold set: `min_pass_rate = 0.9`** in `eval/tool_smoke.toml` — the
run is deterministic, so two dropped prompts means materially degraded
and fires the tripwire.

**Notes:**

- The harness scores what serving writes to disk: outputs are normalized
  with an exact mirror of rae-local-agent's `_strip_fences` before
  scoring. Measured raw (no strip), both models collapse to near-zero —
  7b 0/22, 32b 3/22 — because they fence nearly every output. That mode
  is absorbed by serving today, but it is also the clearest formatting
  gap a fine-tune on unfenced outputs should close.
- The philosophy-anchor column is the fine-tune's headroom in one
  number: stock 7b is perfect on straight transforms and preservation
  traps and fails exactly where the owner's philosophy diverges from
  generic habits (keeps noise comments, keeps dead code, keeps
  backcompat aliases, won't widen to abstract types).
- Both models fail `decline-no-dead-code` the same way: told to delete
  commented-out code from a file whose only comments are real
  why-comments, both delete the real comments instead of declining.

First eval after the workhorse GPU swap captured in ADR-027: the RTX
5060 Ti is gone, replaced by an XFX Radeon RX 7900 XTX (Navi 31, RDNA3,
24 GB VRAM). Ollama auto-detected the card via its **Vulkan backend**;
no ROCm install was needed. This entry records the resulting
performance and quality numbers so ADR-027's "Vulkan is sufficient"
claim has lived data.

**Not** a new baseline. Same model, same config, same eval set as the
2026-07-05 entry — the only variable is the physical GPU + the
compute library (CUDA cu128 → Vulkan). This entry answers: "did the
GPU change move the review quality?" **No, within sampling-variance
noise.**

- **Commit:** `35680ac` (main HEAD at run time; this entry adds on top)
- **Backend:** `qwen2.5-coder:latest` on `http://workhorse:11434`
- **Config:** `configs/review.toml` (unchanged)
- **GPU + library:** XFX RX 7900 XTX via Ollama's Vulkan backend
  (`library=Vulkan description="AMD Radeon RX 7900 XTX (RADV NAVI31)"
  total="24.0 GiB" available="23.8 GiB"`)
- **Wall time:** **24 s** for all 11 cases
- **Full report:** `docs/baseline-eval-7900xtx-vulkan.md`

#### Three-way comparison across M8 runs on this same setup

| run date | GPU | library | wall | strict F1 | sev-only F1 | verdict |
| --- | --- | --- | ---:| ---:| ---:| ---:|
| 2026-06-28 | 5060 Ti | CUDA cu128 | 72 s (cold) | 0.273 | — (strict-only harness) | 0.727 |
| 2026-07-05 | 5060 Ti | CUDA cu128 | 21 s (warm) | 0.364 | 0.545 | 0.727 |
| **2026-10-12** | **7900 XTX** | **Vulkan** | **24 s** | **0.455** | **0.636** | **0.727** |

**Verdict accuracy is identical across all three runs** (0.727, 8 of
11). The strict F1 drift (0.273 → 0.364 → 0.455) is sampling variance
from `temperature = 0.2` compounded over three months of possible
`qwen2.5-coder:latest` tag updates in Ollama's registry — not a
hardware signal. The 2026-07-05 entry's "soft target" framing holds:
the baseline exists as a *range*, not a hard number.

#### Per-case shape

Same security-perfect pattern as every prior run. Specific per-case
drift from 2026-07-05 (sampling-variance churn, not systematic):

- `n-plus-one`: 2026-07-05 was strict 0 / sev-only 0 (genuine miss);
  today strict 0 / sev-only 1 (label-fixable). Improved by one tier.
- `new-function-no-tests`: 2026-07-05 was strict 0 / sev-only 1
  (label-fixable); today strict 0 / sev-only 0 (genuine miss).
  Regressed by one tier.
- `god-function`: 2026-07-05 model produced 2 findings; today model
  produced 0 findings. Different behavior, same outcome under scoring.
- `cryptic-names`: unchanged (strict 0, sev-only 1).

The ADR-023 "~⅓ categorization, ~⅔ detection" split for the
weakness-targeted slice still holds in aggregate — just which
specific cases are in which bucket varies run-to-run.

#### What this validates for ADR-027

- **Vulkan handles our workload.** 24 s wall time is noise-equivalent
  to the 5060 Ti CUDA setup (21 s warm). Review-quality is unchanged
  (within noise).
- **Zero install cost to get here.** Pop!_OS 24.04 ships `amdgpu` in
  the kernel; Ollama ships a Vulkan backend; the models were already
  cached. The 7900 XTX was serving reviews on first boot after the
  swap.
- **24 GB VRAM is headroom.** `qwen2.5-coder:latest` is 4.7 GB; model
  loads with ~19 GB VRAM free. Room for larger-model experiments
  (e.g. `qwen2.5-coder:14b`) without touching the hardware.

#### What this does not say

- **Nothing about ROCm vs Vulkan performance** on this card. We didn't
  install ROCm; we didn't need to. ADR-027 defers that comparison to
  a future amendment ADR if any of three triggers hit.
- **Nothing about larger-model performance.** If we move to
  `qwen2.5-coder:14b` for the serving backend, Vulkan may show a
  larger perf gap vs ROCm than it does on the 7B. Would need to
  measure then.
- **Nothing about Phase 2 training performance.** Phase 2 training
  rents NVIDIA GPUs per ADR-003 / ADR-026; the 7900 XTX is a serving
  machine, not a training machine. Local PyTorch would require ROCm,
  which this ADR explicitly defers.

---

### 2026-07-05 — Dual-metric baseline rerun on qwen2.5-coder (post-ADR-024 impl)

First eval run using the dual-metric harness implemented in PR #34
(ADR-024's decision made concrete). Same setup as the 2026-06-28 M8
baseline entry — same `qwen2.5-coder` on workhorse Ollama, same
`configs/review.toml`, same 11 cases in `eval/eval_set.toml` — but
scored twice per case (strict + severity-only).

**Not** a new baseline number. The M8 strict F1 (0.273 from the
2026-06-28 entry) remains load-bearing as the Phase 2 target. This
entry adds the *severity-only companion* the dual-metric harness now
produces, plus surfaces something worth flagging about eval variance.

- **Commit:** `ff63b5d` (PR #34 dual-metric implementation)
- **Backend:** `qwen2.5-coder:latest` on `http://workhorse:11434`
- **Config:** `configs/review.toml` (unchanged from M8 run)
- **Wall time:** 21 s (model already warm; original M8 run was 72 s
  including cold-load)
- **Full report:** `docs/baseline-eval-dual.md`

#### Headline numbers

| metric | strict | severity-only | delta |
| --- | ---:| ---:| ---:|
| Macro precision | 0.364 | **0.545** | **+0.181** |
| Macro recall    | 0.364 | **0.545** | **+0.181** |
| Macro F1        | 0.364 | **0.545** | **+0.181** |
| Verdict accuracy | 0.727 (8/11) | — (verdict is severity-derived, so identical) | 0 |

**The delta is the interesting number.** About one-third of what looks
like "reviewer skill" under strict scoring is actually "agreement with
our proposed taxonomy labels." The other two-thirds is genuine issue
detection.

#### Per-case delta: which failures were label-disagreement vs. genuine

Of the 11 cases, two show the exact ADR-024 pattern (strict 0,
severity-only 1):

| case | strict | sev-only | interpretation |
| --- | ---:| ---:| --- |
| `new-function-no-tests` | 0 | 1 | Model found the right-severity issue (a `warning`), filed it in a different category than our `test-gap` reference. Real find, wrong label. |
| `cryptic-names` | 0 | 1 | Same shape — right severity (`info`), wrong category. Real find, wrong label. |

Four cases show strict 0 / severity-only 0 — **genuine misses**, not
label disagreements:

| case | interpretation |
| --- | --- |
| `off-by-one-loop` | Model found *something* (1 finding) but at wrong severity. |
| `retry-on-auth-failure` | Model found *nothing* (0 findings). Truly missed. |
| `god-function` | Model produced 2 findings, neither at reference severity. |
| `n-plus-one` | Model produced 1 finding at wrong severity. |

The four "genuine miss" cases match the M8 baseline's false-negative
list from the 2026-06-28 entry (verdict was wrong on off-by-one,
retry, and n-plus-one; god-function passed verdict but missed the
design finding). **These are the specific targets Phase 2's
ADR-023 dataset needs to skew toward** — labels won't fix them; the
model needs to actually catch these patterns.

#### Category recall (strict) — unchanged shape from M8

| category | recall | reading |
| --- | ---:| --- |
| security | **1.000** | Both security cases caught, exactly at `(error, security)`. Consistent with M8. |
| bug / design / performance / readability / test-gap | 0.000 | All still zero under strict. Two of them (test-gap, readability) show up as severity-only matches but the ADR-024 rule keeps category recall strict-only, so they're not credited here. |

The severity-only fix would surface `test-gap` and `readability` if
we relaxed the category-recall computation too — but per ADR-024
that would erase the model-personality signal these zeros carry,
which is the actionable Phase 2 shape.

#### A note about strict-score variance across runs

The strict macro-F1 here (**0.364**) is higher than the M8 baseline's
strict macro-F1 from 2026-06-28 (**0.273**). Same eval set, same
config, same model tag — different numbers.

Two plausible causes: (a) `temperature = 0.2` in
`configs/review.toml` is non-zero, so Ollama's sampling has run-to-run
variance; (b) the underlying `qwen2.5-coder:latest` in Ollama's
registry may have been updated in the six days between runs (Ollama
doesn't version tags). Without running multiple times we can't
distinguish, and it's not this PR's job to.

**Implication for Phase 2 evaluation:** the M8 baseline is a *soft*
target, not a hard 0.273 floor. A responsible Phase 2 comparison
should re-run the harness against `qwen2.5-coder:latest` at the same
time as the fine-tuned model, so both sides see the same
model-registry state and sampling noise. Recording that as an
implicit requirement for whatever the fine-tune-evaluation PR does.

#### Verdict

**PASS** for the ADR-024 implementation validation:
- Dual-metric harness runs end-to-end against a live backend ✓
- Report format matches ADR-024's described shape ✓
- Delta between strict and severity-only surfaces actionable Phase 2
  signal ✓ (two cases have label-fixable gaps; four have detection
  gaps)
- Category recall stays strict-only per ADR-024 ✓
- M8's original strict F1 remains the load-bearing target (this entry
  adds companion signal, doesn't replace the historical baseline) ✓

#### For Phase 2 planning

Concrete addition to the ADR-023 dataset composition, now with real
numbers:

- **2 of 6 non-security misses are label-fixable** (new-function-no-tests,
  cryptic-names). Dataset should include `(diff, review)` pairs
  demonstrating how to categorize test-gap and readability findings
  in our proposed taxonomy.
- **4 of 6 non-security misses need detection improvement**
  (off-by-one, retry, god-function, n-plus-one). Dataset should
  over-index on these patterns per ADR-023's weakness-targeted slice.

The 2-vs-4 split gives ADR-023's 15% weakness-targeted slice a
concrete design ratio: ~⅓ of the weakness-targeted pairs demonstrate
correct categorization; ~⅔ demonstrate hard issue detection.

---

### 2026-07-05 — ADR-022 cross-check, part 2: starcoder2:15b-instruct

Follow-up to the 2026-07-04 base-model run. That run showed StarCoder2's
base model can't participate in a JSON-schema eval — the whole 11-case
run errored. The proper cross-vendor comparison ADR-022 was after
requires an instruction-tuned StarCoder2. BigCode released StarCoder2-
Instruct only at the 15B size (`starcoder2-15b-instruct-v0.1` on
Hugging Face), which Ollama exposes as `starcoder2:15b-instruct`.

This entry captures the resulting three-way comparison:
qwen2.5-coder:7b (M8 baseline), starcoder2:15b-instruct, and the
starcoder2:7b base (2026-07-04 entry) side by side.

- **Commit:** `394c147` (main HEAD at the time of the run) plus
  `fcfd4b3` (the harness fix from the base run — still load-bearing:
  one case still errors on malformed JSON)
- **Backend:** `starcoder2:15b-instruct` on `http://workhorse:11434`
  via Ollama (~10 GB q4, runs on the 5060 Ti per ADR-021)
- **Eval set:** `eval/eval_set.toml` — same 11 cases
- **Config:** `configs/review-starcoder2-instruct.toml`
- **Run command:**
  ```bash
  uv run python -m codereview eval --config configs/review-starcoder2-instruct.toml --report docs/starcoder2-instruct-baseline.md
  ```
- **Wall time:** 1 min 45 s (slower per case than Qwen 7B despite the
  15B being on the same GPU — parameter count matters more than the
  Blackwell speedup within one model)

#### Three-way headline

| metric | qwen2.5-coder:**7b** | starcoder2:**15b**-instruct | starcoder2:7b (base) |
| --- | ---:| ---:| ---:|
| Macro precision | **0.273** | 0.136 | 0.000 |
| Macro recall | **0.273** | 0.182 | 0.000 |
| Macro F1 | **0.273** | 0.152 | 0.000 |
| Verdict accuracy | **0.727** (8/11) | 0.545 (6/11) | 0.000 (0/11) |
| Errored cases | 0/11 | **1/11** | 11/11 |

Full report: `docs/starcoder2-instruct-baseline.md`.

**Qwen wins across the board — despite being half the parameters** (7B
vs. 15B). More instruct compute didn't overcome different-quality
instruction tuning + code-focus. ADR-022's Qwen choice is validated.

#### The interesting finding: models have different "review personalities"

Per-category recall reveals fundamentally different behaviors on the
same eval set:

| category | qwen2.5-coder:7b | starcoder2:15b-instruct |
| --- | ---:| ---:|
| **security** | **1.000** | 0.000 |
| **performance** | 0.000 | **1.000** |
| bug / design / readability / test-gap | 0.000 | 0.000 |

- **Qwen is a security-focused reviewer.** Caught `sql-injection` and
  `hardcoded-secret`. Missed everything else.
- **StarCoder2-Instruct is a performance-focused reviewer.** Caught
  `n-plus-one` (with real matched finding — P=0.50, R=1.00, F1=0.67
  on that case). Missed both security cases.

They don't just score differently — they *find different things*.

#### Case-by-case highlights

- `sql-injection` — Qwen caught (found + matched); SC2-I found but
  miscategorized (P/R = 0/1)
- `hardcoded-secret` — same shape: Qwen caught; SC2-I flagged but
  wrong category
- `n-plus-one` — **Qwen missed entirely**; SC2-I is the only model
  that produced a matched finding here (`P=0.50, R=1.00, F1=0.67`)
- `off-by-one-loop` — SC2-I errored on malformed JSON (line 13);
  Qwen's verdict was wrong on this case too
- LGTM cases — both models agree on verdict most of the time, though
  SC2-I over-flags on `lgtm-rename-only` and `lgtm-typing-improvement`
  (found 2 and 1 non-blocking findings respectively)

#### Bigger picture

1. **Qwen's false-negative bias from M8 is a specific category
   weakness, not a fundamental problem.** SC2-I catching `n-plus-one`
   proves the pattern IS learnable from code-only training. This
   directly informs Phase 2's fine-tuning target: teach Qwen (which
   is already strong on security + instruction-following) to also
   catch performance issues Qwen currently misses.

2. **Our proposed taxonomy aligns better with Qwen's natural output
   than with SC2-I's.** SC2-I found more findings on many cases (3 on
   `god-function`, 3 on `new-function-no-tests`, 2 on
   `lgtm-rename-only`), but almost none of them match our
   (severity, category) key. That's the flip side of the M8 lesson:
   the eval is measuring "compliance with our proposed defaults"
   as much as "review capability."

3. **Ensembling would win on this eval.** Neither model alone gets
   everything, but Qwen ∪ SC2-I covers security + performance.
   Not a Phase 2 plan (over-engineered for the goal, cost doubles),
   but an interesting future direction — and an observation worth
   recording for whoever revisits scoring methodology later.

4. **15B model, only ~1 min 45 s.** The 5060 Ti serves the 15B q4
   comfortably. The ADR-021 hardware swap keeps paying off — even
   larger models are practical for eval iteration now.

#### Compared to what we knew after part 1 (the base run)

Part 1 said the intended cross-check was unanswerable because base
StarCoder2 couldn't take the test — the value was the two unintended
findings (latent harness bug, and "M8 measures skill + instruction-
following").

Part 2 turns that around: **the cross-check IS answerable now, and
the answer is nuanced.** Not "Qwen and StarCoder agree on all cases"
or "totally disagree" — they agree on the LGTM shape and disagree on
which non-LGTM categories to catch. That's more useful than either
extreme would have been.

#### Verdict

**PASS** for the ADR-022 cross-check clause, this time in the way the
ADR intended:

- Independent-vendor comparison recorded ✓
- Qwen choice validated by the numbers ✓
- Specific weakness in Qwen (performance category) identified with a
  concrete example (`n-plus-one`) that Phase 2 fine-tuning should
  address ✓
- Prompt/taxonomy sensitivity confirmed as a real axis worth
  attention in ADR-017's deferred scoring-methodology decision ✓

#### For Phase 2 planning

Two concrete things this run adds to the deferred-ADR list:

1. **Fine-tuning dataset should over-index on performance-category
   examples** (n+1 queries, unnecessary allocations, blocking calls
   in async paths) — the specific weakness Qwen exhibits and
   StarCoder2-Instruct doesn't. Not a full-corpus rebalancing, just a
   deliberate skew.

2. **Consider severity-only scoring as an alternative** — the
   "personality difference" between the two models suggests category
   labels are less durable across models than severities are.
   Severity-only would let both models get credit for finding the
   right severity issue even if the taxonomy bucket differs. Would
   halve the strictness of the metric but might correlate better
   with practical usefulness. Not deciding now; adding to the
   ADR-017 deferred list.

---

### 2026-07-04 — ADR-022 cross-check: starcoder2:7b vs. the M8 harness

One-time cross-vendor comparison mandated by ADR-022. Ran the M8 eval
harness against `starcoder2:7b` (BigCode/HuggingFace/ServiceNow, released
alongside a peer-reviewed paper documenting training data provenance)
to test whether an independent, more transparently-trained model agrees
with the Qwen-based baseline in `docs/baseline-eval.md`.

**The intended comparison isn't the interesting outcome. The two
unintended findings are.**

- **Commit:** `394c147` (main HEAD at the time of the run) plus
  `fcfd4b3` (the harness fix this run required — see below)
- **Backend:** `starcoder2:7b` on `http://workhorse:11434` via Ollama
  (4.0 GB, runs on the 5060 Ti per ADR-021)
- **Eval set:** `eval/eval_set.toml` — same 11 cases as the Qwen baseline
- **Config:** `configs/review-starcoder2.toml` — identical to
  `configs/review.toml` except `backend.model`
- **Run command:**
  ```bash
  uv run python -m codereview eval --config configs/review-starcoder2.toml --report docs/starcoder2-baseline.md
  ```

#### Headline numbers

| metric | starcoder2:7b | qwen2.5-coder (M8 baseline) |
| --- | ---:| ---:|
| Macro precision | 0.000 | 0.273 |
| Macro recall | 0.000 | 0.273 |
| Macro F1 | 0.000 | 0.273 |
| Verdict accuracy | 0.000 (0/11) | 0.727 (8/11) |

Full report: `docs/starcoder2-baseline.md`.

#### What actually happened

**All 11 cases errored on JSON parsing** — StarCoder2's base model
never produced a valid `Review`-shaped object. Two error categories:

- **7 cases**: `no JSON object found in model output` — the model
  didn't produce anything JSON-shaped at all. Almost certainly
  continued the diff, riffed on it in prose, or emitted code.
- **4 cases**: `malformed JSON: Expecting property name enclosed in
  double quotes: line 2 column N` — attempted structured output but
  got syntax wrong. Column positions vary (1, 2, 3, 5) so the failures
  are per-response, not systematic.

The intended trust-anchor question (does an independent model agree
with Qwen's category assignments?) **can't be answered from this
data**. StarCoder2 base didn't take the test — it failed at the
format layer before content mattered.

#### The two unintended findings

**1. The harness had a latent bug that the M8-all-Qwen-compliant
baseline never surfaced.** The original `run_eval` (PR #18) treated
any single case failure as fatal and bailed with
`error: eval failed: no JSON object found in model output` on the
first StarCoder2 attempt. Qwen never triggered this because it always
returned parseable JSON. Fixed in commit `fcfd4b3` on this same branch:
per-case exceptions now score the case as P=R=F1=0 with
`verdict_correct=False` and record the error message; the aggregate
reflects the failures. Report gains an "Errored cases" appendix. Two
new tests (mixed-success run, ERR rendering) added.

*This is arguably the more valuable outcome of the cross-check than
the intended one.* Silent success on Qwen was hiding a bug that would
have bitten anyone plugging in a less compliant backend.

**2. The M8 baseline is measuring "reviewer skill + structured-output
compliance", not "reviewer skill" alone.** Qwen2.5-Coder-**Instruct**
does both; StarCoder2-**base** does neither of the second. That's
important context for reading the 0.727 verdict accuracy — some
non-trivial fraction of that number is the instruction-tuning, not
underlying reviewer capability. Phase 2 fine-tuning gets meaningful
credit for tightening the instruction-following axis specifically.

#### What this does not say

- **Nothing about StarCoder2's reviewer quality.** The base model
  isn't instruction-tuned for structured output. Judging it on that
  test is like judging a code-completion model on chess — wrong tool.
- **Nothing about whether a StarCoder2-*Instruct* variant would agree
  with Qwen.** That's the proper apples-to-apples comparison and
  remains open. Follow-up option: pull `starcoder2:7b-instruct` (or
  whichever tag Ollama exposes) and re-run the same eval. Would take
  ~10 min.
- **Nothing about ADR-022's base-model choice.** ADR-022 chose Qwen
  for baseline-comparability and instruction-tuned-out-of-the-box,
  both of which this result reinforces rather than challenges.

#### Verdict

**PASS** for the cross-check clause of ADR-022 in an unexpected way:
- Ran a cross-vendor comparison on the M8 harness ✓
- Recorded the result in `docs/results.md` alongside the Qwen
  baseline ✓ (this entry)
- Recorded the raw harness output in `docs/starcoder2-baseline.md` ✓
- **Not** a training target — StarCoder2 base is not viable for the
  reviewer role, and StarCoder2-Instruct is a future follow-up ✓
- Surfaced and fixed a latent bug that would have bitten future
  backends ✓ (bonus)

#### For a future proper cross-check

Pull `starcoder2:7b-instruct` (or the current instruct tag) and
re-run the eval. If it agrees with Qwen on most cases, that's the
trust-anchor signal ADR-022 was after. If it disagrees materially,
that's a signal about our prompt/scoring worth investigating before
locking Phase 2's fine-tuning design.

Not blocking Phase 2 either way. Recorded as an open follow-up.

---

### 2026-06-28 — M8: baseline eval against qwen2.5-coder (closes M8, closes Phase 1)

First scored run of the eval harness from PR #18 against the off-the-shelf
`qwen2.5-coder` served from workhorse via Ollama on the new 5060 Ti.
**Closes M8.** Establishes the Phase-2-must-beat baseline per ADR-005.

- **Commit:** `e77078d` (PR #24 — same point as the M3 and M6 entries above)
- **Backend:** `qwen2.5-coder:latest` on `http://workhorse:11434`
  (4.7 GB, runs fully on 5060 Ti VRAM per ADR-021)
- **Eval set:** `eval/eval_set.toml` — 11 hand-authored cases shipped in PR #18
- **Scoring methodology:** the *(proposed)* precision-aware defaults
  (PR #18 / ARCHITECTURE.md §4 / ADR-017)
- **Run command:**
  ```bash
  uv run python -m codereview eval --config configs/review.toml --report docs/baseline-eval.md
  ```
- **Wall time:** **72 seconds for all 11 cases** (was projected at hours on
  the GTX 1050; the ADR-021 GPU swap turned this into an interactive run)

#### Headline numbers

| metric | value |
| --- | ---:|
| Macro precision | **0.273** |
| Macro recall | **0.273** |
| Macro F1 | **0.273** |
| **Verdict accuracy** | **0.727 (8/11)** |

Full report committed to `docs/baseline-eval.md` alongside this entry.

#### Two different stories

The macro F1 reads worse than the actual model quality. The reason:
scoring requires `(severity, category)` to match **exactly**, and
qwen2.5-coder's idea of the taxonomy disagrees with our *(proposed)*
default. Per-case, the model usually *finds something* — it just files
the finding in a different category bucket than we expected.

#### Per-category recall — the real signal

| category | recall | reading |
| --- | ---:| --- |
| **security** | **1.000** | **Caught both** SQL injection and hardcoded secret. 2/2 on the safety-critical category — meaningful for a code reviewer. |
| bug | 0.000 | Model flagged the bug cases but with non-`bug` categories |
| design / performance / test-gap / readability | 0.000 | Same shape — issue found, taxonomy disagrees |

Security being the strongest is the right place to start: false
negatives on `security` are the costliest failure mode, and 100 %
recall there means qwen2.5-coder catches real security smells out of
the box. The other "0.000s" need a closer look — the model isn't
silent on those cases, it's miscategorizing.

#### Verdict accuracy is the practical metric

The model agreed with our *expected* `verdict.passed` on **8 of 11**
cases. The 3 misses were all **false negatives** on real bugs — model
said *pass* when we expected *fail*:

- `off-by-one-loop` — should fail; model passed
- `retry-on-auth-failure` (mask permanent auth failure) — should fail;
  model passed
- `n-plus-one` (DB query per loop iteration) — should fail; model passed

The model is biased toward "this looks fine." For a code reviewer
that's the worse failure mode (a false negative ships a bug; a false
positive just annoys a developer). **A clear Phase-2 fine-tuning
target.**

#### The macro F1 is informative, not damning

This isn't a damnation of `qwen2.5-coder` — it's the data ADR-017
anticipated:

> Final category taxonomy and severity threshold defaults are deferred
> to the Phase 2 boundary.

We're seeing the *(proposed)* defaults hit real model output and
disagreeing. Two honest paths for Phase 2:
1. **Tighten the prompt** to demand specific categories from our list
2. **Relax the matching** to score by severity-only, with category as
   a soft signal (less strict; rewards "found a real issue")

Both are reasonable. The data informs the choice; neither is forced.

#### Per-case scoring detail

(also in `docs/baseline-eval.md` verbatim)

| case | ref | model | matched | P | R | F1 | verdict |
| --- | ---:| ---:| ---:| ---:| ---:| ---:| :---:|
| off-by-one-loop | 1 | 1 | 0 | 0.00 | 0.00 | 0.00 | ✗ |
| retry-on-auth-failure | 1 | 0 | 0 | 0.00 | 0.00 | 0.00 | ✗ |
| sql-injection | 1 | 1 | 1 | 1.00 | 1.00 | 1.00 | ✓ |
| hardcoded-secret | 1 | 1 | 1 | 1.00 | 1.00 | 1.00 | ✓ |
| new-function-no-tests | 1 | 1 | 0 | 0.00 | 0.00 | 0.00 | ✓ |
| god-function | 1 | 2 | 0 | 0.00 | 0.00 | 0.00 | ✓ |
| n-plus-one | 1 | 2 | 0 | 0.00 | 0.00 | 0.00 | ✗ |
| cryptic-names | 1 | 1 | 0 | 0.00 | 0.00 | 0.00 | ✓ |
| lgtm-rename-only | 0 | 1 | 0 | 0.00 | 0.00 | 0.00 | ✓ |
| lgtm-typing-improvement | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | ✓ |
| lgtm-test-added-with-feature | 0 | 1 | 0 | 0.00 | 0.00 | 0.00 | ✓ |

The 8 `✓` verdicts correspond to cases where threshold-based blocking
agreed with our expectation. The 3 `✗` are the safety-critical false
negatives noted above.

#### Verdict

**PASS** for M8 done-means:
- Harness produces a scored report for the off-the-shelf Ollama
  model ✓
- Report recorded as the baseline any Phase 2 candidate must beat ✓
- Eval set committed (PR #18) ✓
- Scoring logic unit-tested (PR #18) ✓

**With M8 closed and the report committed, Phase 1 fully closes.**

#### Phase 1 → Phase 2

The deferred ADR-017 items come back to the table now:

- **Phase 2 base model choice** — `qwen2.5-coder:1.5b/7b/14b` are the
  obvious candidates; the 7b runs comfortably on the 5060 Ti's 16 GB.
- **Fine-tuning dataset sourcing** — not `data/corpus.txt`; needs
  `(diff, review)` *pairs* (per the M6 entry's explanation). Could
  use this very project's PR history as a starter — every commit's
  squash-message + the diff is a real review-shaped artifact.
- **Final severity / category taxonomy** — informed directly by this
  M8 baseline. The macro-F1 = 0.273 vs verdict-accuracy = 0.727 split
  is the data that drives the design.
- **Precision-aware scoring methodology** — current scoring uses
  exact `(severity, category)` match. Two reasonable adjustments:
  severity-only with category as soft signal, or message-similarity
  scoring via a small embedding model.

Phase 2 starts with a new branch and the first new ADR since this
rebuild closed Phase 1.

---

### 2026-06-28 — M6: baby-GPT on BPE (closes M6, Phase 1 main learning artifact)

First end-to-end run of the ADR-016 step-2 spec: ~14 M-param GPT trained
on BPE-4096 encoded tokens, on the new 5060 Ti. **The headline Phase 1
learning artifact.** Two samples below tell the real story.

- **Commit:** `e77078d` (PR #24 merged earlier this same session)
- **Config:** `configs/baby_gpt.toml`
- **Corpus:** `data/corpus.txt` (54.7 MB pruned), BPE-encoded to 10.88 M tokens
- **Tokenizer:** BPE trained from scratch on the corpus, **vocab=4096**
  (trained inline at run start — ~3-5 min of the wall time below)
- **Device:** workhorse, RTX 5060 Ti 16 GB (Blackwell, `sm_120`),
  cu128 PyTorch venv per ADR-021

#### Results

| | value |
| --- | ---:|
| **param_count** | **13.88 M** (slightly above ADR-016's "~10 M" estimate — block_size=256 + vocab=4096 grew the embedding table) |
| **Total wall time** | **~24.5 min** |
| ↳ BPE training + corpus encode | ~9 min (CPU, single-threaded) |
| ↳ Model training (10 000 steps) | **~15.5 min** on the 5060 Ti |
| **Throughput** | ~10.7 steps/sec × 32 × 256 tokens = **~87 k tokens/sec** |
| **Initial train loss** | 8.38 (≈ random over 4096 tokens) |
| **Final train loss** | **1.47** |
| **Final val loss** | 4.30 |
| **Min val loss** | **4.16 at step 8000** |

#### The overfitting story (the headline lesson)

| | train | val | gap |
| --- | ---:| ---:| ---:|
| Char-level (M3 closure, 920 k params) | 0.94 | 0.88 | val *better* than train |
| **Baby-GPT (this run, 13.88 M params)** | **1.47** | **4.30** | **2.93×** |

Val bottomed at step 8000 (1500 steps shy of the end) then rose while
train kept dropping — textbook *should-have-stopped-earlier*. Same
shape as the char-level long run from PR #14, but **amplified** by the
~15× capacity increase (920 k → 13.88 M params) on essentially the
same dataset (10.88 M tokens). Capacity outran the data's structure;
the model started memorizing instead of generalizing.

Three honest fixes for a future run:
1. **Dropout** (currently 0.0) — the easiest first lever
2. **Weight decay** — already 0.1, could go higher
3. **More data** — Phase 2's curated review dataset will be a totally
   different corpus shape, so this is a Phase 1 lesson, not a Phase 2
   blocker

#### Samples

The two samples below make the memorization visible. Both use the same
checkpoint, same seed, just different prompts.

**Python (`--prompt "def "` — memorizes FastAPI):**

```python
def post(
        self,
        url: str,
        title: str | None = None,
        description: str | None = None,
        gt: float | None = None,
        price: float | None = None,
        ge: float | None = None,
        ge: int | None = None,
        ge: float | None = None,
        min_n: int | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
        pattern: str | None = None,
        regex: int | None = None,
        discriminator: str | None = None,
        strict: bool | None = None,
        strict: bool | None = None,
        include_in_schema: bool | None = False,
        ...
        **Ex: Annotated[
            Any,
            Doc,
            Doc(
                """
                Include this response.

                You could be the sent serializer (without the response directly API).

                Read more about it in the
                [FastAPI docs for Custom Response - HTML, Stream, File, others](https://fastapi.tiangolo.com/advanced/custom-response/#redirectresponse).
                """
            ),
        ] = Default(JSONResponse),
```

The smoking gun: that URL is **verbatim from FastAPI's source** — the
model didn't generate it, it recited it. Real FastAPI types
(`APIRoute`, `JSONResponse`, `Default`, `Doc`, `Annotated`), real
`Annotated[..., Doc("""...""")]` pattern (FastAPI's actual docstring
convention). But also: `ge: float | None = None` repeated 3×,
`include_in_schema` repeated, `strict: bool | None` twice — the model's
parameter list keeps cycling because it learned the *shape* of a Field
without learning that each parameter should be distinct.

**TypeScript (`--prompt "function "` — memorizes microsoft/TypeScript):**

```typescript
function hasNonSameName(node: Node | Node) {
        if (node.kind === SyntaxKind.SourceFile || node.kind === SyntaxKind.SourceFile) {
            const compilerOptions = resolver.getEmitResolver();
            const compilerOptions = resolver.useSourceFiles!;
            ...
            if (emitFlags & EmitFlags.Ignormalizedlags & EmitFlags.CustomTransform) {
                emitDecoratorsAndEmitHelpersAndEmitHelpersAndDisposeInternalEmitHelpers = [classDecorator, classDecorator, classDecorator, classDecorator, In) {
                emitDecoratorsAndDisposableFunctionsOrAssignedName(node, classDecl, InternalName.PrivateFieldInitializers);
                checkExternalEmitHelpers(node, ExternalEmitHelpers.LoadingFactory.createPropertyAssignment("_classPrivateFieldDecorate"));
                ...
                if (classInfo.classExtraInitializers) {
                    emitHelpers.push(createRunMethodExtraInitializer(classInfo.classMethodExtraInitializers));
                    emitHelpers.
```

Real TS-compiler internals (`SyntaxKind.SourceFile`,
`resolver.getEmitResolver`, `EmitFlags`,
`ExternalEmitHelpers.LoadingFactory.createPropertyAssignment`,
`classInfo.classExtraInitializers`). The naming convention
(`emitDecoratorsAndDisposableFunctionsOrAssignedName`,
`createRunMethodExtraInitializer`) is exactly the
verb-noun-with-helper-suffix pattern microsoft/TypeScript uses
internally. Overfitting tells: `Node | Node`, two identical `if`
branches, `classDecorator` × 4, `emitHelpersHelpersHelpersHelpers`,
truncated mid-statement at the end.

#### What the samples tell us about the corpus mix

- **Python sample is FastAPI-flavored** because FastAPI is ~5 MB of the
  corpus and the most distinctive Python idiom (real type hints +
  `Annotated[..., Doc()]` decorators).
- **TS sample is microsoft/TypeScript-flavored** because that one
  source is ~50 MB — over half the entire corpus.
- **Owner code (~1.2 MB after the prep-corpus exclude fix in PR #13)
  is invisible** in the samples. With owner code at 2 % of the corpus,
  that's expected. To get owner-flavored output, we'd need to weight
  the owner slice higher or train on owner-only (per the M4 ablation
  in the 2026-06-22 entry, but with this larger model + BPE).

This is exactly the "garbage in → garbage out" lesson from the
2026-06-22 entry, restated at higher capacity: **the model is a mirror
of its training data's proportions, not its quality**. microsoft/TypeScript
dominates because it's biggest, not because it's most representative
of what we'd want to review.

#### Compared to the char-level run from the 2026-06-22 entry

| | char-level baseline | **baby-GPT** |
| --- | --- | --- |
| Params | 920 k | **13.88 M** (~15×) |
| Tokens / batch | 32 × 128 = 4 096 chars | 32 × 256 = 8 192 BPE tokens (~40 k chars at 5× compression) |
| Effective context | ~128 bytes | **~1 280 bytes** (10× more code per training example) |
| Sample quality | English-y gibberish that *looked* like code | Actual code that *looks plausible until you read it* |
| Generalization | val < train (under-fit) | **val ≫ train** (over-fit, memorizing) |

The qualitative jump from "looks like code" to "is plausibly-valid code"
is the headline ADR-016 promised. The over-fit is the **same lesson**
as the char-level run, just amplified by capacity.

#### Verdict

**PASS** for M6 done-means:
- Completed run with loss curves ✓
- Samples saved ✓ (above)
- Headline numbers (wall time, throughput, param count) recorded ✓
- BPE wired into training via `tokenizer.type = "bpe"` config knob ✓
  (PR #16) and trains inline per ADR-016 — works exactly as designed
- M5 char-vs-BPE compression lesson is now visible in real samples:
  same model architecture, BPE encoding gives qualitatively different
  output

**This is also the formal "main learning artifact" of Phase 1.** The
disposable from-scratch model is now durably recorded. With M3 closed
earlier in this session and M6 closed here, **only M8 baseline scoring
remains for Phase 1 to fully close.**

---

### 2026-06-28 — Phase 1 char-level: CPU vs CUDA on the RTX 5060 Ti (closes M3)

First real CUDA training run after the workhorse rebuild (PR #23 + ADR-021).
**Closes M3's last unmet done-means clause** — *"the identical config runs
to completion with `--device cuda`"*. Same config, same seed, byte-identical
loss trajectory — just an order of magnitude faster.

- **Commit:** `9842dd5` (PR #22, BPE encode perf — workhorse cloned at this point)
- **Config:** `configs/char_step1.toml` (unchanged since the 2026-06-22 entry)
- **Corpus:** `data/corpus.txt` (54.7 MB pruned), vocab 439
- **Workhorse hardware:** RTX 5060 Ti 16GB (Blackwell, `sm_120`),
  i7-8700 host, cu128 PyTorch venv per ADR-021

#### Results

| device | wall time | param_count | initial train | final train | final val | min val (step) |
| --- | ---:| ---:| ---:| ---:| ---:| ---:|
| cpu — command (Ryzen 9 9900X, 24t) *(2026-06-22 entry)* | ~11 min | 920,064 | 6.05 | 0.94 | 0.88 | **0.81** (4250) |
| cuda — workhorse (RTX 5060 Ti) | **63 s** | 920,064 | 6.05 | 0.94 | 0.88 | **0.81** (4250) |

**Speedup: ~10.5×.** Loss trajectory is **byte-identical** to the CPU
run — same seed + fp32 + deterministic ops gives the same weights
regardless of device. ADR-016's "training code is fp32 and
device-agnostic" rule held up exactly as designed; the only thing
that changed was the hardware doing the matmuls.

#### Sample (`--prompt "def " --temperature 0.8 --top-k 40 --seed 42`)

CUDA checkpoint:

```
def == typescrenaping && typeof === type.dits.type) />;
        type = type === varow.log(importType) && isReturns.minit) || isGraneritance;
        return transformFlags.Namespace = regular withParameters
        result = result;
    }
}

/** @internal
```

For comparison, the CPU checkpoint sample (from the 2026-06-22 entry,
same prompt + seed) was English-y gibberish:

```
def undefined alse was the object" write allow's have to the clist in the eneed insertor
if the procked in in line the parent. * End to return object. Count function file
the file constructor be of the can maination is the the returning and the the
```

Samples differ even though the model weights are byte-identical because
`torch.multinomial` uses different RNG streams on CPU vs CUDA — same
seed value, separate RNG engines. The CUDA sample looks more
TypeScript-flavored (`@internal`, `transformFlags.Namespace`,
`typeof === type.dits.type`) — also expected, since the model learned
JSDoc and TS keyword patterns from the microsoft/TypeScript slice of
the corpus.

#### Verdict

**PASS** for M3's last clause:
- Identical config runs to completion with `--device cuda`: ✓
- Resume from checkpoint reproduces: not re-verified here (already
  shown in PR #4's tests; the loop is unchanged)
- Loss curves match CPU within numerical noise: ✓ (byte-identical
  in fact, since fp32 + deterministic + same seed)

**M3 is now fully closed.** The Phase 1 CPU-vs-CUDA benchmark from
ADR-016 step 1 is concrete: 10× speedup with no math change. The
serving plane (ADR-013) is doing what it was always meant to do.

---

### 2026-06-22 — Phase 1 char-level: pruned-corpus re-baseline + data-quality lesson

Re-run of the 2026-06-20 ablation on the **cleaned corpus** from PR #13
(`prep_corpus.py` now prunes `node_modules` / `.venv` / `dist` /
`build` / build caches / etc.). Two purposes: (a) re-baseline the
project on clean data, and (b) make the data-quality lesson concrete
and side-by-side comparable with the bloated run.

- **Commit:** `94e09a2` (PR #13's merge, immediately before this entry)
- **Configs:** same as the bloated entry —
  `char_step1.toml` / `_small.toml` / `_long.toml` / `_owner.toml`
- **Corpus:** `data/corpus.txt` shrank from 130 MB to **54.7 MB** (58 % drop);
  `data/corpus-owner-only.txt` shrank from 77 MB to **1.2 MB** (98 % drop)
- **Device:** `command` (Ryzen 9 9900X, CPU, fp32). No CUDA leg.

#### Headline numbers

| run | params | vocab | final train | min val (step) | × over random *(min-val)* |
| --- | --- | --- | --- | --- | --- |
| **baseline (5000 steps)** | 920 k | 439 | 0.94 | **0.81** (4750) | **196×** |
| small (`n_layer=2, d_model=64`) | 164 k | 439 | 1.38 | 1.13 (4500) | 142× |
| owner-only (clean 1.2 MB) | 834 k | **104** | **0.56** | 0.74 (4750) | 50× |
| long (10000 steps) | 920 k | 439 | 0.80 | **0.65** (8500) | **226×** |

#### Compared to the 2026-06-20 bloated runs

| run | bloated min val → pruned | bloated × random → pruned |
| --- | --- | --- |
| baseline | 1.30 → **0.81** | 252× → **196×** |
| small | 1.66 → 1.13 | 158× → 142× |
| owner-only | 1.32 → 0.74 | 273× → **50×** |
| long | 1.18 → **0.65** | 287× → **226×** |

Raw loss got *better* (lower) across the board on the pruned corpus,
**but the "× over random" ratio dropped**. This is the headline lesson:
loss alone is misleading when vocabulary changes, because the random
baseline `1/V` moves too. Pruning halved the full-corpus vocab
(924 → 439) and quartered the owner-only vocab (666 → 104), making
the random baseline easier to beat by default.

The pruned numbers are the **honest new baseline**: 196× for baseline,
226× for long, no contamination from npm ambient type files.

#### Samples (prompt `"def "`, temp 0.8, top-k 40, seed 42, 250 chars)

**Baseline (pruned, 920 k, 5000 steps):**

```
def undefined alse was the object" write allow's have to the clist in the eneed insertor if the procked in in line the parent.
     * End to return object. Count function file the file constructor be of the can maination is the the returning and the the
```

**Small (pruned, 164 k):**

```
def actory(start)
               """
                 "title""; tyt: {
               }
                                                                                                                                                                      
```

**Owner-only (clean 1.2 MB, 834 k):**

```
def when seriods", () => {
    renderWithTemplate();
    expect(result.errors[0]).toMatch(/NvdRow');
  });

  it('returns at async () to0 in exist', () => {
    expect(screen.queryByText('rawait content')).toBeInTheDocument();
    expect(screen.getByPlac
```

**Long (pruned, 920 k, 10000 steps):**

```
def returns the service index of the given to all set to the client type. If a changed a test user the return line to TS or this is sort of the is sorting. This type sort attarte that is here con matched on a return match to match the a so at referent wa
```

#### What the samples actually show (the qualitative lesson)

- **Owner-only is the headline.** Before pruning, it produced
  `private _tags?;` JSDoc nonsense — the model was almost entirely
  learning **npm ambient type definitions**, not the owner's code.
  After pruning to actual hand-written source: **the sample is
  recognizable Jest + React Testing Library**:
  `renderWithTemplate()`, `expect(...).toMatch(...)`, `it('...', () => {...})`,
  `expect(screen.queryByText(...)).toBeInTheDocument()`. **The model
  finally learned the owner's testing style.** This single before/after
  is the rawest "garbage in → garbage out" demonstration the project
  could produce.
- **Baseline pruned** is more English-prose-y and less JSDoc-flavored
  than the bloated baseline. The microsoft/TypeScript repo's `built/`
  output (which the prune removed) was a major source of the previous
  baseline's `* @default - "--"`-style noise.
- **Long pruned** continued to produce coherent prose ("service index",
  "client type", "TS sort"). Val bottomed at step 8500 (0.65), then
  bounced — same "should-have-early-stopped" signal as the bloated
  long run, but at a lower absolute floor.

#### Data-quality math (answering "was the 50× over random skewed?")

For posterity — the corrected math that motivated this rerun:

```
bloated baseline:  loss 1.02  → model prob e^(-1.02) ≈ 36.1 %
                   random 1/924 ≈ 0.108 %
                   ratio: 334× (corrected; earlier "50×" claim used
                                wrong vocab estimate of 140)

pruned baseline:   loss 0.94  → model prob e^(-0.94) ≈ 39.1 %
                   random 1/439 ≈ 0.228 %
                   ratio: 172× (at final train; 196× at min val)
```

So **yes, the bloated number was inflated** — not by the model being
worse on real data, but by the vocab being twice as large and the
random-uniform baseline correspondingly twice as easy to beat. Loss
numbers across different vocabularies aren't directly comparable.

#### Verdict

The **new project baseline is `0.81 min-val / 196× over random`** on
the pruned 54.7 MB corpus. This supersedes the bloated baseline for
purposes of comparing future models. The 2026-06-20 entry stands as
the historical pre-prune snapshot and the data-quality lesson.

---

### 2026-06-20 — Phase 1 char-level: baseline + ablation triplet

- **Commit:** `88119a4` (commit at run time; this entry adds on top)
- **Configs:** `char_step1.toml` (baseline), `char_step1_small.toml`,
  `char_step1_long.toml`, `char_step1_owner.toml`
- **Corpus:** `data/corpus.txt` (130 MB, vocab 924) for
  baseline / small / long; `data/corpus-owner-only.txt`
  (77 MB, vocab 666) for owner
- **Device:** `command` (Ryzen 9 9900X, 24t, CPU). **No CUDA leg:**
  workhorse driver install bricked Pop! boot during this session;
  M3's CUDA done-means clause is **deferred** to the future
  GPU replacement (likely RTX 5060 Ti 16GB), captured in a future ADR
- **Wall time (with concurrent contention noted):**
  baseline 11 min · small 8.5 min (contended) · owner-only 7 min
  (contended) · long 36 min (contended)

#### Results

| run | params | final train | min val (step) | final val |
| --- | --- | --- | --- | --- |
| baseline (5000 steps, full corpus) | 1.04 M | 1.02 | **1.295** (4250) | 1.40 |
| small (`n_layer=2, d_model=64`, 5000 steps) | 226 k | 1.50 | 1.660 (4500) | 1.71 |
| owner-only corpus (5000 steps) | 978 k | 0.88 | **1.318** (5000) | 1.32 |
| long (same as baseline, 10000 steps) | 1.04 M | 0.85 | **1.177** (6500) | 1.24 |

Random-init loss is ~6.85 across the runs that share the 130 MB corpus
(vocab 924). Owner-only starts at 6.54 — smaller vocab (666) lowers the
random-init ceiling. **All four runs reach a clearly different floor**,
which is the lesson.

#### Samples (prompt `"def "`, temp 0.8, top-k 40, seed 42, 250 chars)

**Baseline (1.04 M params, 5000 steps, full corpus):**

```
def updates attribute only appendand.
     *
     * @default - "--"
     */
     pathTs: "path";
     * @depreprese-iorspecation.html
     */
     interface _maliftDatarisPathSetAccessProperty {
      /**
      * The **`ice`** method of the ID of the Paths object (units an options event.
      */
```

**Small (226 k params):**

```
def a boot a be done a Das appen: notable baseArn, object to of expected morized on ots.
     *
     * [** `Start of or connection the port inse.
      *
       * @see resource in object dibject, notad of the a parser type inonstry to thins wable the ret
```

**Owner-only (978 k params, owner corpus):**

```
def in the gion.
     */
    private _tags?;
    /**
     * Reads a stream of the file deplay of tags protection.
     *
     * You can express the key or tags your defining can it AT cully be up to the formats entry of the cloud one instance in the endi
```

**Long (1.04 M params, 10000 steps):**

```
def kind: string,
            emit?: number | A | If boolean |  Emitter | None = None,
              none: None,
                : none,
                   only: string,
                   break,
                    ""
                    file = file(rea
```

#### Observations

- **Param count matters more than anything.** Baseline → small (77 %
  fewer params, same data, same steps): final train 1.02 → 1.50, val
  1.40 → 1.71. Sample collapses to gibberish — model didn't have
  capacity to learn structure. Small is *underfit*, not "smaller and
  worse"; you can see this in the sample lacking the JSDoc indentation
  and `* @see` patterns the bigger models picked up.
- **Doubling steps is real but with sharp diminishing returns.**
  Baseline → long (same architecture, 2× steps): val loss bottomed at
  step 6500 (1.18), then plateaued and bounced around 1.18–1.32 while
  train kept slowly dropping (0.97 → 0.85). **Textbook
  "should have early-stopped" outcome** — model is fitting training
  data harder but no longer generalizing. The long run's sample is
  qualitatively the best — actually starts looking like Python
  (`def kind: string, emit?: number | A | If boolean | Emitter | None = None,`)
  with real function-def shape, mixed with TS-style optional markers
  (`?:`). 5000 steps was a slightly low default; ~6500 would have
  been optimal for this corpus.
- **Corpus diversity is its own axis.** Owner-only → final train 0.88
  is *better than baseline's 1.02*, but that's a **dataset effect, not
  a model-quality effect**: smaller, more self-similar corpus is easier
  to fit. Val is lower for the same reason — the train/val slices come
  from the same author's style. The sample shows the model leaned hard
  into owner code: `private _tags?;`, "the cloud", "the file deplay of
  tags protection" — JSDoc + the owner's domain vocabulary. Compare
  baseline's `pathTs`, `interface _maliftData`, which carry
  microsoft/TypeScript-flavored noise.
- **Corpus contamination disclaimer.** The owner-only 77 MB is
  **not clean owner-written code**. `prep_corpus.py` doesn't yet
  exclude `node_modules`, so the corpus includes every `.d.ts` in the
  owner repos' `node_modules/` directories — i.e., a lot of generic
  npm ambient type definitions. A cleaner ablation would patch
  `prep_corpus.py` to exclude `node_modules/`, `.venv/`, `dist/`,
  `build/` by default. Filed for a follow-up.

#### Verdict

**PASS** for M4 Phase-1-on-`command` done-means: lifecycle exercised
(train, sample, checkpoint, eval), loss curves recorded, samples
saved, results tied to a commit. M3's `--device cuda` clause is
**explicitly deferred** to post-GPU-replacement.
