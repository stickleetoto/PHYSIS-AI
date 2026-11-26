"""Exercise production verification and recovery with deliberately faulty local HTTP responses."""
import argparse
import json
import os
import sys
import threading
import time
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
os.environ["PYTHON_DOTENV_DISABLED"]="1"
from fastapi.testclient import TestClient
from physis.api import create_app
from physis import providers

QUESTION = "현재 자유낙하 실험에서 두 물체가 함께 떨어지는 이유를 설명해 줘."
class FaultServer(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass
    def send_body(self,data,ctype="application/json"):
        self.send_response(200)
        self.send_header("Content-Type",ctype)
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
            pass
    def do_GET(self):
        models = [] if self.server.fault=="loading" and not self.server.loaded else [{"name":"classroom","model":"classroom"}]
        self.send_body(json.dumps({"models":models}).encode())
    def do_POST(self):
        req=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        fault=self.server.fault
        self.server.calls.append(self.path)
        if self.path=="/api/generate":
            time.sleep(.12)
            self.server.loaded=True
            self.send_body(b'{"done":true,"load_duration":120000000}')
            return
        ctx=json.loads(req["messages"][-1]["content"])
        source=(ctx.get("passages") or [{"id":"missing","quote":"중력장에서는 물체의 운동을 관찰할 수 있습니다."}])[0]
        self.server.proposed_quote = source["quote"]
        answer={"text":source["quote"],"source_ids":[source["id"]]}
        if fault=="optional":
            answer.update(assumptions={"invalid":True},uncertainty=[])
        if fault=="settings":
            answer.update(level="research",action="modify",patch={"values":{"height":999}})
        if fault=="wrong_target":
            answer.update(target_experiment_id=str(uuid4()),action="modify",patch={"values":{"height":90}})
        if fault=="numbers":
            n=ctx["calculations"][0]
            answer.update(numeric_claims=[{k:n[k] for k in ("key","experiment_id","revision","run_id","unit")} | {"value":912345}])
            answer["text"] += " 도착 시간은 912345 s입니다."
        if fault=="citation":
            answer.update(source_ids=["no-such-reference"],text="존재하지 않는 문헌에 따르면 모든 실험의 값은 912345 s입니다.")
        if fault=="partial":
            answer["text"] += " 도착 시간은 912345 s입니다."
        if fault=="timeout":
            time.sleep(.7)
        content = "{broken" if fault=="invalid_format" else json.dumps(answer,ensure_ascii=False)
        record={"model":"classroom","message":{"role":"assistant","content":content},"done":fault!="stream_cut"}
        self.send_body((json.dumps(record,ensure_ascii=False)+"\n").encode(),"application/x-ndjson")

def events(client,s,question):
    res=client.post("/api/tutor/stream",json={"experiment_id":s["experiment"]["id"],"revision":s["revision"],
         "level":"school","mode":"explain","message":question,"selection":{"provider":"ollama","model":"classroom"}})
    return [json.loads(l) for l in res.iter_lines() if l][-1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True)
    output=parser.parse_args().out
    rows=[]
    with ExitStack() as stack:
        http=stack.enter_context(ThreadingHTTPServer(("127.0.0.1",0),FaultServer))
        worker=threading.Thread(target=http.serve_forever,daemon=True)
        worker.start()
        stack.callback(http.shutdown)
        stack.enter_context(patch.dict(os.environ,{"OLLAMA_BASE_URL":f"http://127.0.0.1:{http.server_port}",
                                                    "PHYSIS_AI_PROVIDER":"mock","PHYSIS_OFFLINE":"0",
                                                    "NO_PROXY":"localhost,127.0.0.1"}))
        directory=stack.enter_context(TemporaryDirectory())
        api=stack.enter_context(TestClient(create_app(Path(directory)/"test.db")))
        s=api.post("/api/experiments",json={"model":"free_fall"}).json()
        for fault in ("optional","settings","wrong_target","numbers","citation","partial","loading","timeout",
                      "stream_cut","invalid_format","ambiguous","unsupported","missing_experiment"):
            http.fault,http.calls,http.loaded,http.proposed_quote=fault,[],False,""
            question={"ambiguous":"서로 다른 두 물체를 떨어뜨렸는데, 도착 시간이 몇 초인가요?",
                      "unsupported":"공기 저항과 바람까지 포함해서 낙하 시간을 시뮬레이션해 줘."}.get(fault,QUESTION)
            anchor=s if fault!="missing_experiment" else {**s,"experiment":{**s["experiment"],"id":str(uuid4())}}
            start=time.perf_counter()
            with patch.object(providers,"GENERATION_TIMEOUT",.18 if fault=="timeout" else 8):
                end=events(api,anchor,question)
            result=end.get("result",{})
            dossier=result.get("evidence",{})
            pipeline=result.get("pipeline",{})
            text=result.get("message","")
            state=api.get("/api/experiments/"+s["experiment"]["id"]).json()
            ok = (end["event"]=="error" if fault=="missing_experiment" else end["event"]=="result" and bool(text))
            ok = ok and state==s and result.get("level","school")=="school" and "912345" not in text
            if fault in {"optional","settings","wrong_target","partial"}:
                ok = ok and pipeline.get("accepted_clauses",0)>0 and http.proposed_quote.split(". ")[0] in text
            if fault=="numbers":
                ok = ok and any(v.get("status")=="failed" and v.get("value")==912345 for v in dossier.get("checks",[]))
            if fault=="citation":
                ok = ok and "no-such-reference" not in {c["id"] for c in dossier.get("sources",[])}
            if fault in {"timeout","stream_cut","invalid_format"}:
                ok = ok and pipeline.get("generation")=="verified_fallback"
            if fault=="loading":
                ok = ok and "/api/generate" in http.calls
            if fault=="ambiguous":
                ok = ok and result.get("answer_state")=="CLARIFICATION_REQUIRED"
            if fault=="unsupported":
                ok = ok and result.get("snapshot") is None and result.get("answer_state")=="UNSUPPORTED_SIMULATION"
            rows.append({"scenario":fault,"passed":bool(ok),"http_calls":list(http.calls),"event":end["event"],
                         "state_preserved":state==s,"pipeline":pipeline,"answer_state":result.get("answer_state"),
                         "answer":text,"detail":end.get("detail"),"checks":dossier.get("checks"),"elapsed_ms":round((time.perf_counter()-start)*1000)})
    report={"provider":"scripted loopback Ollama-compatible HTTP fault server; no language model",
            "timing":"timeout scenario uses 180 ms, loading simulates 120 ms, other cases use 8 s inference budget",
            "passed":sum(r["passed"] for r in rows),"total":len(rows),"rows":rows}
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print(report["passed"],"/",len(rows),[r["scenario"] for r in rows if not r["passed"]])
    return int(report["passed"]!=len(rows))

if __name__=="__main__":
    raise SystemExit(main())
