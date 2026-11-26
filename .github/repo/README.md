# Repository settings as code

Each file here is the exact body the GitHub REST API takes, so you can copy from the API docs
or export a ruleset from the GitHub UI and drop it in. `scripts/repo_settings.py` compares
these with the live repo and applies them.

| file | endpoint | notes |
|---|---|---|
| `repository.json` | `PATCH /repos/{owner}/{repo}` | only the keys listed are managed |
| `actions-permissions.json` | `PUT …/actions/permissions` | which Actions may run |
| `actions-workflow.json` | `PUT …/actions/permissions/workflow` | `GITHUB_TOKEN` defaults; approvals stay off (no release automation here) |
| `rulesets/*.json` | `POST`/`PUT …/rulesets` | matched to the live ruleset by `name` |
| `labels.json` | `POST`/`PATCH …/labels` | optional and not used here; issue labels matched by name |

```
uv run python scripts/repo_settings.py diff    # show drift (exit 1 if any)
uv run python scripts/repo_settings.py apply   # push the files to GitHub (needs repo admin)
```

CI runs `diff` on every PR that touches this folder. The default Actions token can't read
the Actions-permission endpoints, so those report `skipped` in CI unless a `REPO_ADMIN_TOKEN`
secret (fine-grained PAT, Administration: read) is set. Applying is always done locally.

## One-off prerequisites (no JSON body, so not managed here)

- Dependabot alerts must be on before `security_and_analysis.dependabot_security_updates` can
  be enabled: `gh api -X PUT repos/{owner}/{repo}/vulnerability-alerts` (204 = on).
- Labels used by `dependabot.yml` and the auto-merge workflow (`dependencies`, `python`,
  `github-actions`, `major-bump`) are created once with `gh label create`.
