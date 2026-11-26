"""Science views over the production UI and Windows launcher. Reusable against the ZIP."""
import os
from pathlib import Path
import re

import pytest
from playwright.sync_api import expect

from test_browser import browser, page, server


def test_formula_render_and_live_input_in_browser(page):
    page.get_by_role("button",name="공식",exact=True).click()
    formula = page.get_by_role("region",name="공식 탐구")
    select = formula.get_by_label("공식 선택")
    expect(select).to_have_value("free_fall")
    expect(formula.locator(".formula-main .katex-html")).to_be_visible()
    expect(formula.locator(".formula-main math")).to_have_count(1)
    expect(formula.get_by_role("img",name="높이 · 현재 실험")).to_be_visible()
    field = formula.get_by_role("spinbutton",name="공식 변수 값")
    expect(field).to_have_value("20")
    field.fill("5")
    with page.expect_response(lambda r:r.request.method=="PATCH") as response:
        formula.get_by_role("button",name="실험에 적용").click()
    assert response.value.json()["run"]["series"]["0.y"][0] == 5
    expect(formula.locator(".science-chart svg text").filter(has_text=re.compile(r"^5$"))).to_be_visible()
    path = os.getenv("PHYSIS_FORMULA_SCREENSHOT")
    if path:
        page.screenshot(path=Path(path), full_page=True)
    keys = select.locator("option").evaluate_all("(o) => o.map(n => n.value)")
    assert len(keys)==13
    for key in keys:
        if key == "free_fall":
            continue
        with page.expect_response(lambda r:r.request.method=="POST" and r.url.endswith("/api/experiments")):
            select.select_option(key)
        expect(formula.locator(".formula-main .katex-html")).to_be_visible()
        expect(formula.locator(".formula-main annotation")).to_have_count(1)
        expect(formula.locator(".science-section ol li").first).to_be_visible()
    formula.get_by_role("button",name="현재 실험 열기").click()
    expect(page.get_by_role("heading",name="관의 단면적과 유속",exact=True)).to_be_visible()


def test_numeric_method_comparison_and_real_timings(page):
    page.get_by_role("button",name="수치해석",exact=True).click()
    lab = page.get_by_role("region",name="수치해석 실험실")
    expect(lab.get_by_role("heading",name="계산 방법별 결과")).to_be_visible()
    lab.get_by_role("spinbutton",name="수치 실험 시간 간격 (s)").fill(".1")
    with page.expect_response(lambda r:r.url.endswith("/api/science/numerical")) as comparison:
        lab.get_by_role("button",name="계산 방법 비교").click()
    data = comparison.value.json()
    assert data["dt"] == .1 and len(data["rows"]) == 4 and all(r["elapsed_ms"] > 0 for r in data["rows"])
    expect(lab.get_by_role("img",name="계산 방법별 위치 비교")).to_be_visible()
    expect(lab.get_by_role("img",name="시간 간격별 최대 위치 오차")).to_be_visible()
    expect(lab.locator("tbody tr")).to_have_count(4)


def test_large_unstable_solver_paths_stay_finite_in_browser(page):
    page.get_by_role("button",name="실험 목록",exact=True).click()
    page.get_by_role("dialog").get_by_role("button",name=re.compile("용수철의 단순 조화 운동")).click()
    for label,value in [("질량",".5"),("용수철 상수","100"),("처음 변위","3"),("처음 속도","5")]:
        page.get_by_role("spinbutton",name=label,exact=True).fill(value)
    page.get_by_text("계산 조건",exact=True).click()
    page.get_by_label(re.compile("시간 간격 Δt")).fill(".2")
    page.get_by_label("계산 시간 (s)",exact=True).fill("30")
    with page.expect_response(lambda r:r.request.method=="PATCH") as changed:
        page.get_by_role("button",name="변경 적용").click()
    assert changed.value.ok
    with page.expect_response(lambda r:r.url.endswith("/api/science/numerical")) as comparison:
        page.get_by_role("button",name="수치해석",exact=True).click()
    assert comparison.value.status == 200
    lab = page.get_by_role("region",name="수치해석 실험실")
    expect(lab.locator("tbody tr")).to_have_count(4)
    for dt in (".2",".14018691588785046"):
        if dt != ".2":
            lab.get_by_role("spinbutton",name="수치 실험 시간 간격 (s)").fill(dt)
            with page.expect_response(lambda r:r.url.endswith("/api/science/numerical")) as comparison:
                lab.get_by_role("button",name="계산 방법 비교").click()
            assert comparison.value.status == 200
        paths = lab.get_by_role("img",name="계산 방법별 위치 비교").locator("path[fill=none]")
        expect(paths).to_have_count(4)
        assert paths.evaluate_all("""paths=>paths.every(p=>{
            const d=p.getAttribute('d'), box=p.getBBox();
            return !/NaN|Infinity/.test(d) && Number.isFinite(p.getTotalLength()) &&
                   box.x>=0 && box.y>=0 && box.x+box.width<=626 && box.y+box.height<=199;
        })""")


@pytest.mark.parametrize("title,coordinate", [("진행하는 사인 횡파","cy"),("압축과 팽창의 종파","cx"),
                                           ("균일한 흐름의 추적 입자","cx")])
def test_field_probe_tracks_real_simulation_time(page,title,coordinate):
    page.get_by_role("button",name="실험 목록",exact=True).click()
    page.get_by_role("dialog").get_by_role("button",name=re.compile(re.escape(title))).click()
    scene=page.get_by_role("img",name=title+" 계산 모식도")
    expect(scene).to_be_visible()
    probe=scene.get_by_test_id("field-probe")
    start=probe.get_attribute(coordinate)
    orthogonal="cy" if coordinate=="cx" else "cx"
    fixed=probe.get_attribute(orthogonal)
    page.get_by_role("button",name=re.compile("한 스텝|단일 스텝|다음 스텝")).click()
    expect(probe).not_to_have_attribute(coordinate,start)
    expect(probe).to_have_attribute(orthogonal,fixed)
    expect(page.get_by_role("img",name=re.compile("시간에 따른 .* 그래프"))).to_be_visible()
