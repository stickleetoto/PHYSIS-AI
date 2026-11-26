# PHYSIS AI v0.3 자료 출처와 라이선스

2026년 11월 25일 실제로 수집한 49개 자료를 기록합니다. OpenStax 교재의 독립된 절 46개에서 영어 원문 116문단을 발췌했고, NASA Glenn 교육 페이지 2건과 NASA Technical Reports Server 문헌 1건의 서지 정보를 수록했습니다. 문서별 원본 SHA-256 전체값과 UTC 다운로드 일시, 책·절·문단 위치, 저자, 권리 범위는 기계 판독 목록에서 확인할 수 있습니다. [전체 수집 기록](backend/physis/corpus/units.json)

## OpenStax 저작자 표시

교재의 권리자와 발행기관은 Rice University의 OpenStax입니다. 아래 저자는 각 책의 Senior Contributing Authors이며 원저의 기여자 표시는 책의 머리말에 있습니다.

| 책과 무료 원저 | 주요 저자 | 원문 버전 | 발췌 단원 |
| --- | --- | --- | ---: |
| [College Physics 2e](https://openstax.org/details/books/college-physics-2e) | Paul Peter Urone, Roger Hinrichs 및 기여자 | [84147e8의 라이선스](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/LICENSE) · [같은 버전의 책 메타데이터](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/collections/college-physics-2e.collection.xml) | 29 |
| [University Physics Volume 1](https://openstax.org/details/books/university-physics-volume-1) | Samuel J. Ling, Jeff Sanny, William Moebs 및 기여자 | [9364cbc의 라이선스](https://github.com/openstax/osbooks-university-physics-bundle/blob/9364cbc32511afea3d4695e70a88687ffc1a3696/LICENSE) · [같은 버전의 책 메타데이터](https://github.com/openstax/osbooks-university-physics-bundle/blob/9364cbc32511afea3d4695e70a88687ffc1a3696/collections/university-physics-volume-1.collection.xml) | 13 |
| [University Physics Volume 2](https://openstax.org/details/books/university-physics-volume-2) | Samuel J. Ling, Jeff Sanny, William Moebs 및 기여자 | [9364cbc의 라이선스](https://github.com/openstax/osbooks-university-physics-bundle/blob/9364cbc32511afea3d4695e70a88687ffc1a3696/LICENSE) · [같은 버전의 책 메타데이터](https://github.com/openstax/osbooks-university-physics-bundle/blob/9364cbc32511afea3d4695e70a88687ffc1a3696/collections/university-physics-volume-2.collection.xml) | 4 |

위 버전의 발췌문에는 **Creative Commons Attribution 4.0 International**이 적용됩니다. PHYSIS는 본문 중 선택한 문단 또는 연속 문장을 발췌하고 공백을 정규화했으며 단순 인라인 수학 기호를 텍스트로 옮겼습니다. 검색용 주제·실험 태그와 한국어 인터페이스, 원문 위치 식별자는 PHYSIS에서 덧붙였습니다. 원저의 사진, 그림, 표, 외부 인용물과 별도 저작자로 표시된 자료는 배포 대상에서 제외했습니다. 라이선스 판정은 위 커밋의 교재에 한정합니다. OpenStax 저장소의 2026년 라이선스 변경 커밋을 구분해 기록합니다. [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) · [내장 라이선스 전문](backend/physis/corpus/CC-BY-4.0.txt) · [College Physics 변경 이력](https://github.com/openstax/osbooks-college-physics-bundle/commit/5182c46ee4854d84e3e35ea34e5ed0bef461b19b) · [University Physics 변경 이력](https://github.com/openstax/osbooks-university-physics-bundle/commit/b375d3f61093460d280a21dddee51e7b6c9ce3b2)

## NASA 공개 자료

NASA Glenn은 교육 페이지 제목과 기관명, 원본 링크, 다운로드 관찰 기록을 수록합니다. NTRS는 공식 서지 API에서 공개 상태, 제목, 저자, NASA의 권리 판정과 레코드 식별자를 수집했습니다. NASA가 게시한 기사·초록·PDF·그림·로고의 본문 재배포 권한은 이 목록에 포함하지 않았으며, 세 항목 모두 `citable=false`이고 튜터의 인용 문단을 제공하지 않습니다. [NASA 이용 지침](https://www.nasa.gov/nasa-brand-center/images-and-media/) · [NASA STI 권리 설명](https://sti.nasa.gov/disclaimers/)

| 자료 | 저자 또는 기관 | 수록 범위 |
| --- | --- | --- |
| [Drag Equation](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/drag-equation/) | NASA Glenn Research Center | 공개 교육 페이지 서지 정보 |
| [Bernoulli's Equation](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/bernoullis-equation/) | NASA Glenn Research Center | 공개 교육 페이지 서지 정보 |
| [Demonstrating Reduced Gravity](https://ntrs.nasa.gov/citations/19970022278) | Howard Pearlman, Dennis Stocker, Daniel Gotti, David Urban, Howard Ross, Thomas Sours | 공개 NTRS ID 19970022278. API 원문 권리 필드 `GOV_PUBLIC_USE_PERMITTED`. [API 레코드](https://ntrs.nasa.gov/api/citations/19970022278) |

## 교재 단원별 원문

아래 링크는 실제로 가져온 버전의 원문 파일을 엽니다. 색인 문단마다 개별 XML 줄 링크가 있습니다. 단원별 원문 해시는 앞 12자리만 여기에 표시합니다.

| 자료 ID | 절 제목과 고정 원문 | 인용 문단 | 원본 SHA-256 앞 12자리 |
| --- | --- | ---: | --- |
| college-m42033 | [Displacement](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42033/index.cnxml) | 3 | ddd54739348b |
| college-m42073 | [Newton’s Second Law of Motion: Concept of a System](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42073/index.cnxml) | 3 | 46a1deb43bb9 |
| college-m42074 | [Newton’s Third Law of Motion: Symmetry in Forces](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42074/index.cnxml) | 2 | 6990d10c2b02 |
| college-m42080 | [Drag Forces](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42080/index.cnxml) | 3 | 90c97ca56876 |
| college-m42084 | [Centripetal Acceleration](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42084/index.cnxml) | 3 | 4da4f6f86b8d |
| college-m42091 | [Physical Quantities and Units](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42091/index.cnxml) | 3 | ade42742d650 |
| college-m42096 | [Time, Velocity, and Speed](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42096/index.cnxml) | 3 | 6365f3fb5cb1 |
| college-m42100 | [Acceleration](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42100/index.cnxml) | 3 | c45772b21866 |
| college-m42102 | [Falling Objects](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42102/index.cnxml) | 2 | 278a64aede35 |
| college-m42130 | [Newton’s First Law of Motion: Inertia](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42130/index.cnxml) | 2 | a6aceec6f144 |
| college-m42139 | [Friction](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42139/index.cnxml) | 3 | 97c1e37a96a2 |
| college-m42147 | [Kinetic Energy and the Work-Energy Theorem](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42147/index.cnxml) | 2 | a0ca84112083 |
| college-m42156 | [Linear Momentum and Force](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42156/index.cnxml) | 3 | 97561f64552a |
| college-m42163 | [Elastic Collisions in One Dimension](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42163/index.cnxml) | 3 | 39bcb54462ba |
| college-m42187 | [Density](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42187/index.cnxml) | 1 | 561a01526f1e |
| college-m42189 | [Pressure](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42189/index.cnxml) | 2 | c83a3fc29333 |
| college-m42192 | [Variation of Pressure with Depth in a Fluid](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42192/index.cnxml) | 1 | ad4ae72ca439 |
| college-m42196 | [Archimedes’ Principle](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42196/index.cnxml) | 3 | 397234f99e16 |
| college-m42205 | [Flow Rate and Its Relation to Velocity](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42205/index.cnxml) | 3 | 558d05abd8fa |
| college-m42206 | [Bernoulli’s Equation](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42206/index.cnxml) | 3 | 1b806d205c70 |
| college-m42216 | [The Ideal Gas Law](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42216/index.cnxml) | 2 | 2e83a21ce12e |
| college-m42224 | [Temperature Change and Heat Capacity](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42224/index.cnxml) | 2 | e7871c3da954 |
| college-m42228 | [Conduction](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42228/index.cnxml) | 2 | 2a275d750213 |
| college-m42229 | [Convection](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42229/index.cnxml) | 2 | 8d5d1f356fe4 |
| college-m42242 | [Simple Harmonic Motion: A Special Periodic Motion](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42242/index.cnxml) | 1 | f44afd50cf9b |
| college-m42243 | [The Simple Pendulum](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42243/index.cnxml) | 2 | fa57ce300885 |
| college-m42246 | [Damped Harmonic Motion](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42246/index.cnxml) | 2 | 626e4ffd11d2 |
| college-m42248 | [Waves](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42248/index.cnxml) | 2 | 7cf7a5644add |
| college-m42249 | [Superposition and Interference](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/modules/m42249/index.cnxml) | 2 | 7b79b97fb37a |
| university1-m58271 | [Unit Conversion](https://github.com/openstax/osbooks-university-physics-bundle/blob/9364cbc32511afea3d4695e70a88687ffc1a3696/modules/m58271/index.cnxml) | 2 | d29f5478b77c |
| university1-m58272 | [Dimensional Analysis](https://github.com/openstax/osbooks-university-physics-bundle/blob/9364cbc32511afea3d4695e70a88687ffc1a3696/modules/m58272/index.cnxml) | 3 | ea6c3b0bc194 |
| university1-m58277 | [Scalars and Vectors](https://github.com/openstax/osbooks-university-physics-bundle/blob/9364cbc32511afea3d4695e70a88687ffc1a3696/modules/m58277/index.cnxml) | 2 | 868e6e9215a7 |
| university1-m58283 | [Instantaneous Velocity and Speed](https://github.com/openstax/osbooks-university-physics-bundle/blob/9364cbc32511afea3d4695e70a88687ffc1a3696/modules/m58283/index.cnxml) | 3 | 287120cefa97 |
| university1-m58297 | [Newton's Second Law](https://github.com/openstax/osbooks-university-physics-bundle/blob/9364cbc32511afea3d4695e70a88687ffc1a3696/modules/m58297/index.cnxml) | 2 | 160923e4fc97 |
| university1-m58356 | [Archimedes’ Principle and Buoyancy](https://github.com/openstax/osbooks-university-physics-bundle/blob/9364cbc32511afea3d4695e70a88687ffc1a3696/modules/m58356/index.cnxml) | 3 | 35df80952529 |
| university1-m58357 | [Fluid Dynamics](https://github.com/openstax/osbooks-university-physics-bundle/blob/9364cbc32511afea3d4695e70a88687ffc1a3696/modules/m58357/index.cnxml) | 3 | a19ff393c97d |
| university1-m58361 | [Simple Harmonic Motion](https://github.com/openstax/osbooks-university-physics-bundle/blob/9364cbc32511afea3d4695e70a88687ffc1a3696/modules/m58361/index.cnxml) | 3 | f8965ac29606 |
| university1-m58364 | [Pendulums](https://github.com/openstax/osbooks-university-physics-bundle/blob/9364cbc32511afea3d4695e70a88687ffc1a3696/modules/m58364/index.cnxml) | 3 | d22ffbf3fbb6 |
| university1-m58365 | [Damped Oscillations](https://github.com/openstax/osbooks-university-physics-bundle/blob/9364cbc32511afea3d4695e70a88687ffc1a3696/modules/m58365/index.cnxml) | 3 | 0104565c7eaf |
| university1-m58368 | [Traveling Waves](https://github.com/openstax/osbooks-university-physics-bundle/blob/9364cbc32511afea3d4695e70a88687ffc1a3696/modules/m58368/index.cnxml) | 3 | 588ef45f8682 |
| university1-m58372 | [Interference of Waves](https://github.com/openstax/osbooks-university-physics-bundle/blob/9364cbc32511afea3d4695e70a88687ffc1a3696/modules/m58372/index.cnxml) | 2 | 6476deffbc1f |
| university1-m58373 | [Standing Waves and Resonance](https://github.com/openstax/osbooks-university-physics-bundle/blob/9364cbc32511afea3d4695e70a88687ffc1a3696/modules/m58373/index.cnxml) | 3 | 840ddb3862c4 |
| university2-m58384 | [Temperature and Thermal Equilibrium](https://github.com/openstax/osbooks-university-physics-bundle/blob/9364cbc32511afea3d4695e70a88687ffc1a3696/modules/m58384/index.cnxml) | 3 | bfb32c2aa5a5 |
| university2-m58387 | [Heat Transfer, Specific Heat, and Calorimetry](https://github.com/openstax/osbooks-university-physics-bundle/blob/9364cbc32511afea3d4695e70a88687ffc1a3696/modules/m58387/index.cnxml) | 4 | 272849307e08 |
| university2-m58389 | [Mechanisms of Heat Transfer](https://github.com/openstax/osbooks-university-physics-bundle/blob/9364cbc32511afea3d4695e70a88687ffc1a3696/modules/m58389/index.cnxml) | 3 | 9faf25a6b397 |
| university2-m58391 | [Molecular Model of an Ideal Gas](https://github.com/openstax/osbooks-university-physics-bundle/blob/9364cbc32511afea3d4695e70a88687ffc1a3696/modules/m58391/index.cnxml) | 3 | 741429f840b4 |

