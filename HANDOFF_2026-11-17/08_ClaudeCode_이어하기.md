# Claude Code에서 이어하기

작성: 2026-11-17 22:40 KST. 앞선 인계 문서(00~07) 이후의 변경과 다음 할 일. 충돌하면 이 문서와 실제 코드가 우선.

## 이번 세션에서 확인한 것
- 전체 pytest: **147 passed** (약 50초). Linux/Python 3.10 별도 환경, 임시 DB. 아래 변경을 넣은 뒤에도 147 passed. Windows `.venv`(Python 3.13)에서는 아직 다시 돌리지 않았다.
- 실행 DB는 읽기 전용으로만 열었다. 행 수는 `04_현재상태.json`과 일치, integrity ok.
- 새 앱 UI(`desk-app.css`, 하단 탭)는 **여전히 브라우저 검증 전**이다.

## 이번 세션에서 바꾼 것 (모두 `youth_secretary_ready/`)
| 파일 | 내용 |
|---|---|
| `policy_codes.py` | 코드표 표기 `bizPrdSecd`와 API 필드 `bizPrdSeCd`의 대소문자 차이 때문에 사업기간 코드가 해석되지 않던 문제 수정(`api_field`). `describe()`에 `api_field`, `collected` 추가 |
| `data/region_sido.json` (신규) | 시도 코드 16개 → 이름. 근거와 한계 포함. 12=전남광주통합특별시 |
| `policy_structure.py` (신규) | API 필드 구조화: 나이, 신청기간 창, 지역 코드, 소득, 취업·학력·전공·결혼 코드, 신청 경로. `period_status()`, `tier()` |
| `screening.py` (신규) | 가상 프로필 대 API 기재값 걸러보기. 기준별 match/mismatch/unknown/skipped, 종합 api_match/needs_check/api_mismatch. 읽기 전용 |
| `app.py` | `GET /api/integrations/ontong/regions`, `POST /api/integrations/ontong/screen` 추가 |
| `ontong.py` | `review_bundle()` 응답에 `structured`, `period_status`, `tier` 추가 |

**새 코드에 대한 테스트는 아직 없다.** 기존 147개가 깨지지 않았다는 것과 실제 DB 사본으로 한 번 돌려 본 것이 전부다.

실제 데이터로 돌려 본 결과(2026-11-17 기준일, DB 사본):
- 갈래: 걸러보기 가능 686 / 원문 링크만 3,334 / 검수 통과 0
- 프로필(26세, 서울 강북구 `11305`, 미취업자) → API 일치 21 / 확인 필요 109 / API 불일치 556
- 4,020건 전체 처리 약 0.5초

## 팀원 작업과의 관계
팀원은 별도 작업 폴더에서 데이터 진단을 했다(요약: `팀원_작업공유_2026-11-17.html`). 그쪽 파일은 이 폴더에 없다.
- 팀원 수집 4,016건(11/17) 대 이 폴더 4,020건(11/16). 소득 무관 3,449 대 3,451, 상시 1,115 대 1,114로 거의 같다.
- 팀원 "쓸 수 있는 정책 662건(A 244·B 418)" 대 이 폴더 `tier()` 686건. 기준이 비슷하지만 같지 않다. 팀원 기준에는 승인 상태가 들어가는데 이 폴더는 그 필드(`plcyAprvSttsCd`)를 수집하지 않았다. A/B 구분 정의는 팀원 문서를 봐야 한다.
- 팀원의 세 갈래(검수 통과 / 기준 통과 / 기준 미통과)는 `tier()`의 reviewed / screenable / link_only에 대응시켰다.
- 팀원이 못 찾았다는 서울 청년월세 2026 공고는 이 폴더에 있다: `data/POLICY_REVIEW.md`, `data/policies/seoul_rent_2026.json`.
- 어느 쪽 코드를 제출본의 기준으로 삼을지는 팀이 정해야 한다. 아직 정해지지 않았다.

## 다음 할 일 (역할: 데이터 구조화 + 판별 엔진)
1. **새 코드 테스트 작성.** `tests/test_codes.py`: `03_이어할작업과검증.md` P0-1 표(선행 0, 복수 jobCd, `0013001`과 `00130010` 구분, 미등록 코드 보존, 빈값, 복합 필터, 422, 필터 초기화, 상시는 접수 확정 아님, 읽기 부작용 없음). `tests/test_structure.py`: 나이 0/빈값, 기간 경계일, `\N`으로 이어진 복수 기간, 전국+지자체 주관, 시도만 입력, 코드표 밖 프로필 값 422, 걸러보기가 DB에 쓰지 않음.
2. **팀원 파일 연결.** `data/region_codes.json`(시군구 이름) → `/regions`와 걸러보기 지역 표시. `data/final_candidates.json`(26건) → `data/policies/`의 `draft` 정책 JSON으로 변환하는 스크립트. 근거 문장과 출처 주소를 `sources[].excerpt/url`로 옮기고 `verified=false` 유지.
3. **갈래 기준 맞추기.** 팀원의 A/B 정의를 받아 `tier()`와 차이를 줄이거나, 다른 이유를 문서로 남긴다.
4. **소득.** 연소득 48건의 금액(예: 5000, 5532)이 만원 단위로 보이지만 근거가 없다. 팀원 대조 결과에서 단위가 확인되면 그 정책만 비교 가능으로 바꾼다.
5. **검수 통과 정책 만들기.** 사람 검수가 끝난 후보를 `approved`로 올리면 `engine.py`가 충돌·서류 판정을 한다. 그때 `source_checks.json`의 `policy_code`로 수집 정책과 연결된다.
6. 걸러보기 결과를 화면에 붙이는 일과 새 앱 UI 브라우저 검증은 담당을 팀과 확인한 뒤 진행.
7. 문서 갱신: `VALIDATION.md`에 이번 147 passed와 새 모듈의 검증 범위를 사실대로 추가.

## 주의
- 이번 세션의 Python 3.10 실행으로 `__pycache__`에 `cpython-310` 파일이 일부 생겼을 수 있다. `.gitignore` 대상이며 지워도 된다.
- 팀원 숫자와 이 폴더 숫자를 발표 자료에서 섞어 쓰지 않는다. 수집일과 기준이 다르다.
