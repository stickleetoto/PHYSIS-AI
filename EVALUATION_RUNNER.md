# PHYSIS AI v0.3.2 평가 실행기

기본 명령은 실행 계획만 출력한다. 비교 결과는 문항, 모델 설정, 파이프라인 조건별로 SQLite에 저장하며, 결과의 출처와 실제 생성 요청 수를 함께 기록한다.

## 저장된 응답으로 확인하기

프로젝트 또는 배포본의 PHYSIS-AI 폴더에서 PowerShell로 실행한다. 소스 환경은 아래 명령의 `.\runtime\python.exe` 자리에 `python`을 사용한다. 예제에는 실제로 보관된 한 응답을 같은 문항의 다섯 조건에 넣어 두었다.

```powershell
$env:PHYSIS_OFFLINE = '1'
.\runtime\python.exe scripts/evaluation_v032.py run --profiles mock --cases release/software-v032/replay-demo-cases.jsonl --progress replay.sqlite
.\runtime\python.exe scripts/evaluation_v032.py run --execute --profiles mock --cases release/software-v032/replay-demo-cases.jsonl --replay release/software-v032/replay-demo-responses.jsonl --progress replay.sqlite --max-requests-per-invocation 1 --max-requests-total 1 --max-seconds-per-invocation 15 --max-seconds-total 300
.\runtime\python.exe scripts/evaluation_v032.py compare --progress replay.sqlite --format csv --output comparison.csv
```

두 번째 명령을 제한 시간 안에 다시 실행하면 완료 행을 건너뛴다. `compare`는 저장된 결과만 읽는다. `--progress first.sqlite second.sqlite --format json`으로 둘 이상의 기록을 내보낼 수 있다. `replay`는 저장 응답을 소비한 경로, `mock`은 내장 모의 공급자, `no_provider_call`은 공급자 호출 없이 끝난 경로, `archived_baseline`은 과거 기록, `actual_provider`는 실제 공급자 요청을 뜻한다. 실패한 요청도 요청 수에 포함될 수 있으므로 상태를 함께 확인한다.

## 모델과 구성 선택

아래는 연결을 나중에 설정할 때 쓸 JSON 예시다. 모델 ID를 해당 서버에 이미 있는 모델 이름으로 바꾸고 파일을 저장한다. 주소와 자격 증명은 실행하는 컴퓨터의 환경변수에서 읽는다. Ollama 주소에는 서버 루트, OpenAI 호환 주소에는 해당 서버의 API 기본 경로(보통 `/v1`)를 지정한다. 원격 인증 키는 HTTPS 주소에만 전송할 수 있다. 키를 요구하지 않는 호환 서버에서는 `api_key_env`를 생략할 수 있다.

```json
{
  "provider_configs": {
    "lab": {"provider": "ollama", "model": "EXISTING_MODEL_TAG", "endpoint_env": "LAB_OLLAMA_URL"},
    "classroom": {"provider": "compatible", "model": "MODEL_ID", "endpoint_env": "CLASSROOM_API_BASE", "api_key_env": "CLASSROOM_API_KEY"}
  }
}
```

```powershell
.\runtime\python.exe scripts/evaluation_v032.py run --config profiles.json --profiles lab,classroom --arms A,C,D,E,F --cases release/software-v032/replay-demo-cases.jsonl --progress future.sqlite
```

이 명령은 연결 없이 행 수를 보여 준다. 실제 평가를 추후 사용자가 선택할 때에는 오프라인 설정을 해제한 환경에서 `--execute`와 호출당·누적 요청 수 및 시간의 네 옵션을 모두 지정해야 한다. 요청 예약은 전송 직전에 발생하며, 실패와 모델 적재 요청도 예산을 소비한다. 시간은 초 단위이며 누적 제한은 첫 실행부터 지난 시간으로 계산해 중단 기간도 포함한다.

| 조건 | 처리 경로 |
|---|---|
| A | 질문을 모델에 단독 제시 |
| B | 보관한 v0.3.1 출력만 가져오기 |
| C | 의도 분류와 선별 문맥 |
| D | C와 문헌 검색 |
| E | D와 물리 계산 결과 |
| F | 제품의 실제 튜터 경로, 검증·재질문·복구 포함 |

B 기록은 `import-b --archive saved-b.json --progress baseline.sqlite`로 읽는다. 원본 JSON의 `arms.B.rows`에 저장된 행을 사용한다. 문항 파일은 JSON 또는 JSONL을 지원한다. 필수 필드는 고유한 `id`와 `question`이며, 필요하면 학습 수준(`level`), 실험 모델(`model`)과 변경값(`patch`)을 지정한다. `prior`를 쓰면 지원하는 경로에 이전 질문을 제공한다. 완전한 대화 이력에 대한 독립 평가 결과는 별도로 확보해야 한다.

같은 설정과 문항·제품·리플레이 자료로 같은 데이터베이스를 지정하면 완료 결과를 보존한다. `--run-id`로 실행을 명명할 수 있다. 중단된 행을 다시 시도하려면 `--retry-interrupted --retries 1`을 명시한다. 최초 누적 예산은 높일 수 없다. 다른 모델이나 입력으로 얻은 결과는 별도 실행으로 보관하여 비교한다.

이번 릴리스의 실제 모델·교육 성능과 외부 서버 운영 환경에서의 연결은 미측정이다. [이번 검증 결과](EDUCATIONAL_EVALUATION_V3.md) · [구성별 결과](PIPELINE_ABLATION_RESULTS.md)
