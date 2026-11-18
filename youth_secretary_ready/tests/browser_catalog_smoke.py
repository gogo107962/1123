"""Live local DB browse/review check. Makes no upstream policy API call."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

BASE=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    sync_requests=[];page.on('request',lambda r:sync_requests.append(r.url) if '/ontong/sync' in r.url else None)
    page.goto('http://127.0.0.1:8000/lab',wait_until='networkidle')
    page.wait_for_function("!document.querySelector('main').inert")
    page.locator('#ontongPanel > summary').click()
    expect(page.locator('#ontongPage')).to_contain_text('4020건')
    assert page.locator('.ontong-candidate').count()==20
    first=page.locator('.ontong-candidate').first.get_attribute('data-external-id')
    page.locator('#ontongNext').click()
    expect(page.locator('#ontongPage')).to_contain_text('2 / 201')
    assert page.locator('.ontong-candidate').first.get_attribute('data-external-id')!=first
    def search(value):
        page.wait_for_function("!document.querySelector('main').inert")
        page.locator('#ontongLocalQuery').fill(value)
        page.locator('#ontongLocalSearch button[type=submit]').click()
        page.wait_for_function("!document.querySelector('main').inert")
    search('20261021005400214208')
    expect(page.locator('#ontongPage')).to_contain_text('검색 결과 1건')
    expect(page.locator('[data-source-check]')).to_contain_text('API와 공식 접수기간 차이')
    expect(page.locator('[data-source-check]')).to_contain_text('2026-05-19 18:00')
    page.locator('[data-open-draft]').click()
    expect(page.locator('[data-review-code="seoul_rent_2026"]')).to_be_visible()
    search('20240418005400200013')
    expect(page.locator('[data-source-check]')).to_contain_text('공식 조기 마감 안내 확인')
    page.locator('[data-open-draft]').click()
    card=page.locator('[data-review-code="seongbuk_exam_2026"]')
    expect(card).to_be_visible()
    card.get_by_text('가상 조건으로 규칙 검토하기 (저장 없음)',exact=True).click()
    card.locator('[data-review-at]').fill('2026-11-16T12:00')
    card.locator('[data-review-run]').click()
    expect(card.locator('[data-review-result]')).to_contain_text('기간: 접수 종료')
    expect(card.locator('[data-review-result]')).to_contain_text('조기 마감')
    expect(card.locator('[data-review-result]')).to_contain_text('차기 모집 공고 확인')
    expect(page.locator('#policyList [data-policy]')).to_have_count(3)
    expect(page.locator('#savedTasks')).to_contain_text('아직 승인해 저장한 작업이 없어')
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1')
    card.screenshot(path=str(BASE/'.local'/'browser-catalog-review.png'))
    assert not errors,errors
    assert not sync_requests,sync_requests
    print(json.dumps({'passed':True,'all_records_searchable':4020,'pagination':True,
                      'source_period_conflict':True,'early_closure':True,'unapproved_drafts_excluded':True,
                      'policy_api_sync_requests':0,'page_errors':errors}))
    browser.close()
