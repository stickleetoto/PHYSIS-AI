"""Authored formula cards for the original validated mechanics and fluid models."""
from .physics import SPECS

BOOK = "https://openstax.org/books/university-physics-volume-1/pages/"
SYMBOLS = {
    "mass":"m","mass_a":"m_A","mass_b":"m_B","height":"h","g":"g","x0":"x_0","v0":"v_0",
    "a":"a","force":"F","mu":r"\mu_k","v_a":"u_A","v_b":"u_B","gap":"d_0","restitution":"e",
    "k":"k","length":"L","angle":r"\theta_0","damping":"b","radius":"R","omega":r"\omega",
    "density":r"\rho","depth":"h","p0":"p_0","volume":"V","area_in":"A_1","area_out":"A_2","speed_in":"v_1",
}


def card(key, latex, steps, dimensions, quantity, related, section, outputs):
    return dict(title=SPECS[key].title, latex=latex, steps=steps, dimensions=dimensions, quantity=quantity,
                related=related, symbols={v.key:SYMBOLS[v.key] for v in SPECS[key].variables},
                source=BOOK+section, outputs=outputs)


FORMULAS = {key:card(key,*content) for key,content in {
    "free_fall":(r"y(t)=h-\tfrac12gt^2,\qquad t_{\rm hit}=\sqrt{2h/g}",
        ["위를 양의 방향으로 정하면 두 물체 모두 mÿ = −mg를 만족합니다. 질량을 약분하면 ÿ = −g입니다.",
         "처음에 정지한 물체의 속도는 vᵧ = −gt입니다. 한 번 더 적분하고 처음 높이 h를 대입합니다.",
         "바닥에서 y = 0을 대입하고 양의 시간 해를 선택합니다."],
        "gt²의 단위는 (m/s²)·s² = m이고 √(h/g)의 단위는 s입니다.","y","acceleration","3-5-free-fall","y 높이 [m] · t 경과 시간 [s] · t_hit 도달 시간 [s]"),
    "uniform":(r"x(t)=x_0+v_0t",
        ["알짜힘이 0이므로 가속도는 0이고 속도는 처음 값 v₀로 유지됩니다.","dx/dt = v₀를 0에서 t까지 적분하면 위치 변화는 v₀t입니다."],
        "v₀t의 단위는 (m/s)·s = m이며 x₀와 더할 수 있습니다.","x","acceleration","3-1-position-displacement-and-average-velocity","x 위치 [m] · t 경과 시간 [s]"),
    "acceleration":(r"v=v_0+at,\qquad x=x_0+v_0t+\tfrac12at^2",
        ["일정한 가속도 dv/dt = a를 적분해 v = v₀ + at를 얻습니다.","속도를 시간에 대해 다시 적분하고 x(0) = x₀를 대입합니다."],
        "속도식의 각 항은 m/s, 위치식의 세 항은 모두 m입니다.","x","newton","3-4-motion-with-constant-acceleration","x 위치 [m] · v 속도 [m/s] · t 경과 시간 [s]"),
    "newton":(r"a=\frac{F}{m},\qquad \Delta K=F(x-x_0)",
        ["일정한 질량에서 운동량의 변화율 F = d(mv)/dt는 ma입니다.","양변에 dx를 곱하고 a dx = v dv를 사용합니다.","적분하면 Δ(mv²/2) = FΔx입니다."],
        "F/m의 단위는 m/s²이며 FΔx의 단위는 N·m = J입니다.","ax","acceleration","7-3-work-energy-theorem","a 가속도 [m/s²] · x 위치 [m] · ΔK 운동 에너지 변화 [J]"),
    "friction":(r"a=-\mathrm{sgn}(v)\mu_k g,\qquad d_{\rm stop}=\frac{v_0^2}{2\mu_k g}",
        ["수평면의 수직항력은 mg이고 운동 마찰력의 크기는 μₖmg입니다.","가속도는 움직이는 방향과 반대입니다. 마찰이 한 일의 크기 μₖmgd가 처음 운동 에너지 mv₀²/2와 같아질 때 멈춥니다.",
         "나눗셈은 μₖ > 0일 때 적용합니다. μₖ = 0이고 처음 움직이면 계속 등속 운동을 합니다."],
        "μₖ는 무차원이고 v₀²/g의 단위는 (m²/s²)/(m/s²) = m입니다.","vx","uniform","6-2-friction","a 가속도 [m/s²] · v 속도 [m/s] · d_stop 정지 거리 [m]"),
    "collision":(r"m_Au_A+m_Bu_B=m_Av_A+m_Bv_B,\quad v_B-v_A=e(u_A-u_B)",
        ["외부 수평 충격량이 0이므로 충돌 직전과 직후의 총운동량이 같습니다.","A가 뒤에서 접근하면 가까워지는 상대 속력은 u_A − u_B입니다. 반발 계수 e를 곱하면 벌어지는 상대 속력입니다.",
         "두 식을 함께 풀면 v_A = [m_Au_A + m_Bu_B − m_Be(u_A−u_B)]/(m_A+m_B)이고 v_B = v_A + e(u_A−u_B)입니다."],
        "운동량 합은 양쪽 모두 kg·m/s입니다. e는 두 상대 속력의 비로 무차원입니다.","momentum","newton","9-3-conservation-of-linear-momentum","v_A, v_B 충돌 직후 속도 [m/s] · d₀ 처음 두 물체 사이 거리 [m]"),
    "spring":(r"m\ddot{x}=-kx,\qquad T=2\pi\sqrt{m/k}",
        ["평형 위치로부터 변위 x에 비례하는 복원력 −kx를 뉴턴 법칙에 대입합니다.","x = A cos(ωt+φ)를 대입하면 ω² = k/m입니다. 한 주기 동안 위상은 2π만큼 변합니다."],
        "k의 단위는 N/m = kg/s²이므로 √(m/k)는 s입니다.","x","damped","15-1-simple-harmonic-motion","x 변위 [m] · T 주기 [s] · ω 각진동수 [rad/s]"),
    "damped":(r"m\ddot{x}+b\dot{x}+kx=0,\qquad \frac{dE}{dt}=-b\dot{x}^2",
        ["복원력 −kx와 점성 감쇠력 −bv를 합하면 mẍ = −kx − bv입니다.","양변에 v를 곱합니다. mvẍ + kxv는 운동·탄성 에너지 합의 시간 변화율입니다.",
         "따라서 b > 0이면 운동 중 역학적 에너지가 감소합니다. 잃은 에너지는 ∫bv²dt입니다."],
        "mẍ, bv, kx의 단위는 N이며 bv²의 단위는 J/s입니다.","energy","spring","15-5-damped-oscillations","x 변위 [m] · ẋ 속도 [m/s] · E 역학적 에너지 [J] · t 시간 [s]"),
    "pendulum":(r"\ddot\theta=-\frac{g}{L}\sin\theta,\quad T\simeq 2\pi\sqrt{L/g}\ \ (|\theta_0|\ll1)",
        ["접선 방향 힘 −mg sinθ를 접선 가속도 Lθ̈와 연결하면 각운동 방정식을 얻습니다.","작은 각도(라디안)에서만 sinθ ≈ θ를 대입할 수 있습니다. 이때 각진동수는 √(g/L)입니다.",
         "실험은 원래 비선형 방정식을 사용합니다. 정지 출발의 유한 진폭 주기는 4√(L/g) K(sin²(θ₀/2))이며 K의 인자는 매개변수 m입니다."],
        "각은 무차원으로 취급하며 g/L은 s⁻², √(L/g)는 s입니다.","angle","spring","15-4-pendulums","θ 순간 각도 [rad] · T 주기 [s] · K 완전 타원적분 [1]"),
    "circular":(r"\vec a=-\omega^2\vec r,\qquad |\vec v|=|\omega|R",
        ["반지름 R인 원 위의 좌표를 x = R cos(ωt), y = R sin(ωt)로 씁니다.","한 번 미분하면 접선 속도, 두 번 미분하면 중심으로 향하는 −ω²r⃗가 됩니다."],
        "각속도는 rad/s입니다. ω²R은 m/s²이며 |ω|R은 m/s입니다.","ax","newton","6-3-centripetal-force","r⃗ 위치 벡터 [m] · v⃗ 속도 [m/s] · a⃗ 가속도 [m/s²]"),
    "hydrostatic":(r"p=p_0+\rho gh",
        ["단면적 A, 깊이 h인 유체 기둥의 무게는 ρAhg입니다.","정지 평형에서 바닥과 수면의 압력차가 만드는 위쪽 힘 (p−p₀)A는 이 무게와 같습니다.","단면적을 약분하면 게이지압은 ρgh입니다."],
        "ρgh의 단위는 (kg/m³)(m/s²)m = kg/(m·s²) = Pa입니다.","pressure","buoyancy","14-1-fluids-density-and-pressure","p 절대압 [Pa] · p−p₀ 게이지압 [Pa]"),
    "buoyancy":(r"F_B=\rho gV,\qquad F_{\rm support}=mg-F_B",
        ["물체와 같은 공간을 차지하는 유체의 질량은 ρV입니다.","정지 유체가 받은 압력의 합력은 그 유체의 무게와 평형을 이루므로 대체한 물체의 부력은 위쪽으로 ρgV입니다.",
         "위를 양수로 두고 지지력 + 부력 − 무게 = 0을 풉니다. 음의 지지력은 아래쪽입니다."],
        "ρV는 kg, ρgV와 mg는 모두 kg·m/s² = N입니다.","buoyancy","hydrostatic","14-4-archimedes-principle-and-buoyancy","F_B 부력 [N] · F_support 지지력 [N]"),
    "continuity":(r"Q=A_1v_1=A_2v_2,\qquad v_2=\frac{A_1v_1}{A_2}",
        ["시간 Δt 동안 단면을 통과하는 부피는 A v Δt입니다.","정상 비압축성 흐름에서는 같은 시간에 들어오고 나가는 부피가 같습니다.","Δt를 약분해 유량 Q를 얻습니다. 같은 유량에서는 단면적과 평균 유속이 반비례합니다."],
        "Av의 단위는 m²·m/s = m³/s입니다.","speed","hydrostatic","14-5-fluid-dynamics","Q 체적 유량 [m³/s] · v₂ 출구 유속 [m/s]"),
}.items()}
