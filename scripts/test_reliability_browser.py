"""Student-visible reliability checks against the source or an extracted Windows release."""
import os
from pathlib import Path

from playwright.sync_api import expect
import pytest

from test_browser import browser, page, server
from test_tutor_browser import ask_tutor, tab


def capture(page, name):
    folder = os.getenv("PHYSIS_RELIABILITY_SCREENSHOTS")
    if folder:
        page.screenshot(path=Path(folder)/f"PHYSIS-0.3.1-{name}.png",full_page=True)


def test_followup_in_the_same_tutor_constructs_the_requested_experiment(page):
    tab(page,"튜터")
    question = ask_tutor(page,"공이 몇 초 만에 땅에 닿아?")
    assert question["classification"] == "needs_clarification" and question["snapshot"] is None
    expect(page.get_by_text(question["message"], exact=False).filter(visible=True).first).to_be_visible()
    capture(page,"clarification")
    answer = ask_tutor(page,"높이 7.5 m")
    assert answer["snapshot"]["experiment"]["values"]["height"] == 7.5
    actual = answer["snapshot"]["run"]["facts"]["arrival_time"]
    assert actual == pytest.approx((15/9.81)**.5,rel=1e-4)
    assert any(r["run_id"] and r["key"]=="arrival_time" and r["value"]==actual
               for r in answer["evidence"]["calculations"])


def test_claim_relation_and_numeric_audit_are_distinct_on_screen(page):
    tab(page,"튜터")
    answer = ask_tutor(page,"뉴턴의 운동 법칙을 설명해 줘")
    panel = page.get_by_role("region",name="답변 근거")
    panel.get_by_role("button",name="주장별 근거").click()
    expect(panel.locator("details").first).to_be_visible()
    capture(page,"alignment")
    panel.get_by_role("button",name="계산 검증").click()
    item = answer["evidence"]["calculations"][0]
    panel.get_by_label("설명에 적힌 값").fill(str(item["value"]))
    panel.get_by_label("설명에 적힌 단위").fill(item["unit"])
    panel.get_by_role("button",name="실제 실행과 대조").click()
    expect(panel.get_by_role("status")).to_contain_text("계산 검증 통과")

