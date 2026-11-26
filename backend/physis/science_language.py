"""Vocabulary for the approved classroom field models."""
import re


MODELS = {
    "wave_transverse":r"횡파|사인\s*파|정현파|transverse|sine\s*wave",
    "wave_longitudinal":r"종파|압축파|소밀파|압축\s*(?:무늬|영역)|(?:용수철|코일).{0,30}(?:조밀|빽빽|압축된\s*부분)|longitudinal|compression\s*wave",
    "wave_superposition":r"(?:파동|파형|파)의?\s*중첩|(?:파동|파형).{0,16}(?:겹치|겹쳐|포개|합성)|보강\s*간섭|상쇄\s*간섭|superposition|waves?.{0,12}(?:overlap|interfere)",
    "wave_standing":r"정상파|정지파|standing\s*wave",
    "ideal_gas":r"이상\s*기체|보일의?\s*법칙|샤를의?\s*법칙|ideal\s*gas",
    "heat_equilibrium":r"열\s*평형|평형\s*온도|thermal\s*equilibrium|equilibrium\s*temperature|heat\s*exchange",
    "cooling":r"냉각|식는\s*(?:속도|과정)|cooling",
    "heat_diffusion":r"열\s*확산|heat\s*diffusion",
    "bernoulli":r"베르누이|bernoulli",
    "fluid_tracer":r"추적\s*(?:입자|자)|유체\s*입자|tracer",
}
ALIASES = {
    "amplitude":["진폭"], "frequency":["주파수","진동수"], "wavelength":["파장"], "phase":["위상차"],
    "moles":["몰수"], "temperature":["온도"], "initial_temp":["초기 온도","처음 온도"], "ambient":["주변 온도"],
    "rate":["냉각 상수"],"temp_a":["A 온도","첫 번째 물체의 온도"],"temp_b":["B 온도","두 번째 물체의 온도"],
    "capacity_a":["A 열용량","첫 번째 열용량"],"capacity_b":["B 열용량","두 번째 열용량"],
    "speed":["유속"],"inlet_pressure":["입구 압력"],
}
SCALES = {"K":{"K":1,"켈빈":1}, "mol":{"mol":1,"몰":1}, "Hz":{"Hz":1,"헤르츠":1},
          "J/K":{"J/K":1}, "W/K":{"W/K":1}, "1/s":{"1/s":1}, "m2/s":{"m2/s":1,"cm2/s":.0001}}
FACTS = {"wave_speed":("구성 진행파의 전파 속력","m/s"),"wave_period":("파동 주기","s"),
         "equilibrium_temp":("평형 온도","K"),"final_temp":("관측 물체의 마지막 온도","K"),
         "diffusion_time":("중심 온도차가 1/e로 줄어드는 시간","s"),"outlet_pressure":("출구 절대압","Pa")}
CONCEPTS = {
    "wave_transverse":"파형은 옆으로 진행하고 매질의 한 점은 위아래로 진동합니다. 같은 위상의 두 이웃점 사이 거리가 파장입니다.",
    "wave_longitudinal":"매질 입자는 파동이 진행하는 축을 따라 앞뒤로 진동합니다. 가까이 모인 구간과 벌어진 구간이 이동합니다.",
    "wave_superposition":"같은 위치와 시각의 두 변위를 부호까지 더합니다. 두 파동이 같은 위상이면 변위가 커지고 반대 위상이면 상쇄됩니다.",
    "wave_standing":"크기가 같은 두 파동이 반대 방향으로 진행할 때 항상 변위가 0인 마디가 생깁니다. 이웃 마디 사이는 반 파장입니다.",
    "ideal_gas":"같은 양의 이상기체에서 부피를 고정하면 절대온도에 비례해 압력이 커집니다. 절대온도를 고정하면 압력과 부피의 곱이 일정합니다.",
    "heat_equilibrium":"열은 더 뜨거운 물체에서 더 차가운 물체로 이동합니다. 외부와 단열된 두 물체의 열용량이 다르면 같은 양의 열에도 온도 변화가 다릅니다.",
    "cooling":"물체와 주변의 온도차가 클수록 온도가 빠르게 변합니다. 일정한 시간이 지날 때마다 남은 온도차의 같은 비율이 줄어듭니다.",
    "heat_diffusion":"뜨거운 중심에서 차가운 양 끝으로 열이 흐릅니다. 초기 온도차가 단일 사인 모양이면 모양을 유지하며 높이가 줄어듭니다.",
    "bernoulli":"높이가 같고 마찰 손실이 없는 정상 흐름에서 유속이 커지면 동압이 커지고 정압이 낮아집니다.",
    "fluid_tracer":"흐름에 실린 작은 표지의 이동 거리는 일정한 유속과 경과 시간을 곱해 구합니다. 이는 균일 흐름의 입자 모식도입니다.",
}


def resolve_field_terms(models, text):
    # Broad words such as 'flow rate' and the 'Newton' in Newton cooling qualify
    # a specific named model. Leave genuinely distinct physics comparisons ambiguous.
    if "cooling" in models and re.search(r"뉴[턴튼]의?\s*냉각|newton.{0,5}cooling",text,re.I):
        models = [m for m in models if m != "newton"]
    if ("bernoulli" in models or "fluid_tracer" in models) and "continuity" in models:
        models = [m for m in models if m != "continuity"]
    if "wave_transverse" in models and any(m in models for m in ("wave_longitudinal","wave_standing","wave_superposition")):
        models = [m for m in models if m != "wave_transverse"]
    if "spring" in models and "wave_longitudinal" in models and not re.search(r"용수철\s*상수|질량.{0,5}용수철|spring constant", text,re.I):
        # A pulse on a spring uses the coils as the medium, not a single attached oscillator.
        models = [m for m in models if m != "spring"]
    return models
