# v0.3.1 heldout Mock semantic review

Frozen 24-item education cohort; actual `/api/tutor/stream` Mock responses. One independent desk reviewer. All 24 responses completed; Mock provider tokens are not applicable and recorded provider-token counters are zero.

- Product snapshot: `86a18410440acb8f5f83d6afeb78bfc9504241d67d745c7a681b99a17b35edb2` (freeze manifest verified by runner).
- Pre-generation seal: `63c2b188c9f5a701789d9bf00462cb7d1835d999b5c8ca8d8373dc5171b83528`; fixture SHA-256 `276b32e62c6db1fc67ff6a7560fbd6de9b5a46a57290e492d0406f19d72a48c9`; rubric SHA-256 `f5211900702df2314de934fa27eeb299a02f0812f0d7daacac6b475a93c76d63`.
- Review file: `release/benchmark-v031-mock-heldout-24-review.json`; graded copy: `release/benchmark-v031-mock-heldout-24-graded.json`.

## Category results

| Category | Correct | n |
|---|---:|---:|
| concept | 0 | 2 |
| misconception | 1 | 2 |
| formula | 1 | 2 |
| applicability | 0 | 2 |
| units | 0 | 2 |
| numeric | 1 | 2 |
| citation | 1 | 2 |
| followup | 0 | 2 |
| ambiguous | 0 | 2 |
| insufficient | 1 | 2 |
| unsupported | 0 | 2 |
| fabricated | 2 | 2 |

## Cross-cutting results

- Clearly answerable set explicit full abstention: 7/16 (`h-applicability-01, h-citation-02, h-concept-01, h-followup-01, h-followup-02, h-misconception-02, h-units-02`).
- Needless clarification on clearly answerable set: 1/16 (`h-numeric-01`).
- Missed necessary clarification on ambiguous items: 2/2 (`h-ambiguous-01, h-ambiguous-02`).
- Unsupported factual/formula/numeric/simulation assertions after excluding generic refusal boilerplate: 3/107 claims; responses with at least one such assertion: 3/24.
- Requested citation items: 1/2 semantic support; automated quote/source trace was 20/20 overall and requested source trace 1/2.
- Generic abstention text is not counted as a factual claim. Claim totals count distinct answer assertions, formulas, numeric fields, assumptions, and model/simulation-result statements; evidence notes bind each judgment to the response.

This is a desk review of generated responses, not a classroom outcome or teacher adjudication. The independent second review is maintained separately.
