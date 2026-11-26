"""User-visible tutor, comparison clock and learning records on the Windows launcher."""
import json
import os
from pathlib import Path
import re

from playwright.sync_api import expect
import pytest

from test_browser import browser, page, server


def tab(page, label):
    page.get_by_role("navigation", name="워크스페이스 탐색").get_by_role("button", name=label, exact=True).click()


def ask_tutor(page, message):
    page.get_by_role("textbox", name="튜터에게 질문").fill(message)
    with page.expect_response(lambda r: r.url.endswith("/api/tutor/stream")) as event:
        page.get_by_role("button", name="질문 보내기").click()
    rows = [json.loads(line) for line in event.value.text().splitlines()]
    assert rows[-1]["event"] == "result", rows[-1]
    expect(page.get_by_role("button", name="요청 취소")).to_have_count(0)
    return rows[-1]["result"]


def test_question_controls_measured_chart_and_time(page):
    tab(page, "튜터")
    answer = ask_tutor(page, "높이 그래프 0.2초부터 0.8초까지 강조해 줘")
    assert answer["snapshot"]["run"]["facts"]["arrival_time"] == pytest.approx(2.019275, abs=1e-5)
    chart = page.get_by_role("img", name=re.compile("시간에 따른 .* 그래프")).filter(visible=True)
    expect(chart).to_be_visible()
    expect(chart.locator('rect[aria-label="튜터 강조 구간"]')).to_be_visible()
    screenshot = os.getenv("PHYSIS_TUTOR_SCREENSHOT")
    if screenshot:
        page.screenshot(path=screenshot, full_page=True)
    assert ask_tutor(page, "0.6초로 이동하고 일시정지해 줘")["action"] == "explain"
    assert float(page.get_by_role("slider", name="튜터 시각").input_value()) == pytest.approx(.6)
    reply = ask_tutor(page, "공기 저항이 있는 낙하의 높이 그래프를 보여줘")
    assert reply["status"] == "UNSUPPORTED"
    for paragraph in reply["message"].split("\n\n"):
        expect(page.get_by_role("status").get_by_text(paragraph, exact=True).first).to_be_visible()


def test_four_workbench_members_share_clock_and_retain_inputs(page):
    region = page.get_by_role("region", name="다중 실험 비교")
    for count in range(2, 5):
        region.get_by_role("button", name="현재 실험 복제").click()
        expect(region.locator(".bench-member")).to_have_count(count)
    expect(region.get_by_role("button", name="현재 실험 복제")).to_be_disabled()
    height = page.get_by_role("spinbutton", name="출발 높이")
    height.fill("5")
    page.get_by_role("button", name="변경 적용").click()
    expect(region.locator(".comparison-notes")).to_contain_text("1.0096")
    region.get_by_role("button", name=re.compile("^기준 ·")).click()
    expect(height).to_have_value("20")
    expect(region.get_by_role("img", name="공통 시간축 비교 그래프")).to_be_visible()
    page.get_by_role("button", name="한 스텝").click()
    assert all(".02 s" in value for value in region.locator(".bench-value").all_text_contents())
    if screenshot := os.getenv("PHYSIS_COMPARE_SCREENSHOT"):
        region.screenshot(path=screenshot)
    page.get_by_role("button", name="재생", exact=True).click()
    expect(region.locator(".bench-value").last).to_contain_text("관찰 종료")
    page.get_by_role("button", name="처음으로").click()
    with page.expect_download() as download:
        region.get_by_role("button", name="실험 4 CSV").click()
    rows = Path(download.value.path()).read_text(encoding="utf-8-sig").splitlines()
    assert float(rows[-1].split(",")[0]) == pytest.approx(1.009638, abs=1e-5)
    page.reload()
    expect(region.locator(".bench-member")).to_have_count(4)
    expect(height).to_have_value("20")


def test_discovery_review_records_export_restoration_and_deletion(page, server):
    tab(page, "튜터")
    page.get_by_role("button", name="발견 학습").click()
    expect(page.get_by_text("예측을 기록하면", exact=False)).to_be_visible()
    page.get_by_label("내 가설", exact=True).fill("질량을 바꿔도 같은 시간에 도착할 것이다.")
    page.get_by_role("button", name="내 가설 기록").click()
    expect(page.get_by_role("slider", name="튜터 시각")).to_be_visible()
    page.get_by_label("관찰 결과", exact=True).fill("두 높이 곡선이 겹쳤다.")
    page.get_by_role("button", name="관찰 결과 기록").click()
    page.get_by_label("결론", exact=True).fill("같은 높이에서 놓은 두 공의 가속도가 같다.")
    page.get_by_role("button", name="결론 기록").click()
    page.get_by_role("textbox", name="튜터에게 질문").fill("내가 아까 세운 가설이 뭐였지?")
    page.get_by_role("button", name="질문 보내기").click()
    expect(page.locator(".edu-reading")).to_contain_text("질량을 바꿔도 같은 시간에 도착할 것이다.")
    page.get_by_role("button", name="북마크", exact=True).click()
    page.get_by_role("button", name="개념 복습").click()
    result = ask_tutor(page, "복습 문제를 내줘")
    page.get_by_role("button", name=re.compile("무거운 공")).click()
    expect(page.get_by_text("다시 생각해 보세요", exact=True)).to_be_visible()
    tab(page, "학습 기록")
    expect(page.get_by_text("복습 답변 · 다시 보기")).to_be_visible()
    with page.expect_download() as event:
        page.get_by_role("button", name="JSON 내보내기").click()
    archive = json.loads(Path(event.value.path()).read_text(encoding="utf-8"))
    kinds = {e["kind"] for e in archive["events"]}
    assert {"turn","hypothesis","observation","conclusion","answer","bookmark","experiment"} <= kinds
    eid = result["snapshot"]["experiment"]["id"]
    assert any(e["id"] == eid for e in archive["server"]["experiments"])
    assert archive["server"]["usage"] and eid in archive["legacy"]["messages"]
    page.reload()
    tab(page, "학습 기록")
    expect(page.get_by_text("복습 답변 · 다시 보기")).to_be_visible()
    page.get_by_role("button", name="전체 삭제").click()
    page.get_by_role("button", name="삭제 확인").click()
    expect(page.get_by_text("첫 학습을 시작해 보세요")).to_be_visible()
    assert page.request.get(server + "/api/experiments/" + eid).status == 404
    assert page.request.get(server + "/api/learning/export").json() == {"experiments":[], "workbenches":[], "usage":[]}


def test_phone_tutor_and_learning_fit_viewport(page):
    page.set_viewport_size({"width":390, "height":844})
    for name in ("튜터", "공식", "수치해석", "학습 기록", "실험실"):
        tab(page, name)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), name


def test_tutor_recovers_from_cancelled_or_truncated_response(page):
    tab(page, "튜터")
    # Keep the first response open until the browser aborts. Truncate the next.
    page.evaluate("""() => {
        const nativeFetch = window.fetch.bind(window);
        let count = 0;
        window.fetch = (url, init) => {
          if (url !== '/api/tutor/stream' || ++count > 2) return nativeFetch(url, init);
          return Promise.resolve(new Response(new ReadableStream({start(controller) {
            controller.enqueue(new TextEncoder().encode('{"event":"stage","stage":"응답 대기"}\\n'));
            if (count === 2) controller.close();
            else init.signal.addEventListener('abort', () => controller.error(new DOMException('aborted','AbortError')));
          }})));
        }
    }""")
    for prompt in ("현재 결과를 설명해 줘", "높이를 5 m로 바꿔 줘"):
        page.get_by_role("textbox", name="튜터에게 질문").fill(prompt)
        page.get_by_role("button", name="질문 보내기").click()
        if prompt.startswith("현재"):
            page.get_by_role("button", name="요청 취소").click()
            expect(page.get_by_text("요청을 취소했습니다.", exact=True)).to_be_visible()
        else:
            expect(page.get_by_role("alert")).to_contain_text("연결이 끊겼습니다")
    result = ask_tutor(page, "왜 두 공은 동시에 떨어져?")
    assert result["snapshot"]["revision"] == 1
    assert result["snapshot"]["experiment"]["values"]["height"] == 20
