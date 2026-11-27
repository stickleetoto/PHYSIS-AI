"""Real Math Lab UI on the loopback service, using the offline launcher and CPU-rendered browser."""
import csv
from io import StringIO
import os
from pathlib import Path
import re

from playwright.sync_api import expect
import pytest

from test_browser import browser, page, server  # noqa: F401

# Fixed-library startup and user computation have independent bounded deadlines.
JOB_WAIT_MS = 30_000


def math_lab(page):
    page.get_by_role("button", name="수학 실험실", exact=True).click()
    return page.get_by_role("region", name="수학 실험실")


def capture(page, name):
    folder = os.getenv("PHYSIS_MATH_SCREENSHOTS")
    if folder:
        directory = Path(folder)
        directory.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=directory / f"PHYSIS-0.4-{name}.png", animations="disabled")


def test_graph_hole_and_exports(page):
    with page.expect_response(lambda r:r.url.endswith("/api/math-lab/calculate"), timeout=JOB_WAIT_MS) as default:
        lab = math_lab(page)
    assert default.value.json()["status"]=="ok", default.value.json().get("detail")
    expect(lab.get_by_role("button",name="그래프 PNG")).to_be_visible(timeout=JOB_WAIT_MS)
    lab.get_by_label("수식 f(x)",exact=True).fill("1/(x-0.25)")
    lab.get_by_label("비교 함수 g(x)").fill("")
    lab.get_by_role("button",name="계산하기").click()
    lines=lab.locator('[data-curve="f(x)"] polyline')
    expect(lines).to_have_count(2,timeout=JOB_WAIT_MS)
    for button,suffix in [("그래프 PNG",".png"),("계산 데이터 CSV",".csv")]:
        with page.expect_download() as event:
            lab.get_by_role("button",name=button).click()
        artifact=event.value
        assert artifact.suggested_filename.endswith(suffix)
        data=Path(artifact.path()).read_bytes()
        if suffix==".png":
            assert data[:8] == b"\x89PNG\r\n\x1a\n" and len(data)>1000
        else:
            rows=list(csv.DictReader(StringIO(data.decode("utf-8-sig"))))
            spans={}
            for r in rows:
                if r["curve"]=="f(x)":
                    x,y=float(r["x"]),float(r["y"])
                    assert y == pytest.approx(1/(x-.25))
                    spans.setdefault(r["segment"],[]).append(x)
            assert len(spans)==2 and all(max(xs)<.25 or min(xs)>.25 for xs in spans.values())
    capture(page,"function")


def test_calculus_to_physics_and_formula_return(page):
    lab=math_lab(page)
    with page.expect_response(lambda r:r.url.endswith("/api/math-lab/calculate") and
                              r.request.post_data_json.get("mode")=="derivative",timeout=JOB_WAIT_MS) as calculus:
        lab.get_by_role("button",name="위치 → 속도·가속도").click()
    assert calculus.value.json()["status"]=="ok", calculus.value.json().get("detail")
    expect(lab.get_by_role("button",name="현재 계수로 물리 실험 열기")).to_be_enabled(timeout=JOB_WAIT_MS)
    lab.get_by_label("계수 c",exact=True).fill("4")
    lab.get_by_role("button",name="계산하기").click()
    link=lab.get_by_role("button",name="현재 계수로 물리 실험 열기")
    expect(link).to_be_enabled(timeout=JOB_WAIT_MS)
    capture(page,"derivative")
    with page.expect_response(lambda r:r.url.endswith("/api/experiments") and r.request.method=="POST") as event:
        link.click()
    first=event.value.json()
    assert first["experiment"]["values"]["a"]==4
    assert first["run"]["series"]["0.ax"][-1]==pytest.approx(4)
    page.get_by_role("button",name="공식",exact=True).click()
    page.get_by_role("button",name="이 공식으로 수학 실험 열기").click()
    expect(lab.get_by_label("계수 c",exact=True)).to_have_value("4")
    lab.get_by_role("button",name="속도 적분 → 변위").click()
    expect(lab.get_by_role("button",name="현재 계수로 물리 실험 열기")).to_be_enabled(timeout=JOB_WAIT_MS)
    expect(lab.get_by_text("정적분",exact=False).first).to_be_visible()
    capture(page,"integral")
    lab.get_by_label("적분 유형",exact=True).select_option("indefinite")
    lab.get_by_label("수식 f(x)",exact=True).fill("1/x")
    with page.expect_response(lambda r:r.url.endswith("/api/math-lab/calculate") and
                              r.request.post_data_json.get("expression")=="1/x") as event:
        lab.get_by_role("button",name="계산하기").click()
    indefinite=event.value.json()
    assert indefinite["status"]=="ok"
    assert next(r["value"] for r in indefinite["rows"] if r["label"]=="부정적분")=="log(Abs(x))"


def test_geometry_statistics_matrix_and_numerics(page):
    lab=math_lab(page)
    lab.get_by_role("button",name="벡터와 정사영").click()
    expect(lab.locator('[data-vector="u"]')).to_be_visible()
    circle=lab.locator('[data-vector="u"]').bounding_box()
    x,y=circle["x"]+circle["width"]/2,circle["y"]+circle["height"]/2
    page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+22,y-26);page.mouse.up()
    assert float(lab.get_by_label("uy",exact=True).input_value())!=0
    capture(page,"vector")
    lab.get_by_role("button",name="삼각함수와 단위원").click()
    lab.get_by_label("각도 단위").select_option("°")
    lab.get_by_label("위상 φ (°)",exact=True).fill("90")
    expect(lab.get_by_text(re.compile("tan θ = 정의되지 않음"))).to_be_visible()
    capture(page,"trig")
    lab.get_by_role("button",name="통계와 실험 데이터").click()
    lab.get_by_role("button",name="시간·측정값 가져오기").click()
    expect(lab.get_by_role("img",name="히스토그램")).to_be_visible()
    lab.get_by_role("button",name="행렬과 선형변환").click()
    with page.expect_response(lambda r:r.url.endswith("/api/math-lab/matrix"),timeout=JOB_WAIT_MS) as matrix:
        lab.get_by_role("button",name="행렬 계산").click()
    assert matrix.value.json()["status"]=="ok", matrix.value.json().get("detail")
    expect(lab.get_by_role("img",name=re.compile("평면 선형변환"))).to_be_visible(timeout=JOB_WAIT_MS)
    lab.get_by_role("button",name="근 찾기와 수치 근사").click()
    lab.get_by_role("button",name="수치해법 비교").click()
    expect(lab.get_by_role("img",name="반복 번호에 따른 잔차 |f(x)|")).to_be_visible(timeout=JOB_WAIT_MS)
    lab.get_by_role("button",name="미분방정식과 시간 변화").click()
    lab.get_by_label("미분방정식",exact=True).select_option("damped")
    lab.get_by_role("button",name="초기값 문제 계산").click()
    expect(lab.get_by_role("img",name="방향장")).to_be_visible()
    with page.expect_response(lambda r:r.url.endswith("/api/experiments") and r.request.method=="POST") as event:
        lab.get_by_role("button",name="같은 초기 조건으로 물리 실험 열기").click()
    assert event.value.json()["experiment"]["model"]=="damped"


def test_work_displacement_and_travelling_wave_use_real_physics(page):
    for name, expected_model, expected in [
        ("일정한 힘 → 일","newton",6), ("복원력 → 일","spring",-6),
        ("속도 적분 → 변위","acceleration",8),
    ]:
        lab=math_lab(page)
        lab.get_by_role("button",name=name,exact=True).click()
        link=lab.get_by_role("button",name="현재 계수로 물리 실험 열기")
        expect(link).to_be_enabled(timeout=JOB_WAIT_MS)
        with page.expect_response(lambda r:r.url.endswith("/api/experiments") and r.request.method=="POST") as event:
            link.click()
        data=event.value.json()
        assert data["experiment"]["model"]==expected_model
        key="0.x" if expected_model=="acceleration" else "0.ke"
        series=data["run"]["series"][key]
        assert series[-1]-series[0]==pytest.approx(expected,abs=1e-5)
    lab=math_lab(page)
    lab.get_by_role("button",name="삼각함수와 단위원").click()
    lab.get_by_role("button",name="횡파 조건 적용").click()
    with page.expect_response(lambda r:r.url.endswith("/api/experiments") and r.request.method=="POST") as event:
        lab.get_by_role("button",name="횡파 실험 열기").click()
    run=event.value.json()["run"]
    index=run["times"].index(.5)
    assert abs(run["series"]["0.displacement"][index])<1e-8
    assert min(run["series"]["0.displacement"])==pytest.approx(-.03,abs=.0001)
