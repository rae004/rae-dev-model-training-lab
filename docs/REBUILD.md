# Workhorse Rebuild Playbook

The day-of procedure for the GPU + PSU swap captured in
[ADR-021](DECISIONS.md). Top-to-bottom: hardware install → fresh OS →
fully-ready workhorse. Each step has a verification; don't proceed
past a failed verification — fix it or report it back.

> **Audience:** the project owner. Steps that run on the workhorse
> machine itself are marked **[wh]**; steps that run on `command`
> are marked **[cmd]**.

> **One-time event.** This doc covers the rebuild only. Routine work
> (training, sampling, review, eval) lives in `RUNBOOK.md`.

> **Username note.** The fresh Pop!_OS install on workhorse uses
> `wh` as the user account, while every other doc in the project
> (SETUP.md, RUNBOOK.md, etc.) assumes `rae004`. This playbook uses
> `wh` because that's what's actually on the box. Whether to update
> the other docs or create a `rae004` account is a separate decision
> tracked outside this playbook.

---

## 1. Physical install

> Skip §1 + §2 if the hardware is already in and Pop!_OS is already
> installed. Pick up at §3.

Power off workhorse fully — unplug, hold power button 5 s to drain
caps. Open the case.

### 1a. Swap the PSU first

The new PSU's cable harness is different from the EVGA's. Routing it
first means clean cables before the GPU is in the way.

1. Photograph existing cable connections (mobo 24-pin, CPU EPS, SATA,
   fans) for reference.
2. Unplug the EVGA 500W from the wall and every internal connection.
3. Unscrew it from the back panel; lift out.
4. Mount the RM650e in the same spot. Same screw pattern.
5. Plug back in: mobo 24-pin, CPU EPS 8-pin, SATA, fans.
6. Leave the PCIe 8-pin connected to the PSU only — other end goes
   to the GPU in §1b.

### 1b. Swap the GPU

1. Unscrew the 1050's slot bracket. Release the slot's retention clip.
   Pull straight out.
2. Set the 5060 Ti in the same x16 slot, press firmly until the clip
   clicks.
3. Screw the bracket in.
4. Connect the PCIe 8-pin to the 5060 Ti.

### 1c. Smoke test before closing the case

1. Plug workhorse into the wall and a monitor (any HDMI on the new GPU).
2. Power on. Watch for: fans spin, no clicks/coil whine, BIOS POST.
3. Enter BIOS (Del/F2), confirm GPU detected in PCI devices.

If BIOS sees the card → close case, screw shut. If not → power down,
reseat the GPU, recheck the PCIe power cable.

### 1d. BIOS settings — required for 16 GB+ cards on older boards

**Don't skip this step.** Modern GPUs need the BIOS to map their full
VRAM into the CPU address space, and older boards (i7-8700 era and
earlier) often ship with this turned *off*. If you skip §1d, the Linux
driver loads but `nvidia-smi` fails with
`NVRM: BAR1 is 0M @ 0x0` — the card is invisible to userspace until
BIOS is fixed.

While still in BIOS (don't reboot back to OS yet), find and set:

1. **Above 4G Decoding** → **Enabled**
   - Usually under `Advanced` → `PCI Configuration` or
     `System Agent Configuration`. Sometimes named "Above 4G MMIO"
     or "Memory Mapped I/O above 4GB".
2. **CSM (Compatibility Support Module)** → **Disabled**
   - Usually under `Boot`. CSM forces legacy boot mode that can't
     allocate large BARs. Linux installers are fine with CSM off.
3. **Re-Size BAR Support / Resizable BAR** → **Enabled** (if present)
   - May not exist on every i7-8700 era board; enable it if you see
     it, skip if you don't.

Save (usually `F10`), reboot, then close the case.

If you've already booted the OS and `nvidia-smi` fails with `BAR1 is
0M`, this is the fix — reboot into BIOS, set the three above, save.

---

## 2. Pop!_OS install

1. Boot from the Pop!_OS 24.04 USB (BIOS boot menu, usually F11/F12).
2. Standard install: pick a username (the rest of this doc uses `wh`,
   substitute whatever you set), set hostname `rae-dev-workhorse`,
   encrypted disk if you want one, connect Wi-Fi or Ethernet, set a
   user password (you'll need it once in §3 for `ssh-copy-id`).
3. Reboot when prompted; log in to the desktop.

---

## 3. SSH bootstrap

### 3a. **[wh]** Base packages + SSH server

Open a terminal on the workhorse desktop:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y git curl rsync zip unzip build-essential openssh-server
```

Confirm `sshd` is running:

```bash
sudo systemctl enable --now ssh
systemctl is-active ssh
# → active
```

Get workhorse's IP:

```bash
ip -4 -o addr show scope global | awk '{print $4}'
# → 192.168.68.XX/22  (note the IP, call it <WH_IP>)
```

### 3b. **[cmd]** Update `/etc/hosts`

If your `/etc/hosts` already had a `workhorse` entry from before the
brick, the IP probably changed:

```bash
sudo nano /etc/hosts
# Change the workhorse line to: <WH_IP>   workhorse
getent hosts workhorse
# → <WH_IP>   workhorse
```

### 3c. **[cmd]** Install the public key on workhorse

The fresh install has no `authorized_keys`. **Use the IP directly here,
not `workhorse`**, in case your `~/.ssh/config` has a stale `HostName`
override (e.g. `rae-dev-workhorse.local` from the pre-rebuild install,
which won't resolve on the new install):

```bash
ssh-copy-id wh@<WH_IP>        # the IP from step 3a, e.g. wh@192.168.68.65
# → password prompt — enter the wh user's password
```

Verify it works without a password:

```bash
ssh wh@<WH_IP> hostname
# → rae-dev-workhorse
```

If `ssh-copy-id` fails with "Permission denied (publickey)" *before*
any password prompt, Pop!_OS shipped sshd with password auth off:

```bash
# [wh] enable password auth temporarily:
sudo sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
sudo systemctl restart ssh
# Then retry ssh-copy-id from command.
```

### 3d. **[cmd]** Fix `~/.ssh/config` so the short name works

If you have a `Host workhorse` block in `~/.ssh/config` from before
the rebuild, it probably overrides the hostname to something that no
longer resolves (e.g. `rae-dev-workhorse.local`). Update it so SSH
honors `/etc/hosts`:

```bash
nano ~/.ssh/config
```

Make the `workhorse` block look like:

```
Host workhorse
    HostName workhorse
    User wh
```

(Or remove the `HostName` line entirely — same effect.)

Verify:

```bash
ssh workhorse hostname
# → rae-dev-workhorse
```

From this point on every `ssh workhorse ...` in the playbook works.

### 3e. **[cmd]** Passwordless sudo on workhorse (one-time)

`ssh workhorse sudo ...` requires either a TTY (`ssh -t`) or an
askpass helper, and prompts for a password every time. Saving you 20
password prompts during the rebuild — set up passwordless sudo for
`wh` once:

```bash
ssh -t workhorse 'sudo bash -c "echo \"wh ALL=(ALL) NOPASSWD: ALL\" > /etc/sudoers.d/wh-nopasswd && chmod 440 /etc/sudoers.d/wh-nopasswd"'
# → password prompt (last one)
```

Verify:

```bash
ssh workhorse sudo whoami
# → root      (no password prompt)
```

If you'd rather not enable passwordless sudo, every command in §4–7
that uses `sudo` needs `-t`:

```bash
ssh -t workhorse sudo apt install -y system76-driver-nvidia
```

### 3f. **[cmd]** Disable auto-suspend on workhorse

Pop!_OS desktop session auto-suspends on idle. Since workhorse runs
headless (no keyboard/mouse on the machine itself), the desktop
treats every minute as "idle" and the box puts itself to sleep —
SSH dies, network dies, you have to physically poke it to wake.

Two layers of fix needed; do both.

**1. Mask the systemd sleep targets** so even if something tries to
suspend, the operation fails:

```bash
ssh workhorse 'sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target'
ssh workhorse 'systemctl status sleep.target | head -3'
# → Loaded: masked
```

**2. Tell `systemd-logind` not to even try.** Without this, logind
fires the "The system will suspend now!" broadcast every idle period
(the mask blocks the actual suspend, but the *attempt* is annoying):

```bash
ssh workhorse 'sudo mkdir -p /etc/systemd/logind.conf.d && printf "[Login]\nIdleAction=ignore\n" | sudo tee /etc/systemd/logind.conf.d/no-suspend.conf'
ssh workhorse 'sudo systemctl restart systemd-logind'
ssh workhorse 'cat /etc/systemd/logind.conf.d/no-suspend.conf'
# → [Login]
# → IdleAction=ignore
```

Don't use a heredoc for the conf file content — multi-line shell
paste can mangle indentation and break the `EOF` terminator.
`printf` is paste-safe.

---

## 4. NVIDIA driver

Pop!_OS standard doesn't ship NVIDIA drivers. From here on, all
commands run from `command` via SSH.

```bash
ssh workhorse sudo apt install -y system76-driver-nvidia
ssh workhorse sudo reboot
```

Wait ~60 s for the reboot, then verify the driver sees the GPU:

```bash
ssh workhorse nvidia-smi
```

Expected output shape:

```
+-----------------------------------------------------------------------+
| NVIDIA-SMI 570.xx     Driver Version: 570.xx     CUDA Version: 12.8+  |
|-----------------------------------------------------------------------|
| GPU  Name                                                              |
|   0  NVIDIA GeForce RTX 5060 Ti                                        |
+-----------------------------------------------------------------------+
```

**Stop here and paste the actual `nvidia-smi` output if:**
- the card name is wrong, or
- CUDA Version is less than 12.8, or
- the command isn't found.

The CUDA Version determines which PyTorch wheel index to use in §6.

**If `nvidia-smi` reports** `NVIDIA-SMI has failed because it couldn't
communicate with the NVIDIA driver` and `dmesg` shows `NVRM: BAR1 is
0M @ 0x0` → BIOS isn't mapping VRAM. Reboot into BIOS and follow
§1d (Above 4G Decoding, CSM off, Resizable BAR on). This is by far
the most common reason `nvidia-smi` fails on older boards with newer
GPUs.

---

## 5. uv install + repo clone

```bash
ssh workhorse 'curl -LsSf https://astral.sh/uv/install.sh | sh'
ssh workhorse 'source ~/.local/bin/env && uv --version'
# → uv 0.X.X
```

```bash
ssh workhorse 'mkdir -p ~/projects && cd ~/projects && \
    git clone https://github.com/rae004/rae-dev-model-training-lab.git'
ssh workhorse 'ls ~/projects/rae-dev-model-training-lab'
# → CLAUDE.md  README.md  configs  data  docs  ...
```

---

## 6. cu128 venv + PyTorch

SSH into workhorse interactively (cleaner than chaining):

```bash
ssh workhorse
# now [wh]
cd ~/projects/rae-dev-model-training-lab
source ~/.local/bin/env       # if uv isn't already on PATH

uv venv .venv-cu128
source .venv-cu128/bin/activate

uv pip install torch --index-url https://download.pytorch.org/whl/cu128
uv pip install tensorboard pytest ruff
uv pip install -e . --no-deps
```

Verify CUDA actually works:

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# → True  NVIDIA GeForce RTX 5060 Ti
```

**Stop and report if it prints `False` or errors** — driver/CUDA/
PyTorch versions don't agree and the wheel index needs adjustment.

---

## 7. Ollama

Still SSH'd into workhorse:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Make Ollama listen on the LAN (not just localhost):

```bash
sudo SYSTEMD_EDITOR=vi systemctl edit ollama
```

In the editor, between the `### Edits below this comment will be discarded`
markers, put **exactly these two lines** (no `#` prefix):

```
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
```

Save, exit, then:

```bash
sudo systemctl restart ollama
systemctl show ollama --property=Environment | grep OLLAMA_HOST
# → Environment=... OLLAMA_HOST=0.0.0.0 ...
```

Pull the code model:

```bash
ollama pull qwen2.5-coder
ollama list
# → qwen2.5-coder ... 4.7 GB ...
exit       # back to command
```

---

## 8. Verify everything from command

```bash
ssh workhorse hostname                       # → rae-dev-workhorse
ssh workhorse nvidia-smi | head -8           # → driver + card visible
curl -s http://workhorse:11434               # → "Ollama is running"
ssh workhorse ollama list                    # → qwen2.5-coder present
```

When all four return what's expected, workhorse is ready.

---

## 9. Close M3's `--device cuda` clause

The last unmet M3 done-means.

### 9a. Smoke first (uses committed sample data, no corpus needed)

```bash
ssh workhorse 'cd ~/projects/rae-dev-model-training-lab && \
    source .venv-cu128/bin/activate && \
    python -m codereview train --config configs/smoke.toml --device cuda'
# → expect "device=cuda", decreasing loss, "training done"
```

The smoke uses `data/sample/sample.py` + `data/sample/sample.ts` which
*are* committed, so this works on a brand-new workhorse with nothing
else copied over. Finishes in seconds.

### 9b. Copy the corpus from command (ADR-015)

`data/corpus.txt` is git-ignored (ADR-018: corpus is regenerable, not
committed). The corpus only exists on `command` where you built it
via `prep_corpus.py`. For the real char-level run on workhorse, rsync
it across per ADR-015's artifact-handoff pattern:

```bash
# [cmd]
rsync -av --progress data/corpus.txt workhorse:~/projects/rae-dev-model-training-lab/data/
# ~5 sec on LAN; 54 MB
```

Alternative: regenerate on workhorse by running `prep_corpus.py`
there (re-clones the public sources, takes ~30 sec). rsync is the
documented path.

### 9c. The real char-level run

```bash
ssh workhorse 'cd ~/projects/rae-dev-model-training-lab && \
    source .venv-cu128/bin/activate && \
    python -m codereview train --config configs/char_step1.toml --device cuda'
```

PR #14's CPU baseline on this same config was ~11 min on command
(24-thread Ryzen 9 9900X). On the 5060 Ti, expect a small fraction of
that. The wall time + final loss go into a new `docs/results.md`
entry comparing CPU vs CUDA.

---

## 10. M6: baby-GPT on BPE

Needs `data/corpus.txt` on workhorse — already in place if you did §9b,
otherwise rsync it now.

```bash
ssh workhorse 'cd ~/projects/rae-dev-model-training-lab && \
    source .venv-cu128/bin/activate && \
    python -m codereview train --config configs/baby_gpt.toml --device cuda'
```

Then sample:

```bash
ssh workhorse 'cd ~/projects/rae-dev-model-training-lab && \
    source .venv-cu128/bin/activate && \
    python -m codereview sample --checkpoint runs/baby_gpt/ckpt.pt \
        --prompt "def " --max-new-tokens 300 --temperature 0.8 --top-k 40 \
        --seed 42 --device cuda'
```

Add a `docs/results.md` entry.

---

## 11. M8 baseline scoring

From `command` (uses the CPU venv — the review call is HTTP-only):

```bash
cd ~/projects/rae-dev-model-training-lab
uv run python -m codereview eval \
    --config configs/review.toml \
    --report docs/baseline-eval.md
```

Commit `docs/baseline-eval.md`. This closes M8 and closes Phase 1.

---

## After Phase 1 closes

Deferred ADR-017 items come back to the table:
- Phase 2 base model choice
- Fine-tuning dataset sourcing
- Final severity/category taxonomy + threshold
- Precision-aware eval scoring methodology

Phase 2 starts with a new branch and the first new ADR since this
rebuild closed Phase 1.
