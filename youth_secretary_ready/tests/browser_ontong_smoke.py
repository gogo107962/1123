"""Opt-in live UI check: fetches one API page when run explicitly.
Never run by pytest; no credential enters the browser.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000},accept_downloads=True)
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    upstream=[];page.on('request',lambda request:upstream.append(request.url) if 'youthcenter.go.kr' in request.url else None)
    page.goto('http://127.0.0.1:8000/lab',wait_until='networkidle')
    page.wait_for_function("!document.querySelector('main').inert")
    page.locator('#ontongPanel > summary').click()
    expect(page.locator('#ontongStatus')).to_contain_text('인증키 설정됨')
    page.locator('#syncOntong').click()
    expect(page.locator('#ontongResult')).to_contain_text('10건 재확인',timeout=60000)
    page.wait_for_function("!document.querySelector('main').inert")
    assert page.locator('.ontong-candidate').count()>=10
    card=page.locator('.ontong-candidate').first
    card.locator('[data-candidate-open]').click()
    expect(card.locator('[data-candidate-detail]')).to_contain_text('제출서류')
    assert card.locator('details').evaluate('(e)=>e.open')
    with page.expect_download() as download_event:
        card.locator('[data-candidate-download]').click()
    download=download_event.value
    download.save_as(str(BASE/'.local'/'ontong-review-smoke.json'))
    bundle=json.loads((BASE/'.local'/'ontong-review-smoke.json').read_text(encoding='utf-8'))
    assert bundle['review_status']=='unreviewed' and bundle['public_fields']['plcyNo']
    expect(page.locator('#policyList [data-policy]')).to_have_count(3)
    page.reload(wait_until='networkidle')
    page.locator('#ontongPanel > summary').click()
    assert page.locator('.ontong-candidate').count()>=10
    page.set_viewport_size({'width':390,'height':844})
    card=page.locator('.ontong-candidate').first
    card.locator('[data-candidate-open]').click()
    expect(card.locator('[data-candidate-detail]')).to_contain_text('제출서류')
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1')
    card.screenshot(path=str(BASE/'.local'/'browser-ontong.png'))
    assert not errors,errors
    assert not upstream,'API key/requests must stay on the Python server'
    print(json.dumps({'passed':True,'live_sync':True,'download':True,'db_reload':True,
                      'approved_policy_count':3,'browser_upstream_requests':0,'page_errors':errors}))
    browser.close()
