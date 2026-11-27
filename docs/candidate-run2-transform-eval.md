# Transform eval report

Model: **rae-agent-candidate:run2**

Overall pass rate: **17/22** (77.3%)

## Per category

| category | passed | total | rate |
| --- | --- | --- | --- |
| decline | 4 | 5 | 80.0% |
| preservation_trap | 5 | 5 | 100.0% |
| philosophy_anchor | 3 | 7 | 42.9% |
| straight_transform | 5 | 5 | 100.0% |

## Per case

| case | category | clean apply | preserved | targeted | runaway | pass |
| --- | --- | --- | --- | --- | --- | --- |
| decline-absent-function | decline | yes | yes | yes | ok | **pass** |
| decline-absent-nullcheck | decline | yes | yes | yes | ok | **pass** |
| decline-no-retry-loop | decline | yes | yes | yes | ok | **pass** |
| decline-already-const | decline | yes | yes | yes | ok | **pass** |
| decline-no-dead-code | decline | **no** | **no** | **no** | ok | FAIL |
| trap-sibling-function-rename | preservation_trap | yes | yes | yes | ok | **pass** |
| trap-adjacent-interface | preservation_trap | yes | yes | yes | ok | **pass** |
| trap-same-literal-elsewhere | preservation_trap | yes | yes | yes | ok | **pass** |
| trap-unused-import | preservation_trap | yes | yes | yes | ok | **pass** |
| trap-similar-log-lines | preservation_trap | yes | yes | yes | ok | **pass** |
| anchor-noise-comments | philosophy_anchor | yes | **no** | **no** | ok | FAIL |
| anchor-dead-code | philosophy_anchor | yes | yes | **no** | ok | FAIL |
| anchor-defensive-validation | philosophy_anchor | yes | yes | yes | ok | **pass** |
| anchor-backcompat-alias | philosophy_anchor | yes | **no** | yes | ok | FAIL |
| anchor-abstract-types | philosophy_anchor | yes | yes | **no** | ok | FAIL |
| anchor-ts-readonly-array | philosophy_anchor | yes | yes | yes | ok | **pass** |
| interface-narrowing-regression | philosophy_anchor | yes | yes | yes | ok | **pass** |
| straight-rename-with-callsites | straight_transform | yes | yes | yes | ok | **pass** |
| straight-async-conversion | straight_transform | yes | yes | yes | ok | **pass** |
| straight-constant-change | straight_transform | yes | yes | yes | ok | **pass** |
| straight-fstring | straight_transform | yes | yes | yes | ok | **pass** |
| straight-export-rename | straight_transform | yes | yes | yes | ok | **pass** |
