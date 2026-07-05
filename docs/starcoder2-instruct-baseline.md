## Aggregate

- **Macro precision:** 0.136
- **Macro recall:**    0.182
- **Macro F1:**        0.152
- **Verdict accuracy:** 0.545  (6 of 11)

### Recall by category

| category | recall |
| --- | ---:|
| bug | 0.000 |
| design | 0.000 |
| performance | 1.000 |
| readability | 0.000 |
| security | 0.000 |
| test-gap | 0.000 |

## Per-case

| case | ref | model | matched | P | R | F1 | verdict |
| --- | ---:| ---:| ---:| ---:| ---:| ---:| :---:|
| off-by-one-loop | 1 | 0 | 0 | 0.00 | 0.00 | 0.00 | ERR |
| retry-on-auth-failure | 1 | 1 | 0 | 0.00 | 0.00 | 0.00 | ✗ |
| sql-injection | 1 | 1 | 0 | 0.00 | 0.00 | 0.00 | ✗ |
| hardcoded-secret | 1 | 1 | 0 | 0.00 | 0.00 | 0.00 | ✗ |
| new-function-no-tests | 1 | 3 | 0 | 0.00 | 0.00 | 0.00 | ✓ |
| god-function | 1 | 3 | 0 | 0.00 | 0.00 | 0.00 | ✗ |
| n-plus-one | 1 | 2 | 1 | 0.50 | 1.00 | 0.67 | ✓ |
| cryptic-names | 1 | 0 | 0 | 0.00 | 0.00 | 0.00 | ✓ |
| lgtm-rename-only | 0 | 2 | 0 | 0.00 | 0.00 | 0.00 | ✓ |
| lgtm-typing-improvement | 0 | 1 | 0 | 0.00 | 0.00 | 0.00 | ✓ |
| lgtm-test-added-with-feature | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | ✓ |

## Errored cases

- **off-by-one-loop**: malformed JSON in model output: Extra data: line 13 column 1 (char 530)
