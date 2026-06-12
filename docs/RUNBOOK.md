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

### 3a. Set up the workhorse training environment

Per ADR-014 / SETUP.md §2, the workhorse uses a **separate** PyTorch
pinned to the cu126 line (the main `uv.lock` is CPU-only). The
cleanest pattern is a parallel venv that doesn't conflict with the
default `.venv/`:

```bash
ssh workhorse
cd ~/projects/rae-dev-model-training-lab
git pull --ff-only main

# Separate venv for the cuda training environment
uv venv .venv-cu126
source .venv-cu126/bin/activate

# cu126-line torch first
uv pip install "torch==2.7.*" --index-url https://download.pytorch.org/whl/cu126

# Non-torch deps, then the package itself without re-resolving torch
uv pip install tensorboard pytest ruff
uv pip install -e . --no-deps

# Verify CUDA actually works
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# → True  NVIDIA GeForce GTX 1050
```

If `cuda.is_available()` is False, see SETUP.md §2 for driver setup.

> **Caveat:** this workhorse venv recipe isn't tested by CI (CI is
> x86_64 + CPU). If the install dance changes shape (uv tightens
> behavior, torch wheels move), prefer SETUP.md §2 over this snippet
> and update both. A future ADR may formalize a workhorse-specific
> pyproject.

### 3b. Run training

```bash
# Still on workhorse, in the cu126 venv
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

Ollama itself is installed per SETUP.md §2 and listens on
`0.0.0.0:11434`. Pull a code model:

```bash
ssh workhorse
ollama pull qwen2.5-coder        # the default in configs/review.toml
# or: ollama pull qwen2.5-coder:7b for a specific size

# Verify
ollama list
curl -s http://workhorse:11434/api/tags     # from command
```

If the curl fails, check that the `OLLAMA_HOST=0.0.0.0` override in the
systemd unit is in place (SETUP.md §2).

---

## 6. Live `git diff | reviewer`  *(M7 done-means)*

```bash
# On command, in any git repo with a recent diff
git -C ~/projects/some-repo diff HEAD~1 \
    | uv run python -m codereview review --config configs/review.toml
```

What to watch for:

- Text rendering on stdout: `[severity/category] file:line` blocks,
  followed by `Summary:` and `Verdict: PASS|FAIL`
- Exit code: `0` if clean, `1` if blocking findings, `2` on error
- Reasonable findings — not nitpicks the linters would catch

Then verify the JSON path validates:

```bash
git -C ~/projects/some-repo diff HEAD~1 \
    | uv run python -m codereview review --config configs/review.toml --json \
    | jq .verdict
# → {"passed": ..., "threshold": "error"}
```

If model output isn't well-formed JSON, the CLI exits 2 with the
parser's `ValueError` on stderr — that's a prompt-engineering signal,
not a bug. The system prompt may need tightening for a smaller model.

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
