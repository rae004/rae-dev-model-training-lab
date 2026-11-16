# Dataset composition report

Total pairs: **1186**

## Shape proportions

| shape | count | share |
| --- | --- | --- |
| chat | 229 | 19.3% |
| decline | 180 | 15.2% |
| review | 237 | 20.0% |
| transform | 540 | 45.5% |

## Mutation-rule coverage

Default minimum per rule: 30

| rule | count | minimum | meets minimum |
| --- | --- | --- | --- |
| backcompat_alias | 32 | 30 | yes |
| commented_out_code | 32 | 30 | yes |
| concrete_annotation | 22 | 20 | yes |
| defensive_validation | 32 | 30 | yes |
| noise_comments | 32 | 30 | yes |

## Source repositories

| repo | pairs |
| --- | --- |
| thealgorithms-python | 861 |
| rae-budget | 106 |
| rae-time-tracker-and-invoice | 97 |
| ai-security-digest | 55 |
| typescript | 45 |
| fastapi | 22 |

## Token-length histogram (full record)

| bucket | records |
| --- | --- |
| <= 1024 | 85 |
| <= 2048 | 281 |
| <= 4096 | 381 |
| <= 512 | 232 |
| <= 8192 | 207 |
