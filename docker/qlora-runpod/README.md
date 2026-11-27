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

## RunPod pod spec (proven on the M12 smoke run, #63)

- **Image:** the GHCR tag above (~29 GB — allow pull time).
- **Container disk:** 80 GB. **No persistent volume** — a volume mounts
  over `/workspace` and buries the baked-in repo.
- **Max runtime:** 4 h (ADR-026; now the backstop behind self-stop.
  ADR-025 estimates 1–3 h for the full run).
- **Secret:** `HF_TOKEN` — HF Hub token with write scope.
- **Env:** `RUN_TAG` (names the artifact repo `rae004/qlora-<RUN_TAG>`)
  and `DEBUG_HOLD=1` (crashed pod holds 2 h for log reading).
  Smoke slice only: `MAX_PAIRS=50`, `MAX_EPOCHS=1` — **drop both for
  the full run.**
- **Entrypoint:** the image CMD runs `train_qlora.py`; artifacts push to
  HF Hub, then the script stops its own pod via RunPod's injected
  pod-scoped `RUNPOD_API_KEY` (success *and* crash — RunPod would
  otherwise restart the container on any exit, forever). The stop call
  retries with a Cloudflare-DoH fallback (run2's pod couldn't resolve
  `rest.runpod.io`), and on failure the script idles instead of exiting
  so the worst case is the max-runtime cap, never a retrain loop.

## Full run (M13, #64/#65)

Config is `configs/qlora_baseline.toml` as committed — 3 epochs, full
1,186-pair dataset (inside ADR-025's 400–1,200 no-revisit band), seed
20261126. The smoke overrides live in pod env, not the config, so the
full run is the same template minus `MAX_PAIRS`/`MAX_EPOCHS`.

Preflight, in order:

1. Build + push a fresh image from main (`run-<date>-<sha>`); update the
   template's Container Image to it.
2. **First deploy verifies self-stop live** — run2 proved the happy
   path can fail (pod DNS couldn't resolve `rest.runpod.io`, so the pod
   restart-looped through full retrains). The entrypoint now retries
   with a DoH fallback and idles on failure. Watch the first run end:
   pod should stop within ~2 min of the final `gguf ->` line; an idling
   pod bills until the 4 h max-runtime cap, so stop it manually if you
   see the idle message.
3. **GPU:** A100 80 GB preferred (ADR-026; ~1–3 h, $3–10). If out of
   capacity, A40 48 GB at ~$0.59/hr is proven end-to-end with this exact
   config — slower, but well inside the 4 h belt and cheaper.
4. Record wall time + cost + metrics in `docs/results.md` (#65).

## Smoke test (M12, #63 — done)

A40 pod, `MAX_PAIRS=50 MAX_EPOCHS=1`: ~10 min and ~$0.10 per cycle,
$0.96 for the whole seven-deploy campaign. Full post-mortem in
`docs/results.md`.

## Local checks (no GPU)

```bash
docker run --rm <image> python -c "import torch, transformers, peft, trl, bitsandbytes"
docker run --rm -e RUN_TAG=x <image> python docker/qlora-runpod/train_qlora.py --dry-run
```
