# PHYSIS AI v0.3.2 튜터 파이프라인

학생용 `POST /api/tutor/stream`은 질문을 읽어 필요한 도구를 선택한다. 검증된 답변 문단만 브라우저로 보낸다. 기존 `POST /api/chat`도 같은 계획·설명·근거 대조 함수를 사용한다. 실험 엔진은 기존 23개 모델과 27개 공식을 사용한다.

| 단계 | 담당 코드 | 학생에게 영향을 주는 결정 |
|---|---|---|
| A. 의도 분류 | `cognitive_routing.route`, `clarification`, `cognitive.local_plan` | 개념·공식·계산·생성·수정·비교·수학·조건 확인·범위 밖 요청을 복수로 분류한다. 명시된 입력, 같은 실험의 조건, 이미 답한 질문을 구분한다. |
| B. 문맥 선별 | `cognitive.compact_context` | 질문·수준, 관련 모델, 필요한 물리량을 우선한다. 검색 문단은 최대 3개, 검산한 수치 최대 4개, 적용 조건 최대 6개다. 짧은 후속 질문은 같은 실험의 이전 사용자 질문 한 개를 참조할 수 있다. 단순 원리 질문에는 현재 그래프의 숫자를 넣지 않는다. |
| C. 도구 실행 | `state.build`, `simulate`, `grounded`, `math_router` | 단위·입력 범위가 맞는 DSL만 실행한다. 수치·실험 ID·리비전·실행 지문은 서버 계산에서 온다. 식을 명시한 간단한 미분·적분·정리는 기존 격리 계산기로 보낸다. |
| D. 설명 생성 | `cognitive.explain_turn`, `providers.request_explanation` | 모델은 근거, 제한점과 짧은 자연어 설명을 제안한다. 실험 생성·수정·학습 수준 변경에 사용할 권한은 없다. 조건 질문, 기호 계산, 발견·복습 활동에는 생성 호출이 필요하지 않다. |
| E. 검증·회복 | `grounded.report`, `cognitive.screened_text`, `finish_trace` | 전달 직전 원문을 다시 조회하고 주장·단위·값을 대조한다. 생성 문장 안의 숫자는 신뢰할 수 있는 실행값으로 제시한다. 다른 문장이 유효하면 살리고 검증된 자료만으로 답한 경우 그 사실을 표시한다. |

문맥의 가변 데이터는 직렬화한 UTF-8 6,000바이트로 제한한다. 한국어·영어의 실제 토큰 수는 공급자가 돌려준 기록으로 측정한다. 긴 질문에서 숫자나 단위를 잘라 적용하지 않는다. 비교 실험의 이전 측정값은 실행 기록에서 읽는다. 대화에 나온 모델의 서술은 변경 명령의 근거가 될 수 없다.

앱은 `ANSWERED`, `PARTIALLY_ANSWERED`, `ASSUMPTION_REQUIRED`, `CLARIFICATION_REQUIRED`, `UNSUPPORTED_SIMULATION`, `INSUFFICIENT_EVIDENCE`, `VERIFICATION_FAILED`를 구분한다. 답변 근거 패널과 API에서 판정을 확인할 수 있다. 파이프라인의 `generation`은 로컬 규칙, 근거 검증 후 남은 모델 문장, 검증된 내장 대체 답변을 구분한다. 이 필드만으로 교육 정답이나 학생의 이해 여부를 판정할 수 없다.

범위 변경 전에는 계산 질문을 수정 요청으로 해석해 현재 카트 실험을 갱신한 사례가 있었다. 배포판에서는 기존 실험을 수정하려면 직접적인 변경 지시가 필요하다. 가정 계산의 새 입력은 별도 실험의 실행 기록에 저장한다. 클라이언트가 연결을 끊으면 보류한 쓰기를 취소한다. 모델 응답 Replay도 같은 설명 파서와 수치·원문 검증을 거친다. [계약 및 권한](ANSWER_CONTRACT.md) · [오류별 처리](FAILURE_RECOVERY.md) · [구성별 평가 상태](PIPELINE_ABLATION_RESULTS.md)
