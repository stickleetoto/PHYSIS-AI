# PHYSIS AI v0.2 교육 품질 평가

2026년 11월 25일 Windows x64에서 Mock 튜터로 9개 시나리오의 33개 한국어 질문을 실제 FastAPI 경로에 순서대로 제출했다. 모든 턴이 해당 문항의 자동 기준을 통과했다. 고정된 개발용 사례의 결과이며 수업에서의 학습 효과, 자유서술 전반의 타당성, 외부 공급자의 성능은 측정하지 않았다.

## 평가 자료와 재현

문항, 출처, 독립 기대값과 판정 항목은 [교육 데이터셋](backend/tests/fixtures/education-v2.json)에 있다. [평가 프로그램](scripts/evaluate_tutor.py)은 임시 SQLite 데이터베이스에 시작 실험을 만들고 `POST /api/tutor/stream`에 `mock/local-rules`를 명시한다. 실제 저장된 실험 버전·입력은 후속 GET 요청으로 검증한다. 앱의 이미 저장된 실험이나 API 키가 필요하지 않다.

```powershell
python scripts/evaluate_tutor.py
python scripts/evaluate_tutor.py --json
```

두 번째 명령은 턴별 의도, 적용한 개별 검사와 실패 이유를 JSON으로 출력한다. 실패한 턴이 있으면 종료 코드는 1이다. 개발 환경에 `requirements-dev.txt`의 테스트 의존성이 필요하다.

| 질문 유형 | 턴 수 | 예시 |
|---|---:|---|
| 기본 개념 | 3 | 진자 운동의 원리 |
| 흔한 오개념 | 2 | 무거운 공이 먼저 떨어지는지, 관이 좁아지면 유량이 줄어드는지 |
| 실험 생성 | 5 | 압력계의 깊이·중력·수면 압력 지정, 주파수와 파장 지정 |
| 변수 변경 | 4 | 길이의 cm→m, 단면적의 cm²→m² 변환 |
| 결과 해석 | 2 | 현재 조건의 절대압·게이지압 또는 낙하 결과 읽기 |
| 연속 후속 질문 | 8 | 질량·주파수의 배수 조절, 같은 실험에서 공식 또는 복습 모드로 이동 |
| 적용 범위 밖 | 5 | 자유낙하에 항력 추가, 강제진동, 비스듬한 충돌 |
| 모순·모호함 | 4 | 단일 질량에 두 값 요구, 깊이에 질량 단위 지정 |

## 실행 결과

| 지표 | 통과 / 시행 | 판정 방식 |
|---|---:|---|
| 의도 분류 | 33 / 33 | 생성·수정·설명·지원 불가 응답이 문항별 기대 의도와 일치 |
| 모델 선택 | 24 / 24 | 지원되는 모든 턴에서 실제 실험의 모델 ID 일치 |
| 변수 추출 | 15 / 15 | 명시한 입력 전체의 SI 값 일치. 배수·시간 조건 포함 |
| 설명의 물리적 일관성 | 23 / 23 | 문항별 물리 원리·적용 조건, 수치와 단위, 미관측 상태, 발견 단계의 정답 비공개 또는 복습 정답 검사 |
| 대화 상태 유지 | 25 / 25 | 생성 이외의 턴에서 원래 ID·예상 버전·지정된 유지 조건 검사. 읽기 또는 거절 후 저장된 전체 실험 조건 대조 |
| 지원 불가 처리 | 9 / 9 | 범위 밖·모호함을 지원 불가로 응답하고 실험 스냅샷 미생성 |

지표마다 대상 문항이 다르며 한 턴에서 여러 지표를 검사한다. 수치 설명을 묻는 문항은 교재식으로 별도 계산한 기준값을 엔진 결과와 대조하고, 문장 속의 물리량 이름·값·단위까지 함께 확인한다. 출력의 네 자리 유효숫자 반올림을 허용한다. 정성 문항은 지정한 개념·조건 문구 및 금지된 결론의 유무를 검사한다. 자동 검사는 문장 전체에 대한 전문가 심사를 대신할 수 없으며, 표현이 달라져도 같은 뜻인지 판단하려면 추가 판독이 필요하다.

## 물리 기준의 예

- 균일한 중력에서 정지 출발·낙하 높이 5 m, g = 10 m/s²이면 도착 시간은 √(2h/g) = 1 s이고 직전 속력은 10 m/s다. 중력장과 출발 조건이 같으면 두 번째 물체의 질량을 8 kg으로 바꿔도 도착 시각이 같다. 실행 시간을 0.2 s로 제한하면 도착 사실이 없어야 한다. [OpenStax, Free Fall](https://openstax.org/books/university-physics-volume-1/pages/3-5-free-fall)
- 순힘 6 N을 받는 2 kg 수레의 가속도는 3 m/s²이며 질량을 두 배로 하면 1.5 m/s²다. 고립계의 비탄성 충돌에서도 총운동량은 보존된다. [Newton’s Second Law](https://openstax.org/books/university-physics-volume-1/pages/5-3-newtons-second-law), [Conservation of Linear Momentum](https://openstax.org/books/university-physics-volume-1/pages/9-3-conservation-of-linear-momentum)
- 물의 밀도 1000 kg/m³, g = 10 m/s², 깊이 3 m의 게이지압은 30,000 Pa다. 수면 압력이 100 kPa이면 절대압은 130,000 Pa다. 정상 비압축 흐름에서는 Q = Av가 두 단면에서 같다. [Measuring Pressure](https://openstax.org/books/university-physics-volume-1/pages/14-2-measuring-pressure), [Fluid Dynamics](https://openstax.org/books/university-physics-volume-1/pages/14-5-fluid-dynamics)
- 작은 각도의 단진자에서 T는 √L에 비례한다. 길이를 4배로 늘리는 복습 문제의 정답은 2배다. [Pendulums](https://openstax.org/books/university-physics-volume-1/pages/15-4-pendulums)
- 파형의 전파 속력은 c = fλ이며 진동수 2 Hz, 파장 1.5 m이면 3 m/s다. 이상기체는 고정된 양과 절대온도에서 부피를 두 배로 늘리면 압력이 절반이 된다. [Mathematics of Waves](https://openstax.org/books/university-physics-volume-1/pages/16-2-mathematics-of-waves), [Molecular Model of an Ideal Gas](https://openstax.org/books/university-physics-volume-2/pages/2-1-molecular-model-of-an-ideal-gas)

평가 과정에서 “측정 결과를 해석해 줘”가 적분법 변경으로 처리되어 실험 버전이 증가하는 오류를 발견했다. 해석 요청과 해석해 선택을 구분한 뒤 같은 시나리오에서 설정과 버전이 유지되는 것을 확인했다. 데이터셋은 수정에 사용한 회귀 세트이며 독립적인 비공개 시험 세트는 없다.
