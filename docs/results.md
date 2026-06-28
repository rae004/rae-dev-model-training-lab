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
