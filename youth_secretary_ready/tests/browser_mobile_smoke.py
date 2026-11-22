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
    # 이전 대화: '새 대화'를 눌러도 방금 대화가 목록에 남고, 눌러서 다시 열 수 있다
    page.locator('[data-a=newchat]').click()
    expect(page.locator('.m.bot')).to_have_count(1)
    page.locator('[data-a=history]').click()
    expect(page.locator('.hist')).to_have_count(1)
    page.locator('.hist .cardbtn').click()
    expect(page.locator('.m.bot').last).to_contain_text('관련 정책')
    page.locator('[data-a=results]').click()

    # 결과 → 상세 → 근거 시트
    expect(page.locator('.cardbtn').first).to_be_visible()
    assert page.evaluate(FITS)
    page.screenshot(path=str(BASE / '.local/mobile-results.png'))
    page.locator('.cardbtn').first.click()
    expect(page.locator('main')).to_contain_text('조건 대조')
    # 공식 사이트: 온통청년 정책 페이지는 모든 정책에 있고, '공식 공고' 버튼은 항상 주소가 있다
    expect(page.locator('main a[href^="https://www.youthcenter.go.kr/youthPolicy/ythPlcyTotalSearch/ythPlcyDetail/"]')).to_have_text('온통청년 정책 페이지')
    assert page.locator('.act a.btn').get_attribute('href').startswith('https://')
    page.locator('[data-a=sheet]').first.click()
    expect(page.locator('.sheet')).to_contain_text('지원 조건')
    expect(page.locator('.sheet')).to_contain_text('온통청년 정책 페이지의')     # 근거의 위치
    expect(page.locator('.sheet')).to_contain_text('정보 수집일')
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
    # 서류를 모두 체크해야 신청 전 점검으로 넘어간다
    if page.locator('input[data-a=doc]').count():
        assert page.locator('[data-a=check]').count() == 0
        expect(page.locator('.act')).to_contain_text('남았어요')
        while page.locator('input[data-a=doc]:not(:checked)').count():
            left = page.locator('input[data-a=doc]:not(:checked)').count()
            page.locator('input[data-a=doc]:not(:checked)').first.click()      # 체크하면 화면을 다시 그리므로 개수가 줄었는지로 확인한다
            expect(page.locator('input[data-a=doc]:not(:checked)')).to_have_count(left - 1)
    page.locator('[data-a=check]').click()
    expect(page.locator('main')).to_contain_text('중복 수혜 여부')
    expect(page.locator('#msg')).to_contain_text('문의드립니다')
    expect(page.locator('main a[href^="https://www.youthcenter.go.kr/youthPolicy/ythPlcyTotalSearch/ythPlcyDetail/"]')).to_have_count(2)                 # 고른 정책마다 공식 사이트 링크
    assert page.locator('.act a.btn').inner_text() in ('공식 신청 페이지로 이동', '공식 공고로 이동')
    assert page.locator('.act a.btn').get_attribute('href').startswith('https://')
    # 승인 전에는 아무것도 저장되지 않는다.
    assert page.evaluate("fetch('/api/desk/workspaces/'+localStorage.getItem('youth-desk-workspace')).then(r=>r.json()).then(d=>d.tasks.length)") == 0
    page.locator('[data-a=approve]').click()
    expect(page.locator('header h1')).to_have_text('내 신청')
    # 내 신청: 계획을 세운 정책만 접힌 카드로 나온다. 정책을 눌러야 준비 작업 체크리스트가 펼쳐지고, 다시 누르면 접힌다.
    expect(page.locator('.plan-card')).to_have_count(2)
    tasks = page.locator('input[data-a=task]')
    saved = tasks.count()
    assert saved >= 6, saved
    expect(tasks.first).to_be_hidden()
    page.locator('.plan-card summary').first.click()
    expect(tasks.first).to_be_visible()
    tasks.first.check()
    expect(page.locator('.plan-card').first).to_contain_text('중 1개 완료')
    expect(tasks.first).to_be_visible()                                # 체크해서 화면을 다시 그려도 펼친 채로 남는다
    page.locator('.plan-card summary').first.click()
    expect(tasks.first).to_be_hidden()

    # 새로고침 뒤 복원
    page.reload(wait_until='networkidle')
    expect(page.locator('.greeting')).to_contain_text('민지 님')
    # 홈 '이어서 준비하기': 저장한 정책에 서류가 있으면 '서류 준비 n / m', 없으면 '확인한 일 n / m'
    expect(page.locator('.prep-count')).to_be_visible()
    assert page.locator('.prep-count span').first.inner_text() in ('서류 준비', '확인한 일')
    # 홈 '이어서 준비하기'에 저장한 정책의 기간 표시(D-day 등)가 붙는다
    expect(page.locator('.policy-line .pill')).to_be_visible()
    assert len(page.locator('.policy-line .pill').inner_text().strip()) >= 2
    page.locator('nav [data-s=plan]').click()
    # 내 신청 탭: 새로 고친 뒤에도 세운 계획 2건이 남아 있고 진행이 그대로다. 서류·순서는 이 탭에 없다(고르는 중이 아니므로 '빼기'와 점검 버튼도 없다)
    expect(page.locator('.plan-card')).to_have_count(2)
    expect(page.locator('.plan-card').first).to_contain_text('중 1개 완료')
    assert page.locator('.ord li').count() == 0
    assert page.locator('[data-a=unsel]').count() == 0 and page.locator('[data-a=check]').count() == 0
    assert page.evaluate(FITS)

    # 공식 페이지에서 보완한 정보(사람 검수 전) 표시
    page.evaluate("openDetail('20261106005400214758')")
    expect(page.locator('main')).to_contain_text('공식 페이지에서 보완한 정보')
    expect(page.locator('main')).to_contain_text('사람 검수 전')
    # 조건 줄은 '지원 조건'으로 나오고, 보완 기록마다 출처에서 문장을 확인했는지 표시가 붙는다
    expect(page.locator('main')).to_contain_text('지원 조건:')
    assert page.locator('details.more .pill').filter(has_text='출처에서 문장 확인').count() + page.locator('details.more .pill').filter(has_text='자동 대조 안 됨').count() >= 1
    page.locator('[data-a=back]').click()

    # 내 정보 지우기 → 시작 화면
    page.locator('nav [data-s=profile]').click()
    expect(page.locator('#birth')).to_have_value('2000-03')
    expect(page.locator('main')).to_contain_text('26세')
    # 소득 구간을 고르고 저장하면 새로고침 뒤에도 남는다
    page.locator('select[data-k=income_band]').select_option('100')
    page.locator('[data-a=save]').click()
    expect(page.locator('#toast')).to_contain_text('저장했어요')
    page.reload(wait_until='networkidle')
    page.locator('nav [data-s=profile]').click()
    expect(page.locator('select[data-k=income_band]')).to_have_value('100')
    assert page.evaluate("JSON.parse(localStorage.getItem('youth-desk-profile')).income_band") == 100
    page.locator('[data-a=logout]').click()
    expect(page.locator('h1.hero')).to_be_visible()

    # 넓은 화면에서도 앱 폭을 유지한다.
    page.set_viewport_size({'width': 1280, 'height': 900})
    assert page.locator('#app').evaluate('(e)=>e.getBoundingClientRect().width<=430')
    assert not errors, errors
    print(json.dumps({'passed': True, 'url': URL, 'ai_ready': ai, 'ai_seconds': ai_seconds, 'saved_tasks': saved,
                      'restore_after_reload': True, 'mobile_no_overflow': True, 'page_errors': errors}, ensure_ascii=False))
    browser.close()
