"""Formula-library navigation, rendering and real symbolic calculation in Chromium."""
import os
from pathlib import Path
import re

from playwright.sync_api import expect

from test_browser import browser, page, server


def open_library(page):
    page.get_by_role("button",name="지식 탐구",exact=True).click()
    page.get_by_role("button",name="공식 라이브러리",exact=True).click()
    return page.get_by_role("region",name="공식 라이브러리",exact=True)


def test_reviewed_formulas_render_search_and_open_experiment(page):
    library = open_library(page)
    select = library.get_by_label("공식 선택")
    expect(select.locator("option")).to_have_count(27)
    for key in select.locator("option").evaluate_all("options=>options.map(o=>o.value)"):
        select.select_option(key)
        expect(library.locator(".formula-main math")).to_have_count(1)
        expect(library.locator(".katex-error")).to_have_count(0)
        expect(library.get_by_role("link")).to_have_attribute("href",re.compile(r"^https://"))
        expect(library.get_by_role("columnheader",name="차원")).to_be_visible()
    library.get_by_label("공식 검색").fill("진자")
    expect(select.locator("option")).to_have_count(3)
    select.select_option("pendulum_small_angle")
    expect(library.get_by_role("listitem").filter(has_text="0.20 rad")).to_be_visible()
    expect(library.get_by_role("heading",name="단진자의 소각도 근사 주기")).to_be_visible()
    directory = os.getenv("PHYSIS_V3_SCREENSHOTS")
    if directory:
        Path(directory).mkdir(parents=True,exist_ok=True)
        page.screenshot(path=Path(directory)/"PHYSIS-0.3-formula.png",full_page=True)
    with page.expect_response(lambda r:r.url.endswith("/api/experiments") and r.request.method=="POST") as event:
        library.get_by_role("button",name="관련 실험 실행").click()
    assert event.value.json()["experiment"]["model"]=="pendulum"
    expect(page.get_by_role("heading",name="단진자의 비선형 진동",exact=True)).to_be_visible()


def test_symbolic_domain_and_discontinuous_graph_in_browser(page):
    library = open_library(page)
    library.get_by_role("button",name="기호 수학 도구",exact=True).click()
    tool = library.get_by_role("region",name="기호 수학 도구")
    operation = tool.get_by_label("연산",exact=True)
    operation.select_option("equivalent")
    tool.get_by_label("왼쪽 식",exact=True).fill("x/x")
    tool.get_by_label("오른쪽 식",exact=True).fill("1")
    tool.get_by_role("button",name="계산하기").click()
    expect(tool.get_by_role("heading",name="정의역 불일치")).to_be_visible(timeout=15_000)
    operation.select_option("graph")
    tool.get_by_label("입력 수식",exact=True).fill("1/(x-0.1)")
    tool.get_by_role("button",name="계산하기").click()
    graph = tool.get_by_role("img",name="x에 따른 함수값")
    expect(graph).to_be_visible(timeout=15_000)
    expect(graph.locator("polyline")).to_have_count(2)
    operation.select_option("compare_root")
    with page.expect_response(lambda r:r.url.endswith("/api/math"),timeout=15_000) as event:
        tool.get_by_role("button",name="계산하기").click()
    result = event.value.json()
    assert result["result"]=="sqrt(2)" and result["absolute_error"]<1e-10
    expect(tool.get_by_text(re.compile("이분법 .*회"))).to_be_visible()
