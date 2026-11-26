"""Provider picker UI with a local launcher and intercepted compatible-provider metadata."""
from playwright.sync_api import expect

from test_browser import browser, page, server


def test_local_probe_and_manual_provider_selection_survive_reload(page):
    page.get_by_role("button", name="AI 공급자 설정").click()
    dialog = page.get_by_role("dialog", name="AI 공급자 설정")
    expect(dialog.get_by_label("모델 ID")).to_have_value("local-rules")
    dialog.get_by_role("button", name="연결 확인").click()
    expect(dialog.get_by_role("status")).to_have_text("로컬 해석기를 사용할 수 있습니다.")
    dialog.get_by_role("button", name="설정 닫기").click()
    expect(dialog).to_have_count(0)

    # Metadata-only fixture, even on machines configured with real API keys.
    rows = [{"id": "mock", "default_model": "local-rules", "configured": True},
            {"id": "compatible", "default_model": "", "configured": True}]
    page.route("**/api/providers", lambda route: route.fulfill(json={"default_provider": "mock", "providers": rows}))
    page.route("**/api/providers/compatible/models", lambda route: route.fulfill(
        json={"models": ["listed/chat"], "reachable": True, "count": 1, "partial": False, "latency_ms": 10}))
    page.get_by_role("button", name="AI 공급자 설정").click()
    dialog.get_by_role("combobox", name="공급자").select_option("compatible")
    dialog.get_by_role("button", name="모델 목록 조회").click()
    dialog.get_by_label("조회한 모델").select_option("listed/chat")
    expect(dialog.get_by_label("모델 ID")).to_have_value("listed/chat")
    dialog.get_by_label("모델 ID").fill("manual/model:latest")
    dialog.get_by_role("button", name="선택 적용").click()
    expect(dialog).to_have_count(0)
    page.reload()
    page.get_by_role("button", name="AI 공급자 설정").click()
    expect(dialog).to_be_visible()
    expect(dialog.get_by_role("combobox", name="공급자")).to_have_value("compatible")
    expect(dialog.get_by_label("모델 ID")).to_have_value("manual/model:latest")
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
