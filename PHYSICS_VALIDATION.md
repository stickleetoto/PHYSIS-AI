# PHYSIS AI 물리 모델과 검증

v0.3은 기존 23개 물리 모델을 유지하며, 각 모델을 적어도 하나의 검토된 레지스트리 공식에 연결합니다. 등록 관계 27개를 독립적으로 차원 검사하고 비기본 입력에서 물리 엔진 출력과 대조했습니다. 소각도 진자 주기의 교육용 기준은 0 < |θ₀| ≤ 0.20 rad이며, 이때 유한 진폭 주기 대비 상대 차이는 0.26% 미만입니다. 각도 0인 정지 진자에서는 관측 주기를 보고하지 않습니다. 실제 장치로 측정한 오차는 별도 항목입니다. [공식, 원자료와 적용 조건](FORMULA_REGISTRY.md) · [실행 수치의 검산](EVIDENCE_VERIFICATION.md)

v0.2에는 기존 13개와 파동·열·유체 입문 10개를 포함한 23개 모델이 있다. 모든 기본 설정이 자동 검사에서 `VERIFIED`를 받았다. 수치는 SI 단위를 사용한다. 검증 대상은 아래 방정식, 초기 조건, 시간 격자로 계산된 결과다. 실제 장치의 측정 불확도나 현실 환경에 대한 정확도는 이 판정의 범위 밖이다.

## 결과 읽기

- `VERIFIED`는 선택한 설정에서 수행한 필수 검사가 모두 통과했음을 뜻한다.
- `LIMITED`는 궤적 검사가 통과했으나 관찰 시간 안에 낙하 도착, 마찰 정지, 두 물체의 충돌 중 해당 사건을 관찰하지 못했음을 뜻한다. 결과의 `관찰 범위` 항목에 사유가 표시된다.
- `FAILED`는 기준해 편차, 보존 법칙, 안정성, 시간 간격 세분화 등 필수 검사 중 하나 이상이 실패했음을 뜻한다. 유한한 계산 결과는 오차를 분석할 수 있게 반환한다. 무한대나 NaN이 생기면 첫 이상 표본 직전까지 반환한다.
- `UNVERIFIED`는 수행한 검사가 없는 경우다. 등록되지 않은 요청은 실험 생성 단계에서 `UNSUPPORTED`로 처리한다.

일반 궤적 검사는 **최대 절대 편차 ≤ 10⁻⁸ + 0.01 × 기준량**을 요구한다. 각 항목에 오차·허용값·단위가 함께 표시된다. 위치 기준량은 낙하 높이, 최대 기준 변위, 진동 진폭, 원의 반지름 등 해당 모델의 길이 척도다. 에너지 기준량은 초기 역학적 에너지 또는 일·운동 에너지의 규모다. 충돌 보존량, 유체 평형, 줄 길이 제약에는 상대 계수 10⁻¹⁰을 적용한다. 이 기준은 교육용으로 선택한 허용 오차다.

## 적분과 사건

`dt`마다 고정 간격으로 적분하며 마지막 구간은 지정된 종료 시각에 맞춰 줄인다. 자유낙하는 수치 궤적이 지면과 만나는 시각을 구해 그 지점에서 끝난다. 마지막 속도와 힘은 착지 직전 값이다. 마찰 정지와 충돌은 구간 내부라도 사건 시각을 시간축에 넣는다. 정지 시각의 속도와 수평 마찰력은 0이다. 충돌 시각에는 두 위치가 같고 속도는 충돌 직후 값이다. 순간 충격은 `impulse`로 기록한다.

운동 모델은 해석해, 전진 오일러, 속도를 먼저 갱신하는 반암시적 오일러, 고전 RK4를 제공한다. 등가속도에서는 각 방법의 한 스텝 변위를 누적한다. RK4의 가중 평균 속도는 이 경우 정확히 중점 속도다. 일반 진동에서는 위치와 속도의 중간 단계까지 계산한다. 충돌과 세 유체 모델은 직접 푸는 대수식만 사용한다.

`error`는 같은 시각의 기준 위치와의 거리(m)다. 수치 실험에서 `dt`, `dt/2`, `dt/4`로 독립 실행한 뒤 각 실행의 **전체 표본 최대 위치 오차**를 비교한다. 각 자유낙하 실행은 자체 착지 시각까지 진행하며 기준 궤적은 착지 뒤 높이 0으로 연장한다. 세분화 검사는 오차가 순서대로 감소하고 최종 오차가 최초보다 작을 때 통과한다. 비교 허용량은 10⁻¹⁰ × max(1 m, 좌표 크기)로 두고 세 오차가 모두 이 범위면 분해 한계로 표시한다. 이 범위 안에서는 수렴 차수를 추정할 수 없다. 해석해를 직접 선택하면 같은 공식에 대한 위치 차이는 0이며 수렴 표는 비어 있다.

선형 용수철, 감쇠 진동, 회전 중인 원운동에는 한 스텝 증폭 행렬을 구성해 장시간 선형 안정성도 검사한다. 최대 고유값 크기 `spectral_radius`가 1 + 10⁻¹⁰을 넘으면 실패다. 감쇠 없는 반암시적 오일러의 경계 `dt × ω = 2`에서는 중복 고유값으로 인해 오차가 누적되므로 실패로 판정한다. 이 검사는 비선형 진자의 장시간 안정성을 보장하지 않는다.

## 모델별 조건과 측정량

| 실험 | 이상화와 기준식 | 대표 결과 및 단위 |
| --- | --- | --- |
| 자유낙하 `free_fall` | 공기 저항 없이 같은 높이에서 동시에 놓는다. 위쪽이 양수이며 두 질량의 기준 위치는 h − gt²/2다. 두 물체의 에너지를 각각 검사한다. | 지면 도달 시 `arrival_time`, `reference_arrival_time`(s), `impact_speed`(m/s) |
| 등속 `uniform` | 수평면에서 알짜힘이 0이다. 기준 위치는 x₀ + v₀t다. | `final_position`(m), `final_velocity`(m/s), `acceleration`(m/s²) |
| 등가속도 `acceleration` | 입력한 일정한 가속도로 운동한다. 기준 위치는 x₀ + v₀t + at²/2다. | 같은 종료 위치·속도·가속도, 일과 운동 에너지 차이(J) |
| 뉴턴 제2법칙 `newton` | 일정한 수평 외력 F로 a = F/m. 수평 이동에서 위치 에너지는 일정하고 외력이 한 일은 FΔx다. | 같은 종료 위치·속도·가속도, 외력에 따른 에너지 변화(J) |
| 마찰 `friction` | 수평면의 운동 마찰 μmg는 속도 반대 방향이다. 정지 후 계속 정지한다. μ = 0이면 등속 운동이다. | `stop_time`(s), `stop_distance` 및 `final_position`(m) |
| 충돌 `collision` | 일직선 위 두 점질량, 외부 충격량 0. 0 ≤ e ≤ 1. e = 0은 완전 비탄성, e = 1은 탄성 충돌이다. | `collision_time`(s), `impulse`(N·s, B가 받은 충격량), `total_momentum`(kg·m/s), `energy_loss`(J), `final_velocity_a/b`(m/s) |
| 용수철 `spring` | 선형 복원력 −kx. 해석해는 사인·코사인 함수이고 E = mv²/2 + kx²/2다. | `reference_period`, `measured_period`(s), `spectral_radius`(무차원) |
| 진자 `pendulum` | 길이 L, 정지 출발, θ̈ = −g sin(θ)/L. 입력 각도는 라디안이다. 지지점 (0,L), 최저점 (0,0). 초기 진폭 ±1.55 rad 이내에서 줄이 팽팽한 진동을 다룬다. | 타원적분 기준 주기·측정 주기(s), `angle`(rad), `angular_velocity`(rad/s), 기준 위치와의 현 길이 오차(m) |
| 감쇠 진동 `damped` | mẍ + bẋ + kx = 0. 부족·임계·과감쇠 해석해를 사용한다. 손실된 에너지는 ∫bv²dt이며 표본 사다리꼴 적분으로 계산한다. 거친 격자에서는 이 적분도 검사를 실패할 수 있다. | `damping_ratio` 및 `spectral_radius`(무차원), `dissipated_energy`(J), 진동할 때의 주기(s) |
| 원운동 `circular` | 선형 중심력 −mω²r에서 접선 초기 속도 Rω를 준다. 기준 궤도는 원이고 위치 에너지는 mω²r²/2다. 수치 궤도는 반지름을 직접 고정하지 않아 오차를 관찰할 수 있다. | `centripetal_acceleration`(m/s²), `reference_speed`(m/s), 회전할 때의 `reference_period`(s) |
| 정수압 `hydrostatic` | 일정 밀도의 정지 유체에서 고정 수심 측정. 절대압 p = p₀ + ρgh, 게이지압 ρgh. | `pressure`, `gauge_pressure`(Pa), `depth`(m) |
| 부력 `buoyancy` | 완전 잠긴 물체를 지지대로 정지시킨다. 부력 ρgV, 무게 mg, 지지력 mg − ρgV. 위쪽은 양수, 무게 항목은 크기다. | `buoyancy`, `weight`, `support`(N), `fy`는 지지력을 포함한 총수직력(N) |
| 연속 방정식 `continuity` | 정상 비압축성 흐름의 두 단면에서 A₁v₁ = A₂v₂. 단면 평균 유속과 유량을 계산한다. | `flow`(m³/s), `outlet_speed`(m/s), 단면별 유속(m/s)·면적(m²) |

측정 주기는 같은 방향의 평형점 통과를 두 번 이상 관찰한 경우에만 표시한다. 표본 사이 통과 시각은 선형 보간한다. 세 유체 실험은 고정 센서의 정상 상태를 표시하므로 시간 그래프가 수평이다. 조건을 바꾼 두 실험을 비교하면 수심에 따른 압력 증가, 부피에 따른 부력 변화, 단면적에 따른 유속 변화를 읽을 수 있다.

## v0.2 파동·열·유체 입문

새 모델은 해석식으로 계산한다. 서버의 각 시계열은 해당 실행의 시간축과 길이가 같다. 파동 화면은 서버에서 받은 원점과 λ/4 위치의 변위로 단일 공간 조화 모드 u(x,t) = u(0,t) cos(kx) + u(λ/4,t) sin(kx)를 복원한다. 종파의 점은 매질 표지의 실제 변위 방향을 나타낸다. 열확산 화면은 양 끝 온도와 중심 온도로 단일 사인 모드의 분포를 복원한다. 베르누이와 추적자 실험은 지정된 일차원 흐름의 개념적 단면을 그린다.

| 모델 | 기준식과 적용 조건 | 별도 검증 및 허용 오차 |
| --- | --- | --- |
| 사인 횡파 `wave_transverse` | u=A sin(kx−ωt), c=fλ. 균일·선형·비분산 매질에서 변위가 전파 방향에 수직이다. | 초기 프로파일을 ct만큼 이동해 네 위치의 계산 결과와 대조. 절대 5×10⁻¹⁵ m. |
| 사인 종파 `wave_longitudinal` | 같은 식의 축방향 변위 ξ를 평형 위치에 더한다. 범위에서 2πA/λ < 1이므로 입자 순서가 유지된다. | 네 위치의 이동 프로파일 및 ¼주기 뒤 원점 변위 −A. 브라우저에서 밝은 표지의 수평 이동과 일정한 수직 좌표 확인. |
| 파동 중첩 `wave_superposition` | 같은 방향·파장·진폭의 두 파동에 상대 위상 φ를 부여한다. 합성 진폭은 2A\|cos(φ/2)\|이다. | 임의 위상에서 두 번 이동시킨 프로파일의 합과 대조. φ=π에서 양 관측점 최대 2×10⁻¹⁶ m 미만. |
| 정상파 `wave_standing` | 반대 방향 두 파동의 합은 2A sin(kx)cos(ωt)이다. c=fλ는 각각의 구성 진행파 속력이다. | 정·역방향 이동 해의 합과 대조. x=0 마디와 λ/4 배를 확인. |
| 이상기체 `ideal_gas` | 고정된 n,V,T에서 p=nRT. 열평형·이상기체 가정이며 R=8.31446261815324 J/(mol·K)이다. | 273.15 K에서 1 mol, 0.02241397 m³의 압력이 101325 Pa와 상대 10⁻⁶ 이내. 부피 두 배에서 압력 절반. |
| 열평형 `heat_equilibrium` | 각 물체는 일정 열용량 C를 가진 등온 물체다. 단열된 계에서 열전류 G(T₁−T₂)로 열을 교환한다. 평형 온도는 열용량 가중평균이다. | 서로 반대 온도차 및 같은 초기 온도에서 별도 적응형 DOP853과 절대 10⁻⁸ K 이내. 주고받은 열의 합은 3×10⁻¹² J 이내. |
| 뉴턴 냉각 `cooling` | 주변 온도와 비례 계수 k가 일정하고 물체 내부 온도가 균일하다. 온도차는 exp(−kt)에 비례한다. | 가열·냉각·평형 초기 조건에서 별도 DOP853과 절대 2×10⁻⁸ K 이내. |
| 1차원 열확산 `heat_diffusion` | 균일 막대, 양 끝 같은 고정 온도, 단일 초기 사인 모드. 중심 온도차는 exp(−απ²t/L²)에 비례한다. | 경계를 고정한 독립 유한차분 공간 연산자의 99개 내부점 해와 모든 표본에서 대조. 절대 0.0003 K 이내. |
| 베르누이 `bernoulli` | 수평 유선을 따르는 정상·비압축성·비점성 흐름. A₁v₁=A₂v₂, p+ρv²/2 일정. | ρ=1000 kg/m³, 입구 100 kPa, 면적비 3, 입구 2 m/s에서 출구 84 kPa. 유속 0에서 두 절대압 일치. |
| 유체 추적자 `fluid_tracer` | 일정 유속 u의 직선 흐름에서 질량 없는 표지의 x=x₀+ut. 확산·점성·난류는 생략한다. | x₀=0.7 m, u=1.25 m/s에서 1.7 m 통과 시각 0.8 s 확인. 유속 0에서 전 구간 정지. |

각 실행의 대수 잔차 기준은 표기한 물리량에서 10⁻⁸ + 10⁻¹⁰ × |기준량|이다. 독립 검증에는 위 표의 별도 허용값을 적용했다. 파동에서 Δt ≥ 1/(2f)이면 시간축이 진행과 진동을 구분할 만큼 촘촘하지 않아 `LIMITED`로 표시한다. 이상기체와 수평 관의 압력은 한 실행에서는 정상값이며 입력 조건을 바꿀 때 다른 평형값이 나온다.

파동의 기준식과 중첩 원리는 [OpenStax 파동의 수학](https://openstax.org/books/university-physics-volume-1/pages/16-2-mathematics-of-waves) 및 [정상파](https://openstax.org/books/university-physics-volume-1/pages/16-6-standing-waves-and-resonance)를 따른다. 열 교환은 [OpenStax 열량 측정](https://openstax.org/books/university-physics-volume-2/pages/1-4-heat-transfer-specific-heat-and-calorimetry), 상태식은 [열역학계](https://openstax.org/books/university-physics-volume-2/pages/3-1-thermodynamic-systems), 온도 확산과 선형 냉각은 [MIT 18.03 열방정식 강의](https://ocw.mit.edu/courses/es-1803-differential-equations-spring-2024/mites_1803_s24_heat_equation.pdf)에 근거한다. 관의 두 단면은 [OpenStax 베르누이 방정식](https://openstax.org/books/university-physics-volume-1/pages/14-6-bernoullis-equation)의 같은 높이 조건을 사용한다.

## 공식 탐구와 수치해석 실험실

기존 13개 공식 카드에는 작성된 유도 과정, 해당 방정식의 적용 조건과 차원, 조절 가능한 변수와 기준 교재가 있다. 그래프는 활성 실험의 서버 측 계산 결과를 다시 사용한다. 자유낙하에서 질량처럼 주 공식에서 약분되는 변수도 조절할 수 있다. 여러 변수의 영향은 그래프 물리량 선택으로 비교한다.

수치해석 실험실은 같은 마찰 없는 용수철을 해석해, 전진 오일러, 반암시적 오일러, RK4로 푼다. 활성 실험이 용수철이면 같은 모델 입력을 복사하고 다른 모델에서는 기본 기준 용수철을 사용한다. 절대 오차는 전체 시간에서 max |x수치−x해석|, 상대 오차는 이를 진폭 √(x₀²+(v₀/ω)²)로 나눈 값이다. 진폭이 0이면 상대 오차는 정의되지 않는다. 에너지 드리프트는 max |mv²/2 + kx²/2 − E(0)|이다. 서버는 네 방법 각각의 궤적 계산만 고해상도 시계로 한 번씩 측정한다. 출력·비교·수렴 그래프 작성·네트워크 시간은 제외한다.

예를 들어 m=2 kg, k=8 N/m, x₀=0.75 m, v₀=1 m/s, Δt=0.04 s, 종료 3.013 s에서 초기 에너지는 3.25 J이다. 전진 오일러의 최대 위치 오차와 에너지 드리프트는 각각 0.152682 m, 1.99776 J, 반암시적 오일러는 0.0305722 m, 0.240378 J, RK4는 1.67843×10⁻⁶ m, 8.86771×10⁻⁷ J였다. 시간 간격을 절반·¼로 줄인 비교는 각 격자에서 독립 재계산한다. 이 오차는 같은 모델을 계산하는 방법의 차이이며 실제 장치와 모델 사이 편차는 별도 실측이 필요하다.

## 재현 결과

프로젝트 루트에서 다음 명령으로 스키마와 물리 시험을 실행한다.

```powershell
python -m pytest -q backend/tests/test_schema.py backend/tests/test_physics_core.py backend/tests/test_physics_models.py
python -m pytest -q backend/tests/test_physics_fields.py backend/tests/test_science_lab.py
python -m pytest -q scripts/test_science_browser.py
```

| 기준 문제 | 실제 결과 |
| --- | --- |
| 1 kg·5 kg, 20 m, g = 9.81 m/s², RK4 0.02 s | 두 물체 모두 2.01927510938461 s에 도달, 충돌 직전 속력 19.8090888231 m/s, 최대 위치 편차 2.49 × 10⁻¹⁴ m |
| 같은 낙하, 전진 오일러 | 시간 간격 0.1, 0.05, 0.025 s에서 최대 오차 0.981, 0.4905, 0.24525 m. 0.1 s 결과는 필수 허용 오차 초과로 실패 |
| m = 1 kg, k = 10 N/m, x₀ = 1 m, 6 s, RK4 | 0.02, 0.01, 0.005 s에서 2.315 × 10⁻⁶, 1.444 × 10⁻⁷, 9.021 × 10⁻⁹ m. 간격을 절반으로 줄일 때 약 16배 감소 |
| 같은 용수철, 전진 오일러 0.2 s, 10 s 관찰 | 증폭 행렬 반경 1.1832, 최대 위치 오차 약 4487 m. 안정성과 기준해 비교 모두 실패 |
| m₁ = 2 kg, m₂ = 3 kg, u₁ = 4 m/s, u₂ = −1 m/s, 간격 1.125 m, e = 0.25 | 0.225 s에 두 물체가 만남. 직후 속도 0.25·1.5 m/s, 총운동량 5 kg·m/s, 손실 14.0625 J |
| 물 1000 kg/m³, g = 10 m/s² | 수면 100000 Pa에서 2 m 깊이의 압력 120000 Pa. 부피 0.002 m³의 완전 잠긴 1 kg 물체에는 아래로 10 N 지지력이 필요 |

감쇠 진동과 진자의 해석해는 시험에서 별도의 적응형 DOP853 적분과 대조한다. 음·양 초기 진자 각도, 무감쇠·부족·임계·과감쇠, 정지 평형, 음의 속도와 회전 방향, 구간 끝의 충돌, 충돌이 없는 궤적, 고유값 경계 조건과 비유한 계산 실패 경로를 포함한다.

## 참고 자료

- 운동학, 마찰, 구심 가속도, 일과 에너지는 OpenStax의 이상화와 부호 규약을 따른다. [Free Fall](https://openstax.org/books/university-physics-volume-1/pages/3-5-free-fall), [Applications of Newton’s Laws](https://openstax.org/books/university-physics-volume-1/pages/6-key-equations), [Work and Kinetic Energy](https://openstax.org/books/university-physics-volume-1/pages/7-key-equations)
- 충돌 전후의 계에 운동량 보존을 적용하고, 반발 계수로 상대 속도를 결정한다. [Conservation of Linear Momentum](https://openstax.org/books/university-physics-volume-1/pages/9-3-conservation-of-linear-momentum), [Linear Momentum and Collisions](https://openstax.org/books/university-physics-volume-1/pages/9-summary)
- 진자의 비선형 운동방정식과 감쇠 용수철의 방정식은 교과서 모델을 따른다. 유한 진폭 기준은 k = sin(θ₀/2), u = K(k²) − t√(g/L), θ = 2 arcsin(k sn(u | k²))로 계산한다. SciPy의 타원함수 인자는 k²다. [Pendulums](https://openstax.org/books/university-physics-volume-1/pages/15-4-pendulums), [Damped Oscillations](https://openstax.org/books/university-physics-volume-1/pages/15-5-damped-oscillations), [SciPy ellipj](https://docs.scipy.org/doc/scipy/reference/generated/scipy.special.ellipj.html)
- 정수압·부력·유량은 정지 유체 또는 정상 비압축성 유동의 보존식으로 계산한다. [Fluid Mechanics equations](https://openstax.org/books/university-physics-volume-1/pages/14-key-equations), [Fluid Mechanics summary](https://openstax.org/books/university-physics-volume-1/pages/14-summary)
