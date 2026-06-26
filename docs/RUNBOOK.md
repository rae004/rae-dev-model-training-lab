# Phase 1 Runbook

The end-to-end procedure for closing out the user-side work behind
M3 (CUDA verification), M4 (the actual training runs and the
`docs/results.md` entry), and M7 (live `git diff | reviewer`).

This is the lived experience the design has been building toward.
Work top-to-bottom — each step assumes the previous one succeeded.

> **Audience:** the project owner on `rae-dev-command`, with SSH to
> `rae-dev-workhorse` and `rae-bot-alpha` per `docs/SETUP.md`.

---

## 0. Prerequisites

All three machines bootstrapped per `docs/SETUP.md` (§4 smoke test
passes on each). On `command`:

```bash
cd ~/projects/rae-dev-model-training-lab
git pull --ff-only main
uv sync --all-groups
uv run pytest -q     # expect: all green
uv run python -m codereview --help    # advertises train / sample / review
```

Pull the latest `main` on `workhorse` too (we'll set up its cu126 env
in §3).

---

## 1. Prepare the corpus  *(M2/M4 prep)*

### 1a. Fill in `data/scripts/sources.toml`

The committed file is an empty scaffold per ADR-018. Add the owner's
own repos plus a small permissively licensed public slice
(MIT/Apache-2.0 only). Example shape:

```toml
extensions = [".py", ".ts", ".tsx"]

[[sources]]
name = "rae-dev-something"           # owner repo via local checkout
type = "path"
path = "~/projects/rae-dev-something"
license = "owner"

[[sources]]
name = "rae-dev-bot"                 # another owner repo via git
type = "git"
url = "https://github.com/rae004/rae-dev-bot.git"
ref = "main"                          # prefer a tag/SHA for determinism
license = "owner"

[[sources]]
name = "popular-mit-lib"             # public slice — MUST be MIT/Apache-2.0
type = "git"
url = "https://github.com/owner/repo.git"
ref = "v1.0.0"
license = "MIT"
```

### 1b. Record provenance

For every source added, add a row to `data/SOURCES.md` with its
license and the date pulled (ADR-018 contract).

### 1c. Build the corpus

```bash
uv run python data/scripts/prep_corpus.py
# → writes data/corpus.txt (git-ignored), prints "wrote N chars"
```

### 1d. Sanity check

```bash
wc -c data/corpus.txt              # how big?
head -c 500 data/corpus.txt        # eyeball it
```

Aim for at least a few MB. The char-level spec config trains for 5000
steps at batch_size=64, block_size=128 → ~40M tokens consumed. Smaller
corpora work but train/val will be very correlated.

### 1e. Commit `data/SOURCES.md` and `sources.toml`

```bash
git add data/SOURCES.md data/scripts/sources.toml
git commit -m "data: add Phase 1 corpus sources"
git push
```

The corpus itself (`data/corpus.txt`) stays git-ignored per CLAUDE.md
rule 2.

---

## 2. Char-level training on `command` (CPU)  *(M3 + M4)*

```bash
cd ~/projects/rae-dev-model-training-lab
uv run python -m codereview train \
    --config configs/char_step1.toml \
    --device cpu
```

What to watch in the log:

- `device=cpu` line up top — confirms no surprise CUDA selection
- `corpus chars=… vocab=… train=… val=…` — sanity check the split
- `step 0  eval train=… val=…` — the **initial** loss
- Loss curve descending in the eval lines
- `step 4999  eval train=… val=…` — the **final** loss
- `training done: param_count=…` — should be ~830k for the spec config
- Wall time at the bottom of the log

Checkpoint lands at `runs/char_step1/ckpt.pt`. TensorBoard logs are in
the same directory; view from anywhere on the LAN:

```bash
uv run tensorboard --logdir runs/char_step1 --bind_all
# → http://command:6006
```

### Sample from it

```bash
uv run python -m codereview sample \
    --checkpoint runs/char_step1/ckpt.pt \
    --prompt "def " \
    --max-new-tokens 200 \
    --temperature 0.8 \
    --top-k 40 \
    --seed 42 \
    --device cpu
```

Save the output verbatim — it goes in `docs/results.md` (§5 below).

---

## 3. Char-level training on `workhorse` (CUDA)  *(M3 done-means)*

This is the last unmet M3 done-means clause:
> *"the identical config runs to completion with `--device cuda`"*

> **Hardware note (2026-06-26, ADR-021):** workhorse is being rebuilt
> with an RTX 5060 Ti 16GB (Blackwell) replacing the GTX 1050. The
> cu128-line venv recipe is in SETUP.md §2 — the original cu126 steps
> below are superseded but kept here verbatim until the rebuild PR
> updates this section with verified post-rebuild commands and the
> first measured CUDA wall time.

### 3a. Set up the workhorse training environment

Per SETUP.md §2, the workhorse uses a **separate** PyTorch from the
cu128 wheel line (the main `uv.lock` is CPU-only). The cleanest pattern
is a parallel venv that doesn't conflict with the default `.venv/`:

```bash
ssh workhorse
cd ~/projects/rae-dev-model-training-lab
git pull --ff-only main

# Separate venv for the cuda training environment
uv venv .venv-cu128
source .venv-cu128/bin/activate

# cu128-line torch first
uv pip install torch --index-url https://download.pytorch.org/whl/cu128

# Non-torch deps, then the package itself without re-resolving torch
uv pip install tensorboard pytest ruff
uv pip install -e . --no-deps

# Verify CUDA actually works
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# → True  NVIDIA GeForce RTX 5060 Ti
```

If `cuda.is_available()` is False, see SETUP.md §2 for driver setup.

> **Caveat:** this workhorse venv recipe isn't tested by CI (CI is
> x86_64 + CPU). If the install dance changes shape (uv tightens
> behavior, torch wheels move), prefer SETUP.md §2 over this snippet
> and update both. A future ADR may formalize a workhorse-specific
> pyproject.

### 3b. Run training

```bash
# Still on workhorse, in the cu128 venv
python -m codereview train \
    --config configs/char_step1.toml \
    --device cuda
```

Same log shape as §2. The interesting numbers vs CPU:

- Wall time (the headline CPU-vs-GTX-1050 comparison from ADR-016)
- Final eval loss (should be within numerical noise of the CPU run,
  since this is fp32 — *not* identical, but close)

### 3c. Pull the checkpoint and TensorBoard logs back to `command`

```bash
# From command
rsync -av workhorse:~/projects/rae-dev-model-training-lab/runs/char_step1/ \
    ./runs/char_step1-workhorse/
```

Per ADR-015: explicit rsync, deliberate, no shared filesystem.

### 3d. Sample from the workhorse checkpoint

```bash
# Back on command, in the main venv
uv run python -m codereview sample \
    --checkpoint runs/char_step1-workhorse/ckpt.pt \
    --prompt "def " --max-new-tokens 200 --temperature 0.8 --top-k 40 \
    --seed 42 --device cpu
```

Save this output verbatim too.

---

## 4. Record the results  *(M4 done-means)*

Edit `docs/results.md`. Copy the template into a new entry under
**Runs**. Fill in:

- Commit SHA of `main` at the time you ran (use `git rev-parse --short HEAD`)
- Config path: `configs/char_step1.toml`
- Corpus chars and vocab size (from the training log)
- Wall time on each device
- Initial / final train + val losses from the eval log lines
- Both generated samples in fenced blocks
- Notes — e.g., did the CPU and CUDA runs converge to similar losses?
  Was the workhorse meaningfully faster? Anything surprising?

Commit:

```bash
git checkout -b results-m4-first-run
git add docs/results.md
git commit -m "results: first M4 char-level run (CPU + CUDA)"
git push -u origin results-m4-first-run
gh pr create --base main --title "results: M4 char-level run" \
    --body "First entry in docs/results.md per M4 done-means."
```

This commit **closes M4** and closes the CUDA verification owed by M3.

---

## 5. Set up Ollama on `workhorse`  *(M7 prep)*

### 5a. Install + LAN override

Per SETUP.md §2. The override file content is fiddly — paste **exactly**
these two lines, no comment prefix:

```
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
```

If you've seen `OLLAMA_NUM_THREADS` suggested elsewhere — including by me
in chat earlier — ignore it; it isn't a real Ollama env var. Threading is
set per-request via `options.num_thread`, which `configs/review.toml`
exposes as the `num_thread` field. See §6.

### 5b. Pull the code model

```bash
ssh workhorse
ollama pull qwen2.5-coder        # the default in configs/review.toml
ollama list                       # confirm it's there
exit
```

### 5c. Verify from `command`

```bash
ssh workhorse systemctl show ollama --property=Environment
# → expect: ... OLLAMA_HOST=0.0.0.0 ...

curl -s http://workhorse:11434
# → "Ollama is running"
```

If the curl fails but ssh works, the LAN override didn't stick — re-do
§5a and re-verify with `systemctl show`. A common gotcha: leading `#`
prefixes in the override file are inert (systemd treats them as comments),
so the override silently does nothing.

---

## 6. Live `git diff | reviewer`  *(M7 done-means)*

### 6a. Smoke check (small input)

Confirm the pipeline first with something tiny — it returns in seconds
and proves the end-to-end stack works without depending on whether the
1050 finishes a real diff in the configured timeout:

```bash
echo 'const truth = true; console.log(truth);' \
    | uv run python -m codereview review --config configs/review.toml
```

### 6b. A real diff

```bash
git -C ~/projects/some-repo diff HEAD~1 \
    | uv run python -m codereview review --config configs/review.toml
```

What to watch for:

- Text rendering on stdout: `[severity/category] file:line` blocks,
  followed by `Summary:` and `Verdict: PASS|FAIL`
- Exit code: `0` if clean, `1` if blocking findings, `2` on error
- Reasonable findings — not nitpicks the linters would catch

JSON sanity (validates against the §4 schema):

```bash
git -C ~/projects/some-repo diff HEAD~1 \
    | uv run python -m codereview review --config configs/review.toml --json \
    | jq .verdict
# → {"passed": ..., "threshold": "error"}
```

### 6c. Realistic latency on the GTX 1050 (and how to tune)

> **Historical (pre-2026-06-26).** ADR-021 replaces the 1050 with an
> RTX 5060 Ti 16GB. With 16 GB VRAM, `qwen2.5-coder` runs entirely on
> the GPU and a PR-sized review drops from minutes to seconds — the
> `timeout = 550` default in `configs/review.toml` will be reduced and
> the `num_thread` workaround becomes unnecessary. Concrete
> post-rebuild numbers will replace this section in the rebuild PR;
> the 1050-era notes below stay as the snapshot of what was true on
> the older hardware.

The 1050 has 2 GB VRAM; `qwen2.5-coder` is ~4.7 GB, so most of the model
runs on the i7-8700 CPU. Concrete numbers observed:

- Small prompts (a few lines of code): a few seconds
- ~40 KB diff (a full PR like #7): several minutes; can exceed the
  default `timeout = 550.0` in `configs/review.toml`
- `num_thread = 8` is ~19 % faster than auto-pick on a short prompt
  (sub-linear past 8 due to hyperthread / cache contention)

If a real diff times out:

1. **Warm the model first** — the first request after Ollama starts pays
   a ~30 s model-load cost; subsequent calls within ~5 min skip it:
   ```bash
   ssh workhorse 'curl -s -X POST http://localhost:11434/api/generate \
       -d "{\"model\":\"qwen2.5-coder\",\"prompt\":\"hi\",\"stream\":false}" \
       -o /dev/null'
   ```
2. **Bump the timeout** in `configs/review.toml` (it ships at `550.0`;
   try `900.0` or higher for full PR diffs).
3. **Uncomment `num_thread = 8`** in `configs/review.toml`. While the
   request is in flight, `htop` on workhorse should show several cores
   active rather than one hot core.

If the model returns text that isn't well-formed JSON, the CLI exits 2
with the parser's `ValueError` on stderr — that's a prompt-engineering
signal, not a bug. Smaller code models may need a tighter system prompt.

This **closes M7**.

---

## What this gets you

After step 6, three previously-pending done-means clauses are met:

- **M3:** identical config runs to completion on both `--device cpu`
  and `--device cuda`
- **M4:** generated samples saved + outcomes in `docs/results.md` tied
  to a commit hash
- **M7:** `git diff | reviewer` returns a sensible review end-to-end

That clears the runway for M5 (BPE, with a real corpus to compare
against), M6 (the baby-GPT main learning run), and M8 (eval harness
scored against the off-the-shelf Ollama model — the baseline any
Phase 2 candidate must beat).
