## Aggregate

- **Macro precision:** 0.000
- **Macro recall:**    0.000
- **Macro F1:**        0.000
- **Verdict accuracy:** 0.000  (0 of 11)

### Recall by category

| category | recall |
| --- | ---:|
| bug | 0.000 |
| design | 0.000 |
| performance | 0.000 |
| readability | 0.000 |
| security | 0.000 |
| test-gap | 0.000 |

## Per-case

| case | ref | model | matched | P | R | F1 | verdict |
| --- | ---:| ---:| ---:| ---:| ---:| ---:| :---:|
| off-by-one-loop | 1 | 0 | 0 | 0.00 | 0.00 | 0.00 | ERR |
| retry-on-auth-failure | 1 | 0 | 0 | 0.00 | 0.00 | 0.00 | ERR |
| sql-injection | 1 | 0 | 0 | 0.00 | 0.00 | 0.00 | ERR |
| hardcoded-secret | 1 | 0 | 0 | 0.00 | 0.00 | 0.00 | ERR |
| new-function-no-tests | 1 | 0 | 0 | 0.00 | 0.00 | 0.00 | ERR |
| god-function | 1 | 0 | 0 | 0.00 | 0.00 | 0.00 | ERR |
| n-plus-one | 1 | 0 | 0 | 0.00 | 0.00 | 0.00 | ERR |
| cryptic-names | 1 | 0 | 0 | 0.00 | 0.00 | 0.00 | ERR |
| lgtm-rename-only | 0 | 0 | 0 | 0.00 | 0.00 | 0.00 | ERR |
| lgtm-typing-improvement | 0 | 0 | 0 | 0.00 | 0.00 | 0.00 | ERR |
| lgtm-test-added-with-feature | 0 | 0 | 0 | 0.00 | 0.00 | 0.00 | ERR |

## Errored cases

- **off-by-one-loop**: no JSON object found in model output
- **retry-on-auth-failure**: malformed JSON in model output: Expecting property name enclosed in double quotes: line 2 column 1 (char 2)
- **sql-injection**: no JSON object found in model output
- **hardcoded-secret**: malformed JSON in model output: Expecting property name enclosed in double quotes: line 2 column 3 (char 4)
- **new-function-no-tests**: malformed JSON in model output: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
- **god-function**: no JSON object found in model output
- **n-plus-one**: no JSON object found in model output
- **cryptic-names**: malformed JSON in model output: Expecting property name enclosed in double quotes: line 2 column 5 (char 6)
- **lgtm-rename-only**: no JSON object found in model output
- **lgtm-typing-improvement**: no JSON object found in model output
- **lgtm-test-added-with-feature**: no JSON object found in model output
