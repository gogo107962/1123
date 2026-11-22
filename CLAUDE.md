# 청년비서 (Youth Secretary)

2026 대한민국 청년 CAREER FAIR AI 해커톤(대한상공회의소) 제출용 서비스. 제출 마감 **2026-11-23 17:00 KST**, 마감 뒤에는 기능·알고리즘·프롬프트·데이터 변경 금지.
청년이 고른 정책의 조건·중복 수혜 제한·서류를 공식 공고 근거로 확인하고, 사용자가 승인한 준비 작업을 DB에 저장·관리한다.

**먼저 읽을 것:** `youth_secretary_ready/VALIDATION.md`의 v0.9~v0.56(11/17~19에 한 일과 검증 범위, 가장 최신) → `HANDOFF_2026-11-17/08_ClaudeCode_이어하기.md` → `HANDOFF_2026-11-17/01_상세인계서.md` → `03_이어할작업과검증.md`. 팀원 작업 요약은 `HANDOFF_2026-11-17/팀원_작업공유_2026-11-17.html`.

## 내 역할
데이터 구조화와 판별 엔진. 화면·배포·제출 문서는 팀원 영역일 수 있으니 손대기 전에 확인한다.

## 구조
- 앱: `youth_secretary_ready/` — FastAPI + SQLite + Vanilla JS + 로컬 Ollama(`qwen3:4b`). 새 프레임워크 도입·전면 재작성 금지.
- 화면: `/`·`/desk` 앱 화면(`static/mobile.*`, 팀 화면 파일 `1119_청년비서_앱.html`과 `청년비서 서비스 이해 자료.html` 기준), `/classic` 이전 소비자 화면, `/lab` 가상 정책 규칙 엔진 시연.
- 사람 검수 `/review`(`review_service.py`): 초안 `data/policy_drafts/` → 사람이 승인 → `data/policies/`. 운영 안내 `OPERATIONS.md`, 제출 재료 `docs/SUBMISSION_DRAFT.md`.
- 대화 오케스트레이터(대화로 찾기) `desk_finder.py`(로컬 모델이 검색어와 부를 도구를 고르고 판별 엔진 → 충돌·순서 플래너 `planner.py` · 서류 준비판 `docboard.py` → 질문 선택기로 잇는다. 도구 선택 평가 `tests/live_orchestrator_eval.py`), 서류 준비판 `docboard.py`, 신청 계획 `desk_plan.py`, 충돌·순서 플래너 `planner.py`(함께 받기 어려울 수 있는 조합·신청 순서와 이유·조합별 금액, `/api/desk/workspaces/{wid}/planner`), 서류 준비판 `docboard.py`(서류 합치기·가진 것과 없는 것·준비 순서와 발급처, `/api/desk/workspaces/{wid}/docboard`), 데이터 점검 `tools/audit_data.py` → `data/DATA_AUDIT.md`, 파일끼리 정합성 `tools/check_data.py`, 공식 링크 점검 `tools/check_links.py` → `data/link_checks.json`(404인 주소는 앱에서 뺀다), 구조화·판별 범위(퍼센트) `tools/coverage.py` → `data/COVERAGE.md`, 시군구 공식 이름표 `data/region_sigungu_official.json`, API 필드 뜻의 근거 `data/api_field_notes.json`, 검색으로 채운 데이터 정리 `tools/supplement_report.py` → `data/SUPPLEMENTS.md`, 인용 문장 자동 대조 `tools/verify_supplements.py` → `data/supplement_checks.json`, 공식 페이지 보완 기록 `data/supplements.json`(수집 원문과 분리, 사람 검수 전).
- 데이터: 온통청년 수집 3,995건(2026-11-19 재수집. `ontong_candidates`에는 API에서 사라진 37건이 남아 있고 `ontong.CURRENT`로 뺀다), 승인 정책은 가상 3개, 실제 정책 초안 3개는 `draft`.
- 판별 두 층: `engine.py`(사람 검수로 승인된 정책의 실제 판정) / `screening.py`+`policy_structure.py`(API 기재값 1차 걸러보기, 자격 판정 아님).

## 실행 (Windows PowerShell, `youth_secretary_ready` 안에서)
```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q      # 임시 DB 사용, 약 50초
.\.venv\Scripts\python.exe -X utf8 start.py           # http://127.0.0.1:8000
.\run_ollama.ps1                                      # AI가 필요할 때만
```

## 지켜야 할 원칙
- 서비스의 끝은 공식 홈페이지로 넘기는 것이다(2026-11-19 사용자 정리). 판정은 신청 준비를 돕는 비교이고 자격 확정이 아니다. 실제 정책을 사람이 승인하는 것은 완성 기준이 아니다. 판별 엔진의 완성 기준 다섯 가지와 잰 값은 `data/COVERAGE.md` 3장에 있다.
- unknown은 false가 아니다. 빈값·0·미기재를 "제한 없음/상시/서류 불필요"로 바꾸지 않는다.
- API 수집값은 공고 원문과 다를 수 있다(팀 대조 45건 중 32건 불일치). API 값만으로 자격을 확정하지 않는다.
- 실제 정책은 사람 검수 없이 `approved`로 올리지 않는다. 검수자·검수일을 지어내지 않는다.
- A→B 제한을 B→A로 뒤집어 적용하지 않는다. 확인일과 접수일을 섞지 않는다. 다음 모집일을 추정하지 않는다.
- 준비 작업은 사용자 승인 뒤에만 DB에 저장한다. AI는 자동 저장하지 않는다.
- AI는 로컬 Ollama가 기본이다. 유료·외부 AI로 자동 전환하지 않는다. 로컬 모델을 둘 수 없는 공개 배포 서버에서만 `AI_PROVIDER=gemini`를 직접 켜서 Gemini의 무료 구간 모델을 쓴다(2026-11-22 사용자 결정, `OPERATIONS.md` 3-1). 실제 개인정보를 받지 않는다(가상 프로필만).
- `.local/ontong_api_key.txt`의 내용을 읽거나 출력·로그·Git에 남기지 않는다.
- `data/youth_secretary.sqlite3`(실행 DB)를 덮어쓰거나 초기화하지 않는다. 다시 수집하는 것은 사용자가 요청할 때만 하고(2026-11-19 요청으로 한 번 재수집), 하기 전에 DB를 `.local/backup/`에 백업한다.
- 검증하지 않은 것을 통과로 적지 않는다. 모의 테스트와 실제 모델·브라우저 검증을 구분해 기록한다.
- 제출·이메일 발송은 명시적으로 요청받았을 때만 한다.
- Git은 작업이 끝나면 묻지 않고 커밋해서 `origin main`에 푸시한다(2026-11-18 사용자 지시). 올리기 전에 전체 테스트 통과와, 비밀·로컬 파일(`.local/`, `data/exports/`, `.venv/`, 실행 DB의 새 변경)이 섞이지 않았는지 확인한다. 테스트가 실패하면 올리지 않고 알린다. 작업 도중의 중간 상태는 올리지 않는다. 강제 푸시와 기록 고쳐 쓰기는 하지 않는다.
- 저장소는 `github.com/trewqyu/1123`(브랜치 `main`, 2026-11-18 첫 푸시)이고 수집 원문(`data/exports/`)·`.local/`·`.venv/`는 올리지 않는다. 실행 DB(`data/youth_secretary.sqlite3`)는 다른 사람이 키 없이 바로 열 수 있게 2026-11-22 사용자 지시로 올렸다. 그 뒤 이 PC에서 생긴 DB 변경은 다시 올리지 않는다(사용자가 요청할 때만).
