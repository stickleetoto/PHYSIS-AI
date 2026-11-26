"""Attach separate editorial judgments to the archived Mock responses and calculate old-cohort metrics."""
import argparse
import json
from collections import Counter,defaultdict
from pathlib import Path

from benchmark_scoring import REVIEW_BY_CATEGORY, summarize, write_json

CLEAR = {"concept","formula","applicability","misconception","units","numeric","citation","followup"}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("responses",type=Path)
    parser.add_argument("ratings",type=Path,help="Object keyed by ID, each with [pass bool, rationale]")
    parser.add_argument("out",type=Path)
    args=parser.parse_args()
    data=json.loads(args.responses.read_text(encoding="utf8"))
    ratings=json.loads(args.ratings.read_text(encoding="utf8"))
    rows=data["rows"]
    assert len(rows)==len(ratings) and set(ratings)=={r["case"]["id"] for r in rows}
    scores=defaultdict(lambda:[0,0])
    states=Counter()
    clear=over=asked=0
    for row in rows:
        case=row["case"]
        category=case["category"]
        ok,comment=ratings[case["id"]]
        assert type(ok) is bool and comment.strip()
        scores[category][0]+=int(ok)
        scores[category][1]+=1
        row["checks"][REVIEW_BY_CATEGORY[category]]=[int(ok),1]
        row["editorial_review"]={"pass":ok,"rationale":comment}
        answer=row.get("answer") or {}
        state=answer.get("answer_state") or "NO_ANSWER"
        states[state]+=1
        if category in CLEAR:
            clear+=1
            asked+=int(state=="CLARIFICATION_REQUIRED")
            over+=int(state in {"INSUFFICIENT_EVIDENCE","UNSUPPORTED_SIMULATION","VERIFICATION_FAILED","NO_ANSWER"}
                      or (answer.get("abstention") or {}).get("status")=="full" and state!="ANSWERED")
    data.update(semantic_scores=dict(scores),summary=summarize(rows),answer_states=dict(states),clear_total=clear,
                clear_full_abstention=over,clear_clarifications=asked,
                correct=sum(v[0] for v in scores.values()),rating_file=args.ratings.name)
    write_json(args.out,data)
    print({k:data[k] for k in ("correct","cohort_size","semantic_scores","clear_full_abstention","clear_total","clear_clarifications")})

if __name__=="__main__":
    main()
