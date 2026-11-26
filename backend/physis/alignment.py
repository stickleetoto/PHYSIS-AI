"""Conservative claim-to-source alignment for reviewed local evidence."""
import re
import unicodedata

from .reviewed_claims import ASSERTION_FRAMES, REVIEWED


STATES = ("direct", "partial", "related", "contradiction", "insufficient", "undecidable")
_SENTENCE = re.compile(r"(?<=[.!?。！？])\s+|\n+")


def _normalize(value):
    # Preserve SI prefix case and exponents in verbatim claims (mW/MW and 4²/42).
    value = unicodedata.normalize("NFC", str(value or ""))
    value = value.replace("’", "'").replace("−", "-").replace("–", "-")
    value = " ".join(value.split())
    # Remove only terminal sentence punctuation. Internal signs, fractions,
    # inequalities, decimals, and units are part of the claim's meaning.
    return re.sub(r"[.!?。！？]+$", "", value).strip()


def split_claims(text):
    """Split user-facing prose into sentence-sized claims without splitting decimals."""
    if not isinstance(text, str):
        return []
    chunks = []
    for part in _SENTENCE.split(text):
        part = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", part).strip()
        if part:
            chunks.append(part)
    return chunks


def _has(text, *patterns):
    return any(re.search(pattern, text, re.I) for pattern in patterns)


_NEGATOR = re.compile(r"\b(?:not|never|no|cannot|can't|doesn't|don't|isn't|aren't|didn't)\b|않|아니|못|없|안\s*(?:되|하|함|되는|할)", re.I)


def _negated_match(text, match):
    phrase = text[match.start():min(len(text), match.end() + 12)]
    if _NEGATOR.search(phrase):
        return True
    before = text[max(0, match.start() - 18):match.start()]
    return bool(re.search(r"\b(?:not|never|cannot|can't|doesn't|don't|isn't|aren't|didn't)\s+(?:(?:the|a|an|be|to)\s+)?$|(?:않|아니|못|없|안)\s*$", before, re.I))


def _has_positive(text, *patterns):
    return any(not _negated_match(text, match)
               for pattern in patterns for match in re.finditer(pattern, text, re.I))


def _has_negated(text, *patterns):
    return any(_negated_match(text, match)
               for pattern in patterns for match in re.finditer(pattern, text, re.I))


_FALL = (r"\bfall(?:s|ing|en)?\b", r"\bdrop(?:s|ped|ping)?\b", r"free[ -]?fall", r"낙하", r"떨어")
_ACCELERATION = (r"accelerat(?:e|es|ed|ing|ion|ions)", r"speed(?:s|ed|ing)?\s+up", r"\brate\b", r"속도\s*(?:변화|가\s*변|가속)", r"가속")
_MASS = (r"\bmass(?:es)?\b", r"\bweigh(?:t|s|ed|ing)?\b", r"\bheavier\b", r"\blighter\b", r"\bmore\s+massive\b", r"\bkilograms?\b", r"\bkg\b", r"질량", r"무거운", r"가벼운")
_EQUAL = (r"same", r"equal", r"identical", r"equally", r"independent\s+of", r"regardless\s+of", r"does\s+not\s+depend\s+on\s+(?:its\s+)?mass", r"같(?:은|다)", r"동일", r"무관", r"차이\s*없", r"질량.{0,10}(?:영향을\s*주지|의존하지|바꾸지|변하지\s*않)")
_NOT_FASTER = (r"not\s+(?:accelerate|fall|speed\s+up)\s+faster", r"does\s+not\s+(?:accelerate|fall|speed\s+up)\s+faster", r"더\s*빠르지\s*않")
_UNEQUAL = (r"different\s+acceleration", r"depends?\s+on\s+(?:its\s+)?mass", r"varies\s+with\s+(?:its\s+)?mass", r"mass\s+affects?\s+acceleration", r"다르", r"같지\s*않", r"질량에\s*따라")
_FASTER = (r"faster", r"greater\s+acceleration", r"larger\s+acceleration", r"accelerat\w*\s+more", r"proportional\s+to\s+(?:its\s+)?mass", r"increases?\s+with\s+(?:its\s+)?mass", r"더\s*빠르", r"가속도.{0,12}(?:크|높)", r"질량.{0,12}(?:비례|커질수록.*가속도.{0,8}커)")
_NO_DRAG = (r"air\s+resistance.{0,25}(?:negligible|ignored|absent|zero)", r"(?:negligible|ignored|absent|zero).{0,25}air\s+resistance", r"(?:drag|friction).{0,20}(?:negligible|ignored|absent|zero)", r"(?:negligible|ignored|absent|zero).{0,20}(?:drag|friction)", r"without\s+(?:air\s+resistance|drag|friction)", r"ignore\w*\s+(?:air\s+resistance|drag|friction)", r"vacuum", r"공기\s*저항.{0,12}(?:무시|없|작)", r"(?:무시|없|작).{0,12}공기\s*저항", r"마찰.{0,12}(?:무시|없|작)", r"진공")
_DRAG_PRESENT = (r"air\s+resistance.{0,20}(?:included|present|acts|matters|significant)", r"with\s+(?:air\s+resistance|drag)\s+(?:present|included|acting|included|is\s+significant)", r"drag\s+is\s+(?:included|present)", r"공기\s*저항.{0,12}(?:포함|작용|있을)", r"항력.{0,12}(?:포함|작용|있을)", r"마찰.{0,12}(?:포함|작용|있을)")
_NEGATED_CONDITION = (r"not\s+without\s+(?:air\s+resistance|drag|friction)", r"air\s+resistance.{0,18}not\s+negligible", r"not\s+negligible.{0,18}air\s+resistance", r"(?:drag|friction).{0,15}not\s+negligible", r"not\s+ignored.{0,18}(?:air\s+resistance|drag|friction)", r"공기\s*저항.{0,12}(?:무시하지|없지\s*않|작지\s*않)", r"(?:무시하지|없지\s*않|작지\s*않).{0,12}공기\s*저항", r"마찰.{0,12}(?:무시하지|없지\s*않)")
_SAME_PLACE = (r"same\s+(?:place|location|point)", r"given\s+location", r"같은\s*(?:장소|위치)", r"동일한\s*(?:장소|위치)")
_DIFFERENT_PLACE = (r"different\s+(?:places|locations)", r"across\s+(?:different\s+)?locations", r"다른\s*(?:장소|위치)(?:에서|의)", r"서로\s*다른\s*위치")


def _free_fall(claim, passage):
    source_id = passage["id"]
    if source_id not in ASSERTION_FRAMES["free_fall_mass_independence"]["source_ids"]:
        return None
    if not _has(claim, *_FALL):
        return None
    if not _has(claim, *_ACCELERATION):
        if _has(claim, *_MASS) and _has(claim, *_FASTER):
            return "undecidable", "인용문은 가속도를 설명하지만, 이 주장은 속도나 도착 시각을 묻고 초기 조건을 제시하지 않습니다."
        return None
    quote = passage["quote"]
    evidence_equal = _has(quote, r"same\s+constant\s+acceleration", r"independent\s+of\s+(?:their\s+)?mass", r"질량.{0,12}무관")
    evidence_faster = _has(quote, r"acceleration.{0,35}(?:greater|faster|larger)", r"(?:heavier|more\s+massive).{0,35}(?:faster|greater\s+acceleration)", r"질량.{0,20}가속도.{0,15}(?:크|빠르)")
    if evidence_equal and evidence_faster:
        return "undecidable", "인용문 안에서 질량과 가속도의 관계가 서로 충돌합니다."
    if not evidence_equal and not evidence_faster:
        return "undecidable", "인용문은 낙하를 다루지만 질량과 가속도의 관계를 확인할 수 없습니다."
    if _has(claim, *_DRAG_PRESENT) or _has(claim, *_NEGATED_CONDITION) or _has(claim, *_DIFFERENT_PLACE):
        return "undecidable", "근거는 항력이 무시 가능하고 위치가 일정한 조건에 한정되지만, 주장은 그 범위를 바꿉니다."
    if not _has(claim, *_MASS):
        return "undecidable", "근거는 질량에 따른 가속도를 비교하지만, 이 주장은 그 비교 대상을 밝히지 않습니다."
    relation_text = re.sub(r"\b(?:does\s+not|doesn't)\s+depend\s+on\s+(?:(?:its|the)\s+)?mass\b",
                           "independent of mass", claim, flags=re.I)
    says_equal = _has_positive(relation_text, *_EQUAL) or _has(claim, *_NOT_FASTER)
    # Keep the word "faster" inside a reviewed negative comparative out of
    # the positive matcher, while still counting a separate affirmative clause.
    faster_search_text = claim
    for pattern in _NOT_FASTER:
        for match in re.finditer(pattern, claim, re.I):
            faster_search_text = faster_search_text[:match.start()] + (" " * (match.end() - match.start())) + faster_search_text[match.end():]
    says_faster = _has_positive(faster_search_text, *_FASTER)
    says_unequal = _has_positive(relation_text, *_UNEQUAL) or _has_negated(relation_text, *_EQUAL)
    if sum((says_equal, says_faster, says_unequal)) > 1:
        return "undecidable", "주장에 가속도가 같다는 관계와 다르다는 관계가 함께 있습니다."
    scoped = _has(claim, *_NO_DRAG) and not _has(claim, *_NEGATED_CONDITION) and not _has(claim, *_DIFFERENT_PLACE)
    if (says_faster or says_unequal) and evidence_equal:
        if scoped:
            return "contradiction", "인용문은 명시된 조건에서 가속도가 질량과 무관하다고 하지만, 주장은 반대 관계를 말합니다."
        return "undecidable", "반대 질량 관계를 주장하지만 근거의 조건과 맞는지 확인할 수 없습니다."
    if says_equal and evidence_faster:
        if scoped:
            return "contradiction", "인용문은 질량이 클수록 가속도가 크다고 하지만, 주장은 반대 관계를 말합니다."
        return "undecidable", "주장이 인용된 질량 관계와 다르지만 근거의 조건이 맞지 않습니다."
    if says_equal and evidence_equal:
        if scoped:
            return "partial", "질량과 무관한 가속도 관계가 명시된 조건에서 뒷받침됩니다."
        return "partial", "이 관계는 항력을 무시하고 같은 위치에서 비교할 때에만 근거가 있습니다."
    if (says_faster or says_unequal) and evidence_faster:
        return "partial", "이 질량과 가속도의 관계는 인용문에 있습니다."
    return "undecidable", "근거는 가속도와 질량의 관계를 다루지만, 주장의 관계가 분명하지 않습니다."


def _newton(claim, source_id):
    if source_id not in ASSERTION_FRAMES["newton_second_law"]["source_ids"]:
        return None
    if not _has(claim, *_ACCELERATION) or not _has(claim, r"\bforce\b", r"\bforces\b", r"net\s+(?:external\s+)?force", r"알짜힘", r"외력"):
        return None
    positive_force_patterns = (r"directly\s+proportional", r"more\s+(?:net\s+)?force.{0,35}(?:greater|larger|more|higher)\s+acceleration", r"force.{0,25}acceleration.{0,20}(?:increases|increased)", r"힘.{0,16}가속도.{0,16}(?:비례|커|증가)")
    opposite_force_patterns = (r"inversely\s+proportional\s+to\s+(?:the\s+)?(?:net\s+)?force", r"more\s+(?:net\s+)?force.{0,35}(?:smaller|lower|less)\s+acceleration", r"힘.{0,16}커.{0,16}가속도.{0,16}(?:작|감소)")
    positive_mass_patterns = (r"inversely\s+proportional\s+to\s+(?:its\s+)?mass", r"(?:greater|larger|more)\s+mass.{0,35}(?:smaller|lower|less)\s+acceleration", r"same\s+(?:net\s+)?force.{0,35}(?:greater|larger|more)\s+mass.{0,35}(?:smaller|lower|less)\s+acceleration", r"질량.{0,16}(?:클|크).{0,20}가속도.{0,16}(?:작|감소)")
    opposite_mass_patterns = (r"directly\s+proportional\s+to\s+(?:its\s+)?mass", r"(?:greater|larger|more)\s+mass.{0,35}(?:greater|larger|more|higher)\s+acceleration", r"질량.{0,16}(?:클|크).{0,20}가속도.{0,16}(?:크|증가)")
    same_direction_patterns = (r"same\s+direction", r"in\s+the\s+direction\s+of", r"같은\s*방향")
    opposite_direction_patterns = (r"opposite\s+direction", r"against\s+the\s+direction", r"반대\s*방향")
    positive_force = _has_positive(claim, *positive_force_patterns) or _has_negated(claim, *opposite_force_patterns)
    opposite_force = _has_positive(claim, *opposite_force_patterns) or _has_negated(claim, *positive_force_patterns)
    positive_mass = _has_positive(claim, *positive_mass_patterns) or _has_negated(claim, *opposite_mass_patterns)
    opposite_mass = _has_positive(claim, *opposite_mass_patterns) or _has_negated(claim, *positive_mass_patterns)
    same_direction = _has_positive(claim, *same_direction_patterns) or _has_negated(claim, *opposite_direction_patterns)
    opposite_direction = _has_positive(claim, *opposite_direction_patterns) or _has_negated(claim, *same_direction_patterns)
    if (positive_force and opposite_force) or (positive_mass and opposite_mass) or (same_direction and opposite_direction):
        return "undecidable", "주장에 서로 양립할 수 없는 관계가 함께 있습니다."
    if opposite_force or opposite_mass or opposite_direction:
        return "contradiction", "근거는 가속도와 알짜 외력 또는 질량 사이에 이 주장과 반대되는 관계를 제시합니다."
    if positive_force or positive_mass or same_direction:
        return "partial", "계의 가속도와 알짜 외력에 관한 이 관계는 검토된 문단에 있습니다."
    return "undecidable", "근거는 관련 있지만 힘과 가속도 사이의 주장을 판단하기 어렵습니다."


def _pendulum(claim, source_id):
    if source_id not in ASSERTION_FRAMES["pendulum_small_angle"]["source_ids"]:
        return None
    if not _has(claim, r"pendulum", r"진자"):
        return None
    relation_patterns = (r"restoring\s+force.{0,35}proportional.{0,20}displacement", r"force.{0,25}directly\s+proportional.{0,20}displacement", r"simple\s+harmonic", r"복원력.{0,20}변위.{0,12}비례", r"단순\s*조화")
    inverse_patterns = (r"restoring\s+force.{0,35}inversely\s+proportional", r"force.{0,20}proportional\s+to\s+the\s+square", r"복원력.{0,20}(?:반비례|제곱에)")
    relation = _has_positive(claim, *relation_patterns)
    inverse = _has_positive(claim, *inverse_patterns) or _has_negated(claim, *relation_patterns)
    small_angle = _has(claim, r"(?:less|smaller)\s+than\s+(?:about\s+)?15\s*(?:degrees|°)", r"small\s+(?:angle|angles)", r"under\s+15\s*(?:degrees|°)", r"15\s*도.{0,12}(?:미만|보다\s*작)", r"작은\s*각")
    large_angle = _has(claim, r"(?:greater|larger)\s+than\s+15\s*(?:degrees|°)", r"large\s+(?:angle|angles)", r"15\s*도.{0,12}(?:이상|보다\s*크)", r"큰\s*각")
    if inverse:
        return "contradiction", "근거는 작은 각도에서 정비례 관계를 제시하며 반비례 관계를 말하지 않습니다."
    if relation and large_angle:
        return "undecidable", "인용된 관계는 작은 각도에 한정되어 제시된 큰 각도에 적용되는지 알 수 없습니다."
    if relation:
        return "partial", "복원력 관계는 인용된 작은 각도 범위에서 뒷받침됩니다."
    if small_angle:
        return "undecidable", "근거는 작은 각도 조건을 제시하지만 이 주장은 뒷받침되는 복원력 관계를 밝히지 않습니다."
    return None


def _reviewed_definition(claim, source_id):
    if source_id == "college-m42100:import-auto-id3526102":
        if not _has(claim, r"\bvelocity\b", r"속도"):
            return None
        magnitude = _has(claim, r"magnitude", r"size", r"크기")
        direction = _has(claim, r"direction", r"방향")
        scalar_patterns = (r"\bscalar\b", r"only\s+(?:a\s+)?magnitude", r"방향.{0,12}(?:필요|상관없|무시)", r"스칼라")
        scalar = _has_positive(claim, *scalar_patterns)
        if scalar:
            return "contradiction", "검토된 문장은 속도에 크기와 방향이 모두 있다고 설명합니다."
        if magnitude and direction:
            return "partial", "속도의 크기와 방향을 함께 가진다는 설명은 검토된 문장에 있습니다."
        if magnitude or direction:
            return "partial", "주장은 속도의 한 특성만 말하므로, 인용문이 설명한 크기와 방향을 모두 포함하지 않습니다."
        return "undecidable", "속도와 관련된 주장이지만 크기와 방향의 관계가 분명하지 않습니다."
    if source_id == "college-m42156:import-auto-id1120695":
        if not (_has(claim, r"momentum", r"운동량") and _has(claim, *_MASS) and _has(claim, r"\bvelocity\b", r"속도")):
            return None
        sum_patterns = (r"\badd(?:ed|s|ing)?\b", r"\bsum\b", r"\bplus\b", r"더한", r"합")
        if _has_positive(claim, *sum_patterns):
            return "contradiction", "검토된 문장은 운동량을 질량과 속도의 곱으로 정의합니다."
        product_patterns = (r"multipli\w*", r"product", r"times", r"\bmass\s*(?:×|\*|x)\s*(?:its\s+)?velocity", r"질량.{0,12}(?:곱|곱한)")
        if _has_positive(claim, *product_patterns):
            return "partial", "운동량이 질량과 속도의 곱이라는 관계는 검토된 문장에 있습니다."
        return "undecidable", "질량과 속도는 언급되지만 두 양과 운동량의 관계가 분명하지 않습니다."
    if source_id == "college-m42187:import-auto-id3217118":
        if not (_has(claim, r"density", r"밀도") and _has(claim, *_MASS) and _has(claim, r"\bvolume\b", r"부피", r"체적")):
            return None
        if _has_positive(claim, r"multipli\w*", r"product", r"\bmass\s*(?:×|\*|x)\s*(?:the\s+)?volume", r"질량.{0,12}(?:곱|곱한).{0,12}부피"):
            return "contradiction", "검토된 문장은 밀도를 부피당 질량으로 설명하며 질량과 부피의 곱이라고 하지 않습니다."
        if _has_positive(claim, r"per\s+(?:unit\s+)?volume", r"divid\w*\s+by\s+(?:the\s+)?volume", r"mass\s*[/÷]\s*volume", r"부피당\s*질량", r"부피로\s*나눈"):
            return "partial", "밀도가 부피당 질량이라는 관계는 검토된 문장에 있습니다."
        return "undecidable", "질량과 부피는 언급되지만 밀도와의 관계가 분명하지 않습니다."
    if source_id == "college-m42096:import-auto-id3538220":
        if not (_has(claim, r"average\s+velocity", r"평균\s*속도") and _has(claim, r"\btime\b", r"시간", r"elapsed")):
            return None
        if _has_positive(claim, r"\bdistance\b", r"이동\s*거리") and not _has(claim, r"displacement", r"변위"):
            return "contradiction", "인용된 정의는 평균 속도에 변위를 사용하며 이동 거리와 구분합니다."
        if _has(claim, r"displacement", r"변위") and _has_positive(claim, r"divid\w*", r"per\s+unit", r"/", r"나눈", r"당"):
            return "partial", "평균 속도가 변위를 걸린 시간으로 나눈 값이라는 관계는 검토된 문장에 있습니다."
        return "undecidable", "시간은 언급되지만 평균 속도와 변위의 관계가 분명하지 않습니다."
    return None


def _related(claim, passages):
    """Find topical overlap for a related-only label; overlap never verifies support."""
    vocab = {
        "fall": _FALL, "acceleration": _ACCELERATION, "mass": _MASS,
        "force": (r"\bforce\b", r"net\s+force", r"힘", r"외력"),
        "pendulum": (r"pendulum", r"진자"), "angle": (r"angle", r"각도", r"각"),
        "displacement": (r"displacement", r"변위"), "restoring force": (r"restoring\s+force", r"복원력"),
    }
    relevant = []
    for passage in passages:
        quote = passage.get("quote", "")
        concepts = []
        for name, patterns in vocab.items():
            if _has(quote, *patterns) and _has(claim, *patterns):
                concepts.append(name)
        if len(concepts) >= 1:
            relevant.append((passage.get("id", ""), concepts))
    return relevant


def align_claim(claim, passages):
    """Return a six-state relation judgment for one claim and verified passages only."""
    claim = str(claim or "").strip()
    if not claim:
        return {"state": "undecidable", "reason": "There is no claim text to assess.", "references": []}
    rows = [p for p in passages if p.get("id") and p.get("quote") and p.get("status") == "source_verified"]
    if not rows:
        return {"state": "insufficient", "reason": "이 주장을 판단할 검증된 인용문이 없습니다.", "references": []}
    normalized = _normalize(claim)
    judgments = []
    for passage in rows:
        source_id = passage["id"]
        source_sentences = split_claims(passage["quote"])
        if normalized and any(normalized == _normalize(sentence) for sentence in source_sentences):
            judgments.append({"state": "direct", "reason": "주장 전체가 검증된 인용문의 한 문장과 일치합니다.", "references": [source_id]})
        entry = REVIEWED.get(source_id)
        if entry and normalized == _normalize(entry[1]) and any(
            entry[0] in sentence and not re.search(r"\b(?:not|never|false|incorrect)\b|아니|틀리|아닙", sentence, re.I)
            for sentence in source_sentences
        ):
            judgments.append({"state": "partial", "reason": "편집자가 검토한 풀이이며 원문 문장에 연결됩니다.", "references": [source_id]})
        for judge in (_free_fall, _newton, _pendulum, _reviewed_definition):
            result = judge(claim, passage) if judge is _free_fall else judge(claim, source_id)
            if result:
                state, reason = result
                judgments.append({"state": state, "reason": reason, "references": [source_id]})
    positive = [j for j in judgments if j["state"] in {"direct", "partial"}]
    negative = [j for j in judgments if j["state"] == "contradiction"]
    unclear = [j for j in judgments if j["state"] == "undecidable"]
    if positive and negative:
        refs = list(dict.fromkeys(r for j in judgments for r in j["references"]))
        return {"state": "undecidable", "reason": "검증된 문단 사이에서 이 주장에 관한 관계가 서로 충돌합니다.", "references": refs}
    if negative:
        return negative[0]
    direct = [j for j in positive if j["state"] == "direct"]
    if direct:
        return {"state": "direct", "reason": direct[0]["reason"],
                "references": list(dict.fromkeys(r for j in direct for r in j["references"]))}
    if positive:
        refs = list(dict.fromkeys(r for j in positive for r in j["references"]))
        return {"state": "partial", "reason": positive[0]["reason"], "references": refs}
    if unclear:
        refs = list(dict.fromkeys(r for j in unclear for r in j["references"]))
        return {"state": "undecidable", "reason": unclear[0]["reason"], "references": refs}

    related = _related(claim, rows)
    if related:
        return {"state": "related", "reason": "인용문에 관련 용어가 있지만 이 관계를 뒷받침하지는 않습니다.",
                "references": list(dict.fromkeys(key for key, _ in related))}
    return {"state": "insufficient", "reason": "검증된 인용문은 이 주장을 다루지 않습니다.", "references": []}

