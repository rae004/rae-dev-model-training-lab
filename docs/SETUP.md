# Machine Bootstrap

System-level setup for the three machines, per their roles
(see [`ARCHITECTURE.md`](ARCHITECTURE.md)). This covers everything *up to*
project dependencies — those are never installed by hand; once the repo has a
`pyproject.toml` and `uv.lock`, a single `uv sync` materializes them. If a step
here disagrees with reality, reality wins: update this doc.

All machines run Pop!_OS 24.04. Steps are safe to re-run.

---

## 0. Every machine

**Base packages**

```bash
sudo apt update
sudo apt install -y git curl rsync zip unzip build-essential
```

**`uv`** (Python environment + lockfile manager)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# restart the shell, then verify:
uv --version
```

**Hostnames** — reserve a fixed IP for each machine in the router's DHCP
settings, then on *every* machine add all three to `/etc/hosts`
(substitute the reserved IPs):

```
192.168.1.X   command      # rae-dev-command
192.168.1.Y   workhorse    # rae-dev-workhorse
192.168.1.Z   alpha        # rae-bot-alpha
```

**SSH** — one key per machine, cross-installed:

```bash
ssh-keygen -t ed25519        # accept defaults; once per machine
ssh-copy-id rae004@command   # run for each *other* machine
ssh-copy-id rae004@workhorse
ssh-copy-id rae004@alpha
```

Verify from each box that `ssh <other-host>` works without a password.

**Clone the repo** (location is per-machine preference; the project assumes
nothing about the path):

```bash
git clone <repo-url> && cd rae-model-training-research
uv sync   # once the lockfile exists
```

---

## 1. `rae-dev-command` — build plane

Nothing beyond section 0. The Phase 1 CPU track uses the standard (CPU)
PyTorch wheel, which arrives via `uv sync` like everything else. 64 GB RAM
needs no special configuration.

Optional quality-of-life: TensorBoard runs here during training; view it from
another machine at `http://command:6006` (bind with `--bind_all`).

---

## 2. `rae-dev-workhorse` — serving plane + CUDA box

Hardware: **RTX 5060 Ti 16GB** (Blackwell, `sm_120`) per ADR-021. The earlier
GTX 1050 + cu126 setup is preserved in ADR-014 (superseded) and
git history for anyone reconstructing the old environment.

**NVIDIA driver** (System76's packaging):

```bash
sudo apt install -y system76-driver-nvidia
sudo reboot
nvidia-smi   # should list the RTX 5060 Ti
```

If `apt` doesn't pick a Blackwell-ready driver (it needs the 570+ branch),
install directly from NVIDIA's repo:

```bash
sudo apt install -y nvidia-driver-570         # or 575 / latest stable
sudo reboot
nvidia-smi   # CUDA Version: should be 12.8 or higher in the header
```

**Pinned CUDA PyTorch environment** (see ADR-021). PyTorch's **cu128** wheel
line supports the 5060 Ti's `sm_120` and is the current generation. Install
in a *separate* venv from the main one (the main lockfile stays CPU-only —
that's the build plane behavior):

```bash
# inside the project on workhorse:
uv venv .venv-cu128
source .venv-cu128/bin/activate

# cu128-line torch first (lets uv resolve the right wheel)
uv pip install torch --index-url https://download.pytorch.org/whl/cu128

# Non-torch deps, then the package itself without re-resolving torch
uv pip install tensorboard pytest ruff
uv pip install -e . --no-deps
```

Verify CUDA is actually reachable before trusting any benchmark:

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# expect: True  NVIDIA GeForce RTX 5060 Ti
```

If a future PyTorch release drops `sm_120` (won't be soon — Blackwell is the
current architecture as of writing), repin within the cu128 line or jump to
whatever the contemporary wheel index is. ADR-021 supersedes ADR-014 on this
mechanism, but the same "separate workhorse environment" pattern still
applies.

**Ollama** (the model runtime):

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Make it listen on the LAN (not just localhost) so other machines can reach it:

```bash
sudo systemctl edit ollama
```

In the editor that opens, between the two `### Anything between here and the
comment below will become the contents of the drop-in file` markers, put
**exactly these two lines** (no `#` prefix — those are markdown comments here,
not file content; pasting them as-is would make the override a no-op):

```
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
```

Save and exit, then:

```bash
sudo systemctl restart ollama
```

Verify the override took effect:

```bash
systemctl show ollama --property=Environment
# → should include OLLAMA_HOST=0.0.0.0

# From another machine on the LAN:
curl -s http://workhorse:11434     # → "Ollama is running"
```

If your default editor is something other than `nano`, prepend
`SYSTEMD_EDITOR=vi` (or your preferred editor) to the `sudo systemctl edit`
command — note the env var goes *after* `sudo`, not before.

**Docker + Compose** (for the serving stack and the Phase 2 training-container
smoke tests; the NVIDIA container toolkit lets containers see the GPU):

```bash
sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER   # log out/in afterwards
# NVIDIA container toolkit — follow NVIDIA's current install guide, then:
docker run --rm --gpus all ubuntu nvidia-smi   # should show the 1050
```

---

## 3. `rae-bot-alpha` — data plane

Nothing beyond section 0. Dataset prep and eval tooling arrive via `uv sync`.
If eval runs here need to call a model, they point at the workhorse over HTTP
(`http://workhorse:11434`) — no local model runtime required.

---

## 4. Smoke test (all machines, after setup)

```bash
ssh workhorse true && echo "ssh ok"
curl -s http://workhorse:11434 && echo " ollama ok"
rsync --version > /dev/null && echo "rsync ok"
uv run python -c "import sys; print(sys.version)"
```

When all four pass on every machine, the fleet is ready for Phase 1.
