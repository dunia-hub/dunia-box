# Speech to text benchmark

Whisper: `large-v3-turbo` (cpu, int8). Scribe: `scribe_v1`.

WER = word error rate after lowercasing and removing punctuation. Lower is better.

| Clip | Language | Whisper WER | Scribe WER | Whisper time (s) | Scribe time (s) |
|---|---|---|---|---|---|
| mixed.m4a | auto | 0.333 | 0.0 | 45.54 | 2.32 |
| swahili.m4a | sw | 0.182 | 0.0 | 23.34 | 2.3 |
| english.m4a | en | 0.25 | 0.25 | 22.99 | 2.04 |

## Transcripts

### mixed.m4a

- Reference: Niandikie invoice ya Wanjiku Traders, three days za plumbing, elfu tano per day, due Friday.
- Whisper: Niyandikie invoice ya Wanjiko Traders, three days of plumbing, elfutano per day, due Friday.
- Scribe: Niandikie invoice ya Wanjiku Traders three days za plumbing elfu tano per day due Friday

### swahili.m4a

- Reference: Nataka kutuma invoice kwa Wanjiku Traders, shilingi elfu tano, ilipwe Ijumaa.
- Whisper: Nataka kutuma invoice kwa wanjiko traders shilingi elfu tano ilipwe ijuma.
- Scribe: Nataka kutuma invoice kwa Wanjiku Traders shilingi elfu tano ilipwe Ijumaa

### english.m4a

- Reference: Write a receipt for Otieno Hardware, two bags of cement, one thousand five hundred shillings each.
- Whisper: Write a receipt for Otieno hardware, two bags of cement, 1,500 shillings each.
- Scribe: Write a receipt for Otieno Hardware, two bags of cement, 1,500 shillings each.

Note: numbers written as digits (1,500) vs words (one thousand five hundred) count as errors here. Amounts are normalised later, in the extraction step.
