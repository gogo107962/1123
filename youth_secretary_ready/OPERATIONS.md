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

## 3-1. Render에 올리기 (공개 주소)

저장소 맨 위의 `render.yaml`이 설정이다. 무료 서버 한 대(0.1 CPU, 512MB, 싱가포르)로 뜬다.

**연결 순서**
1. 저장소 주인(trewqyu)이 GitHub에서 Render 앱이 이 저장소를 볼 수 있게 허용한다(Render의 GitHub 연결 화면에서 저장소 선택). 비공개 저장소라 이 단계는 주인만 할 수 있다.
2. 배포할 사람이 Render에 GitHub 계정으로 로그인해 **New → Blueprint**에서 이 저장소를 고른다. `render.yaml`대로 서비스가 만들어진다.
3. 만들 때 `GEMINI_API_KEY`를 묻는다. Google AI Studio의 키를 넣는다. 비워 두면 AI 없이 낱말로 찾는다.
4. 배포가 끝나면 `https://<서비스 이름>.onrender.com`으로 열린다.

**알아 둘 것**
- **데이터**: 저장소에 있는 실행 DB(`data/youth_secretary.sqlite3`)를 그대로 쓴다. 무료 서버는 디스크가 재시작·잠들 때마다 저장소의 상태로 돌아가므로, 배포된 서버에서 만든 준비 공간·저장한 작업은 **서버가 잠들면 사라진다.** 정책 데이터는 항상 저장소의 것과 같다.
- **잠들기**: 15분 동안 접속이 없으면 잠들고, 다음 접속에 1분쯤 걸린다. 심사 직전에 한 번 열어 깨워 둔다.
- **다시 배포**: 저장소에 올려도 자동으로 다시 배포되지 않게 했다(`autoDeployTrigger: off`). 바꾼 것을 반영하려면 Render 화면에서 **Manual Deploy**를 누른다. 제출 마감 뒤에는 누르지 않는다.
- **관리 기능**: 공개 배포 모드(`PUBLIC_DEPLOY=1`)에서는 수집 실행·정책 검수가 `X-Admin-Token` 헤더로만 열린다. 값은 Render 화면의 `ADMIN_TOKEN`에 있다. `/review` 화면은 열리지만 그 안의 기능은 토큰 없이는 403이다.
- **요청 횟수 제한**은 앞단 서버가 적어 준 사용자 주소(`X-Forwarded-For`)로 센다. 꾸밀 수 있는 값이라 관리 권한에는 쓰지 않는다.
- **AI**: 서버에 로컬 모델을 둘 수 없어 Gemini의 무료 구간 모델(`gemini-3.5-flash-lite`)을 쓴다. 사용자가 챗봇에 적은 글과 고른 정책 번호가 Google로 전송되고, 무료 구간에서는 그 글이 Google 제품 개선에 쓰인다. **화면의 'AI에게 물어보기' 카드에는 아직 '로컬 AI'라고 적혀 있다(화면 파일은 고치지 않았다).** 실제 개인정보를 적지 말라는 안내가 필요하다.
- **로그인이 없다.** 주소를 아는 누구나 쓸 수 있다. 저장소의 DB에 들어 있는 준비 공간(시험하며 만든 것)은 식별자를 아는 사람만 열 수 있다.
- 로컬에서 실행하면 저장소의 DB 파일이 바뀐다(준비 공간이 쌓인다). 올리기 전에 `git status`로 DB가 섞이지 않았는지 본다.

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

