# Char vs. BPE: compression measured on the Phase 1 corpus

The "compression lesson, made concrete" half of M5. Trains BPE at
five vocab sizes against a fixed sample of the corpus, measures
**tokens-per-KB** (the headline metric), and compares to the
char-level baseline.

Reproduce with:

```bash
uv run python data/scripts/tokens_per_kb.py --corpus <path>
```

## Measurement

- **Corpus sample:** the first 200 KB (195.3 KB UTF-8) of
  `data/corpus.txt` from the pruned ablation re-run (PR #14). A sample
  is used so the table is reproducible in seconds; the compression
  *ratio* per vocab size is corpus-distribution-dependent but stable
  across reasonably-sized samples of the same corpus.
- **Hardware:** `command` (Ryzen 9 9900X, CPU).
- **Algorithm:** the incremental BPE from PR #19's perf optimization
  (replaces the original O(N)-per-merge reference impl, byte-identical
  output, ~10–20× faster). See "BPE training-time was the bottleneck"
  below for the comparison.

## Results

| tokenizer | vocab | tokens | tokens / KB | bytes / token | compression vs. char | train s | encode s |
| --- | ---:| ---:| ---:| ---:| ---:| ---:| ---:|
| char-level | 103 | 183,030 | 937.11 | 1.093 | 1.00× | 0.0 | 0.0 |
| BPE | 512 | 86,816 | 444.50 | 2.304 | **2.11×** | 0.3 | 2.3 |
| BPE | 1,024 | 59,558 | 304.94 | 3.358 | **3.07×** | 0.6 | 5.4 |
| BPE | 2,048 | 40,314 | 206.41 | 4.961 | **4.54×** | 1.6 | 9.7 |
| BPE | 4,096 | 26,220 | 134.25 | 7.628 | **6.98×** | 3.6 | 15.3 |
| BPE | 8,192 | 15,354 | 78.61 | 13.026 | **11.92×** | 7.5 | 22.7 |

### BPE training-time was the bottleneck (the M5 → M6 perf story)

The original reference BPE in PR #15 was O(N) per merge step. On the
same 200 KB sample its training column was: 4.5 → 11.4 → 21.4 → 36.1 →
56.4 s. Extrapolating to the full 54.7 MB corpus at vocab 4096
projected **~hours of training time** — prohibitive for M6.

The incremental algorithm shipped in PR #19 maintains pair counts +
position sets via a doubly-linked-list view of the token stream, so
each merge is O(occurrences of the chosen pair), not O(N). Output is
**byte-identical** (validated by `test_incremental_matches_reference`
across 12 diverse inputs). Speedup vs. reference at this sample:

| vocab | reference s | incremental s | speedup |
| ---:| ---:| ---:| ---:|
| 512 | 4.5 | 0.3 | **15×** |
| 1,024 | 11.4 | 0.6 | **19×** |
| 2,048 | 21.4 | 1.6 | **13×** |
| 4,096 | 36.1 | 3.6 | **10×** |
| 8,192 | 56.4 | 7.5 | **7.5×** |

This unblocks training BPE-4096 on the full corpus for M6 (projected
~16 min wall, vs. hours+ with the reference). Encode-time is unchanged
— `BPETokenizer.encode` was never the bottleneck.

## What the table says

1. **Char-level is ~1 byte per token by definition.** Our corpus is
   mostly ASCII (a few JSDoc / Unicode comment chars push the average
   to 1.09 bytes/token). The 103-token char vocab is just the unique
   characters in this sample.
2. **BPE compression grows sub-linearly with vocab.** Doubling the
   vocab (512 → 1,024 → 2,048 → 4,096 → 8,192) compresses by 2.11× →
   3.07× → 4.54× → 6.98× → 11.92× — each doubling buys ~1.5× more
   compression, not 2×. This is the diminishing-returns curve in code
   form.
3. **Effective context grows directly with compression.** With
   block_size 128:
   - char-level sees ~140 bytes of context
   - BPE-1024 sees ~430 bytes
   - BPE-2048 sees ~635 bytes
   - BPE-4096 sees ~976 bytes
   - BPE-8192 sees ~1,668 bytes
   At fixed training cost (same step count, same batch size), the BPE
   model is **learning patterns across 7–12× more source code per
   batch.** That's the real payoff per ADR-016 step 2.
4. **Training-time cost scales roughly with vocab size**, since the
   reference BPE makes one full pass per merge. Encode-time scales
   too, but more gently (longer merge chains, but fewer of them
   triggered per input token).

## Implications for M6

ADR-016 step 2 calls for a ~4k–8k vocab BPE feeding a ~10M-param
baby-GPT. Based on this table:

- **Vocab 4096** is the sweet spot: ~7× more effective context than
  char-level, with manageable training cost on the full corpus.
- **Vocab 8192** doubles the embedding table size for a ~70% extra
  compression gain — still worth it for the baby-GPT's headline learning
  run, especially since the BPE training is a one-time cost amortized
  across all subsequent model training.
- ~~The from-scratch BPE will need to be optimized~~ — done in PR #19
  (incremental pair counts via linked-list view of the token stream).
  M6 now trains BPE-4096 on the full corpus in tractable time (~16 min
  projected from the sample numbers above).

## Why bytes, not codepoints

The BPE here operates on **UTF-8 bytes**, not Python `str` codepoints.
Two reasons:

1. **No UNK token needed.** All 256 byte values are always in the
   vocab, so any UTF-8 input round-trips by construction — even text
   the tokenizer wasn't trained on.
2. **Smaller vocab floor.** Codepoint-level BPE would start with the
   full set of Unicode characters seen in training (the char tokenizer's
   vocab of 924 on the full corpus). Byte-level starts at exactly 256
   and *learns* multi-codepoint sequences as merges — both more
   compressed and more robust to novel input.

This matches what modern code LLMs do (`tiktoken` is byte-level BPE).
