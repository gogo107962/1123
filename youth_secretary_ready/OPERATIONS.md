# 청년비서 운영 안내 (2026-11-18)

앱을 켜고, 정책을 검수해 승인하고, 다른 사람이 접속하게 할 때 필요한 것만 적었다. 검증 기록은 [VALIDATION.md](VALIDATION.md), 화면 사용법은 [SERVICE_GUIDE.md](SERVICE_GUIDE.md)에 있다.

## 1. 켜기

```powershell
.\run_ollama.ps1                                   # 로컬 AI. 끝에 오류처럼 보이는 줄이 나와도 서버는 뜬다
.\.venv\Scripts\python.exe -X utf8 start.py        # http://127.0.0.1:8000
```

- `/` 앱 화면, `/review` 정책 검수, `/classic` 이전 화면, `/lab` 가상 정책 시연.
- AI가 꺼져 있어도 앱은 동작한다. 챗봇은 정해 둔 낱말로 찾고 화면에 그렇게 표시한다.

## 2. 정책 검수와 승인 (사람이 하는 일)

앱의 결과는 기본적으로 "API 기재값 기준"이다. 사람이 공고와 대조해 승인한 정책만 "검수 완료"로 표시되고 규칙 엔진(`engine.py`)이 판정한다.

1. 초안 만들기: `.\.venv\Scripts\python.exe -X utf8 tools\draft_policy.py <정책번호> ...` → `data/policy_drafts/`에 생긴다. 지금 11건이 있다.
2. 서버를 켠 PC에서 `http://127.0.0.1:8000/review`를 연다.
3. 초안을 고르고, 출처마다 링크를 열어 **원문에 있는 문장**을 확인한다. 문장을 고쳐 넣고 "직접 확인했습니다"에 체크한다.
4. 원문과 맞는 규칙만 남기고, 검수자 이름을 적고, 대조 확인에 체크한 뒤 승인한다.
5. 승인본은 `data/policies/<code>.json`에 저장되고 바로 엔진에 등록된다. 앱에서 그 정책이 "검수 완료"로 나온다.

- 확인하지 않은 출처와 그 출처에 기댄 규칙·서류는 승인본에서 빠진다. "사람이 따로 확인할 항목"은 남아서 앱에 "확인 필요"로 표시된다.
- 이름과 대조 확인 없이는 승인되지 않는다. 서버나 AI가 스스로 승인하지 않는다.
- 승인을 되돌리려면 `data/policies/`의 해당 파일에서 `review.status`를 `draft`로 바꾸고 서버를 다시 켠다.

## 3. 다른 사람이 접속하게 하기

지금 서버는 이 PC에서만 열린다(127.0.0.1). 로컬 AI를 쓰는 구조라 서버 PC가 켜져 있어야 한다. 방법은 팀이 정한다.

| 방법 | 필요한 것 | 주의 |
|---|---|---|
| 같은 공유기 안에서 접속 | `uvicorn app:app --host 0.0.0.0 --port 8000`으로 실행, 방화벽 허용 | 같은 네트워크의 누구나 접속한다 |
| 임시 공개 주소(터널) | 터널 프로그램 설치와 계정 | 주소를 아는 누구나 접속한다. PC를 끄면 닫힌다 |
| 시연 영상 + 현장 로컬 시연 | 없음 | 심사위원이 직접 눌러 볼 수 없다 |

밖에서 접속하게 할 때 지켜지는 것:

- 관리 기능(수집 실행, 정책 검수·승인)은 서버 PC에서만 된다. 다른 PC에서 쓰려면 환경 변수 `ADMIN_TOKEN`을 정하고 요청 헤더 `X-Admin-Token`에 같은 값을 넣는다.
- 요청 횟수 제한(주소별): 챗봇 1분에 20번, 준비 공간 만들기 1시간에 30개, 그 밖의 쓰기 1분에 300번. 넘으면 429로 거절한다. 서버 한 대의 메모리 기준이라 서버를 다시 켜면 초기화된다.
- 로컬 모델은 한 번에 한 질문만 처리한다. 겹치면 "AI가 다른 질문에 답하고 있어요"로 거절한다.
- 보안 헤더와 스크립트 실행 제한(CSP)이 켜져 있다.

지켜지지 않는 것(공개 운영 전에 필요):

- 로그인이 없다. 준비 공간은 브라우저에 저장된 식별자로만 구분한다.
- HTTPS를 직접 제공하지 않는다. 터널이나 앞단 서버가 맡아야 한다.
- 여러 대 서버, 장애 복구, 백업은 없다.

## 4. 데이터를 다시 점검할 때

```powershell
.\.venv\Scripts\python.exe -X utf8 tools\audit_data.py            # data/DATA_AUDIT.md
.\.venv\Scripts\python.exe -X utf8 tools\verify_engine.py         # 전체 데이터 판정 검증(복사본 사용)
.\.venv\Scripts\python.exe -X utf8 tools\build_region_names.py    # 시군구 이름표
.\.venv\Scripts\python.exe -X utf8 tools\build_region_sets.py     # 시도 전체 대상 기준표
.\.venv\Scripts\python.exe -X utf8 -m pytest -q                   # 단위 테스트
$env:APP_URL='http://127.0.0.1:8000'; .\.venv\Scripts\python.exe -X utf8 tests\browser_mobile_smoke.py   # 화면 기본 흐름
.\.venv\Scripts\python.exe -X utf8 tests\browser_mobile_edges.py  # 화면 예외
.\.venv\Scripts\python.exe -X utf8 tests\live_finder_eval.py      # 실제 AI 평가(로컬 모델 필요)
```

모든 도구는 실행 DB를 읽기 전용으로 열거나 복사해서 쓴다. 마감(2026-11-23 17:00) 뒤에는 기능·규칙·프롬프트·데이터를 바꾸지 않는다.

## 5. 저장소를 새로 받았을 때

2026-11-18에 GitHub 저장소를 빈 폴더에 받아 확인한 내용이다.

```powershell
cd youth_secretary_ready
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt "pytest>=8,<10"
.\.venv\Scripts\python.exe -X utf8 -m pytest -q        # 351개 통과
.\.venv\Scripts\python.exe -X utf8 start.py
```

- **정책 데이터는 저장소에 들어 있다.** 실행 DB(`data/youth_secretary.sqlite3`, 2026-11-19 수집 3,995건)를 2026-11-22에 올렸다. API 키 없이 받아서 바로 실행하면 정책이 나온다. 키는 다시 수집할 때만 필요하다. 정책이 0건으로 나오면 DB 파일이 받아졌는지 확인한다.
- **브라우저 테스트 도구는 따로 설치한다.** `requirements-dev.txt`에는 `playwright`가 들어 있는데, 폴더 경로가 길면 Windows 경로 길이 제한(260자) 때문에 설치가 실패한다(실제로 겪음). 짧은 경로(예: `C:\work\1123`)에 받거나 위처럼 `pytest`만 설치한다. 단위 테스트에는 `playwright`가 필요 없다.
- AI 챗봇은 로컬 Ollama와 `qwen3:4b` 모델이 있어야 한다. 없어도 낱말 일치로 찾기는 동작한다.

