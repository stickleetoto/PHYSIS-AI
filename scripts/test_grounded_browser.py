"""The v0.3 classroom acceptance scenarios over the actual Windows launcher and browser."""
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from playwright.sync_api import expect
import pytest

from test_browser import browser, page, server
from test_tutor_browser import ask_tutor, tab


@pytest.fixture(scope="module",autouse=True)
def offline_profile():
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("PHYSIS_OFFLINE","1")
        for name in ("OPENAI_API_KEY","ANTHROPIC_API_KEY","PHYSIS_COMPATIBLE_API_KEY"):
            mp.delenv(name,raising=False)
        yield


def capture(page, name, locator=None):
    if folder := os.getenv("PHYSIS_V3_SCREENSHOTS"):
        target=Path(folder)/("PHYSIS-0.3-"+name+".png")
        target.parent.mkdir(parents=True,exist_ok=True)
        if locator is not None:
            locator.screenshot(path=target)
        else:
            page.screenshot(path=target,full_page=True)


def test_a_newton_answer_original_passage_and_reproducible_run(page):
    tab(page,"튜터")
    result=ask_tutor(page,"뉴턴의 운동 법칙을 설명해 줘")
    e=result["evidence"]
    assert e["simulation_supported"] and e["formula"]["formula_id"]=="newton"
    assert e["calculations"][0]["experiment_id"]==result["snapshot"]["experiment"]["id"]
    panel=page.get_by_role("region",name="답변 근거")
    expect(panel.get_by_text("근거 확인",exact=False).first).to_be_visible()
    expect(panel.get_by_role("link",name="원문 열기 ↗").first).to_have_attribute("href",re.compile("^https://"))
    assert all(s["quote"] and s["locator"] for s in e["sources"])
    capture(page,"evidence",panel)
    with page.expect_download() as event:
        panel.get_by_role("button",name="보고서 저장").click()
    exported=Path(event.value.path()).read_text(encoding="utf8")
    assert e["sources"][0]["id"].split(":")[-1] in exported and e["calculations"][0]["run_id"] in exported
    panel.get_by_role("button",name="계산 검증").click()
    panel.get_by_label("설명에 적힌 값").fill("99")
    panel.get_by_label("설명에 적힌 단위").fill("m/s²")
    panel.get_by_role("button",name="실제 실행과 대조").click()
    expect(panel.get_by_role("status")).to_contain_text("검증 실패")


def test_b_pendulum_small_angle_conditions_and_source(page):
    tab(page,"튜터")
    result=ask_tutor(page,"진자의 주기 공식은 언제 성립해?")
    assert result["evidence"]["formula"]["formula_id"]=="pendulum_small_angle"
    assert result["evidence"]["formula"]["applicability"]["status"]=="outside_conditions"
    panel=page.get_by_role("region",name="답변 근거")
    panel.get_by_role("button",name="공식과 가정").click()
    expect(panel.get_by_text("적용 범위 밖",exact=False)).to_be_visible()
    panel.get_by_role("button",name="공식과 단위 열기").click()
    expect(page.get_by_role("region",name="공식 라이브러리")).to_contain_text("소각")


def test_c_missing_publication_and_e_unsupported_drag(page):
    tab(page,"튜터")
    absent=ask_tutor(page,"“보랏빛 시계의 제77 낙하 법칙”이라는 논문을 인용해 줘")
    assert absent["evidence"]["sources"]==[] and absent["evidence"]["theory_status"]=="insufficient"
    panel=page.get_by_role("region",name="답변 근거")
    expect(panel.get_by_text("이론 자료 · 근거 부족")).to_be_visible()
    theory=ask_tutor(page,"공기 저항을 포함해서 물체가 떨어지는 실험을 해줘")
    assert theory["snapshot"] is None and theory["evidence"]["sources"]
    expect(panel.get_by_text("이론 자료 · 확인")).to_be_visible()
    expect(panel.get_by_text("시뮬레이션 · 미지원")).to_be_visible()
    expect(page.get_by_text("이 질문에 연결된 시뮬레이션이 없습니다.")).to_be_visible()


def test_f_math_prerequisite_roadmap_checkpoint_and_tool(page):
    tab(page,"튜터")
    result=ask_tutor(page,"벡터가 무엇인지 잘 모르겠어")
    assert result["evidence"]["prerequisite"]=="vectors"
    page.get_by_role("button",name="선행 개념 학습 열기").click()
    roadmap=page.get_by_role("region",name="학습 로드맵")
    expect(roadmap).to_contain_text("확인 문제 통과 0")
    expect(roadmap.locator(".roadmap-detail a").first).to_be_visible()
    roadmap.get_by_role("button",name="크기만",exact=True).click()
    expect(roadmap.get_by_role("status")).to_contain_text("다시 살펴보세요")
    expect(roadmap).to_contain_text("복습 1")
    roadmap.get_by_role("button",name="크기와 방향",exact=True).click()
    expect(roadmap).to_contain_text("확인 문제 통과 1")
    capture(page,"roadmap")
    roadmap.get_by_role("button",name="기초 수학 도구 열기").click()
    tool=page.get_by_role("region",name="기호 수학 도구")
    with page.expect_response(lambda r:r.url.endswith("/api/math")) as response:
        tool.get_by_role("button",name="계산하기").click()
    assert response.value.json()["result"]=="2*x + 1"


def test_g_offline_browser_library_model_and_math(browser,server):
    # DNS and non-loopback connect are blocked in the launched server. Block browser-side requests too.
    ctx=browser.new_context(viewport={"width":1440,"height":950})
    attempted=[]
    def route(req):
        if urlsplit(req.request.url).hostname not in {"127.0.0.1","localhost"}:
            attempted.append(req.request.url)
            req.abort()
        else:
            req.continue_()
    ctx.route("**/*",route)
    p=ctx.new_page()
    try:
        p.goto(server)
        health=p.request.get(server+"/api/health").json()
        assert health["offline"] is True and health["provider"]=="mock"
        expect(p.get_by_role("heading",name="두 물체의 자유낙하")).to_be_visible()
        tab(p,"지식 탐구")
        search=p.get_by_role("searchbox",name="과학 문헌 검색")
        search.fill("뉴턴 제2법칙")
        p.get_by_role("button",name="검색",exact=True).click()
        detail=p.locator('[aria-label="문헌 상세"]')
        expect(detail.get_by_role("link",name="원문 위치").first).to_be_visible()
        expect(detail).to_contain_text("CC BY")
        capture(p,"library")
        p.set_viewport_size({"width":390,"height":844})
        assert p.evaluate("document.documentElement.scrollWidth <= innerWidth")
        tab(p,"튜터")
        assert ask_tutor(p,"현재 실험 결과를 설명해 줘")["evidence"]["sources"]
        math=p.request.post(server+"/api/math",data={"operation":"differentiate","expression":"x^2","variable":"x"})
        assert math.ok and math.json()["result"]=="2*x"
        assert attempted==[]
    finally:
        ctx.close()

