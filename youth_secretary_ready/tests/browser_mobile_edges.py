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
    expect(page.locator('.greeting')).to_contain_text('반가워요')
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
        expect(page.locator('h2.h20')).to_be_visible()                   # 계획(서류가 있을 때) 또는 신청 전 점검(서류가 없을 때)의 머리
        page.locator('[data-a=back]').click()                      # 신청 계획 → 상세
        page.locator('[data-a=back]').click()                      # 상세 → 지원 찾기
        expect(page.locator('.browse-item').first).to_be_visible()
    expect(page.locator('.act')).to_contain_text('5개 선택')
    page.locator('.browse-item').nth(5).click()
    page.locator('[data-a=prep]').click()
    expect(page.locator('#toast')).to_contain_text('5개까지')
    page.locator('[data-a=back]').click()
    # '이 정책 준비하기'로 들어온 신청 계획은 그 정책 하나만 보여 준다. 전에 고른 정책은 '함께 보기'를 눌러야 나온다(고른 목록은 그대로 5개)
    # 서류를 하나도 찾지 못한 정책은 빈 계획 화면을 건너뛰고 바로 '신청 전 점검'으로 가고, 공식 신청 페이지를 확인하라는 카드가 나온다
    nodoc = page.evaluate("(async()=>{for(const [i,x] of S.list.items.slice(0,5).entries()){const r=await fetch(space('/plan'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({external_ids:[x.external_id]})}).then(r=>r.json());if(!r.documents.length)return i}return -1})()")
    withdoc = page.evaluate("(async()=>{for(const [i,x] of S.list.items.slice(0,5).entries()){const r=await fetch(space('/plan'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({external_ids:[x.external_id]})}).then(r=>r.json());if(r.documents.length)return i}return -1})()")
    assert nodoc >= 0 and withdoc >= 0, (nodoc, withdoc)
    page.locator('.browse-item').nth(nodoc).click()
    page.locator('[data-a=prep]').click()
    expect(page.locator('header h1')).to_have_text('신청 전 점검')
    expect(page.locator('main')).to_contain_text('제출서류는 공식 신청 페이지에서 확인해 주세요')
    expect(page.locator('main')).to_contain_text('서류가 필요 없다는 뜻이 아니에요')
    assert page.locator('main .card a.btn[href^="https://"]').count() >= 1
    assert '서류 0종 중 0종 준비' not in page.locator('main').inner_text()          # 서류 줄 대신 위 카드가 안내한다
    page.locator('[data-a=back]').click()                          # 계획 화면을 쌓지 않았으므로 뒤로 가면 상세
    expect(page.locator('[data-a=prep]')).to_be_visible()
    page.locator('[data-a=back]').click()
    expect(page.locator('.browse-item').first).to_be_visible()
    done.append('no_documents_skip_to_check')
    page.locator('.browse-item').nth(withdoc).click()
    page.locator('[data-a=prep]').click()
    expect(page.locator('[data-a=all]')).to_contain_text('고른 정책 5개 함께 보기')
    expect(page.locator('.plan-head h2')).not_to_contain_text('신청 준비')     # 정책 하나면 머리에 그 정책 이름
    assert page.locator('.ord li').count() == 0
    page.locator('[data-a=all]').click()
    expect(page.locator('.plan-head h2')).to_have_text('정책 5개 신청 준비')
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
    # 승인하지 않은 5건은 '임시저장'에 정책별 카드로 나온다. 카드를 펼쳐 '신청 계획 이어서 하기'로 간다.
    expect(page.locator('main')).to_contain_text('임시저장')
    expect(page.locator('.draft-card')).to_have_count(5)
    page.locator('.draft-card summary').first.click()
    page.locator('.draft-card[open] [data-a=plan]').click()
    expect(page.locator('.ord li').first).to_be_visible()
    assert page.locator('.ord li').count() == 5 and page.evaluate(FITS)
    page.screenshot(path=str(BASE / '.local/mobile-edge-plan.png'))
    done.append('back_and_reload_keep_selection')

    # 6) 신청 계획 머리에 어떤 정책인지 나오고(여럿이면 'N개 신청 준비'와 목록), 빼기 버튼은 없다. 저장은 일어나지 않는다.
    expect(page.locator('.plan-head h2')).to_have_text('정책 5개 신청 준비')
    expect(page.locator('.plan-head')).to_contain_text('기준일')
    assert page.locator('[data-a=unsel]').count() == 0
    assert page.evaluate("fetch('/api/desk/workspaces/'+localStorage.getItem('youth-desk-workspace')).then(r=>r.json()).then(d=>d.tasks.length)") == 0
    done.append('plan_header_without_remove_and_no_saving')

    # 6-2) 내 신청의 임시저장 카드에서 하나를 지우면 4건이 되고, 서버에는 여전히 저장된 것이 없다
    page.locator('[data-a=back]').click()                      # '이어서 하기'로 들어온 계획에서 뒤로 가면 '내 신청' 탭으로 돌아간다
    expect(page.locator('header h1')).to_have_text('내 신청')
    expect(page.locator('.draft-card')).to_have_count(5)
    if page.locator('.draft-card').first.get_attribute('open') is None:   # 앞에서 펼친 카드는 펼친 채로 남아 있다
        page.locator('.draft-card summary').first.click()
    page.locator('.draft-card').first.locator('[data-a=deldraft]').click()
    expect(page.locator('.draft-card')).to_have_count(4)
    expect(page.locator('#toast')).to_contain_text('임시저장한 계획을 지웠어요')
    assert len(page.evaluate("JSON.parse(localStorage.getItem('youth-desk-selected'))")) == 4
    assert page.evaluate("fetch('/api/desk/workspaces/'+localStorage.getItem('youth-desk-workspace')).then(r=>r.json()).then(d=>d.tasks.length)") == 0
    done.append('delete_draft_plan')

    # 7) 넓은 화면에서도 폰 크기를 유지하고, 가로 화면에서도 넘치지 않는다
    page.set_viewport_size({'width': 1440, 'height': 900})
    assert page.locator('#app').evaluate('(e)=>e.getBoundingClientRect().width<=430')
    page.set_viewport_size({'width': 740, 'height': 360})
    assert page.evaluate(FITS)
    done.append('wide_and_landscape')

    assert not errors, errors
    print(json.dumps({'passed': True, 'url': URL, 'checks': done, 'page_errors': errors}, ensure_ascii=False))
    browser.close()
