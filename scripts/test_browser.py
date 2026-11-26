"""Real Chromium + local Windows launcher + FastAPI. Run after the Vite build."""
import csv
from http.client import HTTPException
from io import StringIO
import json
import os
from pathlib import Path
import re
from secrets import randbelow
import socket
import subprocess
import time
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright
import pytest


ROOT = Path(os.getenv("PHYSIS_TEST_APP") or Path(__file__).resolve().parents[1])


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    directory = tmp_path_factory.mktemp("physis-browser")
    # Use a listener port outside Windows' default outbound ephemeral range.
    # This prevents a readiness probe from connecting to its own source port.
    for _ in range(20):
        port = 20000 + randbelow(20000)
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
                break
            except OSError:
                continue
    else:
        pytest.fail("Could not allocate a local test port.")
    address = f"http://127.0.0.1:{port}"
    env = dict(os.environ, PHYSIS_AI_PROVIDER="mock", PHYSIS_DATA_DIR=str(directory / "data"))
    log = directory / "server.log"
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(["cmd.exe", "/d", "/c", "Start-PHYSIS.cmd", "--port", str(port), "--no-browser"],
                                   cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    with urlopen(address + "/api/health", timeout=1) as response:
                        if json.load(response)["service"] == "PHYSIS AI":
                            break
                except (OSError, URLError, HTTPException):
                    time.sleep(.15)
            else:
                pytest.fail(log.read_text(encoding="utf-8", errors="replace"))
            yield address
        finally:
            if process.poll() is None:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                process.wait(timeout=10)


@pytest.fixture(scope="module")
def browser():
    candidates = [Path(os.getenv("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
                  Path(os.getenv("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe"]
    installed = next((str(p) for p in candidates if p.is_file()), None)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=installed, headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser, server):
    ctx = browser.new_context(viewport={"width": 1440, "height": 980}, locale="ko-KR", accept_downloads=True)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(server)
    expect(page.get_by_role("heading", name="두 물체의 자유낙하")).to_be_visible()
    yield page
    ctx.close()
    assert errors == []


def ask(page, question):
    page.get_by_role("textbox", name="실험 질문").fill(question)
    with page.expect_response(lambda r: r.url.endswith("/api/chat") and r.request.method == "POST") as result:
        page.get_by_role("button", name="보내기", exact=True).click()
    assert result.value.ok, result.value.text()
    return result.value.json()


def test_conversation_modification_and_real_csv(page):
    screenshot = os.getenv("PHYSIS_TEST_SCREENSHOT")
    if screenshot:
        path = Path(screenshot)
        path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=path, full_page=True)
    first = ask(page, "무거운 물체가 가벼운 물체보다 빨리 떨어지는 거 아니야?")["snapshot"]
    second = ask(page, "그러면 두 물체의 질량 차이를 더 크게 해봐.")["snapshot"]
    assert second["experiment"]["id"] == first["experiment"]["id"]
    assert second["revision"] == first["revision"] + 1
    assert second["experiment"]["values"]["mass_b"] > first["experiment"]["values"]["mass_b"]
    assert second["run"]["facts"]["arrival_time"] == pytest.approx(2.019275, abs=.00001)
    answer = ask(page, "왜 결과가 같아?")
    assert answer["action"] == "explain" and answer["snapshot"]["revision"] == second["revision"]
    expect(page.get_by_text(answer["message"], exact=True).last).to_be_visible()
    expect(page.get_by_role("button", name="이전 조건 비교")).to_be_visible()
    page.get_by_role("button", name="이전 조건 비교").click()
    expect(page.get_by_text("이전 물체 A", exact=True)).to_be_visible()
    expect(page.get_by_text("이전 물체 B", exact=True)).to_be_visible()
    with page.expect_download() as event:
        page.get_by_role("button", name="CSV 내보내기").click()
    rows = list(csv.reader(StringIO(Path(event.value.path()).read_text(encoding="utf-8-sig"))))
    assert len(rows) == len(second["run"]["times"]) + 1
    assert float(rows[-1][0]) == pytest.approx(second["run"]["facts"]["arrival_time"])
    assert float(rows[1][rows[0].index("0.y [m]")]) == 20
    expect(page.get_by_role("button", name="재생", exact=True)).to_be_enabled()
    page.get_by_role("button", name="재생", exact=True).click()
    page.get_by_role("button", name="일시정지").click()
    page.get_by_role("button", name="처음으로").click()
    page.get_by_role("button", name=re.compile("한 스텝|단일 스텝|다음 스텝")).click()
    assert float(page.get_by_role("slider", name="재생 시간").input_value()) == pytest.approx(.02)


def test_manual_edit_recompute_reload_and_unsupported(page):
    page.get_by_role("spinbutton", name="출발 높이").fill("5")
    with page.expect_response(lambda r: r.request.method == "PATCH") as event:
        page.get_by_role("button", name="변경 적용").click()
    snapshot = event.value.json()
    assert snapshot["run"]["facts"]["arrival_time"] == pytest.approx(1.009638, abs=.00001)
    page.reload()
    expect(page.get_by_role("spinbutton", name="출발 높이")).to_have_value("5")
    response = ask(page, "양자 얽힘을 시뮬레이션해줘")
    assert response["status"] == "UNSUPPORTED"
    expect(page.get_by_text("지원 범위 안내", exact=True)).to_be_visible()
    expect(page.get_by_role("spinbutton", name="출발 높이")).to_have_value("5")


def test_discovery_and_failed_solver_are_visible(page):
    page.get_by_role("button", name="개념 탐구").click()
    expect(page.get_by_role("button", name="CSV 내보내기")).to_be_disabled()
    expect(page.get_by_role("button", name="결과 공개")).to_be_disabled()
    page.get_by_label("가설", exact=True).fill("같은 높이에서는 같은 시간에 도착한다.")
    page.get_by_label("예측", exact=True).fill("두 높이 곡선이 겹친다.")
    page.get_by_role("button", name="결과 공개").click()
    expect(page.get_by_label("관찰과 결론")).to_be_visible()
    page.get_by_role("button", name="개념 탐구").click()
    page.get_by_role("button", name="실험 목록", exact=True).click()
    page.get_by_role("button", name=re.compile("용수철의 단순 조화 운동")).click()
    expect(page.get_by_role("heading", name="용수철의 단순 조화 운동")).to_be_visible()
    page.get_by_text("계산 조건", exact=True).click()
    page.get_by_label("계산 방법", exact=True).select_option("euler")
    page.get_by_label(re.compile("시간 간격 Δt")).fill("0.2")
    page.get_by_label("계산 시간 (s)", exact=True).fill("10")
    page.get_by_role("button", name="변경 적용").click()
    expect(page.get_by_text("검증 실패", exact=True).first).to_be_visible()
    page.get_by_role("button", name="수렴", exact=True).click()
    expect(page.get_by_role("img", name="시간 간격에 따른 수렴 그래프")).to_be_visible()
    page.get_by_role("button", name="해설", exact=True).click()
    page.get_by_label("설명 수준").select_option("research")
    expect(page.get_by_label("설명 수준")).to_have_value("research")


def test_phone_question_and_layout(page):
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.get_by_role("button", name="어시스턴트 열기").click()
    answer = ask(page, "용수철 실험을 만들어 줘")
    assert answer["snapshot"]["experiment"]["model"] == "spring"
    page.get_by_role("button", name="어시스턴트 닫기").click()
    expect(page.get_by_role("heading", name="용수철의 단순 조화 운동")).to_be_visible()


def test_every_catalog_model_opens_with_measured_graph(page, server):
    with urlopen(server + "/api/catalog") as response:
        models = json.load(response)["models"]
    for model in models:
        page.get_by_role("button", name="실험 목록", exact=True).click()
        with page.expect_response(lambda r: r.url.endswith("/api/experiments") and r.request.method == "POST") as result:
            page.get_by_role("dialog").get_by_role("button", name=re.compile(re.escape(model["title"]))).click()
        assert result.value.json()["run"]["status"] == "VERIFIED"
        expect(page.get_by_role("heading", name=model["title"], exact=True)).to_be_visible()
        expect(page.get_by_role("img", name=re.compile("시간에 따른 .* 그래프"))).to_be_visible()


def test_pressure_gauge_moves_with_depth(page):
    page.get_by_role("button", name="실험 목록", exact=True).click()
    page.get_by_role("button", name=re.compile("깊이에 따른 정수압")).click()
    field = page.get_by_role("spinbutton", name="수면 아래 깊이")
    expect(field).to_have_value("2")
    # The sensor and its lead occupy an SVG group labelled by its depth.
    reading = page.locator("svg text.fluid-reading").first
    expect(reading).to_be_visible()
    start = float(reading.get_attribute("y"))
    field.fill("10")
    with page.expect_response(lambda r: r.request.method == "PATCH") as result:
        page.get_by_role("button", name="변경 적용").click()
    assert result.value.json()["run"]["facts"]["gauge_pressure"] == pytest.approx(98100)
    expect(reading).not_to_have_attribute("y", str(int(start) if start.is_integer() else start))
    assert float(reading.get_attribute("y")) > start
