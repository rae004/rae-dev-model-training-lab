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

**NVIDIA driver** (System76's packaging):

```bash
sudo apt install -y system76-driver-nvidia
sudo reboot
nvidia-smi   # should list the GTX 1050
```

**Pinned CUDA PyTorch environment** (see ADR-014). The GTX 1050 is Pascal
(`sm_61`), which current PyTorch wheels no longer support — this machine's
training environment pins an older release from the **cu126** wheel line, in a
*separate* lockfile/venv from the main one:

```bash
# inside the project, in the workhorse-specific environment:
uv pip install "torch==2.7.*" --index-url https://download.pytorch.org/whl/cu126
```

Verify CUDA is actually reachable before trusting any benchmark:

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# expect: True  NVIDIA GeForce GTX 1050
```

If a future install rejects the card with an `sm_61` error, the wheel is too
new — re-pin within the cu126 line.

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
