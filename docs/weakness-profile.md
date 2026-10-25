# Weakness profile — Phase 2 fine-tune targets

M9's output: the specific weaknesses the ADR-023 fine-tune dataset must
exercise, derived from the dual-metric baseline run (ADR-024 impl,
PR #34; results entry `docs/results.md` 2026-07-05 "Dual-metric
baseline rerun on qwen2.5-coder (post-ADR-024 impl)").

Scope: no code; a sighting shot for the dataset-build pipeline (M10)
to execute against. All claims trace back to the 11-case eval set
(`eval/eval_set.toml`) and the paired reports (`docs/baseline-eval.md`
single-metric, `docs/baseline-eval-dual.md` dual-metric).

## Baseline numbers in one line

Macro F1 strict **0.364** / severity-only **0.545**; verdict accuracy
**0.727** (8 of 11). Model: `qwen2.5-coder:latest` via Ollama on
workhorse (`http://workhorse:11434`), served under the config at
`configs/review.toml`.

The strict-vs-severity-only delta (**+0.181**) is the first teaching
signal: roughly one-third of what *looks* like reviewer skill under
strict scoring is agreement with our taxonomy labels — not detection.
The other two-thirds is genuine issue-finding capability.

## (i) Categories with recall = 0, broken down by failure mode

Six categories appear in the eval set; `security` is the only one the
baseline hits (recall 1.000). Every other category has recall 0.000
under strict scoring. The failure *shape* differs by category and is
what tells us what the dataset must teach:

| category | eval cases | failure shape | miscat vs. silence |
| --- | --- | --- | --- |
| `bug` | `off-by-one-loop`, `retry-on-auth-failure` | Mixed: one wrong-severity, one zero findings. | **Both.** `off-by-one` is miscategorization + severity underestimate; `retry-on-auth-failure` is complete **silence**. |
| `design` | `god-function` | Model emitted 2 findings; neither matched the reference severity+category. Overfinds at the wrong level. | **Miscategorization + severity underestimate.** |
| `performance` | `n-plus-one` | Model emitted 1 finding, wrong severity+category. | **Miscategorization + severity underestimate.** The reference finding is `(warning, performance)`; model surfaced *something* but not that pair. |
| `readability` | `cryptic-names` | Model emitted 1 finding, right severity (`info`), wrong category. Severity-only credit; strict zero. | **Clean miscategorization.** The signal was found; the label was wrong. |
| `test-gap` | `new-function-no-tests` | Same shape — right severity (`warning`), wrong category. Severity-only credit; strict zero. | **Clean miscategorization.** |
| `security` | `sql-injection`, `hardcoded-secret` | Both matched exactly on `(error, security)`. | — (recall 1.000). |

Reading: the model has roughly correct severity instincts on three of
five non-security categories (`readability`, `test-gap`, plus
`cryptic-names` and `new-function-no-tests` severity hits). On
`bug`/`design`/`performance` it either goes silent or picks a wrong
severity, which is the harder problem — detection, not labelling.

## (ii) The three false-negative verdicts (verdict = ✗)

Verdict is derived from max finding severity; the three verdict
failures are all cases where the model found zero `error`-severity
findings on diffs that *should* have one. Pattern across all three:
**under-estimates severity on real bugs**, which collapses the
verdict to `passed=true` on a diff that should block.

### 1. `off-by-one-loop` (ref: `error`, `bug`)

**Diff shape:** `for i in range(len(xs) - 1)` loop iterates one short
of the collection length.

**Miss shape:** model surfaced one finding but at `warning` or `info`
severity, not `error`. The off-by-one semantics landed somewhere; the
"this breaks correctness, block the merge" judgment did not.

**What the fine-tune must learn:** off-by-one in `range(len(x)-1)` is
`(error, bug)`, not `(warning, readability)`. The pattern is cheap to
synthesize at scale — any numeric-loop boundary variant qualifies.

### 2. `retry-on-auth-failure` (ref: `error`, `bug`)

**Diff shape:** a retry loop that treats `!res.ok` uniformly, including
401/403/404, instead of fail-fast on permanent-failure HTTP status.

**Miss shape:** model returned **zero findings**. True silence, not
label disagreement. The anti-pattern (retry masking permanent failure)
is semantically subtle; the baseline is blind to it.

**What the fine-tune must learn:** retry loops that don't discriminate
by status code are bugs, not style. More broadly: control-flow
anti-patterns that silently swallow errors.

### 3. `n-plus-one` (ref: `error`, `performance`)

**Diff shape:** per-element DB query inside a `for uid in user_ids:`
loop; obvious batching opportunity.

**Miss shape:** model surfaced one finding at wrong severity+category.
Not silent, but mis-tagged. The baseline knows *something* is up but
doesn't name it correctly or weight it as blocking.

**What the fine-tune must learn:** n-plus-one in `for X: db.execute`
is `(error, performance)` (or `(warning, performance)` per the eval
set's reference — reconfirm during dataset build). Severity convention
TBD, but the category must be `performance`.

**Common thread across the three false negatives:** all expect
`severity = error`; the baseline produced `< error`. The severity
discriminator is weak. The dataset should include explicit
*severity-calibrated* pairs — real-bug diffs tagged `error`, true
style-only diffs tagged `info`, with as little in between as possible
so the model has a crisp decision boundary.

## (iii) Prioritized target list for the ADR-023 pipeline

ADR-023's dataset is 70 / 15 / 15 (synthetic / weakness-targeted /
authentic voice). This section is scoped to the **15%
weakness-targeted slice** (≈ 75–150 pairs at the 500–1000 target
range).

Internal split within the weakness-targeted slice, from the 2026-07-05
results entry: **4 of 6 non-security misses need detection work; 2 of
6 are label-fixable.** That becomes a design ratio:

- **~⅔ detection-focused pairs** (≈ 50–100 pairs): hard patterns the
  baseline misses outright or mis-severities. Highest priority.
- **~⅓ categorization-focused pairs** (≈ 25–50 pairs): right-signal
  pairs demonstrating correct `(severity, category)` labelling for
  the three categories that already show severity-only credit
  (`readability`, `test-gap`, severity-correct subset of
  `performance`/`design`).

### A — Detection-focused patterns (highest priority)

Each pattern below is a bucket; the pipeline should produce multiple
variants per bucket to keep the model from overfitting on surface
form.

1. **Off-by-one in loop boundaries** → `(error, bug)`
   - `range(len(xs) - 1)`, `< n - 1`, `<= n` where exclusive expected,
     `[1:]`/`[:-1]` with off-by-one intent.
2. **Retry/catch anti-patterns that swallow permanent failures** → `(error, bug)`
   - Retry loop with no status-code discrimination (401/403/404).
   - `except Exception: pass` on operations that *should* propagate.
   - Retry on `KeyboardInterrupt`-equivalents.
3. **N-plus-one queries** → `(error, performance)` or `(warning, performance)` — pin at build time
   - Loop with inner `db.execute` / ORM `get`.
   - Multiple sequential awaits on independent calls (should be
     `asyncio.gather`).
4. **Blocking call in async path** → `(warning, performance)`
   - `time.sleep` inside `async def`.
   - Sync `requests.get` inside `async def`.
5. **Mutable default argument** → `(error, bug)`
   - `def f(xs=[])` / `def f(d={})`.
6. **Unreachable or dead branches** → `(warning, bug)`
   - `if x: ... else: raise ...` where x is a tautology.
   - `return` followed by code.
7. **Early return shadowing** → `(warning, bug)`
   - Early `return None` on a path that must raise.
   - Returning `False` where the signature says `-> int`.

### B — Severity-calibration pairs

Scattered across A/C, not a bucket of their own. Each pair should
make the severity choice *decidable from the diff*:

- Real correctness break → `error`.
- Avoidable performance pitfall that still works → `warning`.
- Style / naming / commentary → `info`.

Avoid middle-ground pairs (debatable `warning`-vs-`error` calls)
until the easy signal is learned.

### C — Categorization-focused patterns (right signal, wrong label fixes)

These are the "severity-only match, strict miss" shape: model already
flags *something*; the dataset teaches it where to file.

1. **`test-gap` labelling** → `(warning, test-gap)`
   - New public function / class with no test file in the same diff.
   - New error path (`raise`) without a corresponding test.
2. **`readability` labelling** → `(info, readability)`
   - Single-letter names in non-trivial scopes.
   - Deep nesting (> 3 levels).
3. **`design` labelling** → `(warning, design)`
   - Function > ~50 lines mixing parse/validate/IO/notify.
   - Class carrying unrelated responsibilities.
4. **`typing` labelling** → `(warning, typing)` or `(info, typing)`
   - Not currently in the eval set, so cold start — include a few
     pairs to establish the slot before Phase 2 ships. Candidates:
     wide `Any` escape hatches, `# type: ignore` without justification,
     function body contradicting its annotations.

### D — Protect existing strengths (regression guards)

The baseline already does these; the dataset must not teach them
away. Include a modest number of pairs so the fine-tune doesn't
regress.

- **Security exemplars**: SQL injection, hardcoded secret, path
  traversal, SSRF, XXE, insecure crypto, auth bypass. Already-strong
  category; keep it strong.
- **LGTM / no-op recognition**: rename-only diffs, pure typing
  improvements, test-added-with-feature diffs — model must return
  **empty findings**. The baseline gets 3 of 3 LGTM cases right
  (one with a false-positive info finding on `lgtm-rename-only`
  that didn't flip the verdict). Reinforce with varied no-op shapes:
  comment-only changes, whitespace-only changes, pure Prettier/Black
  reformats, dependency-version bumps with no behavior change.
  This also directly addresses the model-fabrication failure
  observed when driving `rae-local-agent` against
  `rae004/ai-security-digest#137` — the model produced a no-op
  reformat PR instead of declining; teaching "nothing to do" is
  explicitly a Phase 2 capability target.

## Non-goals for the dataset

- **Not** expanding diff sources beyond `data/SOURCES.md` (per
  ADR-018 / ADR-023).
- **Not** rewriting the eval set to match the dataset. The eval set
  stays frozen; dataset is judged by whether M13's eval beats the
  baseline on the *existing* 11 cases, not by in-sample fit.
- **Not** targeting `typing` beyond a cold-start handful — it's not
  in the eval harness, so improvement is unmeasurable in Phase 2.

## Pointer to M10

The M10 PR implements this profile: the generation pipeline in
`data/scripts/` should emit a composition report with per-pattern
counts so A/B/C/D ratios are inspectable before training. If the
teacher model struggles to produce a particular bucket at target
proportion, that's an input into whether to extend ADR-023 or
accept the shortfall and note it in the M13 result.
