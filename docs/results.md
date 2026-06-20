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
