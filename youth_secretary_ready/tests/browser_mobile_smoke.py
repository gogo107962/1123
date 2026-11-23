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
LAST_MONTH = time.strftime('%Y-%m', time.localtime(time.mktime(time.localtime()[:1] + (time.localtime()[1] - 1, 1, 0, 0, 0, 0, 0, -1))))
PROFILE = {'name': '민지', 'birth': '2000-03', 'moved': '2024-02', 'age': 26, 'sido': '28', 'region_code': '28177', 'job_code': '0013003',
           'school_code': '', 'household': 1, 'housing': '월세', 'exams': [{'name': '정보처리기사', 'month': LAST_MONTH}]}     # 가상 인물

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width': 390, 'height': 844})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(URL, wait_until='networkidle')

    # 시작 화면(정보 없음): 아래에 '데모 계정으로 시작하기'와 '내 정보 입력하기' 두 버튼(2026-11-23 사용자 요청). 미리보기(화면 예시)에는 버튼이 없다
    expect(page.locator('h1.hero')).to_contain_text('공고는 저희가 읽을게요')
    assert page.locator('main button').count() == 2 and page.locator('.peek button').count() == 0
    expect(page.locator('[data-a=demo]')).to_have_text('데모 계정으로 시작하기')
    expect(page.locator('[data-a=start]')).to_have_text('내 정보 입력하기')
    assert '민지' not in page.locator('main').inner_text()                         # 시작 화면에 가상 인물 이름을 적지 않는다
    colors = page.evaluate("['demo','start'].map(a=>getComputedStyle(document.querySelector(`[data-a=${a}]`)).backgroundColor)")
    assert colors == ['rgb(255, 255, 255)', 'rgb(254, 230, 80)'], colors          # 데모 계정은 흰색, 내 정보 입력하기는 노란색
    assert page.evaluate("(()=>{const m=document.querySelector('main');return m.scrollHeight<=m.clientHeight})()")   # 시작 화면은 스크롤 없이 한 화면에 들어간다
    # 새 정보 입력에서 이름을 적고 저장하면 홈에 그 이름이 나온다
    page.locator('[data-a=start]').click()
    assert '체험' not in page.locator('main').inner_text()
    page.locator('#name').fill('민지')
    expect(page.locator('.pick > span').first).to_have_text('선택')             # 비어 있는 달 칸은 '선택'이라고 보인다
    page.locator('[data-a=save]').click()
    expect(page.locator('.greeting')).to_contain_text('민지 님')
    # 나머지 흐름은 가상 인물의 정보를 넣어 두고 '기존 정보로 계속 이용'으로 이어 간다
    page.evaluate('p=>localStorage.setItem("youth-desk-profile",JSON.stringify(p))', PROFILE)
    page.reload(wait_until='networkidle')
    expect(page.locator('.login-two')).to_be_visible()                            # 계속 이용 아래에 데모 계정으로 시작하기 · 내 정보 입력하기
    page.locator('[data-a=continue]').click()
    expect(page.locator('.greeting')).to_contain_text('민지 님')
    assert '지금 할 일' not in page.locator('main').inner_text()
    # 도움말: 알림 옆의 버튼을 누르면 이용 방법이 나오고, 확인을 누르면 닫힌다
    page.locator('header [data-a=help]').click()
    expect(page.locator('.sheet')).to_contain_text('이렇게 이용해요')
    expect(page.locator('.sheet li')).to_have_count(5)
    assert page.evaluate(FITS)
    page.locator('.sheet [data-a=closehelp]').click()
    expect(page.locator('.sheet')).to_have_count(0)
    expect(page.locator('.pill.ok').first).to_contain_text('맞아요')
    assert '조건 맞아요' not in page.locator('main').inner_text()
    assert page.evaluate(FITS)
    page.screenshot(path=str(BASE / '.local/mobile-home.png'))

    # 홈 '나에게 필요한 지원': 종류를 누르면 그 종류로 거른 정책 목록으로 간다(챗봇이 아니다)
    assert page.locator('.category').all_inner_texts() == ['일자리', '주거', '교육 · 훈련', '자격증']
    for i, kind in enumerate(['일자리', '주거', '교육 · 훈련', '자격증 · 시험']):
        page.locator('.category').nth(i).click()
        expect(page.locator('.chip.on')).to_have_text(kind)
        expect(page.locator('.browse-item').first).to_be_visible()
        page.locator('nav [data-s=home]').click()

    # 챗봇으로 찾기
    ai = page.evaluate("fetch('/api/health').then(r=>r.json()).then(d=>d.llm.ready)")
    started = time.monotonic()
    page.evaluate("openChat(TOPICS['자격증 응시료'])")
    page.locator('[data-a=results]').wait_for(timeout=120000)
    ai_seconds = round(time.monotonic() - started, 1)
    expect(page.locator('.m.bot').last).to_contain_text('관련 정책')
    assert '다시 묻지 않을게요' not in page.locator('main').inner_text()
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
    expect(page.locator('main h3').filter(has_text='지원 조건')).to_be_visible()
    text = page.locator('main').inner_text()
    assert '조건 대조' not in text and '내 정보:' not in text and '공식 사이트' not in text
    assert text.index('지원 내용') < text.index('지원 조건')                    # 지원 내용이 먼저
    # '공식 공고' 버튼은 항상 주소가 있다
    assert page.locator('.act a.btn').get_attribute('href').startswith('https://')
    # 신청기간 줄은 맨 위에 판정 없이 표시만(회색) 나오고, 누르면 오늘 날짜와 '표시만' 안내가 보인다
    expect(page.locator('[data-a=sheet]').first).to_contain_text('신청기간')
    assert page.locator('[data-a=sheet]').first.locator('.pill.gray').count() == 1
    page.locator('[data-a=sheet]').first.click()
    expect(page.locator('.sheet')).to_contain_text('표시만 해요')
    expect(page.locator('.sheet')).to_contain_text('오늘 ' + page.evaluate('today()')[2:].replace('-', '.'))
    page.locator('.sheet button[data-a=closesheet]').click()
    page.locator('[data-a=sheet]').nth(1).click()
    expect(page.locator('.sheet')).to_contain_text('지원 조건')
    assert '위치' not in page.locator('.sheet').inner_text()                    # 팝업에 '위치' 줄은 보여 주지 않는다
    assert '정보 수집일' not in page.locator('.sheet').inner_text()                # 팝업에는 수집일을 보여 주지 않는다
    page.screenshot(path=str(BASE / '.local/mobile-detail.png'))
    page.locator('.sheet button[data-a=closesheet]').click()
    page.locator('[data-a=back]').click()

    # 정책 2개 선택 → 신청 계획 → 점검 → 승인 → 내 신청
    page.locator('input[data-a=sel]').nth(0).check()
    page.locator('input[data-a=sel]').nth(1).check()
    expect(page.locator('.act')).to_contain_text('2개 선택')
    page.locator('[data-a=plan]').click()
    expect(page.locator('.ord li')).to_have_count(2)
    assert page.locator('main h3').filter(has_text='고른 정책').count() == 0     # '고른 정책' 칸은 없다
    assert '신청 순서' not in page.locator('main').inner_text()
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
    assert '문의 문구' not in page.locator('main').inner_text() and '공식 사이트' not in page.locator('main').inner_text()                 # 고른 정책마다 공식 사이트 링크
    assert page.locator('.act a.btn').inner_text() in ('공식 신청 페이지로 이동', '공식 공고로 이동', '온통청년 공고로 이동')
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

    # 새로고침 뒤: 첫 화면에서 '기존 정보로 계속 이용'을 누르면 복원
    page.reload(wait_until='networkidle')
    expect(page.locator('[data-a=start]')).to_have_text('내 정보 입력하기')
    page.locator('[data-a=continue]').click()
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
    # 준비 완료: 계획을 펼쳐 '준비 완료로 옮기기'를 누르면 '준비 완료' 칸으로 옮겨지고 공식 사이트 버튼이 보인다. 체크를 하나 풀면 다시 준비 중으로 돌아간다.
    expect(page.locator('main')).to_contain_text('2건 준비 중')
    expect(page.locator('.ready-card')).to_have_count(0)
    page.locator('.plan-card summary').first.click()
    expect(page.locator('.plan-card[open]')).to_contain_text('개도 완료로 표시돼요')
    page.locator('.plan-card[open] [data-a=ready]').click()
    expect(page.locator('.ready-card')).to_have_count(1)
    expect(page.locator('#toast')).to_contain_text('준비 완료')
    expect(page.locator('main')).to_contain_text('1건 준비 중')
    expect(page.locator('.ready-card')).to_contain_text('모두 완료')
    expect(page.locator('.ready-card')).to_contain_text('공식 사이트')       # 안내 문장은 접수 상태에 따라 다르다(접수 중이면 '신청하세요', 끝났으면 '다음 모집 여부 확인')
    assert page.locator('.ready-card a.btn[href^="https://"]').count() >= 1
    assert page.locator('.ready-card [data-a=ready]').count() == 0
    assert page.evaluate(FITS)
    page.locator('.ready-card input[data-a=task]').first.uncheck()
    expect(page.locator('.ready-card')).to_have_count(0)
    expect(page.locator('#toast')).to_contain_text('내가 세운 신청 계획')
    expect(page.locator('.plan-card')).to_have_count(2)

    # 공식 페이지에서 보완한 정보(사람 검수 전) 표시
    page.evaluate("openDetail('20261106005400214758')")
    expect(page.locator('main')).to_contain_text('공식 페이지에서 보완한 정보')
    expect(page.locator('main')).to_contain_text('사람 검수 전')
    # 조건 줄은 '지원 조건'으로 나오고, 보완 기록마다 출처에서 문장을 확인했는지 표시가 붙는다
    expect(page.locator('main')).to_contain_text('지원 조건')
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
    page.locator('[data-a=continue]').click()
    page.locator('nav [data-s=profile]').click()
    expect(page.locator('select[data-k=income_band]')).to_have_value('100')
    assert page.evaluate("JSON.parse(localStorage.getItem('youth-desk-profile')).income_band") == 100
    page.locator('[data-a=logout]').click()
    expect(page.locator('h1.hero')).to_be_visible()
    assert page.locator('[data-a=continue]').count() == 0                      # 정보를 지우면 '계속 이용'이 없다
    # 로그아웃 뒤에도 데모 계정으로 다시 들어갈 수 있다(가상 인물 민지의 정보가 그대로 들어간다)
    page.locator('[data-a=demo]').click()
    expect(page.locator('.greeting')).to_contain_text('민지 님')
    expect(page.locator('.greeting')).to_contain_text('미추홀구')
    demo = page.evaluate("JSON.parse(localStorage.getItem('youth-desk-profile'))")
    assert {k: demo[k] for k in ('name', 'birth', 'sido', 'region_code', 'job_code', 'housing')} == {k: PROFILE[k] for k in ('name', 'birth', 'sido', 'region_code', 'job_code', 'housing')}
    assert demo['exams'] == PROFILE['exams'], demo['exams']                       # 지난달 정보처리기사 응시
    page.reload(wait_until='networkidle')
    expect(page.locator('[data-a=continue]')).to_be_visible()                     # 정보가 있으면 계속 이용 · 데모 계정으로 시작하기 · 내 정보 입력하기
    expect(page.locator('.login-two [data-a=demo]')).to_have_text('데모 계정으로 시작하기')
    assert page.evaluate("[...document.querySelectorAll('.login-actions .btn')].every(b=>b.scrollWidth<=b.clientWidth)")   # 버튼 글이 잘리지 않는다
    assert page.evaluate(FITS)

    # 넓은 화면에서도 앱 폭을 유지한다.
    page.set_viewport_size({'width': 1280, 'height': 900})
    assert page.locator('#app').evaluate('(e)=>e.getBoundingClientRect().width<=430')
    assert not errors, errors
    print(json.dumps({'passed': True, 'url': URL, 'ai_ready': ai, 'ai_seconds': ai_seconds, 'saved_tasks': saved,
                      'restore_after_reload': True, 'mobile_no_overflow': True, 'page_errors': errors}, ensure_ascii=False))
    browser.close()
