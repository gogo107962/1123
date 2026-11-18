"""Real service browser flow; no upstream policy calls or AI required."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

BASE=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    page.add_init_script("localStorage.getItem('youth-desk-profile')||localStorage.setItem('youth-desk-profile','{}')")  # 내 정보 입력 화면 건너뛰기
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://127.0.0.1:8000/classic',wait_until='networkidle')
    expect(page.locator('#policyGrid .policy-card')).to_have_count(12)
    expect(page.locator('#catalogCount')).to_contain_text('4,020')
    page.screenshot(path=str(BASE/'.local/desk-desktop.png'),full_page=True)
    first=page.locator('#policyGrid .policy-card').first
    policy_id=first.get_attribute('data-policy-id')
    first.locator('[data-save]').click()
    expect(page.locator('#savedCount')).to_have_text('1')
    page.locator('[data-tab="saved"]').click()
    expect(page.locator('#savedGrid .policy-card')).to_have_count(1)
    page.locator('#savedGrid [data-open]').click()
    expect(page.locator('#detailBody')).to_be_visible()
    page.locator('#showPreview').click()
    expect(page.locator('#previewTasks .preview-item')).to_have_count(3)
    page.locator('#approvePlan').click()
    expect(page.locator('#tasksView')).to_be_visible()
    expect(page.locator('#tasksList [data-task]')).to_have_count(3)
    page.locator('#tasksList [data-task]').first.check()
    expect(page.locator('#progressText')).to_have_text('1 / 3 완료')
    page.reload(wait_until='networkidle')
    expect(page.locator('#savedCount')).to_have_text('1')
    page.locator('[data-tab="tasks"]').click()
    expect(page.locator('#progressText')).to_have_text('1 / 3 완료')
    page.locator('[data-tab="explore"]').click()
    page.locator('#searchInput').fill('20261021005400214208')
    page.locator('#searchForm button').click()
    expect(page.locator('#resultCount')).to_have_text('1개의 정책')
    page.locator('#policyGrid [data-open]').click()
    expect(page.locator('#detailEvidence')).to_contain_text('접수가 끝났어요')
    page.locator('#showPreview').click()
    expect(page.locator('#previewTasks .preview-item')).to_have_count(1)
    expect(page.locator('#previewTasks')).to_contain_text('다음 모집 공고')
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1')
    assert page.locator('#policyDialog').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
    page.screenshot(path=str(BASE/'.local/desk-mobile-detail.png'))
    page.locator('#closeDialog').click()
    page.locator('#clearSearch').click()
    expect(page.locator('#policyGrid .policy-card')).to_have_count(12)
    page.screenshot(path=str(BASE/'.local/desk-mobile.png'))
    page.locator('#searchInput').fill('no-matching-policy-xyz')
    page.locator('#searchForm button').click()
    expect(page.locator('#policyGrid')).to_contain_text('검색 결과가 없어요')
    assert not errors,errors
    print(json.dumps({'passed':True,'real_catalog':4020,'bookmark_restore':True,'task_approval_restore':True,
                      'closed_policy_guard':True,'mobile_no_overflow':True,'page_errors':errors}))
    browser.close()
