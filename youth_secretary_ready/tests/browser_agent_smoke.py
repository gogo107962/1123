"""Explicit browser -> real local LLM -> fact approval -> task approval check."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    page.set_default_timeout(180000)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000/lab',wait_until='networkidle')
    expect(page.locator('#askAgent')).to_be_enabled()
    page.locator('[data-persona="unemployed"]').click()
    page.wait_for_function("document.querySelector('main').inert===false")
    page.locator('#agentInput').fill('가상 프로필에서 나이는 27세이고 월세는 계좌이체로 냈어. 이 두 정보만 변경 제안하고, 변경된 조건으로 자격 분석과 준비 서류를 도구로 확인해 줘. 아직 저장하지 마.')
    page.locator('#askAgent').click()
    page.wait_for_function("document.querySelector('main').inert===false")
    expect(page.locator('#applyAiFacts')).to_be_visible()
    expect(page.locator('#agentOutput')).to_contain_text('update_user_facts')
    expect(page.locator('#age')).to_have_value('26')
    expect(page.locator('#savedTasks')).to_contain_text('아직 승인해 저장한 작업이 없어')
    page.locator('#applyAiFacts').click()
    expect(page.locator('#age')).to_have_value('27')
    expect(page.locator('#rent')).to_have_value('bank')
    expect(page.locator('#previewList')).to_contain_text('월세 이체내역')
    page.locator('#confirmPlan').click()
    expect(page.locator('#savedTasks')).to_contain_text('월세 이체내역')
    page.reload(wait_until='networkidle')
    expect(page.locator('#age')).to_have_value('27')
    expect(page.locator('#savedTasks')).to_contain_text('월세 이체내역')
    assert not errors,errors
    page.locator('#assistant').screenshot(path=str(BASE/'.local'/'browser-agent.png'))
    print(json.dumps({'passed':True,'real_model':True,'fact_confirmation':True,'task_confirmation':True,'reload_persistence':True,'page_errors':errors}))
    browser.close()
