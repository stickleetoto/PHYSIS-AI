# PHYSIS AI 공급자 연결

기본값 `mock`은 로컬에서 한국어 질문을 교실 물리 실험으로 해석합니다. 설치 직후 API 키 없이 사용할 수 있습니다. 질문 예시는 다음 순서로 입력해 보세요.

1. “무거운 물체가 가벼운 물체보다 빨리 떨어지는 거 아니야?”라고 물으면 두 물체의 자유낙하 실험을 엽니다. 이미 열려 있으면 그 실험의 현재 질량과 관측값으로 설명합니다.
2. “그러면 두 물체의 질량 차이를 더 크게 해봐.”라고 하면 물체 B의 질량을 조정합니다. 출발 높이와 중력 가속도는 이전 실험의 값을 사용합니다.
3. “왜 결과가 같아?”라고 물으면 현재 실행에서 기록한 수치와 모델 가정에 근거해 설명합니다. “연구자 수준으로 설명해 줘”라고 하면 시간 간격별 위치 편차도 볼 수 있습니다. 바닥에 도달하기 전에 관찰이 끝났으면 도착 시간이 측정되지 않았다고 표시합니다.

값을 직접 지정할 때는 “높이를 250 cm로”, “물체 B의 질량을 750그램으로”처럼 변수와 단위를 함께 쓰세요. “진자의 처음 각도를 30도로”는 라디안으로 환산합니다. “새 실험으로 자유낙하를 해줘”는 새 ID로 등록된 기본 조건에서 시작합니다. 모호한 값이나 지원 범위 밖의 모델은 `UNSUPPORTED`로 표시합니다.

완전비탄성 충돌은 반발 계수 0, 탄성 충돌은 1을 사용합니다. 일반적인 비탄성 충돌을 요청할 때는 원하는 반발 계수를 함께 적으세요. 자유낙하는 정지 상태에서 동시에 놓는 두 물체, 충돌은 일차원, 부력은 완전히 잠긴 채 고정된 물체를 다룹니다. 달처럼 특정 환경을 가리킬 때는 필요한 중력 가속도를 직접 지정할 수 있습니다. 예를 들어 기존 실험에 “중력 가속도를 1.62 m/s²로 바꿔”라고 입력하세요. 내장 해석기는 정해진 한국어 표현과 단위를 인식하므로 복합 문장이 의도대로 해석되었는지는 실험 입력값에서 확인하세요.

## 공급자 선택

프로젝트 루트의 `.env.example`을 `.env`로 복사하고 사용할 공급자에 해당하는 값을 채운 후 백엔드를 재시작하세요. 프로세스에 이미 설정한 환경 변수가 우선합니다. `GET /api/health`는 서버 기본 공급자를 표시합니다. 튜터의 **AI 공급자 설정**에서 공급자와 모델을 선택하면 그 선택을 각 질문에 함께 보냅니다. 다른 탭의 질문이나 v0.1 실험실 채팅은 자체 설정을 사용합니다.

설정 창을 열면 서버의 구성 여부를 표시합니다. **연결 확인**을 누르면 모델 목록 API에 접근하고 응답 시간을 표시합니다. **모델 목록 조회**로 받은 ID를 선택하거나 **모델 ID**에 직접 입력한 뒤 **선택 적용**을 누르세요. 목록 API가 없는 호환 서비스도 모델 ID로 시도할 수 있습니다. 목록의 모델이 튜터의 채팅, JSON 및 스트리밍을 지원하는지는 실제 질문으로 확인할 수 있습니다. 모델 목록 조회는 첫 페이지에서 최대 1,000개 ID를 읽습니다.

| `PHYSIS_AI_PROVIDER` | 추가 환경 변수 | 요청 방식 |
| --- | --- | --- |
| `mock` | 없음 | 내장 한국어 규칙 |
| `openai` | `PHYSIS_AI_MODEL`, `OPENAI_API_KEY` | JSON 객체 응답을 지원하는 모델과 Chat Completions를 사용합니다. [OpenAI API 문서](https://developers.openai.com/api/reference/resources/chat) |
| `anthropic` | `PHYSIS_AI_MODEL`, `ANTHROPIC_API_KEY` | Messages API의 `system`과 사용자 메시지를 전달하고 단일 텍스트 블록의 JSON을 읽습니다. [Anthropic API 문서](https://platform.claude.com/docs/en/api/messages/create) |
| `ollama` | `PHYSIS_AI_MODEL`, 선택적으로 `OLLAMA_BASE_URL` | 실행 중인 Ollama에 설치된 모델 태그를 입력하세요. 기본 주소는 `http://127.0.0.1:11434`이며 `/api/chat`에서 JSON 스키마를 전달합니다. [Ollama API 문서](https://docs.ollama.com/api/chat) |
| `compatible` | `PHYSIS_AI_MODEL`, `PHYSIS_COMPATIBLE_BASE_URL`, 선택적으로 `PHYSIS_COMPATIBLE_API_KEY` | Chat Completions 및 `response_format`의 `json_object`를 지원하는 엔드포인트를 사용합니다. 기본 URL에는 서비스의 API 접두사까지 포함하세요. `http://127.0.0.1:8001/v1`로 설정하면 `/v1/chat/completions`에 요청합니다. |

`PHYSIS_AI_MODEL`에는 기본 공급자에서 사용 가능한 모델 ID를 지정하세요. 공급자별 초기 ID를 별도로 지정하려면 `PHYSIS_OPENAI_MODEL`, `PHYSIS_ANTHROPIC_MODEL`, `PHYSIS_OLLAMA_MODEL`, `PHYSIS_COMPATIBLE_MODEL`을 사용하세요. 이 값이 해당 공급자의 공통 기본값보다 우선합니다. 튜터에서 직접 고른 모델이 있으면 이를 우선합니다. API 키와 호환 서버 주소는 백엔드 환경에서 관리합니다. 공급자별 키는 해당 공급자로 보내는 인증 헤더에만 담깁니다. 인증 키를 받는 원격 호환 서버는 HTTPS를 사용하세요. 루프백 주소의 로컬 서버는 HTTP를 사용할 수 있습니다.

| 요청 | 역할 |
| --- | --- |
| `GET /api/providers` | 서버 구성 여부와 공급자별 기본 모델. 외부 요청 0회 |
| `POST /api/providers/{provider}/probe` | 모델 목록을 읽어 접근 여부, 목록 개수와 응답 시간 확인 |
| `GET /api/providers/{provider}/models` | 동일한 목록 API에서 모델 ID 조회 |
| `GET /api/usage` | 최근 30개 튜터 요청의 모델, 처리 시간, 결과 및 단계별 공급자 사용량 |

## 실험 명세와 검산

v0.3.2에서 실험 계획과 설정은 앱이 소유합니다. 물리 엔진이 계산 결과와 실행 ID를 만들고, 설명을 위해 선택된 공급자에는 해당 질문에 필요한 문단·조건·계산값만 전달합니다. 설명은 주장 단위로 검토하며 잘못된 수치, 없는 인용, 요청하지 않은 제어 필드를 처리합니다. 발생한 문제와 정상으로 남은 문장은 답변의 근거 패널에서 확인할 수 있습니다. [응답 계약](ANSWER_CONTRACT.md) · [튜터 파이프라인](COGNITIVE_PIPELINE.md)

이번 릴리스의 기본값은 Mock입니다. 저장된 응답을 재생하는 Replay는 파싱·검산을 시험하기 위한 오프라인 경로입니다. 실모델 비교는 사용자가 별도 실행기에서 지시하고 예산을 지정할 때 시작할 수 있습니다. [평가 도구 사용법](EVALUATION_RUNNER.md)

## 스트리밍, 취소와 사용량

튜터는 OpenAI 및 OpenAI 호환 서버의 Chat Completions SSE, Anthropic Messages SSE, Ollama의 줄 단위 JSON을 수신합니다. 수신 중에는 단계와 수신 조각 수만 전달합니다. 서버가 종료 신호와 완료 사유, JSON 스키마를 확인한 뒤 튜터가 한국어 설명을 구성합니다. 역할이 잘못됐거나 길이 제한으로 잘린 응답, 도구 호출, 거부 또는 중단된 응답은 사용하지 않습니다. Anthropic은 단일 텍스트 블록을 지원합니다. 추론·도구 블록이 필수인 모델은 이 구성에서 사용할 수 없습니다. [OpenAI 스트림 옵션](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) · [Anthropic 스트림 이벤트](https://platform.claude.com/docs/en/build-with-claude/streaming) · [Ollama 채팅](https://docs.ollama.com/api/chat)

각 생성 호출의 전체 제한 시간은 45초, 연결 제한 시간은 5초입니다. 생성 호출은 자동 재시도하지 않습니다. 목록 및 연결 확인은 전체 8초 안에 일시적인 네트워크 오류나 HTTP 502·503·504에 한해 1회 재시도합니다. 튜터 요청을 취소하면 진행 중인 공급자 응답 스트림을 닫습니다. 취소 시점까지 공급자가 처리한 토큰에는 요금이 발생할 수 있습니다.

**최근 사용 기록**에서 같은 공급자·모델의 최근 튜터 요청 시간과 단계별 입력·출력 토큰을 봅니다. `null`과 ‘미제공’은 공급자가 해당 수치를 보내지 않았다는 뜻입니다. OpenAI에는 최종 사용량 이벤트를 요청하며, 호환 서버는 표준 SSE에 사용량을 포함할 때 기록합니다. Mock은 외부 모델 요청 0회로 표시합니다. 학습 데이터 삭제 시 로컬 사용 기록도 삭제됩니다. 공급자 진단 오류에는 공급자의 원문 응답과 인증 정보를 포함하지 않습니다.

## 연결 검증 범위

v0.3에서 외부 공급자를 선택해 질문을 제출할 때 서버는 질문, 현재 실험의 관련 조건·단위·물리 모델·검증 결과, 실험 ID와 버전·실행 지문, 공식 및 최대 4개의 공개 문단 발췌와 위치를 전송할 수 있습니다. 학습 노트, 복습 기록, 문헌 색인 전체는 요청에 포함하지 않습니다. API 키는 서버 쪽 인증에만 사용합니다. `Start-PHYSIS.cmd --offline`으로 실행하면 외부 공급자 호출이 차단됩니다.

`python -m pytest -q backend/tests/test_reasoning.py backend/tests/test_reasoning_providers.py backend/tests/test_provider_v2.py`로 대화 흐름·단위 환산·해설과 공급자 규약을 확인할 수 있습니다. v0.2의 어댑터 시험은 `httpx.MockTransport`로 분할된 스트림, 통신 중단, 취소, 시간 초과, 잘린·거부된 응답, 사용량, 요청별 모델 격리와 메타데이터 재시도를 재현합니다. 이번 공급자 시험에서 실제 유료 계정, 원격 호환 서버, 설치된 Ollama 모델의 인증·추론·한국어 품질은 검증하지 않았습니다.

프런트엔드 빌드 후 `python -m pytest -q scripts/test_provider_settings.py`로 Chromium에서 로컬 연결 확인, 모델 목록 선택, 수동 ID 입력, 새로고침 뒤 선택 복원 및 Esc 닫기를 재현할 수 있습니다. 호환 서버의 목록은 브라우저 시험에서 모의 응답을 사용합니다.
