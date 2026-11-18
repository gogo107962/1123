"""Run explicitly against the local server. Uses installed Edge, no cloud browser."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000/lab',wait_until='networkidle')
    expect(page.locator('#analysis')).to_contain_text('조건 불충족')
    page.locator('[data-persona="unemployed"]').click()
    page.wait_for_function("document.querySelector('main').inert===false")
    expect(page.locator('#analysis')).to_contain_text('신청 검토 가능')
    # Searching must not silently unselect a policy hidden by the filter.
    page.locator('#policySearch').fill('월세')
    page.locator('[data-policy="demo_rent"]').uncheck()
    page.wait_for_function("document.querySelector('main').inert===false")
    page.locator('#policySearch').fill('')
    expect(page.locator('[data-policy="demo_allowance"]')).to_be_checked()
    page.locator('[data-policy="demo_rent"]').check()
    page.wait_for_function("document.querySelector('main').inert===false")
    expect(page.locator('#previewList')).to_contain_text('월차임 납부확인서')
    expect(page.locator('#savedTasks')).to_contain_text('아직 승인해 저장한 작업이 없어')
    page.locator('#confirmPlan').click()
    expect(page.locator('#savedTasks [data-task]').first).to_be_visible()
    page.locator('#savedTasks [data-task]').first.check()
    expect(page.locator('#savedTasks [data-task]').first).to_be_checked()
    page.reload(wait_until='networkidle')
    expect(page.locator('#savedTasks [data-task]').first).to_be_checked()
    page.locator('#rent').select_option('bank')
    page.locator('#saveFacts').click()
    expect(page.locator('#previewList')).to_contain_text('월세 이체내역')
    expect(page.locator('#savedTasks')).to_contain_text('조건 변경 후 미재확인')
    expect(page.locator('#savedTasks [data-task]').first).to_be_disabled()
    page.locator('#confirmPlan').click()
    page.wait_for_function("document.querySelector('main').inert===false")
    # An unknown value must remain unknown, not revert to cash/default age.
    page.locator('#age').fill('')
    page.locator('#rent').select_option('')
    page.locator('#saveFacts').click()
    expect(page.locator('#analysis')).to_contain_text('확인 필요')
    expect(page.locator('#previewList')).to_contain_text('대체서류 조건 확인')
    assert '서류 준비: 월세 이체내역' not in page.locator('#previewList').inner_text()
    expect(page.locator('#age')).to_have_value('')
    expect(page.locator('#rent')).to_have_value('')
    assert set(page.locator('#draftPolicies article').evaluate_all('(items)=>items.map(x=>x.dataset.reviewCode)'))=={'seoul_rent_2026','seoul_allowance_2026_round2','seongbuk_exam_2026'}
    page.set_viewport_size({'width':390,'height':844})
    page.evaluate('window.scrollTo(0,0)')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+1')
    output=BASE/'.local'/'browser-smoke.png'
    page.screenshot(path=str(output),full_page=True)
    assert not errors,errors
    print(json.dumps({'passed':True,'browser':'Edge','page_errors':errors,'screenshot':str(output)},ensure_ascii=False))
    browser.close()
