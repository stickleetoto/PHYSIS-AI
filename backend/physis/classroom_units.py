"""Build short unit explanations from this model's reviewed variables and SI dimension table."""
import re
import unicodedata

from .formula_registry import formulas_for
from .symbolic_units import UNITS, dimension


def _plain(text):
    return unicodedata.normalize("NFKC",text).replace("^2","2").replace("^3","3")


UNIT_WORDS = re.compile(r"단위|차원|무차원|units?\b|dimension|붙여도|붙이나",re.I)
SPELLINGS = {_plain(unit):unit for unit in UNITS if unit != "1"}
UNIT_TOKEN = re.compile(r"(?<![A-Za-z0-9_·/])(?:" +
                        "|".join(map(re.escape, sorted(SPELLINGS,key=len,reverse=True))) +
                        r")(?![A-Za-z0-9_·/])")


def unit_note(question, model):
    if not UNIT_WORDS.search(question):
        return ""
    normalized = _plain(question)
    found = [SPELLINGS[m[0]] for m in UNIT_TOKEN.finditer(normalized)]
    if len(found)==2 and re.search(r"곱|multipl|product",question,re.I) and not re.search(r"나누|나눈|divid",question,re.I):
        left, right = found
        exponents = tuple(a+b for a,b in zip(UNITS[left],UNITS[right]))
        match = next((unit for unit, dims in UNITS.items() if dims==exponents),None)
        if match:
            return f"단위의 곱 {left} × {right} = {match}입니다. 결과의 차원은 {dimension(match)}입니다."
    variables = {}
    compact = "".join(question.split())
    for formula in formulas_for(model):
        for var in formula["variables"]:
            # Match a Korean quantity name or an explicit, case-sensitive formula symbol.
            name = var["symbol"]
            named = "".join(var["description"].split()) in compact
            symbol = bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9]*",name) and
                          re.search(r"(?<![A-Za-z0-9])"+re.escape(name)+r"(?![A-Za-z0-9])",question))
            if name in UNITS and not re.search(r"(?:변수|기호)\s*"+re.escape(name)+r"\b|"
                                               +re.escape(name)+r"\s*(?:의\s*단위|의\s*차원)",question):
                symbol = False
            if named or symbol:
                variables.setdefault(var["name"],var)
    if not variables:
        return ""
    entries = [f"{var['description']}({var['name']})의 단위는 {var['unit']}"
               + ("이며 무차원" if var["unit"]=="1" else f"이며 차원은 {var['dimension']}")
               for var in variables.values()]
    return ". ".join(entries)+"입니다."

