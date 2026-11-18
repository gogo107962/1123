"""새 앱 화면(팀 프로토타입 기준)의 실제 흐름. 실행 중인 서버와 실제 4,020건 DB가 필요하다.

    $env:APP_URL='http://127.0.0.1:8765'; .venv\\Scripts\\python.exe -X utf8 tests\\browser_mobile_smoke.py

챗봇 단계는 로컬 Ollama가 켜져 있으면 실제 모델 응답을, 꺼져 있으면 안내 문구를 확인한다.
새 준비 공간에 확인 작업을 저장하므로 실행 DB에 시험용 행이 남는다(수집 데이터는 바꾸지 않는다).
"""
import json
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = Path(__file__).resolve().parents[1]
URL = os.environ.get('APP_URL', 'http://127.0.0.1:8000')
FITS = 'document.documentElement.scrollWidth<=window.innerWidth+1'

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width': 390, 'height': 844})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(URL, wait_until='networkidle')

    # 시작 → 데모 계정 → 홈
    expect(page.locator('h1.hero')).to_contain_text('공고는 저희가 읽을게요')
    page.locator('[data-a=demo]').click()
    expect(page.locator('.greeting')).to_contain_text('민지 님')
    expect(page.locator('.pill.ok').first).to_contain_text('조건 맞아요')
    assert page.evaluate(FITS)
    page.screenshot(path=str(BASE / '.local/mobile-home.png'))

    # 챗봇으로 찾기
    ai = page.evaluate("fetch('/api/health').then(r=>r.json()).then(d=>d.llm.ready)")
    started = time.monotonic()
    page.locator('[data-a=topic]').first.click()
    page.locator('[data-a=results]').wait_for(timeout=120000)
    ai_seconds = round(time.monotonic() - started, 1)
    expect(page.locator('.m.bot').last).to_contain_text('관련 정책')
    # AI가 꺼져 있으면 낱말로 찾고, 그렇게 했다고 화면에 밝힌다.
    expect(page.locator('main')).to_contain_text('실행한 도구: 정책 검색' if ai else '낱말로 찾았어요')
    # 데모 프로필에는 '받고 있는 지원'이 없어서 그 질문을 되묻는다.
    expect(page.locator('.m.bot').last).to_contain_text('지금 받고 있는 지원이 있나요?')
    page.screenshot(path=str(BASE / '.local/mobile-chat.png'))
    page.locator('[data-a=results]').click()

    # 결과 → 상세 → 근거 시트
    expect(page.locator('.cardbtn').first).to_be_visible()
    assert page.evaluate(FITS)
    page.screenshot(path=str(BASE / '.local/mobile-results.png'))
    page.locator('.cardbtn').first.click()
    expect(page.locator('main')).to_contain_text('조건 대조')
    page.locator('[data-a=sheet]').first.click()
    expect(page.locator('.sheet')).to_contain_text('API 기재 조건')
    page.screenshot(path=str(BASE / '.local/mobile-detail.png'))
    page.locator('.sheet button[data-a=closesheet]').click()
    page.locator('[data-a=back]').click()

    # 정책 2개 선택 → 신청 계획 → 점검 → 승인 → 내 신청
    page.locator('input[data-a=sel]').nth(0).check()
    page.locator('input[data-a=sel]').nth(1).check()
    expect(page.locator('.act')).to_contain_text('2개 선택')
    page.locator('[data-a=plan]').click()
    expect(page.locator('main')).to_contain_text('신청 순서')
    # 안내 글에 서로 막는 문구가 있으면 그 문장을, 없으면 확인 필요 안내를 보여 준다.
    expect(page.locator('.warnbox')).to_contain_text('함께 받')
    assert page.evaluate(FITS)
    page.screenshot(path=str(BASE / '.local/mobile-plan.png'))
    page.locator('[data-a=check]').click()
    expect(page.locator('main')).to_contain_text('중복 수혜 여부')
    expect(page.locator('#msg')).to_contain_text('문의드립니다')
    # 승인 전에는 아무것도 저장되지 않는다.
    assert page.evaluate("fetch('/api/desk/workspaces/'+localStorage.getItem('youth-desk-workspace')).then(r=>r.json()).then(d=>d.tasks.length)") == 0
    page.locator('[data-a=approve]').click()
    expect(page.locator('header h1')).to_have_text('내 신청')
    tasks = page.locator('input[data-a=task]')
    expect(tasks.first).to_be_visible()
    saved = tasks.count()
    assert saved >= 6, saved
    tasks.first.check()
    expect(page.locator('main')).to_contain_text(f'{saved}개 중 1개 완료')

    # 새로고침 뒤 복원
    page.reload(wait_until='networkidle')
    expect(page.locator('.greeting')).to_contain_text('민지 님')
    expect(page.locator('main')).to_contain_text('확인한 일')
    page.locator('nav [data-s=plan]').click()
    expect(page.locator('main')).to_contain_text(f'{saved}개 중 1개 완료')

    # 공식 페이지에서 보완한 정보(사람 검수 전) 표시
    page.evaluate("openDetail('20261106005400214758')")
    expect(page.locator('main')).to_contain_text('공식 페이지에서 보완한 정보')
    expect(page.locator('main')).to_contain_text('사람 검수 전')
    page.locator('[data-a=back]').click()

    # 내 정보 지우기 → 시작 화면
    page.locator('nav [data-s=profile]').click()
    expect(page.locator('#age')).to_have_value('26')
    page.locator('[data-a=logout]').click()
    expect(page.locator('h1.hero')).to_be_visible()

    # 넓은 화면에서도 앱 폭을 유지한다.
    page.set_viewport_size({'width': 1280, 'height': 900})
    assert page.locator('#app').evaluate('(e)=>e.getBoundingClientRect().width<=430')
    assert not errors, errors
    print(json.dumps({'passed': True, 'url': URL, 'ai_ready': ai, 'ai_seconds': ai_seconds, 'saved_tasks': saved,
                      'restore_after_reload': True, 'mobile_no_overflow': True, 'page_errors': errors}, ensure_ascii=False))
    browser.close()
