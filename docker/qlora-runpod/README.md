# QLoRA training image (ADR-026)

Container-plane workflow for M12/M13. Training deps live here, never in
the shared CPU-only lockfile (CLAUDE.md rule 1 / ADR-003).

## Build + publish (on command)

```bash
SHA=$(git rev-parse HEAD)   # must be pushed — the image clones it
docker build -f docker/qlora-runpod/Dockerfile --build-arg REPO_SHA=$SHA \
    -t ghcr.io/rae004/rae-dev-model-training-lab-qlora:run-$(date +%Y%m%d)-$(git rev-parse --short HEAD) .
docker push ghcr.io/rae004/rae-dev-model-training-lab-qlora:run-<date>-<short-sha>
```

Pushing needs a GitHub token with `write:packages`
(`gh auth refresh -s write:packages`, then
`gh auth token | docker login ghcr.io -u rae004 --password-stdin`).

## RunPod pod spec

- **Image:** the GHCR tag above (~29 GB — allow pull time).
- **Max runtime:** 4 h (ADR-026 belt; ADR-025 estimates 1–3 h for the full run).
- **Secret:** `HF_TOKEN` — HF Hub token with write scope.
- **Env:** `RUN_TAG` (names the artifact repo `rae004/qlora-<RUN_TAG>`);
  smoke slice only: `MAX_PAIRS=50`, `MAX_EPOCHS=1`.
- **Entrypoint:** the image CMD runs `train_qlora.py`; artifacts push to
  HF Hub, then the script stops its own pod via RunPod's injected
  pod-scoped `RUNPOD_API_KEY` (success *and* crash — RunPod would
  otherwise restart the container on any exit, forever). `DEBUG_HOLD=1`
  holds a crashed pod 2h for log reading before stopping. Keep the
  template's max-runtime cap as the belt.

## Smoke test first (M12, #63)

A4000-tier pod, `MAX_PAIRS=50 MAX_EPOCHS=1`, expect ≤30 min / <$2.
Validates train → adapter push → GGUF convert → push → auto-exit before
any A100 time is bought. Record cost + wall time in `docs/results.md`.

## Local checks (no GPU)

```bash
docker run --rm <image> python -c "import torch, transformers, peft, trl, bitsandbytes"
docker run --rm -e RUN_TAG=x <image> python docker/qlora-runpod/train_qlora.py --dry-run
```
