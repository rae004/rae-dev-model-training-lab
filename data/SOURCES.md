# Corpus Provenance (ADR-018)

Every source in the Phase 1 pretraining corpus is recorded here: what, where
from, license, and date pulled. The corpus itself is git-ignored; this record
and the prep scripts in `data/scripts/` are how it is regenerated.

| Source | Type | License | Pulled | Notes |
| --- | --- | --- | --- | --- |
| `~/projects/ai-security-digest` | owner — local path | n/a (owner) | 2026-06-20 | TS-heavy (~60 .ts / 1 .py); not on GitHub |
| `~/projects/rae-budget` | owner — local path | n/a (owner) | 2026-06-20 | Balanced Python + TS (~40 / 61) |
| `~/projects/rae-time-tracker-and-invoice` | owner — local path | n/a (owner) | 2026-06-20 | Balanced Python + TS (~49 / 58) |
| `github.com/fastapi/fastapi` @ `master` | public — git | MIT | 2026-06-20 | Canonical modern Python web framework |
| `github.com/TheAlgorithms/Python` @ `master` | public — git | MIT | 2026-06-20 | Diverse Python idioms; balances against TS dominance; tutorial-style |
| `github.com/microsoft/TypeScript` @ `main` | public — git | Apache-2.0 | 2026-06-20 | Dominates the TS slice by volume; will dwarf owner code |

> Determinism note: both public sources use `ref = "main"` for the initial
> Phase 1 run, accepting non-reproducibility across pulls in exchange for
> not chasing tag versions for a disposable teaching artifact (ADR-016).
> Pin to a SHA in `data/scripts/sources.toml` if you need to reproduce a
> specific run.

## Fine-tune dataset pulls (ADR-029 / M10)

The same six sources feed the Phase 2 fine-tune dataset. Git sources are
fresh shallow clones (`--depth 2000`, single branch) into
`data/finetune_cache/`; owner repos are read in place. The exact HEAD SHA of
every source at generation time is recorded in `data/finetune/provenance.json`
and uploaded to the HF dataset repo alongside `dataset.jsonl`, so the branch
refs below stay reproducible per run even though they drift over time.

| Source | Ref | License | Pulled |
| --- | --- | --- | --- |
| `~/projects/ai-security-digest` | local HEAD | n/a (owner) | 2026-11-15 |
| `~/projects/rae-budget` | local HEAD | n/a (owner) | 2026-11-15 |
| `~/projects/rae-time-tracker-and-invoice` | local HEAD | n/a (owner) | 2026-11-15 |
| `github.com/fastapi/fastapi` | `master` | MIT | 2026-11-15 |
| `github.com/TheAlgorithms/Python` | `master` | MIT | 2026-11-15 |
| `github.com/microsoft/TypeScript` | `main` | Apache-2.0 | 2026-11-15 |
