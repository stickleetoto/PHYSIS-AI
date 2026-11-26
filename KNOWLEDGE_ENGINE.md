# PHYSIS AI v0.3 과학 지식 엔진

첫 실행 시 내장 자료에서 문헌 인덱스 `knowledge-v3.sqlite3`를 만듭니다. 교재 46개 절에 속한 영어 원문 116문단을 인용할 수 있고, NASA 자료 3건은 서지 정보와 원문 링크를 제공합니다. 앱 시작과 검색에는 인터넷이나 API 키가 필요하지 않습니다. 서재 화면에서 한글로 검색한 뒤 영어 원문, 절과 문단 위치, 라이선스, 연결된 실험과 공식을 볼 수 있습니다. [자료 출처 목록](SOURCE_MANIFEST.md)

## 위치와 재현

| 파일 | 용도 |
| --- | --- |
| `backend/physis/corpus/selection.json` | 책, 모듈, 선택한 문단 ID, 개념·모델 태그, 고정 원본 해시 |
| `backend/physis/corpus/units.json` | 배포 원문, 서지 정보, 원본·문단별 SHA-256, UTC 수집 일시, 추출 상태 |
| `backend/physis/corpus/units.sha256` | 배포 자료 전체의 SHA-256 |
| `backend/physis/corpus/CC-BY-4.0.txt` | 고정한 교재 저장소의 라이선스 원문 |
| `scripts/collect_knowledge.py` | 선별 자료 다운로드, 캐시 검증, 재생성, 자료별 관리 |
| `scripts/evaluate_retrieval.py` | 재현 가능한 로컬 검색 비교 |
| `backend/physis/corpus/retrieval_queries.json` | 검색 질의와 관련 절 정답 ID |

소스 체크아웃에서는 프로젝트 루트에서 다음 명령을 사용합니다. Windows 배포 ZIP에서는 `python` 대신 `.\runtime\python.exe`를 사용할 수 있습니다.

```powershell
python scripts/collect_knowledge.py --cache .\public-cache --output .\verified\units.json
python scripts/collect_knowledge.py --offline --cache .\public-cache --output .\verified\units.json
python scripts/collect_knowledge.py --inspect .\lesson.pdf
python scripts/evaluate_retrieval.py --output .\retrieval-result.json
```

수집기는 고정한 OpenStax 공식 배포 경로, NASA Glenn 교육 페이지와 NASA NTRS 서지 API에만 HTTPS GET을 보냅니다. 출처별 어댑터가 자료 형식과 권리 정보를 확인합니다. 한 프로세스의 요청 시작 간격은 0.35초 이상이고 파일당 응답 상한은 2 MiB, 캐시 예산은 64 MiB입니다. 네트워크 조회 시간 제한은 18초입니다. 실패 시 자료 ID와 원인을 출력하고 종료 코드 1을 반환합니다. 모든 항목이 성공한 후 새 결과를 게시합니다. 재시도는 기존 캐시를 재사용합니다. `--refresh`는 원본을 다시 조회합니다. 캐시에는 URL별 다운로드 기록과 SHA-256별 본문이 저장됩니다. 동일 바이트는 공유하며 다른 버전은 별도 해시로 저장합니다.

OpenStax는 저장소 커밋을 고정하고 그 시점의 저장소 LICENSE와 책 컬렉션의 CC BY 4.0 표시를 모두 확인합니다. 선택 목록의 원본 SHA-256과 일치해야 본문을 내보냅니다. NASA 자료는 제목, 저자·기관, 원본 URL, 관찰한 원본 해시 등의 서지 필드만 내보냅니다. 인덱스는 초기화 시 배포 묶음 해시와 삽입할 문단 해시를 확인하고 트랜잭션 안에서 변경합니다. 해시는 로컬 손상 감지에 사용합니다. 배포 주체의 디지털 서명은 제공하지 않습니다.

## 처리와 인용

- CNXML에서 문서 제목, 장, 절, 상위 본문 문단 순번과 원본 문단 ID를 보존합니다. 선택 문단의 연속된 원문 또는 온전한 연속 문장을 추출합니다. 공백은 정규화하며 단순 인라인 MathML 기호를 표시 문자로 투영합니다. 복합 수식, 그림, 도표, 외부 링크에 걸친 문장은 제외합니다. 인용 링크는 고정한 파일의 해당 XML 줄로 연결됩니다. 이 형식에는 인쇄 쪽수가 없어 `page`는 null입니다.
- HTML은 제목과 가장 가까운 소제목, 문단 ID 또는 순번을 추출하고 스크립트·내비게이션·표를 제외합니다. MathML 누락을 표시합니다. Markdown은 ATX 제목과 문단 경계를 보존하며 코드 블록과 표를 빼고 수식 표기의 검증 여부를 기록합니다.
- 텍스트 PDF는 pypdf로 쪽별 텍스트 층을 읽고 1부터 시작하는 페이지와 해당 페이지 내 문단 순번을 보관합니다. 텍스트가 없는 쪽에는 OCR 미지원 상태를 남깁니다. 암호화 PDF, 200쪽 초과 파일, 텍스트 추출 결과 200만 자 초과 파일은 거절합니다. 다단·표·수식의 읽기 순서는 검증할 수 없어 `limited_layout`을 반환합니다.
- `--inspect`는 로컬 파일 추출 결과를 보여줍니다. 인용 자료로 배포하려면 별도로 출처 권리와 문단을 검토해야 합니다. PDF·표·OCR 수식이 공식 레지스트리에 자동 등록되는 경로는 없습니다.

## 검색

SQLite FTS5의 Unicode 토크나이저와 BM25가 제목, 소제목, 문단을 각각 7·2·1 가중치로 조회합니다. 질의는 정규화하고 단어 단위로 이스케이프합니다. 하이브리드 모드에서는 한·영 물리 용어와 공식·기호 사전으로 식별한 개념의 순위를 추가합니다. 이 사전은 `F=ma`, `A₁v₁=A₂v₂`, `ρ` 등의 표기를 처리합니다. 공식의 대수적 동치 판정은 수식 엔진에서 수행합니다.

RRF는 각 순위 목록의 `1/(60+순위)` 합으로 문단을 정렬합니다. v0.3.2는 텍스트 색인과 교과 개념 목록을 사용합니다. 이전 클라이언트의 `embeddings=true` 요청에도 같은 검색 결과와 `embeddings: false`를 반환합니다. 출처·난이도·모델 필터는 각 순위 목록을 만들기 전에 적용합니다.

| API | 결과 |
| --- | --- |
| `GET /api/knowledge/stats` | 실제 색인한 자료·문단 수, 출처별 수, 비활성 출처, 코퍼스 해시 |
| `GET /api/knowledge/documents?q=&source=&level=&model=` | 서지 필드 및 개념 검색. 메타데이터 전용 자료 포함 |
| `GET /api/knowledge/search?q=진자&mode=hybrid&limit=6` | 실제 문단과 원본 위치. 출처·수준·모델 필터 지원 |
| `GET /api/knowledge/documents/{id}` | 문헌 상세, 인용 가능한 문단, 개념·모델을 공유하는 관련 자료 |
| `GET /api/knowledge/chunks/{id}` | 해당 문단의 정본. 없는 ID는 HTTP 404 |

관련 모델 태그는 실험과 읽을 자료의 연결을 의미합니다. 예를 들어 유량 단원은 유체 입자 실험에서 쓰는 개념을 설명합니다. 태그만으로 특정 적분 알고리즘이나 실험의 모든 수치가 원문에서 뒷받침된다고 판단할 수 없습니다.

## 검색 평가

한국어 10문항, 영어 10문항, 공식·기호 6문항에 관련 문서 ID를 지정했습니다. 각 검색이 반환한 최대 50문단에서 동일 문서를 한 번만 세고 상위 다섯 문서를 평가했습니다. Hit@k는 정답 절 하나 이상이 k개 안에 있는 문항의 비율입니다. MRR@5는 첫 정답 순위의 역수 평균이며 5위 안에 없으면 0입니다. [질의별 실제 순위와 측정값](release/retrieval-v0.3.json)

| 실행 모드 | 전체 Hit@1 | 전체 Hit@5 | MRR@5 | 한국어 Hit@5 | 영어 Hit@1 | 공식·기호 Hit@5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BM25 키워드 | 10/26 | 10/26 | 0.3846 | 0/10 | 10/10 | 0/6 |
| BM25 + 개념 RRF | 22/26 | 25/26 | 0.9038 | 9/10 | 8/10 | 6/6 |
| BM25 + 개념 + LSA RRF | 22/26 | 25/26 | 0.8974 | 9/10 | 8/10 | 6/6 |

“물에 잠긴 물체가 위쪽으로 밀리는 까닭”처럼 부력을 직접 언급하지 않은 한국어 질문은 세 모드 모두 놓쳤습니다. 이 시험은 개발자가 선정한 작은 고정 코퍼스와 질의의 절 검색을 측정합니다. 검색되지 않은 관련 절이 정답 집합에 더 있을 수 있습니다. 자유 형식 질문의 일반 성능, 문장의 의미적 타당성, 사용자 학습 효과는 이 수치로 판단할 수 없습니다.

## 삭제와 데이터 경계

출처 ID는 `college`, `university1`, `university2`, `glenn`, `ntrs`입니다. 다음은 특정 출처를 사용자의 공개 문헌 인덱스에서 제거하거나, 내장 자료로 복원하는 명령입니다.

```powershell
python scripts/collect_knowledge.py --delete-source glenn --db "$env:LOCALAPPDATA\PHYSIS-AI\knowledge-v3.sqlite3"
python scripts/collect_knowledge.py --reindex-source glenn --db "$env:LOCALAPPDATA\PHYSIS-AI\knowledge-v3.sqlite3"
```

삭제하면 해당 문서·문단·FTS 행을 한 트랜잭션에서 제거하고 비활성 상태를 기록합니다. 재시작과 코퍼스 버전 갱신 후에도 비활성 상태가 유지됩니다. 재색인 명령은 해당 출처만 복원하며 중복 행을 만들지 않습니다. 설치본에 포함된 읽기 전용 자료와 운영자가 별도로 지정한 다운로드 캐시는 이 명령의 삭제 대상에서 제외됩니다.

문헌 DB는 학습 기록·실험 DB와 분리됩니다. 문헌 서비스는 검색어·학습 기록을 저장하거나 문헌 제공자에게 전송하지 않습니다. 수집 시 출처에는 고정 문서 경로, 제품 User-Agent와 일반 연결 정보가 전달됩니다. 외부 원문 링크를 누르면 해당 사이트를 엽니다. 문서 내용은 인용할 수 있는 외부 데이터이며 명령으로 해석하지 않습니다. HTTP 서비스에는 임의 URL 다운로드, 파일 업로드, 삭제 엔드포인트가 없습니다. 튜터 모델 사용 시 전송 범위는 튜터 설정과 근거 검증 문서를 참조하십시오.

