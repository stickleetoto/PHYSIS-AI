"""Student-facing file, history and keyboard workflows on the Windows launcher."""
import json

from playwright.sync_api import expect

from test_browser import ask, browser, page, server


def test_shortcuts_share_history_with_mock_and_ignore_text_inputs(page):
    mass = page.get_by_role("spinbutton", name="물체 B 질량")
    before = mass.input_value()
    mass.fill("12")
    page.locator("h1").click()
    page.keyboard.press("r")
    expect(mass).to_have_value(before)
    answer = ask(page, "물체 B의 질량을 10 kg으로 바꿔 줘")
    assert answer["action"] == "modify"
    expect(mass).to_have_value("10")
    undo = page.get_by_role("button", name="실행 취소", exact=True)
    expect(undo).to_be_enabled()
    question = page.get_by_role("textbox", name="실험 질문")
    question.fill("입력 중")
    question.press("r")
    question.press("n")
    question.press("Space")
    expect(mass).to_have_value("10")
    expect(page.get_by_role("slider",name="재생 시간")).to_have_value("0")
    page.locator("h1").click()
    page.keyboard.press("Control+z")
    expect(mass).to_have_value(before)
    expect(page.get_by_role("button",name="다시 실행")).to_be_enabled()
    page.keyboard.press("Control+y")
    expect(mass).to_have_value("10")
    page.keyboard.press("r")
    expect(mass).to_have_value(before)
    expect(undo).to_be_enabled()
    page.keyboard.press("Control+z")
    expect(mass).to_have_value("10")
    page.keyboard.press("n")
    clock=page.get_by_role("slider",name="재생 시간")
    page.wait_for_function("Number(document.querySelector('[aria-label=\"재생 시간\"]').value)>0")
    page.keyboard.press("Space")
    expect(page.get_by_role("button",name="일시정지",exact=True)).to_be_visible()
    page.keyboard.press("Space")
    expect(page.get_by_role("button",name="재생",exact=True)).to_be_visible()
    assert float(clock.input_value()) > 0


def test_versioned_file_restores_named_comparison_and_rejects_invalid_input(page, tmp_path):
    board=page.get_by_role("region",name="다중 실험 비교")
    board.get_by_role("button",name="현재 실험 복제").click()
    expect(board.locator(".bench-member")).to_have_count(2)
    page.get_by_label("실험 이름",exact=True).fill("질량 비교 B")
    page.get_by_role("button",name="이름 적용").click()
    expect(page.locator("h1")).to_have_text("질량 비교 B")
    height=page.get_by_role("spinbutton",name="출발 높이")
    height.fill("7")
    page.get_by_role("button",name="변경 적용").click()
    expect(page.get_by_role("button",name="실행 취소")).to_be_enabled()
    board.get_by_label("공통 물리량").select_option("vy")
    board.get_by_label("비교할 물체").select_option("1")
    page.get_by_label("재생 속도").select_option("2")
    page.locator("h1").click()
    page.keyboard.press("n")
    with page.expect_download() as download:
        page.keyboard.press("Control+s")
    assert "질량 비교 B" in download.value.suggested_filename
    saved=tmp_path/"실험 비교.json"
    download.value.save_as(saved)
    record=json.loads(saved.read_text(encoding="utf8"))
    assert record["format_version"]==1 and len(record["experiments"])==2
    assert record["comparison"]["view"]["quantity"]=="vy"
    assert record["comparison"]["view"]["object_index"]==1
    copied={**record,"format_version":200}
    page.get_by_label("실험 JSON 파일").set_input_files({"name":"bad.json","mimeType":"application/json",
                                                   "buffer":json.dumps(copied).encode()})
    expect(page.get_by_role("alert")).to_be_visible()
    expect(page.locator("h1")).to_have_text("질량 비교 B")
    page.locator("h1").click()
    with page.expect_file_chooser() as chooser:
        page.keyboard.press("Control+o")
    chooser.value.set_files(saved)
    expect(page.get_by_role("alert")).to_have_count(0)
    expect(page.get_by_role("button",name="실행 취소")).to_be_disabled()
    expect(board.locator(".bench-member")).to_have_count(2)
    expect(page.locator("h1")).to_have_text("질량 비교 B")
    expect(height).to_have_value("7")
    expect(board.get_by_label("공통 물리량")).to_have_value("vy")
    expect(board.get_by_label("비교할 물체")).to_have_value("1")
    expect(page.get_by_label("재생 속도")).to_have_value("2")
    board.get_by_role("button",name="기준 ·",exact=False).click()
    expect(height).to_have_value("20")


def test_converter_and_preset_from_the_tools_dialog(page):
    page.get_by_role("button",name="프리셋·단위 변환").click()
    dialog=page.get_by_role("dialog",name="프리셋 및 단위 변환")
    dialog.get_by_role("tab",name="단위 변환").click()
    dialog.get_by_label("변환할 양").select_option("temperature")
    dialog.get_by_label("입력 단위",exact=True).select_option("fahrenheit")
    dialog.get_by_label("변환 단위",exact=True).select_option("celsius")
    dialog.get_by_label("입력값",exact=True).fill("32")
    expect(dialog.get_by_label("변환 결과",exact=True)).to_have_text("0")
    dialog.get_by_role("tab",name="학습 프리셋").click()
    cards=dialog.locator("details.lab-preset-card")
    expect(cards).to_have_count(23)
    card=cards.filter(has_text="질량과 자유낙하").first
    title=card.locator("summary b").first.inner_text()
    card.locator("summary").first.click()
    expect(card.get_by_role("heading",name="생각해 볼 질문")).to_be_visible()
    card.get_by_role("button",name="이 프리셋으로 실험",exact=False).click()
    expect(dialog).to_have_count(0)
    expect(page.locator("h1")).to_have_text(title)
