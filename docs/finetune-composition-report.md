# Dataset composition report

Total pairs: **1180**

## Shape proportions

| shape | count | share |
| --- | --- | --- |
| chat | 225 | 19.1% |
| decline | 180 | 15.3% |
| review | 235 | 19.9% |
| transform | 540 | 45.8% |

## Mutation-rule coverage

Default minimum per rule: 100

| rule | count | minimum | meets minimum |
| --- | --- | --- | --- |
| backcompat_alias | 120 | 100 | yes |
| commented_out_code | 120 | 100 | yes |
| concrete_annotation | 22 | 20 | yes |
| defensive_validation | 119 | 100 | yes |
| noise_comments | 119 | 100 | yes |

## Source repositories

| repo | pairs |
| --- | --- |
| thealgorithms-python | 809 |
| rae-budget | 115 |
| rae-time-tracker-and-invoice | 111 |
| typescript | 63 |
| ai-security-digest | 59 |
| fastapi | 23 |

## Token-length histogram (full record)

| bucket | records |
| --- | --- |
| <= 1024 | 88 |
| <= 2048 | 266 |
| <= 4096 | 415 |
| <= 512 | 222 |
| <= 8192 | 189 |
