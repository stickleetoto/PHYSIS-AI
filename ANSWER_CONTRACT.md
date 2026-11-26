# Answer Contract (v0.3.2 P0)

학생의 문장과 실험 저장 사이에는 세 가지 계약이 있다. 모델은 `ExplanationResponse`로 설명·근거 후보·가정·불확실성만 반환한다. 앱은 사용자의 요청을 해석한 뒤 `ExperimentAction`의 대상·변수·버전을 검사하고, 실제 저장한 실험과 학습 수준을 `ApplicationState`로 돌려준다. 학습 설정과 이력은 기존 앱·저장소가 소유한다. 선택적 메타데이터의 오류는 해당 필드에서 처리하고, 자연어 문장과 수치는 다시 물리 근거와 대조한다. 가정 계산이 현재 실험을 수정했던 이전 실패는 별도의 Mock 사례로 재검증한다. [실행 경로](COGNITIVE_PIPELINE.md) · [원래 실험과 새 실험의 상태 기록](release/software-v032/write-authority.json)

## ExplanationResponse

The explanation provider returns a bounded `ExplanationResponse` with:

- `text`: natural-language explanation proposal, at most 8,000 characters.
- `source_ids`: at most three IDs that exactly match supplied passage IDs.
- `assumptions`: at most four strings that exactly match supplied conditions.
- `uncertainty`: optional short statement about limits or missing evidence.
- `warnings`: always a list of generic warning codes. It never echoes rejected values.

`text` is untrusted until the application runs the existing claim, citation, and numeric checks. The checked report is the only explanation delivered to the student. Missing or truncated structured output is rejected so the route can use its deterministic fallback. Clearly plain prose may be salvaged with empty references and the `plain_text_salvaged_unverified` warning; it must pass the same downstream checks.

Provider output cannot set user settings, learning level, experiment inputs, experiment IDs, revisions, or actions. Unsolicited action/state fields are dropped and recorded as `state_action_metadata_dropped`. Optional metadata errors do not discard valid explanation text.

## Compact provider context

`request_explanation(name, context, *, transport=None)` accepts the app-built context keys `question`, `level`, `intents`, `model`, and optional `inputs`, `history`, `passages`, `formula`, `calculations`, and `conditions`. It emits only those compact fields. History is capped at six entries; passages at four quotes; calculations at eight; source and text lengths are bounded. Unknown context keys, the experiment catalog, and full response schemas are not sent.

Formula information is whitelisted to a short identity/expression, bounded conditions, review status, formula status, and applicability status/reason. This preserves partial/outside-condition labels without sending a full physics schema. Passage text is treated as untrusted quoted data.

The model may return `numeric_claims` as proposals. Structurally valid proposals are kept only in request-local metrics for `grounded.report` to check against the active run, experiment, revision, units, and value. A mismatching proposal is warned about and never becomes a user-visible fact by itself. Malformed proposals are dropped with a warning. Citations and assumptions are filtered before they enter metrics or the response.

## Application-owned state and actions

`ApplicationState` is owned by the application/store. It contains the selected learning level and the current experiment snapshot identity (experiment ID and revision); the snapshot itself remains the server's validated `Experiment`/`Run` data. The provider receives only the bounded context derived from that state and cannot write it.

`ExperimentAction` is a separate dispatcher command. It contains the validated action kind and, when applicable, the target experiment ID, expected revision, and a `Patch`. Planning output continues through the existing `Candidate`/`Intent`, `reasoning._checked`, and `state.build` validation path before any state commit. `ExplanationResponse` has no action or state fields.

## Transport, timing, and recovery

Ollama inference checks `/api/ps` with a five-second bound. If the selected model is not resident, it makes a separate empty `/api/generate` preload request, capped at 180 seconds, before starting inference. The preload record and inference record remain separate. Inference streams internally so time to first generated text can be measured; its timeout is 45 seconds and its output is capped at 768 generated tokens, 16 KiB provider text, and 8 KiB explanation text. Cancellation propagates. There is no automatic inference retry; timeout, disconnect, or invalid output returns a sanitized `ProviderError` for the application fallback.

Token counts are populated only from provider-reported usage. Ollama load and generation durations are recorded only when the server reports them. Unavailable values remain `null`; no token or timing values are estimated.

## Offline replay and provider defaults

`ReplayTransport` accepts one previously stored assistant-content string or a complete normalized/provider response envelope. It is a one-shot in-memory adapter: it never opens a socket, invokes a model, or estimates usage, and its request record has `origin: replay`. Replayed content goes through the same compact-context builder, explanation parser, optional-metadata filtering, and tutor grounding path as runtime content. `replay_context(...)` is a scoped Mock-only seam for integration tests; Replay is not an HTTP-selectable provider.

A non-Mock `PHYSIS_AI_PROVIDER` environment value does not activate inference by itself. Set `PHYSIS_ALLOW_ENV_PROVIDER_DEFAULT=1` for an intentional server-wide environment default. A request-local provider selection from the UI remains explicit and continues to work without that flag.
