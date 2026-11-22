"""새 앱 화면의 예외 상황 확인. 실행 중인 서버와 실제 4,020건 DB가 필요하다(수동 실행, pytest가 모으지 않는다).

    $env:APP_URL='http://127.0.0.1:8765'; .venv\\Scripts\\python.exe -X utf8 tests\\browser_mobile_edges.py

기본 흐름은 browser_mobile_smoke.py 가 본다. 여기서는 실제 사용에서 깨지기 쉬운 곳만 본다:
글꼴 서버 차단(인터넷 없음), 내 정보 없이 시작, 정책 5개 선택 제한, 뒤로 가기, 잘못된 나이, 새로고침 뒤 선택 유지, 넓은 화면.
AI는 쓰지 않는다. 저장(승인)은 하지 않는다.
"""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = Path(__file__).resolve().parents[1]
URL = os.environ.get('APP_URL', 'http://127.0.0.1:8000')
FITS = 'document.documentElement.scrollWidth<=window.innerWidth+1'
done = []

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    context = browser.new_context(viewport={'width': 360, 'height': 740})        # 작은 폰
    context.route('**/fonts.googleapis.com/**', lambda route: route.abort())      # 인터넷이 없는 상황
    context.route('**/fonts.gstatic.com/**', lambda route: route.abort())
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(URL, wait_until='networkidle')

    # 1) 글꼴 서버가 막혀도 화면과 아이콘이 나온다
    expect(page.locator('h1.hero')).to_be_visible()
    page.locator('[data-a=start]').click()
    assert page.locator('header .ms svg').count() == 1 and page.evaluate(FITS)
    done.append('fonts_blocked_still_renders')

    # 2) 말이 안 되는 출생 연월은 저장하지 않고, 아무것도 고르지 않으면 정보 없이 시작한다
    page.locator('#birth').fill('1800-01')
    page.locator('[data-a=save]').click()
    expect(page.locator('#toast')).to_contain_text('출생 연월')
    assert page.evaluate("localStorage.getItem('youth-desk-profile')") is None
    page.locator('#birth').fill('')
    page.locator('[data-a=save]').click()
    expect(page.locator('.greeting')).to_contain_text('체험 사용자')
    expect(page.locator('main')).to_contain_text('내 정보를 입력하면 맞는 지원부터 보여드려요')
    done.append('invalid_age_rejected_and_empty_profile_ok')

    # 3) 내 정보가 없으면 '맞아요/달라요' 표시 없이 전체를 보여 준다
    page.locator('nav [data-s=browse]').click()
    expect(page.locator('.browse-item').first).to_be_visible()
    expect(page.locator('main > p.tiny').first).to_contain_text('정책')
    assert page.locator('.pill.ok').count() == 0 and page.locator('.pill.bad').count() == 0
    assert page.evaluate(FITS)
    done.append('no_profile_no_judgement_labels')

    # 4) 정책은 5개까지만 함께 준비할 수 있다(팀 화면처럼 상세의 '이 정책 준비하기'로 고른다)
    for i in range(5):
        page.locator('.browse-item').nth(i).click()
        page.locator('[data-a=prep]').click()
        expect(page.locator('.ord li').first).to_be_visible()
        page.locator('[data-a=back]').click()                      # 신청 계획 → 상세
        page.locator('[data-a=back]').click()                      # 상세 → 지원 찾기
        expect(page.locator('.browse-item').first).to_be_visible()
    expect(page.locator('.act')).to_contain_text('5개 선택')
    page.locator('.browse-item').nth(5).click()
    page.locator('[data-a=prep]').click()
    expect(page.locator('#toast')).to_contain_text('5개까지')
    page.locator('[data-a=back]').click()
    # '이 정책 준비하기'로 들어온 신청 계획은 그 정책 하나만 보여 준다. 전에 고른 정책은 '함께 보기'를 눌러야 나온다(고른 목록은 그대로 5개)
    page.locator('.browse-item').nth(4).click()
    page.locator('[data-a=prep]').click()
    expect(page.locator('[data-a=all]')).to_contain_text('고른 정책 5개 함께 보기')
    expect(page.locator('.ord li')).to_have_count(1)
    page.locator('[data-a=all]').click()
    expect(page.locator('.ord li')).to_have_count(5)
    page.locator('[data-a=back]').click()
    page.locator('[data-a=back]').click()
    expect(page.locator('.browse-item').first).to_be_visible()
    done.append('five_policy_limit')

    # 5) 상세 → 뒤로 가도 목록과 선택이 그대로다. 새로고침해도 선택이 남는다.
    first = page.locator('.browse-item strong').first.inner_text()
    page.locator('.browse-item').first.click()
    expect(page.locator('main')).to_contain_text('지원 조건')
    expect(page.locator('main')).to_contain_text('내 정보를 입력하면 조건을 비교해 드려요')
    page.locator('[data-a=back]').click()
    expect(page.locator('.browse-item strong').first).to_have_text(first)
    expect(page.locator('.act')).to_contain_text('5개 선택')
    page.reload(wait_until='networkidle')
    page.locator('[data-a=continue]').click()
    page.locator('nav [data-s=plan]').click()
    # 내 신청 탭은 세운(저장한) 계획만 보여 준다. 고르기만 한 정책은 '이어서 만들기'로 신청 계획 화면에서 이어 간다.
    expect(page.locator('main')).to_contain_text('아직 세운 신청 계획이 없어요')
    expect(page.locator('main')).to_contain_text('고른 정책 5개')
    page.locator('main [data-a=plan]').click()
    expect(page.locator('.ord li').first).to_be_visible()
    assert page.locator('.ord li').count() == 5 and page.evaluate(FITS)
    page.screenshot(path=str(BASE / '.local/mobile-edge-plan.png'))
    done.append('back_and_reload_keep_selection')

    # 6) 계획에서 하나씩 빼면 줄어들고, 저장은 일어나지 않는다
    page.locator('[data-a=unsel]').first.click()
    expect(page.locator('.ord li')).to_have_count(4)
    assert page.evaluate("fetch('/api/desk/workspaces/'+localStorage.getItem('youth-desk-workspace')).then(r=>r.json()).then(d=>d.tasks.length)") == 0
    done.append('remove_from_plan_without_saving')

    # 7) 넓은 화면에서도 폰 크기를 유지하고, 가로 화면에서도 넘치지 않는다
    page.set_viewport_size({'width': 1440, 'height': 900})
    assert page.locator('#app').evaluate('(e)=>e.getBoundingClientRect().width<=430')
    page.set_viewport_size({'width': 740, 'height': 360})
    assert page.evaluate(FITS)
    done.append('wide_and_landscape')

    assert not errors, errors
    print(json.dumps({'passed': True, 'url': URL, 'checks': done, 'page_errors': errors}, ensure_ascii=False))
    browser.close()
