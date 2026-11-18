"""Opt-in browser + actual local AI. Uses public policy and a generic question only."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

BASE=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1280,'height':900})
    page.add_init_script("localStorage.getItem('youth-desk-profile')||localStorage.setItem('youth-desk-profile','{}')")  # 내 정보 입력 화면 건너뛰기
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000/classic',wait_until='networkidle')
    page.locator('#searchInput').fill('20261021005400214208');page.locator('#searchForm button').click()
    expect(page.locator('#resultCount')).to_have_text('1개의 정책')
    page.locator('#policyGrid [data-open]').click()
    expect(page.locator('#detailBody')).to_be_visible()
    page.locator('#aiQuestion').fill('이 회차의 모집기간과 다음에 확인할 일을 도구로 확인해줘.')
    page.locator('#askPolicy').click()
    expect(page.locator('#aiStatus')).to_contain_text('조회 완료',timeout=180000)
    expect(page.locator('#aiAnswer')).to_contain_text('정책 자료 조회')
    expect(page.locator('#aiAnswer')).to_contain_text('준비 작업 조회')
    expect(page.locator('#aiAnswer')).to_contain_text('원문 대조일: 2026-11-16')
    expect(page.locator('#taskCount')).to_have_text('0')
    page.locator('.ai-box').screenshot(path=str(BASE/'.local/desk-ai.png'))
    assert not errors,errors
    print(json.dumps({'passed':True,'real_local_ai':True,'evidence_dates_displayed':True,'no_automatic_task_save':True,'page_errors':errors}))
    browser.close()
