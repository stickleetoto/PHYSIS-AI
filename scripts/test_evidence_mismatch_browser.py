"""Scenario D: an actual loopback model adapter sends the wrong value to the real verifier."""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import expect
import pytest

from test_browser import browser, page, server
from test_tutor_browser import ask_tutor, tab
from test_grounded_browser import capture


@pytest.fixture(scope="module",autouse=True)
def classroom_provider():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            context=json.loads(body["messages"][-1]["content"])
            if "catalog" in context:
                answer={"action":"explain","model":context["current"]["model"],"patch":{},"level":context["level"]}
            else:
                n=context["calculations"][0]
                claim={k:n[k] for k in ("key","experiment_id","revision","run_id","unit")}
                claim["value"]=99
                answer={"text":"도착 시간은 99초입니다.","numeric_claims":[claim],"source_ids":["missing-fictional-source"]}
            record={"choices":[{"index":0,"delta":{"content":json.dumps(answer)},"finish_reason":None}]}
            done={"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}
            stream=("data: "+json.dumps(record)+"\n\ndata: "+json.dumps(done)+"\n\ndata: [DONE]\n\n").encode()
            self.send_response(200)
            self.send_header("Content-Type","text/event-stream")
            self.send_header("Content-Length",str(len(stream)))
            self.end_headers()
            self.wfile.write(stream)
    with ThreadingHTTPServer(("127.0.0.1",0),Handler) as upstream, pytest.MonkeyPatch.context() as mp:
        t=threading.Thread(target=upstream.serve_forever,daemon=True);t.start()
        mp.delenv("PHYSIS_OFFLINE",raising=False)
        mp.setenv("PHYSIS_COMPATIBLE_API_KEY","")
        mp.setenv("PHYSIS_COMPATIBLE_BASE_URL",f"http://127.0.0.1:{upstream.server_port}/v1")
        try:
            yield
        finally:
            upstream.shutdown()
            t.join()


def test_d_wrong_model_claim_is_visible_and_engine_untouched(page):
    page.evaluate("localStorage.setItem('physis-provider',JSON.stringify({provider:'compatible',model:'classroom-fixture'}))")
    page.reload()
    expect(page.get_by_role("heading",name="두 물체의 자유낙하")).to_be_visible()
    tab(page,"튜터")
    r=ask_tutor(page,"현재 실험 결과를 설명해 줘")
    panel=page.get_by_role("region",name="답변 근거")
    errors=panel.get_by_role("alert")
    expect(errors.filter(has_text="기준값")).to_be_visible()
    assert any(c.get("value")==99 and c["status"]=="failed" for c in r["evidence"]["checks"])
    assert r["evidence"]["sources"]==[] and r["snapshot"]["revision"]==1
    assert r["evidence"]["calculations"][0]["value"]!=99
    capture(page,"verification",panel)

