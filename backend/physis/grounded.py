"""Prepare trusted local evidence, then independently check the lesson and provider selections."""
import re

from . import evidence
from .alignment import align_claim, split_claims
from .education import LEVELS, education_for
from .formula_registry import check_applicability
from .knowledge_terms import VOCABULARY, concepts
from .reviewed_claims import REVIEWED


FOUNDATIONS = {
    "vectors": (r"벡터|스칼라|vectors?|scalars?", "vectors scalars magnitude direction",
                "벡터는 크기와 방향을 함께 나타냅니다. 변위를 예로 들어 방향을 바꿀 때 어떤 값이 달라지는지 살펴보세요."),
    "units": (r"단위|차원|unit conversion|dimensions?", "units conversion dimensional analysis",
                   "먼저 물리량의 단위를 적고, 변환 인자의 분자와 분모에서 같은 단위가 소거되는지 확인해 보세요."),
    "calculus": (r"미분|적분|도함수|기울기|derivative|integral", "instantaneous velocity slope derivative",
                 "위치–시간 그래프의 기울기는 속도를 나타냅니다. 짧은 구간에서 위치 변화량을 시간 간격으로 나누는 것부터 시작하세요."),
    "graphs": (r"함수|그래프|equation|function|방정식", "position graphs functions equations",
                  "가로축에 입력을, 세로축에 결과를 놓고 입력 하나를 바꿨을 때 그래프가 어떻게 달라지는지 확인해 보세요."),
}
PUBLICATION = re.compile(r"인용|문헌|논문|서지|보고서|출처|cite|citation|bibliograph|reference|\bquotes?\b|\bsource\b|paper", re.I)
FICTION = re.compile(r"존재하지|실재하지|가상[의 ]|허구|허위|날조|지어내|없는\s*(?:논문|문헌)|fictitious|fabricat|nonexistent|made.up", re.I)
DRAG = re.compile(r"공기\s*저항|항력|air\s*resistance|\bdrag\b", re.I)
FOUNDATION_HELP = re.compile(r"모르|어려|헷갈|이해가?\s*(?:잘\s*)?안|기초|선행|처음|뭐[예야]|무엇|뜻|어떻게\s*(?:해|하는)|don.t understand|prerequisite|basics", re.I)
FOUNDATION_QUESTION = re.compile(
    r"왜|원리|설명|알려|뜻|무엇|뭐|어떻게|what\s+is|why|how|explain|meaning|definition|teach|help",
    re.I,
)
CITED_TITLE = re.compile(r"""《([^》]{2,180})》|〈([^〉]{2,180})〉|「([^」]{2,180})」|『([^』]{2,180})』|“([^”]{2,180})”|"([^"]{2,180})"|‘(.{2,180}?)’(?!\w)|(?<!\w)'(.{2,180}?)'(?!\w)""")
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z“])")
CAUSE_REQUEST = re.compile(
    r"왜|이유|원리|원인|메커니즘|관계|방향|수직|나란히|why|because|cause|mechanis|principle|"
    r"relationship|orientation|direction|perpendicular|parallel",
    re.I,
)
CAUSE_MARKER = re.compile(
    r"because|due to|caus(?:e|es|ed|ing)|result(?:s|ed)? from|depend(?:s|ed)? on|"
    r"proportional|therefore|as a result|in the same direction|opposes|converted into|"
    r"perpendicular|parallel|at right angles|oscillat|direction of|"
    r"때문|원인|결과로|비례|반비례|따라서|방향으로 작용|전환되|작용하여|수직|나란히|진동",
    re.I,
)


def _normalized(value):
    return " ".join(value.casefold().replace("’","'").split())


PAGE_REF = re.compile(r"(?:\bpages?\b|\bp\.|페이지)\s*(\d+)|(\d+)\s*(?:쪽|페이지)")
PARA_REF = re.compile(r"(?:¶|\bparagraph\b|문단)\s*(\d+)|(\d+)\s*(?:번째|번|째)?\s*문단")
REQUEST_WORDS = re.compile(
    r"\b(?:cite|citation|quote|quotation|source|reference|excerpt|provide|show|find|give|me|please|the|a|an|"
    r"from|in|of|by|and|at|section|chapter|paragraph|book|author|titled|called|passage|text|location|for|this)\b|"
    r"인용(?:문|할|해\s*(?:주시겠어요|주실래요|주세요|줘요|줘|달라|달라고|봐)|하세요|해요|하기|해)?|"
    r"(?:찾아|알려|보여|제시해|확인해)\s*(?:주세요|줘요|줘)|"
    r"부탁(?:드립니다|합니다|해요|해)?|해\s*(?:주세요|줘요|줘)|"
    r"문헌|논문|교육\s*자료|자료|출처|원본|원문|본문|제목|저자|위치|해당|실제|문단|구절|에서도|에서|으로|의|을|를|에|절|장")


def _citation_matches(row, remaining):
    """Qualify an exact title against recorded fields only, including all requested locators."""
    rest = _normalized(remaining)
    for pattern, field in ((PAGE_REF, "page"), (PARA_REF, "paragraph")):
        refs = pattern.findall(rest)
        if any(row.get(field) != int(a or b) for a,b in refs):
            return False
        rest = pattern.sub(" ", rest)
    author_names = [_normalized(name) for name in row["author"].split(";")]
    for marker, allowed in ((r"\bby\b|\bauthor\b|저자", author_names),
                            (r"""\bsection\b|절(?=\s*["'“‘《〈「『])""", [_normalized(row["section"])]),
                            (r"""\bchapter\b|장(?=\s*["'“‘《〈「『])""", [_normalized(row["chapter"])])):
        for match in re.finditer(marker, rest):
            suffix = rest[match.end():].lstrip(" :-=\t‘’“”\"'《〈「『")
            if not any(v and re.match(re.escape(v) + r"(?![a-z0-9])", suffix) for v in allowed):
                return False
    fields = [row["section"], row["chapter"], row["book"], row["publisher"], row["paragraph_id"],
              *row["author"].split(";")]
    for value in sorted({_normalized(v) for v in fields if v.strip()}, key=len, reverse=True):
        rest = re.sub(r"(?<![a-z0-9])" + re.escape(value) + r"(?![a-z0-9])", " ", rest)
    # Unknown qualifiers (including DOI, edition, date or an unrecorded author)
    # leave lexical/numeric residue. Never use retrieval/download date as publication date.
    return not re.search(r"[\w]", REQUEST_WORDS.sub(" ", rest))


def _literature_rows(store, message):
    if FICTION.search(message):
        return []
    quoted = list(CITED_TITLE.finditer(message))
    if not quoted:
        return []
    matches = []
    for doc in store.documents():
        if not doc["citable"]:
            continue
        for match in quoted:
            title = next(v for v in match.groups() if v is not None)
            if _normalized(title) == _normalized(doc["title"]):
                prefix = re.sub(r"\bsection\s+(?:(?:titled|called)\s*)?$", "", message[:match.start()], flags=re.I)
                remaining = prefix + " " + message[match.end():]
                canonical = store.document(doc["id"])
                if canonical:
                    matches.extend(row for row in canonical["chunks"] if _citation_matches(row, remaining))
                break
    return matches[:8]


def specialty(message):
    if PUBLICATION.search(message) and (FICTION.search(message) or CITED_TITLE.search(message)
            or re.search(r"논문|문헌명|보고서|paper|ISBN|DOI|저자|페이지|\bp\.\s*\d", message, re.I)):
        return "literature"
    if FOUNDATION_HELP.search(message) or FOUNDATION_QUESTION.search(message):
        return next((k for k, (pat, _, _) in FOUNDATIONS.items() if re.search(pat, message, re.I)), None)
    return None


def quote_for(row, words=""):
    text = row["text"].strip()
    terms = {t for t in re.findall(r"[a-z]{3,}",words.lower())}
    sentences = SENTENCE.split(text)
    if not sentences:
        return ""
    reviewed = REVIEWED.get(row["id"])
    anchor = next((i for i,s in enumerate(sentences) if reviewed and reviewed[0] in s), None)
    if anchor is None:
        anchor = max(range(len(sentences)), key=lambda i: sum(t in sentences[i].lower() for t in terms))
    # Preserve the exact whitespace of the canonical paragraph. Definitions often use
    # a demonstrative or give their qualifying condition in the neighboring sentence.
    starts = [0, *(m.end() for m in SENTENCE.finditer(text))]
    left = right = anchor
    for candidate in (anchor - 1, anchor + 1):
        if 0 <= candidate < len(sentences):
            lo, hi = min(left, candidate), max(right, candidate)
            if starts[hi] + len(sentences[hi]) - starts[lo] <= 600:
                left, right = lo, hi
    return text[starts[left]:starts[right] + len(sentences[right])][:900]


def retrieved_for(store, message, model=None, special=None):
    if special == "literature":
        return _literature_rows(store, message)
    query = message
    if special in FOUNDATIONS:
        query = FOUNDATIONS[special][1]
    elif special == "drag":
        query = "drag force air resistance opposite relative motion"
    rows = store.search(query, model=model, limit=16)
    if not rows and model:
        rows = store.search(model, model=model, limit=16)
    if special == "drag":
        rows = [r for r in rows if re.search(r"\bdrag force|\bair resistance",r["text"],re.I)]
    elif special is None and CAUSE_REQUEST.search(message):
        # A why/how request needs a passage that states the relationship or mechanism,
        # not just a definition containing the same topic words. Search a compact
        # concept expansion, then rank only the already citable local corpus rows.
        matched = concepts(message)
        topic_terms = " ".join(VOCABULARY[key].split("|")[0] for key in matched)
        expanded = " ".join(part for part in (topic_terms, "physical mechanism cause because proportional relation") if part)
        expanded_rows = store.search(expanded, model=model, limit=16) if expanded else []
        candidates = {row["id"]: row for row in rows}
        candidates.update({row["id"]: row for row in expanded_rows})
        def score(row):
            tags = sum(matched.get(key, 0) for key in row.get("concepts", []))
            causal = len(CAUSE_MARKER.findall(" ".join((row.get("section", ""), row.get("text", "")))))
            reviewed = .35 if row["id"] in REVIEWED else 0
            rank_bonus = max(0, 17 - row.get("rank", 17)) * .025
            return tags * 1.5 + min(causal, 5) * .55 + reviewed + rank_bonus
        rows = sorted(candidates.values(), key=lambda row: (-score(row), row["id"]))[:8]
    else:
        rows = rows[:8]
    return [r for r in rows if r.get("citable")][:8]


def chosen_formula(message, exp):
    from .model_lesson import select_formula
    row = select_formula(message, exp)
    if not row:
        return None
    checked = check_applicability(row["formula_id"],exp)
    return {k: row[k] for k in ("formula_id","title","latex","model","conditions","variables","review_status")} | {
        "applicability":checked,
        "status":{"applicable":"source_verified","outside_conditions":"partial"}.get(checked["status"],"unverifiable")}


def make_context(store, rows, message, snapshot=None, *, question=None):
    sources = []
    for row in rows:
        quote = quote_for(row,message)
        result = evidence.check_quote(store, rows, {"id":row["id"], "doc_id":row["doc_id"],"locator":row["locator"],"quote":quote})
        if result["status"] == "source_verified":
            sources.append(result)
    query = question if question is not None else message
    return {"passages":sources,"formula":chosen_formula(message,snapshot.experiment) if snapshot else None,
            "calculations":evidence.readings(snapshot, question=query) if snapshot else [], "observations":[]}


def diverse_sources(sources, limit=3):
    by_doc = {}
    for row in sorted(sources,key=lambda s: s["id"] not in REVIEWED):
        by_doc.setdefault(row["doc_id"],row)
    return list(by_doc.values())[:limit]


def _number_text(value):
    if value.get("display_value") is not None:
        return value["display_value"]
    formatter = getattr(evidence, "format_value", None)
    return formatter(value["value"]) if formatter else format(value["value"], ".4g")


def _verified_readings(readings, snapshot, checks):
    if not snapshot:
        return [], list(readings)
    accepted, checked_rows, seen = [], [], set()
    for item in readings:
        try:
            candidate = evidence.NumberClaim(**{key: item[key] for key in
                ("key", "value", "unit", "experiment_id", "revision", "run_id")})
            result = evidence.check_number(candidate, snapshot)
        except (KeyError, TypeError, ValueError):
            checked_rows.append(item | {"status":"unverifiable", "reason":"실행 기록과 연결할 수 없는 수치입니다."})
            continue
        identity = (candidate.key, candidate.run_id)
        if identity in seen:
            continue
        seen.add(identity)
        checked = item | {"status":result["status"]}
        for key in ("reason", "expected", "expected_unit", "display_value", "expected_display"):
            if key in result:
                checked[key] = result[key]
        checked_rows.append(checked)
        if result["status"] == "calculation_verified":
            accepted.append(checked)
        else:
            checks.append(result)
    return accepted, checked_rows


def _verified_graph_observation(item, snapshot):
    """Recheck a typed graph readout against the current, verified engine run."""
    if not snapshot or snapshot.run.status != "VERIFIED" or item.get("status") != "calculation_verified":
        return False
    if (item.get("run_id") != evidence.run_id(snapshot)
            or item.get("experiment_id") != str(snapshot.experiment.id)
            or item.get("revision") != snapshot.revision):
        return False
    series_key = item.get("reference")
    if not isinstance(series_key, str) or "." not in series_key:
        return False
    object_index, _, quantity = series_key.partition(".")
    if (not object_index.isdigit() or int(object_index) >= len(snapshot.experiment.objects)
            or quantity not in snapshot.experiment.measurements):
        return False
    if item.get("unit") != snapshot.experiment.measurements[quantity]:
        return False
    samples = snapshot.run.series.get(series_key, [])
    previous = -1
    for sample in item.get("samples", []):
        index, when, value = sample.get("index"), sample.get("time"), sample.get("value")
        if type(index) is not int or not previous < index < len(samples) or index >= len(snapshot.run.times):
            return False
        if when != snapshot.run.times[index] or value != samples[index]:
            return False
        previous = index
    return bool(item.get("samples"))


def _model_education(question, snapshot, selected_level):
    if not snapshot or not question:
        return None
    from .model_lesson import explain_model
    levels = {}
    for name in LEVELS:
        lesson = explain_model(question, snapshot, name)
        if not lesson:
            return None
        levels[name] = {"core": lesson["text"], "conditions": lesson.get("limits", []),
                        "misconception": None, "follow_up": None,
                        "source_ids": lesson.get("references", []),
                        "provenance": lesson.get("provenance", "registered_model"),
                        "scope_model": lesson.get("scope_model", snapshot.experiment.model)}
    return {"status":"model_explanation", "selected_level":selected_level,
            "scope_model":snapshot.experiment.model, "provenance":"registered_model", "levels":levels}


def _related_features(store, rows, verified, snapshot=None):
    """Return only local features linked to a rechecked source or the active registered model."""
    from .formula_registry import formula_for
    from .physics import SPECS

    verified_ids = {source["id"] for source in verified}
    relevant = []
    for row in rows:
        if row.get("id") not in verified_ids:
            continue
        canonical = store.chunk(row["id"])
        if (canonical and canonical.get("doc_id") == row.get("doc_id")
                and canonical.get("text") == row.get("text")):
            relevant.append(canonical)
    documents = {}
    model_counts = {}
    model_sources = {}
    for row in relevant:
        doc_id = row.get("doc_id")
        if doc_id:
            item = documents.setdefault(doc_id, {"title":row.get("title", doc_id), "source_ids":[]})
            item["source_ids"].append(row["id"])
        for model in row.get("models", []):
            if model in SPECS:
                model_counts[model] = model_counts.get(model, 0) + 1
                model_sources.setdefault(model, []).append(row["id"])
    features = [
        {"kind":"reviewed_material", "id":doc_id, "title":item["title"],
         "source_ids":list(dict.fromkeys(item["source_ids"]))}
        for doc_id, item in sorted(documents.items())
    ]
    if snapshot and snapshot.experiment.model in SPECS:
        model_counts[snapshot.experiment.model] = max(1, model_counts.get(snapshot.experiment.model, 0))
        model_sources.setdefault(snapshot.experiment.model, [])
    for model in sorted(model_counts, key=lambda key: (-model_counts[key], key)):
        formula = formula_for(model)
        features.append({"kind":"registered_model", "id":model, "title":SPECS[model].title,
                         "formula_id":formula.get("formula_id") if formula else None,
                         "source_ids":list(dict.fromkeys(model_sources.get(model, [])))})
    return features


def _reading_answer_state(special, has_text, dossier, default_text, message):
    if special == "literature":
        return "ANSWERED" if has_text else "INSUFFICIENT_EVIDENCE"
    if special == "drag":
        requested_simulation = bool(re.search(
            r"계산|몇\s*(?:초|분|시간)|얼마|시뮬레이션|simulate|calculate|run\s+(?:a\s+)?simulation|fall\s*time",
            message, re.I))
        if requested_simulation:
            return "UNSUPPORTED_SIMULATION"
        return "ANSWERED" if has_text else "INSUFFICIENT_EVIDENCE"
    if special in FOUNDATIONS:
        return ("ANSWERED" if has_text and dossier["education"].get("status") == "available"
                else "INSUFFICIENT_EVIDENCE")
    if dossier["sources"] or dossier["education"].get("status") in {"available", "model_explanation"}:
        return "PARTIALLY_ANSWERED" if default_text else "ANSWERED"
    if default_text and any(check.get("status") in {"failed", "unverifiable", "conflict"}
                            for check in dossier["checks"]):
        return "VERIFICATION_FAILED"
    if default_text and re.search(r"시뮬레이션|simulate|calculate|계산", message, re.I):
        return "UNSUPPORTED_SIMULATION"
    return "INSUFFICIENT_EVIDENCE"


def _abstention(claims, verified, checks, question, snapshot, formula, education,
                *, registry_text=False, safe_text=False, supported_numbers=False, supported_observations=False,
                special=None):
    reasons = []
    for claim in claims:
        if claim.get("kind") == "explanation" and claim.get("withheld"):
            reasons.append(claim.get("withheld_reason") or claim.get("alignment", {}).get("reason") or
                           "일부 설명 문장을 근거에 연결하지 못해 보류했습니다.")
        if claim.get("kind") == "explanation" and claim.get("status") == "contradiction":
            reasons.append("인용 근거와 모순되는 주장은 답변에서 보류했습니다.")
    for check in checks:
        if check.get("status") in {"failed", "unverifiable", "conflict"}:
            reasons.append(check.get("reason") or "검증 실패 또는 자료 충돌로 해당 내용을 보류했습니다.")
    if re.search(r"공식|수식|유도|formula|equation|derive", question, re.I) and not formula and not registry_text:
        reasons.append("요청한 공식이나 유도 과정을 등록 자료에서 확인하지 못했습니다.")
    if re.search(r"조건|적용|성립|applicability|conditions?", question, re.I):
        if not formula:
            reasons.append("요청한 적용 조건에 연결된 등록 공식을 확인하지 못했습니다.")
        elif formula.get("applicability", {}).get("status") == "outside_conditions":
            reasons.append("현재 입력이 공식의 적용 조건을 벗어났습니다.")
        elif not formula.get("conditions") and not (snapshot and snapshot.experiment.assumptions):
            reasons.append("적용 조건을 제시할 등록 정보가 없습니다.")
    if snapshot and snapshot.run.status != "VERIFIED":
        reasons.append(f"실행 상태가 {snapshot.run.status}여서 일부 관측값을 확인할 수 없습니다.")
    if not verified and education.get("status") == "model_explanation":
        reasons.append("설명은 인용 문헌이 아니라 등록된 교실 모델에서 가져왔습니다.")
    supported = bool(verified or registry_text or safe_text or supported_numbers or supported_observations
                     or education.get("status") in {"available", "model_explanation"})
    if not verified and not snapshot and not registry_text and not safe_text and not supported_numbers \
            and not supported_observations and education.get("status") == "insufficient":
        reasons.append("내장 자료에서 이 요청을 뒷받침하는 근거를 확인하지 못했습니다.")
        supported = False
    if special == "literature" and not verified:
        reasons.append("요청한 제목·서지 조건·원문 위치를 함께 확인하지 못했습니다.")
        supported = False
    reasons = list(dict.fromkeys(reason for reason in reasons if reason))
    return {"status": "none" if not reasons else "partial" if supported else "full", "reasons": reasons}


_MODEL_CONCEPT_REQUEST = re.compile(
    r"왜|이유|원리|개념|설명|해석|어떻게|무거운|가벼운|먼저|더\s*빠르|가속도|보존|줄어들|커지|작아|같아|동일|상관|차이|관계|방향|수직|나란히|비례|반비례|"
    r"why|explain|principle|concept|interpret|how|relationship|orientation|direction|perpendicular|parallel|"
    r"heavier|faster|accelerat|conserv|proportional|decreas|increas",
    re.I,
)


def report(store, rows, context, text, *, snapshot=None, mode="explain", metrics=None, special=None,
           level="school", question=""):
    sources = context["passages"]
    checks = []
    if metrics and metrics.proposed_sources:
        chosen = []
        sent_ids = {p["id"] for p in metrics.research_context.get("passages", [])}
        for key in dict.fromkeys(metrics.proposed_sources):
            row = next((v for v in sources if v["id"] == key and key in sent_ids), None)
            if row is None:
                checks.append({"status":"failed","reason":"공급자가 이번 질문에서 검색되지 않은 문단을 지정했습니다."})
            else:
                chosen.append(row)
        sources = chosen
    sources = diverse_sources(sources)
    # Re-read immediately before delivery. A source may have been removed during inference.
    verified = []
    for candidate in sources:
        reread = evidence.check_quote(store,rows,candidate)
        if reread["status"] == "source_verified":
            verified.append(reread)
        else:
            checks.append(reread)
    formula, numbers = context["formula"], context["calculations"]
    if snapshot:
        if metrics:
            checks.extend(evidence.check_number(evidence.NumberClaim(**claim),snapshot) for claim in metrics.proposed_numbers)
    if mode in {"discovery","review"}:
        return {"core":text, "sources":[], "formula":None, "calculations":[], "assumptions":[],
                "claims":[], "checks":[], "uncertainty":["답을 예측하거나 제출하는 동안 근거 열람을 유보합니다."],
                "theory_status":"deferred","simulation_supported":bool(snapshot),"related_models":[],
                "related_features":[], "prerequisite":None,
                "education":education_for(level, []),
                "abstention":{"status":"full","reasons":["발견·복습 모드에서는 답을 유보합니다."]}}
    registry_notes, registry_derivations = [], []
    if snapshot and question:
        from .classroom_units import unit_note
        expected_unit_note = unit_note(question, snapshot.experiment.model)
        if expected_unit_note:
            registry_notes = [paragraph.strip() for paragraph in text.split("\n\n")
                              if paragraph.strip() == expected_unit_note]
        if mode == "equation":
            from .tutor import teach
            expected_equation = teach(question, "equation", snapshot.experiment, snapshot.run, level, "")["text"]
            if text == expected_equation:
                registry_derivations = [expected_equation]
    claims = [{"kind":"quotation","text":s["quote"],"status":"source_verified","references":[s["id"]]} for s in verified]
    for source in verified:
        entry = REVIEWED.get(source["id"])
        if entry and entry[0] in source["quote"]:
            claims.append({"kind":"reviewed_paraphrase","text":entry[1],"status":"partial","references":[source["id"]]})
    if formula and formula.get("title") and formula.get("formula_id"):
        claims.append({"kind":"formula","text":formula["title"],"status":formula["status"],"references":[formula["formula_id"]]})
    for note in registry_notes:
        claims.append({"kind":"registry_unit","text":note,"status":"registry_verified",
                       "references":[formula["formula_id"] if formula and formula.get("formula_id")
                                     else "classroom_units.dimension_table"]})
    for derivation in registry_derivations:
        claims.append({"kind":"registry_derivation", "text":derivation, "status":"registry_verified",
                       "references":[formula["formula_id"] if formula and formula.get("formula_id")
                                     else f"science_formulas.{snapshot.experiment.model}"]})
    verified_numbers, checked_numbers = _verified_readings(numbers, snapshot, checks)
    numbers = checked_numbers
    for item in verified_numbers:
        claims.append({"kind":"simulation_observation",
                       "text":f"{item['label']} {_number_text(item)} {item['unit']}",
                       "status":"calculation_verified", "references":[item["run_id"]]})
    verified_identities = {(item["key"], item["run_id"]) for item in verified_numbers}
    for item in numbers:
        if (item.get("key"), item.get("run_id")) not in verified_identities:
            claims.append({"kind":"numeric", "text":f"{item.get('label', item.get('key', '수치'))} {_number_text(item)} {item.get('unit', '')}",
                           "status":item.get("status", "unverifiable"),
                           "references":[item["run_id"]] if item.get("run_id") else []})
    verified_observations = []
    observation_ids = set()
    for item in context.get("observations", []):
        if _verified_graph_observation(item, snapshot):
            identity = (item["run_id"], item["reference"],
                        tuple(sample["index"] for sample in item["samples"]))
            if identity in observation_ids:
                continue
            observation_ids.add(identity)
            canonical = item | {"text":evidence.graph_observation_text(item, snapshot)}
            verified_observations.append(canonical)
            claims.append({"kind":"simulation_observation", "text":canonical["text"],
                           "status":"calculation_verified", "references":[item["run_id"]],
                           "samples":item["samples"], "label":item.get("label"), "unit":item.get("unit")})
        else:
            checks.append({"status":"failed", "reason":"실험 실행과 일치하지 않는 그래프 표본 기록을 보류했습니다."})
    uncertainty = []
    if not verified:
        uncertainty.append("요청을 뒷받침할 인용 가능한 문단을 확인하지 못했습니다.")
    # Verified extraction and adjacent reading are separate from a semantic entailment judgement.
    safe_paragraphs, withheld_numeric = [], []
    trusted_registry_text = set(registry_notes + registry_derivations)
    other_paragraphs = [paragraph.strip() for paragraph in text.split("\n\n")
                        if paragraph.strip() and paragraph.strip() not in trusted_registry_text]
    for paragraph in other_paragraphs:
      for p in split_claims(paragraph):
        alignment = align_claim(p, verified)
        paragraph_checks = evidence.check_reported_numbers(p,snapshot) if snapshot else []
        checks.extend(paragraph_checks)
        numeric_failures = [c for c in paragraph_checks if c["status"] in {"failed", "unverifiable"}]
        # A partial relation whose reason says its scope is narrower than the prose is not
        # safe to repeat as an unqualified answer. The educational card supplies that scope.
        scope_incomplete = alignment["state"] == "partial" and any(
            word in alignment["reason"] for word in ("때에만 근거", "범위에서 뒷받침", "조건에 한정")
        )
        withheld = alignment["state"] not in {"direct", "partial"} or bool(numeric_failures) or scope_incomplete
        claim = {"kind":"explanation", "text":p, "status":alignment["state"],
                 "references":alignment["references"], "alignment":alignment, "withheld":withheld}
        if numeric_failures:
            claim["numeric_status"] = [c["status"] for c in numeric_failures]
            claim["withheld_reason"] = "실행 결과와 수치가 일치하지 않거나 이 실행에서 검증할 수 없습니다."
            withheld_numeric.extend(numeric_failures)
        elif scope_incomplete:
            claim["withheld_reason"] = alignment["reason"]
        elif withheld:
            claim["withheld_reason"] = alignment["reason"]
        claims.append(claim)
        if not withheld:
            safe_paragraphs.append(p)
    model = snapshot.experiment.model if snapshot else None
    education = education_for(level, verified, claims=claims, question=question, model=model)
    unit_question = bool(re.search(r"단위|차원|units?\b|dimension", question, re.I))
    include_model = bool(snapshot and question and (
        snapshot.run.status == "LIMITED" or (_MODEL_CONCEPT_REQUEST.search(question) and not unit_question)
    ))
    contextual = _model_education(question, snapshot, level) if include_model else None
    if contextual and education["status"] == "available":
        for name in LEVELS:
            education["levels"][name]["model_explanation"] = contextual["levels"][name]["core"]
            education["levels"][name]["model_limits"] = contextual["levels"][name]["conditions"]
            education["levels"][name]["model_references"] = contextual["levels"][name]["source_ids"]
            education["levels"][name]["model_provenance"] = contextual["levels"][name]["provenance"]
            education["levels"][name]["model_scope"] = contextual["levels"][name]["scope_model"]
    elif contextual and education["status"] == "insufficient":
        education = contextual
    current_education = education["levels"].get(level, education["levels"]["school"])
    model_text = current_education.get("model_explanation")
    if education["status"] == "model_explanation":
        model_text = current_education["core"]
    if model_text:
        claims.append({"kind":"model_explanation", "text":model_text,
                       "status":"model_explanation", "references":current_education["model_references"]
                           if "model_references" in current_education else current_education["source_ids"],
                       "limits":current_education.get("model_limits", current_education["conditions"]),
                       "provenance":current_education.get("model_provenance", education.get("provenance", "registered_model")),
                       "scope_model":current_education.get("model_scope", education.get("scope_model", model))})
    selected = education["levels"].get(level, education["levels"]["school"])
    safe_core = [*registry_notes, *registry_derivations]
    if education["status"] in {"available", "model_explanation"}:
        safe_core.append(model_text if model_text and education["status"] == "available" else selected["core"])
    safe_core.extend(safe_paragraphs)
    safe_core.extend(item["text"] for item in verified_observations)
    if verified_numbers:
        safe_core.append("이 실행에서 확인한 값: " + ", ".join(
            f"{item['label']} {_number_text(item)} {item['unit']}" for item in verified_numbers
        ))
    if withheld_numeric:
        verified_values = list(dict.fromkeys(
            f"{c['label']} {c.get('expected_display') or _number_text({'value':c['expected']})} {c['expected_unit']}"
            for c in withheld_numeric if c.get("expected") is not None
        ))
        note = "설명의 수치를 실행 기록에서 확인할 수 없어 해당 문장을 보류했습니다."
        if verified_values:
            note += " 검산값: " + ", ".join(verified_values)
        safe_core.append(note)
    if not safe_core:
        safe_core.append("이 질문에 대해 검토된 자료가 주장을 뒷받침하는지 확인하지 못해 설명을 보류했습니다.")
    if verified:
        uncertainty.append("인용문은 원문과 대조했습니다. 각 설명 문장은 근거 관계를 따로 판정했으며, 확인되지 않은 문장은 보류했습니다.")
    if any(c.get("withheld") for c in claims if c["kind"] == "explanation"):
        uncertainty.append("일부 해설 문장은 관련 근거만 있거나 범위가 맞지 않아 답변 본문에서 보류했습니다.")
    if snapshot and snapshot.run.status != "VERIFIED":
        uncertainty.append(f"물리 엔진 판정은 {snapshot.run.status}입니다. 수치 일치는 이 실행의 표본에 한정됩니다.")
    abstention = _abstention(
        claims, verified, checks, question, snapshot, formula, education,
        registry_text=bool(registry_notes or registry_derivations),
        safe_text=bool(safe_paragraphs), supported_numbers=bool(verified_numbers),
        supported_observations=bool(verified_observations), special=special,
    )
    features = _related_features(store, rows, verified, snapshot)
    return {"core":"\n\n".join(safe_core),"sources":verified,"formula":formula,"calculations":numbers,"checks":checks,"claims":claims,
            "assumptions":snapshot.experiment.assumptions if snapshot else [],"uncertainty":uncertainty,
            "theory_status":"available" if verified else "insufficient","simulation_supported":snapshot is not None,
            "related_models":[item["id"] for item in features if item["kind"] == "registered_model"],
            "related_features":features,"prerequisite":special if special in FOUNDATIONS else None,
            "education":education,"abstention":abstention}


def reading_only(store, message, mode, level, special=None, default_text=None):
    import sqlite3

    try:
        rows = retrieved_for(store,message,special=special)
    except sqlite3.OperationalError as exc:
        # A missing local index cannot substantiate a claim. Other storage faults
        # need their original diagnostic rather than an empty search result.
        if not str(exc).startswith("no such table: "):
            raise
        rows = []
    context = make_context(store,rows,message)
    has_text = bool(context["passages"])
    if special == "literature":
        text = ("요청한 제목과 조건에 맞는 원문 위치를 아래에서 확인할 수 있습니다." if has_text else
                "요청한 문헌의 제목·서지 조건·인용 위치를 내장 자료에서 함께 확인하지 못했습니다. 확인할 수 있는 인용은 없습니다.")
    elif special == "drag" and has_text:
        text = "공기와 물체의 상대 운동에 의한 항력을 다루는 자료가 있습니다. 현재 자유낙하 실험은 공기 저항을 무시하므로 항력을 포함한 낙하 시간은 계산할 수 없습니다."
    elif special in FOUNDATIONS and has_text:
        text = FOUNDATIONS[special][2]
    else:
        text = default_text or "이 질문에 해당하는 검토된 자료와 계산 모델을 확인하지 못했습니다."
    dossier = report(store,rows,context,text,special=special,level=level,question=message)
    scope_parts = []
    if default_text:
        scope_parts.append("요청 범위: " + default_text.strip())
    if special == "drag":
        from .physics import SPECS
        spec = SPECS["free_fall"]
        scope_parts.append(
            f"등록 모델 '{spec.title}'은 공기 저항을 무시하는 조건으로 계산하므로 항력을 포함한 낙하 계산은 지원하지 않습니다."
        )
    feature_titles = list(dict.fromkeys(item["title"] for item in dossier.get("related_features", [])))
    if feature_titles:
        scope_parts.append("관련 기능·자료: " + ", ".join(feature_titles[:3]) + ".")
    if scope_parts:
        for part in scope_parts:
            if part not in dossier["core"]:
                dossier["core"] = (dossier["core"].rstrip() + "\n\n" + part).strip()
        dossier["scope_recovery"] = {
            "reason":default_text,
            "supported_part":bool(dossier["sources"] or dossier["education"].get("status") == "available"),
            "related_features":dossier.get("related_features", []),
            "narrative":scope_parts,
        }
    answer_state = _reading_answer_state(special, has_text, dossier, default_text, message)
    adjudicated = dossier["core"]
    lesson = {"mode":mode,"title":"학습 자료 확인","text":adjudicated,"prompt":"","actions":[],"evidence":dossier}
    return {"action":"unsupported","status":"UNSUPPORTED","message":adjudicated,"snapshot":None,
            "level":level,"lesson":lesson,"evidence":dossier,"answer_state":answer_state}, None

