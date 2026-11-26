"""Check scope and clarification as the student sees them in the shipped tutor."""
import os
from pathlib import Path

from playwright.sync_api import expect

from test_browser import browser, page, server
from test_tutor_browser import ask_tutor, tab


def test_missing_input_and_scope_are_visible_without_running_a_new_scene(page):
    tab(page, "튜터")
    reply = ask_tutor(page, "서로 다른 두 물체를 떨어뜨렸는데 도착 시간이 몇 초인가요?")
    assert reply["answer_state"] == "CLARIFICATION_REQUIRED"
    assert reply["snapshot"] is None
    expect(page.get_by_text("답변 · 추가 조건 필요", exact=True)).to_be_visible()
    if directory := os.getenv("PHYSIS_V032_SCREENSHOTS"):
        page.screenshot(path=Path(directory)/"PHYSIS-0.3.2-clarification.png",full_page=True)
    supplied = ask_tutor(page, "높이 8 m")
    assert supplied["snapshot"]["experiment"]["values"]["height"] == 8
    outside = ask_tutor(page, "공기 저항과 바람까지 포함해서 낙하 시간을 시뮬레이션해 줘.")
    assert outside["answer_state"] == "UNSUPPORTED_SIMULATION"
    assert outside["snapshot"] is None
    expect(page.get_by_text("답변 · 계산 모델 범위 밖", exact=True)).to_be_visible()
    if directory:
        page.screenshot(path=Path(directory)/"PHYSIS-0.3.2-scope.png",full_page=True)
