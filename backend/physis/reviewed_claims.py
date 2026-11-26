"""Short editorial paraphrases; each is released only with its reviewed source sentence."""
# A changed paragraph has to contain the reviewed evidence fragment to activate a link.
# The user still sees the verbatim English sentence and its precise origin.
REVIEWED = {
 "college-m42073:import-auto-id1355832": ("directly proportional to and in the same direction", "알짜힘이 커지면 가속도가 커지고, 같은 알짜힘에서는 질량이 클수록 가속도가 작습니다."),
 "university1-m58297:fs-id1165038999240": ("inversely proportional to its mass", "가속도는 알짜 외력과 같은 방향이며 계의 질량에 반비례합니다."),
 "college-m42102:import-auto-id2006874": ("same constant acceleration", "공기 저항과 마찰을 무시하면 같은 장소에서 물체들은 같은 중력 가속도로 떨어집니다."),
 "college-m42243:import-auto-id2672250": ("For angles less than about", "작은 진폭에서는 진자의 복원력을 변위에 비례하는 힘으로 근사할 수 있습니다."),
 "university1-m58364:fs-id1167131485483": ("For small displacements", "단진자의 작은 진동은 단순 조화 운동으로 근사할 수 있습니다."),
 "college-m42139:import-auto-id1165298838484": ("opposes relative motion", "마찰은 서로 접촉하는 표면 사이의 상대 운동을 방해합니다."),
 "college-m42156:import-auto-id1120695": ("mass multiplied by its velocity", "운동량은 질량과 속도의 곱입니다."),
 "college-m42084:import-auto-id2422195": ("toward the center of rotation", "등속 원운동의 가속도는 원의 중심을 향합니다."),
 "college-m42196:import-auto-id3179465": ("weight of the fluid it displaces", "부력의 크기는 물체가 밀어낸 유체의 무게와 같습니다."),
 "college-m42096:import-auto-id3538220": ("displacement (change in position) divided by", "평균 속도는 변위를 걸린 시간으로 나눈 값입니다."),
 "university1-m58283:fs-id1168326802131": ("the derivative of x with respect to t", "순간 속도는 위치를 시간에 대해 미분한 값입니다."),
 "college-m42100:import-auto-id3526102": ("both magnitude and direction", "속도는 크기와 방향을 가지므로 속력이 같아도 방향이 바뀌면 속도가 변합니다."),
 "college-m42080:import-auto-id1165298462418": ("force of drag on an object", "유체 속에서 움직이는 물체에는 항력이 작용할 수 있습니다."),
 "college-m42187:import-auto-id3217118": ("mass per unit volume", "밀도는 단위 부피당 질량입니다."),
 "university1-m58357:fs-id1170959782778": ("volume flow rate", "체적 유량은 일정한 위치를 단위 시간에 통과하는 유체 부피입니다."),
 "university1-m58373:fs-id1165037186222": ("These positions are called nodes", "정상파에서 변위가 항상 0인 위치를 마디라고 합니다."),
 "university2-m58391:fs-id1172100572336": ("pressure is proportional to the temperature", "부피와 분자 수가 일정한 이상기체에서는 압력이 절대온도에 비례합니다."),
 "university2-m58387:fs-id1170903831782": ("the sum of the heats equals zero", "외부와 열 교환이 없는 열량 측정에서는 얻은 열과 잃은 열의 대수적 합이 0입니다."),
 "university1-m58272:fs-id1168328194195": ("dimensionally consistent", "물리량을 연결하는 방정식에는 양변의 차원이 일치해야 한다는 조건이 있습니다."),
}

# Small, explicitly reviewed assertion frames used by the local alignment judge.
# They describe source-supported propositions, not user questions or prompt templates.
ASSERTION_FRAMES = {
    "free_fall_mass_independence": {
        "source_ids": ("college-m42102:import-auto-id2006874",),
        "source_fragment": "same constant acceleration",
        "concepts": ("fall", "acceleration", "mass"),
        "needs_condition": ("air resistance or friction negligible", "same location"),
    },
    "newton_second_law": {
        "source_ids": ("college-m42073:import-auto-id1355832", "university1-m58297:fs-id1165038999240"),
        "source_fragment": "directly proportional to and in the same direction",
        "concepts": ("acceleration", "net external force", "mass"),
    },
    "pendulum_small_angle": {
        "source_ids": ("college-m42243:import-auto-id2672250",),
        "source_fragment": "For angles less than about",
        "concepts": ("pendulum", "angle", "restoring force", "displacement"),
        "needs_condition": ("angle less than about 15 degrees",),
    },
    "velocity_vector": {
        "source_ids": ("college-m42100:import-auto-id3526102",),
        "source_fragment": "both magnitude and direction",
        "concepts": ("velocity", "magnitude", "direction"),
    },
    "momentum_definition": {
        "source_ids": ("college-m42156:import-auto-id1120695",),
        "source_fragment": "mass multiplied by its velocity",
        "concepts": ("momentum", "mass", "velocity", "product"),
    },
    "density_definition": {
        "source_ids": ("college-m42187:import-auto-id3217118",),
        "source_fragment": "mass per unit volume",
        "concepts": ("density", "mass", "volume", "ratio"),
    },
    "average_velocity_definition": {
        "source_ids": ("college-m42096:import-auto-id3538220",),
        "source_fragment": "displacement (change in position) divided by",
        "concepts": ("average velocity", "displacement", "time", "ratio"),
    },
}


# Level variants are editorial explanations grounded only in the cited reviewed rows.
# The research version states the source's limits instead of extrapolating beyond them.
EDUCATION_CARDS = {
    "free_fall_mass_independence": {
        "source_ids": ("college-m42102:import-auto-id2006874",),
        "conditions": [
            "공기 저항과 마찰을 무시할 수 있어야 합니다.",
            "같은 장소에서 비교해야 합니다.",
        ],
        "misconception": "무거운 물체는 언제나 더 빨리 떨어진다는 생각은 이 조건에서는 맞지 않습니다.",
        "levels": {
            "intro": "공기 저항과 마찰이 거의 없고 같은 장소라면, 무거운 물체와 가벼운 물체의 낙하 가속도는 같아요.",
            "school": "같은 장소에서 공기 저항과 마찰을 무시하면, 질량이 달라도 낙하 가속도는 같습니다. 질량은 이 조건에서 가속도를 바꾸지 않습니다.",
            "university": "자유 낙하에서 공기 저항과 마찰이 무시 가능하고 위치가 같으면, 중력에 의한 가속도는 질량과 무관하게 같습니다.",
            "research": "검토된 문장은 고정된 위치와 무시 가능한 공기 저항·마찰 아래에서 질량 독립적인 낙하 가속도를 뒷받침합니다. 다른 위치나 실제 항력이 큰 조건까지 일반화하지 않습니다.",
        },
    },
    "newton_second_law": {
        "source_ids": ("college-m42073:import-auto-id1355832", "university1-m58297:fs-id1165038999240"),
        "conditions": ["가속도와 힘은 같은 계에 작용하는 알짜 외력을 기준으로 비교합니다."],
        "misconception": "같은 알짜 외력이라면 질량이 클수록 가속도는 작아집니다.",
        "levels": {
            "intro": "물체를 더 세게 미는 알짜힘은 가속도를 키워요. 같은 힘으로 밀면 더 무거운 물체의 가속도는 더 작아요.",
            "school": "계의 알짜 외력이 커지면 가속도도 커집니다. 알짜 외력이 같을 때에는 질량이 큰 계의 가속도가 작습니다.",
            "university": "뉴턴의 제2법칙에서 가속도는 계에 작용하는 알짜 외력에 정비례하고 계의 질량에 반비례하며, 방향은 알짜 외력과 같습니다.",
            "research": "검토된 자료가 직접 지지하는 관계는 계의 가속도와 알짜 외력의 방향 일치, 힘에 대한 정비례, 질량에 대한 반비례입니다. 자료에 없는 계 경계나 추가 힘은 여기서 추정하지 않습니다.",
        },
    },
    "pendulum_small_angle": {
        "source_ids": ("college-m42243:import-auto-id2672250",),
        "conditions": ["인용된 근사는 각도가 약 15°보다 작은 범위에 관한 것입니다."],
        "misconception": "큰 각도에서도 작은 각도 근사가 그대로 맞는다고 가정할 수 없습니다.",
        "levels": {
            "intro": "진자가 조금만 흔들릴 때에는 되돌리는 힘이 이동한 거리와 비례한다고 볼 수 있어요.",
            "school": "각도가 약 15°보다 작으면 복원력이 변위에 비례하고, 진자를 단순 조화 진동자로 다룰 수 있습니다.",
            "university": "인용된 작은 각도 범위에서 복원력은 변위에 정비례하므로 단진자는 단순 조화 진동자로 근사됩니다.",
            "research": "자료가 제시하는 선형 복원력 관계는 약 15° 미만 조건에 한정됩니다. 이 문장만으로 더 큰 진폭의 오차나 주기 변화를 정량화하지 않습니다.",
        },
    },
}

