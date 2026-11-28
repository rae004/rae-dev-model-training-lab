# Tool-calling smoke report

Model: **rae-agent-candidate:run3**

Tool-call rate: **10/10** (100.0%)
Threshold: 90% — pass

| prompt | tool called | detail |
| --- | --- | --- |
| read-config | yes | content JSON: read_file (missing <tool_call> tags) |
| read-readme | yes | content JSON: read_file (missing <tool_call> tags) |
| write-gitignore | yes | content JSON: write_file (missing <tool_call> tags) |
| write-note | yes | content JSON: write_file (missing <tool_call> tags) |
| run-tests | yes | content JSON: run_command (missing <tool_call> tags) |
| run-list | yes | content JSON: run_command (missing <tool_call> tags) |
| search-todo | yes | content JSON: search_code (missing <tool_call> tags) |
| search-function | yes | content JSON: search_code (missing <tool_call> tags) |
| chained-intent | yes | content JSON: read_file (missing <tool_call> tags) |
| fix-typo | yes | content JSON: read_file (missing <tool_call> tags) |

