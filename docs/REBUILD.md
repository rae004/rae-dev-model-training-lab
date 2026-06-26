# Workhorse Rebuild Playbook

The day-of procedure for the GPU + PSU swap captured in
[ADR-021](DECISIONS.md). Top-to-bottom physical install → working
system → first verified CUDA run. Each step assumes the previous one
succeeded; bail and read the relevant sub-doc if a step fails.

> **Audience:** the project owner, with workhorse physically accessible
> (this isn't an SSH-only procedure until step 4) and an Ethernet /
> Wi-Fi connection ready.

> **One-time event.** This doc isn't for routine work — `RUNBOOK.md` is.
> When the rebuild is done and the first CUDA run completes, future
> Phase 1 work follows `RUNBOOK.md §3` onwards.

---

## 0. Before you start

Inventory check on the bench:
- [ ] Corsair RM650e PSU
- [ ] ASUS Dual RTX 5060 Ti 16GB OC
- [ ] Pop!_OS 24.04 install USB (or burn one fresh — current install is
      bricked, see ADR-021 context)
- [ ] Phillips screwdriver, anti-static wristband (or just touch the
      case frame before handling components)

On `command` (which stays online throughout):
```bash
cd ~/projects/rae-dev-model-training-lab
git pull --ff-only main
uv run pytest -q     # sanity: 180+ tests pass; baseline doesn't change today
```

---

## 1. Physical install

**Power down workhorse fully** — unplug, hold power button 5 s to drain
caps. Open the case.

### 1a. Swap the PSU first (before the GPU)

Reasoning: the new PSU's cable harness is different from the EVGA's.
Doing it first means you can route the new cables cleanly without the
GPU in the way.

1. Photograph existing cable connections (mobo 24-pin, CPU EPS, any
   SATA, fans). Just for reference if something looks weird later.
2. Unplug the EVGA 500W from the wall + every internal connection.
3. Unscrew it from the back panel; lift out.
4. Mount the RM650e in the same spot. Same screw pattern.
5. Plug back in: mobo 24-pin, CPU EPS 8-pin, SATA cables, fans.
6. **Leave the PCIe 8-pin cable connected to the PSU only** — the
   other end goes to the new GPU in step 1b.

### 1b. Remove the GTX 1050, install the RTX 5060 Ti

1. Unscrew the 1050's PCIe slot bracket. Release the slot's retention
   clip. Pull straight out.
2. Set the 5060 Ti in the same x16 slot, press firmly until the clip
   clicks.
3. Screw the bracket in.
4. Connect the PCIe 8-pin (the cable hanging from step 1a) to the
   5060 Ti.

### 1c. Smoke test before closing the case

1. Plug workhorse into the wall + a monitor (any HDMI port on the new
   GPU works).
2. Power on. **Watch for:** fans spin up, no clicks/coil whine, BIOS
   POST screen appears.
3. Enter BIOS (usually Del or F2), confirm the new GPU is detected in
   PCI devices.

If BIOS sees the card → close the case, screw it shut. If not → power
down, reseat the GPU, recheck the PCIe power cable.

---

## 2. Fresh Pop!_OS install

Current install is bricked (ADR-021 context). Don't try to recover —
clean slate is faster.

1. Boot from the Pop!_OS USB (BIOS boot menu, usually F11/F12).
2. Standard install: same username (`rae004`), same hostname
   (`rae-dev-workhorse`), encrypted disk, same Wi-Fi or Ethernet
   network. Reboot when prompted.
3. First login: set the disk-encryption password if you set one; log
   into the desktop.

### 2a. Update + base packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl rsync zip unzip build-essential openssh-server
```

### 2b. SSH back in

Get the new IP (it may have changed if your old DHCP lease was
reserved):
```bash
ip -4 -o addr show scope global | awk '{print $4}'
```

On `command`, update `~/.ssh/config` if needed, then verify:
```bash
ssh workhorse hostname    # should print "rae-dev-workhorse"
```

If hostname resolution fails, follow `SETUP.md §0` `/etc/hosts` recipe
— same as the first-time bootstrap.

---

## 3. Drivers + uv + repo

All commands now via SSH from `command`. Follow `SETUP.md §2`
verbatim, but for convenience the critical bits are:

### 3a. NVIDIA driver (Blackwell-ready)

```bash
ssh workhorse
sudo apt install -y system76-driver-nvidia
sudo reboot
```

After reboot:
```bash
ssh workhorse nvidia-smi
# → expect: GPU 0  NVIDIA GeForce RTX 5060 Ti  ...  CUDA Version: 12.8+
```

If `nvidia-smi` reports a driver older than 570, follow `SETUP.md §2`'s
fallback to `nvidia-driver-570+` directly.

### 3b. uv + repo

```bash
ssh workhorse
curl -LsSf https://astral.sh/uv/install.sh | sh
# new shell to pick up PATH:
exec $SHELL
uv --version

mkdir -p ~/projects && cd ~/projects
git clone https://github.com/rae004/rae-dev-model-training-lab.git
cd rae-dev-model-training-lab
```

### 3c. cu128 venv (the workhorse-specific environment)

```bash
# on workhorse, inside the project
uv venv .venv-cu128
source .venv-cu128/bin/activate

uv pip install torch --index-url https://download.pytorch.org/whl/cu128
uv pip install tensorboard pytest ruff
uv pip install -e . --no-deps

python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# → True  NVIDIA GeForce RTX 5060 Ti
```

If `torch.cuda.is_available()` is False, the driver and PyTorch don't
agree on CUDA versions. Recheck `nvidia-smi`'s CUDA Version header vs.
the cu128 wheel line.

---

## 4. Ollama back online + first interactive review

### 4a. Reinstall + LAN override

```bash
ssh workhorse
curl -fsSL https://ollama.com/install.sh | sh

# Follow SETUP.md §2's exact override file content (two lines,
# no '#' prefix — that comment-prefix gotcha is RUNBOOK §5a's note):
sudo SYSTEMD_EDITOR=vi systemctl edit ollama
# In the editor, between the markers:
#   [Service]
#   Environment="OLLAMA_HOST=0.0.0.0"
sudo systemctl restart ollama
```

### 4b. Pull qwen2.5-coder + verify

```bash
ssh workhorse ollama pull qwen2.5-coder
ssh workhorse ollama list

# From command:
curl -s http://workhorse:11434     # → "Ollama is running"
```

### 4c. The 5060 Ti payoff — first interactive review

Pick any small diff and run it through. Should return in **seconds**,
not minutes (the 1050-era latency in RUNBOOK §6c is gone):

```bash
echo 'const x: any = JSON.parse(input);' \
    | uv run python -m codereview review --config configs/review.toml
```

The `timeout = 550` default in `configs/review.toml` is now wildly
oversized. **Don't lower it in this rebuild PR** — measure the actual
post-rebuild latency on a real PR-sized diff first, then a follow-up
PR adjusts the default with the observed number.

---

## 5. Close M3's `--device cuda` clause

The last unmet M3 done-means. Smoke run first to prove the GPU path works:

```bash
ssh workhorse
cd ~/projects/rae-dev-model-training-lab
source .venv-cu128/bin/activate

python -m codereview train --config configs/smoke.toml --device cuda
# → expect "device=cuda" at the top, decreasing loss, "training done" at the end
```

Then the real char-level run for the M3 done-means (matches the M4
results-entry shape):

```bash
python -m codereview train --config configs/char_step1.toml --device cuda
```

Wall time + final loss go into a new `docs/results.md` entry (template
in that file). The CPU baseline numbers from PR #14 are the comparison.

---

## 6. Headline M6 run: baby-GPT on BPE

The big one. `configs/baby_gpt.toml` is the ADR-016 step-2 spec
(6L/6H/d_model=384/block_size=256, BPE vocab 4096). The reference BPE
training is O(N) per merge and will take some time; if it's
prohibitive, see the BPE perf PR (TBD) for the optimized variant.

```bash
# still on workhorse, cu128 venv active
python -m codereview train --config configs/baby_gpt.toml --device cuda
```

Once done, sample from each checkpoint:

```bash
python -m codereview sample --checkpoint runs/baby_gpt/ckpt.pt \
    --prompt "def " --max-new-tokens 300 --temperature 0.8 --top-k 40 \
    --seed 42 --device cuda
```

Add a `docs/results.md` entry.

---

## 7. M8 baseline scoring

The Phase-2-must-beat baseline. With Ollama serving qwen2.5-coder:

```bash
# from command (uses the CPU venv — the review call is HTTP-only)
uv run python -m codereview eval \
    --config configs/review.toml \
    --report docs/baseline-eval.md
```

Commits `docs/baseline-eval.md` to capture the score. This **closes
M8** and **closes Phase 1**.

---

## After Phase 1 closes

The deferred ADR-017 items come back to the table:
- Phase 2 base model choice (e.g., Qwen2.5-Coder-7B / Phi-4)
- Fine-tuning dataset sourcing
- Final severity/category taxonomy + threshold
- Precision-aware eval scoring methodology

Phase 2 starts with a new branch and the first new ADR since this
rebuild closed Phase 1.
