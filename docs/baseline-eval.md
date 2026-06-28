## Aggregate

- **Macro precision:** 0.273
- **Macro recall:**    0.273
- **Macro F1:**        0.273
- **Verdict accuracy:** 0.727  (8 of 11)

### Recall by category

| category | recall |
| --- | ---:|
| bug | 0.000 |
| design | 0.000 |
| performance | 0.000 |
| readability | 0.000 |
| security | 1.000 |
| test-gap | 0.000 |

## Per-case

| case | ref | model | matched | P | R | F1 | verdict |
| --- | ---:| ---:| ---:| ---:| ---:| ---:| :---:|
| off-by-one-loop | 1 | 1 | 0 | 0.00 | 0.00 | 0.00 | ✗ |
| retry-on-auth-failure | 1 | 0 | 0 | 0.00 | 0.00 | 0.00 | ✗ |
| sql-injection | 1 | 1 | 1 | 1.00 | 1.00 | 1.00 | ✓ |
| hardcoded-secret | 1 | 1 | 1 | 1.00 | 1.00 | 1.00 | ✓ |
| new-function-no-tests | 1 | 1 | 0 | 0.00 | 0.00 | 0.00 | ✓ |
| god-function | 1 | 2 | 0 | 0.00 | 0.00 | 0.00 | ✓ |
| n-plus-one | 1 | 2 | 0 | 0.00 | 0.00 | 0.00 | ✗ |
| cryptic-names | 1 | 1 | 0 | 0.00 | 0.00 | 0.00 | ✓ |
| lgtm-rename-only | 0 | 1 | 0 | 0.00 | 0.00 | 0.00 | ✓ |
| lgtm-typing-improvement | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | ✓ |
| lgtm-test-added-with-feature | 0 | 1 | 0 | 0.00 | 0.00 | 0.00 | ✓ |
