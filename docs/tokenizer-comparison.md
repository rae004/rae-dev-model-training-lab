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
  is used because the from-scratch BPE is the simple O(N)-per-merge
  reference impl from `src/codereview/bpe_tokenizer.py`; full-corpus
  measurement would take hours. The compression *ratio* per vocab size
  is corpus-distribution-dependent but stable across reasonably-sized
  samples of the same corpus.
- **Hardware:** `command` (Ryzen 9 9900X, CPU). 9 minutes total wall
  for the run on the sample, dominated by BPE training time.

## Results

| tokenizer | vocab | tokens | tokens / KB | bytes / token | compression vs. char | train s | encode s |
| --- | ---:| ---:| ---:| ---:| ---:| ---:| ---:|
| char-level | 103 | 183,030 | 937.11 | 1.093 | 1.00× | 0.0 | 0.0 |
| BPE | 512 | 86,816 | 444.50 | 2.304 | **2.11×** | 4.5 | 2.3 |
| BPE | 1,024 | 59,558 | 304.94 | 3.358 | **3.07×** | 11.4 | 5.4 |
| BPE | 2,048 | 40,314 | 206.41 | 4.961 | **4.54×** | 21.4 | 9.7 |
| BPE | 4,096 | 26,220 | 134.25 | 7.628 | **6.98×** | 36.1 | 15.2 |
| BPE | 8,192 | 15,354 | 78.61 | 13.026 | **11.92×** | 56.4 | 22.3 |

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
- The from-scratch BPE will need to be optimized (incremental pair
  counts, hash-keyed merge lookup) or replaced (`tiktoken`,
  `sentencepiece`) before training on the full pruned 54.7 MB corpus
  with vocab 4096+ — projected ~hours of training time with the
  reference impl. Filed as a follow-up for whoever runs M6.

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
