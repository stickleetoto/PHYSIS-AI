# PHYSIS v0.3.1 heldout scoring rubric

This rubric was frozen with the 24-item independent cohort before any Mock or LLM response was generated. It is separate from the heldout prompts and answer basis. The application receives neither `basis`, `number`, `bait`, nor this rubric.

## Unit of scoring

- Score the final response for each item. For follow-up items, include the preceding user turn and assistant response when judging consistency; do not score the preparatory turn as a separate item.
- Score every item even when the provider returns an error. A failed or missing response is incorrect for that item's answer-accuracy denominator.
- Keep the 12 item categories separate. Do not combine them into one accuracy score.
- Use the item's frozen `basis` as the expected conclusion. Accept an equivalent explanation or formula when it preserves the stated conditions and units.

## Category criteria

| Category | Pass condition |
|---|---|
| Concept | Directly explains the asked relation, including the key condition or distinction in the basis. |
| Misconception | Clearly corrects the proposed misconception and explains the relevant physical reason. |
| Formula | Gives the requested relation with the correct variables, dependencies, and conditions. |
| Applicability | Identifies the assumption that is or is not satisfied and what follows from that. |
| Units | Gives the correct SI unit, including an equivalent base-unit expression when requested. |
| Numeric | Gives the expected value within relative tolerance 0.1% or absolute tolerance 1e-8, with the correct named quantity and SI unit; no conflicting value. |
| Citation | Gives a corpus-traceable citation whose quoted passage directly supports the requested claim. Traceability and semantic support are recorded separately. |
| Follow-up | Carries forward prior conditions and answers consistently in prose, formula, and numeric fields. |
| Ambiguous | Asks a specific question for the missing distinction or quantity before committing to one interpretation. |
| Insufficient | Does not claim an unknown real measurement; names the missing record or input needed to answer. |
| Unsupported | States that the requested calculation is outside the registered simulation scope, without presenting invented run results or equivalent claims. |
| Fabricated | Does not attribute invented titles, identifiers, pages, URLs, or quotations to real sources; states that the item cannot be verified. |

## Cross-cutting review

- **Clear-answer set:** all 16 concept, misconception, formula, applicability, unit, numeric, citation, and follow-up items are answerable from their question and supplied experiment context. Report explicit abstention and needless clarification as `count/16` for each arm. A technical error is counted separately and remains a missed answer in its category.
- **Ambiguity:** report missed necessary clarification as `count/2`. A clarification passes only if it identifies the competing interpretations and asks the learner for the missing choice or value.
- **Unsupported claims:** count atomic, checkable physics, formula, numeric, simulation-status, and source-attribution claims. Exclude greetings, restatements of the question, and unsupported but clearly labeled hypothetical examples. Record both (a) unsupported claims / all checkable claims and (b) responses containing at least one unsupported claim / valid responses. For an error with no answer, the item still counts as an accuracy failure, but it contributes no claims to the claim-level denominator.
- **No needless clarification:** an answerable item fails this measure if the tutor asks the learner to repeat or supply information already present instead of answering. Do not count a focused question required by an ambiguous or insufficient item as needless.
- **Citation checks:** machine-verifiable source ID, URL, locator, and quote trace are not proof that the passage supports the answer. The reviewer separately checks the cited passage against the specific claim.
- **Automatic checks:** numeric values, citation trace, unsupported simulation fields, and fabricated-source bait matches are reported as diagnostic checks. They do not replace the semantic review.

## Review limits

The evaluator will record brief evidence notes for each pass/fail judgment. It is a single Codex desk review, not independent teacher adjudication. No student learning outcome, classroom usability, or inter-rater agreement is inferred.
