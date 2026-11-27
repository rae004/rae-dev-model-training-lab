## Aggregate

| metric | strict | severity-only |
| --- | ---:| ---:|
| Macro precision | 0.455 | 0.500 |
| Macro recall    | 0.455 | 0.545 |
| Macro F1        | 0.455 | 0.515 |

- **Verdict accuracy:** 0.818  (9 of 11)

### Recall by category (strict)

| category | recall |
| --- | ---:|
| bug | 0.500 |
| design | 0.000 |
| performance | 0.000 |
| readability | 0.000 |
| security | 1.000 |
| test-gap | 0.000 |

## Per-case

| case | ref | model | strict matched | strict P/R/F1 | sev-only matched | sev-only P/R/F1 | verdict |
| --- | ---:| ---:| ---:| ---:| ---:| ---:| :---:|
| off-by-one-loop | 1 | 1 | 1 | 1.00/1.00/1.00 | 1 | 1.00/1.00/1.00 | ✓ |
| retry-on-auth-failure | 1 | 0 | 0 | 0.00/0.00/0.00 | 0 | 0.00/0.00/0.00 | ✗ |
| sql-injection | 1 | 1 | 1 | 1.00/1.00/1.00 | 1 | 1.00/1.00/1.00 | ✓ |
| hardcoded-secret | 1 | 1 | 1 | 1.00/1.00/1.00 | 1 | 1.00/1.00/1.00 | ✓ |
| new-function-no-tests | 1 | 2 | 0 | 0.00/0.00/0.00 | 1 | 0.50/1.00/0.67 | ✓ |
| god-function | 1 | 0 | 0 | 0.00/0.00/0.00 | 0 | 0.00/0.00/0.00 | ✓ |
| n-plus-one | 1 | 1 | 0 | 0.00/0.00/0.00 | 0 | 0.00/0.00/0.00 | ✗ |
| cryptic-names | 1 | 1 | 0 | 0.00/0.00/0.00 | 0 | 0.00/0.00/0.00 | ✓ |
| lgtm-rename-only | 0 | 0 | 0 | 1.00/1.00/1.00 | 0 | 1.00/1.00/1.00 | ✓ |
| lgtm-typing-improvement | 0 | 0 | 0 | 1.00/1.00/1.00 | 0 | 1.00/1.00/1.00 | ✓ |
| lgtm-test-added-with-feature | 0 | 1 | 0 | 0.00/0.00/0.00 | 0 | 0.00/0.00/0.00 | ✓ |
