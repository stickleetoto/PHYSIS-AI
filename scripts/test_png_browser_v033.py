"""Real-browser coverage for experiment and graph PNG downloads."""
from pathlib import Path
import re
import struct

from playwright.sync_api import expect

from test_browser import browser, page, server


def captured_svg(page, expected_count):
    page.wait_for_function(
        "(count) => window.__pngSvgDocuments && window.__pngSvgDocuments.length >= count",
        arg=expected_count,
    )
    return page.evaluate("window.__pngSvgDocuments.at(-1)")


def assert_rendered_png(download):
    data = Path(download.path()).read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert data[12:16] == b"IHDR"
    width, height = struct.unpack(">II", data[16:24])
    assert width == 1200 and height > 300
    assert b"IDAT" in data and len(data) > 4_000


def begin_svg_capture(page):
    page.evaluate("""() => {
      window.__pngSvgDocuments = [];
      const createObjectURL = URL.createObjectURL.bind(URL);
      URL.createObjectURL = (blob) => {
        if (blob.type.includes('image/svg+xml')) {
          blob.text().then((content) => window.__pngSvgDocuments.push(content));
        }
        return createObjectURL(blob);
      };
    }""")


def export_and_inspect(page, button_name, expected_count):
    with page.expect_download() as download:
        page.get_by_role("button", name=button_name, exact=True).click()
    assert_rendered_png(download.value)
    return captured_svg(page, expected_count)


def open_catalog_model(page, model):
    catalog = page.evaluate("async () => (await fetch('/api/catalog')).json()")
    title = next(entry["title"] for entry in catalog["models"] if entry["model"] == model)
    page.get_by_role("button", name="실험 목록", exact=True).click()
    with page.expect_response(lambda response: response.url.endswith("/api/experiments") and response.request.method == "POST"):
        page.get_by_role("dialog").get_by_role("button", name=re.compile(re.escape(title))).click()
    expect(page.get_by_role("heading", name=title, exact=True)).to_be_visible()
    return title


def test_simulation_and_graph_pngs_include_rendered_data_and_evidence(page):
    begin_svg_capture(page)
    scene = export_and_inspect(page, "시뮬레이션 PNG 내보내기", 1)
    assert "두 물체의 자유낙하" in scene
    assert "출발 높이" in scene and "m" in scene
    assert "검증 통과" in scene and "표시 시각" in scene
    assert "<path" in scene and "<circle" in scene

    graph = export_and_inspect(page, "그래프 PNG 내보내기", 2)
    assert "시계열 · 높이 (m) 대 시간 (s)" in graph
    assert "<path" in graph and "시간에 따른 높이 그래프" in graph


def test_field_and_fluid_models_can_export_their_current_scenes(page):
    begin_svg_capture(page)
    wave_title = open_catalog_model(page, "wave_transverse")
    wave = export_and_inspect(page, "시뮬레이션 PNG 내보내기", 1)
    assert wave_title in wave and "계산 모식도" in wave
    assert "field-wave" in wave and "파장" in wave

    fluid_title = open_catalog_model(page, "continuity")
    fluid = export_and_inspect(page, "시뮬레이션 PNG 내보내기", 2)
    assert fluid_title in fluid
    assert "fluid-svg" in fluid and "m/s" in fluid
