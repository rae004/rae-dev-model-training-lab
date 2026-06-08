# Training Results

Reverse-chronological log of training runs. Each entry records the commit
it was generated from, the config, devices used, loss outcomes, and a
representative sample — the M4 "done means" contract from
`docs/MILESTONES.md`.

## How to add an entry

1. Note the commit SHA you trained from (`git rev-parse --short HEAD`).
2. For each device the run was performed on, capture the
   `param_count` and the `initial_eval` / `final_eval` numbers printed
   by `codereview train` at the end of the run.
3. Generate a sample from the saved checkpoint:
   `codereview sample --checkpoint <run-dir>/ckpt.pt --prompt "<seed>" --seed 42`
4. Copy the template below into the **Runs** section, fill in, commit
   (the entry should live alongside the code at the commit it describes).

## Template

```
### YYYY-MM-DD — <short run name>

- **Commit:** `<short SHA>`
- **Config:** `configs/<name>.toml`
- **Corpus:** `<source(s)>`, `<N>` chars, vocab=`<V>`
- **Wall time:** command=`<Xs>`, workhorse=`<Ys>`

| device | param_count | initial train | initial val | final train | final val |
| --- | --- | --- | --- | --- | --- |
| cpu (command) | ... | ... | ... | ... | ... |
| cuda (workhorse, GTX 1050) | ... | ... | ... | ... | ... |

**Sample (`--prompt "<seed>" --temperature 0.8 --top-k 40 --seed 42`):**

\`\`\`
<paste sample here>
\`\`\`

**Notes:** <observations>
```

---

## Runs

_(none yet — the first M4 run lands here when the char-level step-1 spec
config is run against the prepared corpus on both `command` and
`workhorse`)_
