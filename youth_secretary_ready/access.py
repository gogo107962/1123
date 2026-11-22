"""누가 부를 수 있는지(서버 PC 또는 관리 토큰)와 요청 횟수 제한. 계정 인증 체계는 아니다."""
import hmac
import os
import threading
import time
from collections import defaultdict, deque
from fastapi import HTTPException, Request

LOCAL = {'127.0.0.1', '::1', 'localhost', 'testclient'}
# (경로 앞부분, 메서드, 허용 횟수, 초). 위에서부터 처음 맞는 규칙 하나만 적용한다.
LIMITS = [('/api/integrations/ontong/ask', 'POST', 20, 60),      # 로컬 모델 호출
          ('/api/agent/message', 'POST', 20, 60),
          ('/api/desk/workspaces', 'POST', 600, 60),             # 계획·승인·AI 등 준비 공간 안의 쓰기
          ('/api/', 'POST', 300, 60), ('/api/', 'PUT', 300, 60), ('/api/', 'PATCH', 300, 60), ('/api/', 'DELETE', 300, 60)]
NEW_WORKSPACES = (30, 3600)                                       # 준비 공간 만들기: 한 주소에서 1시간에 30개
_hits, _lock = defaultdict(deque), threading.Lock()


def public():
    """공개 배포 서버(PUBLIC_DEPLOY=1). 앞단 서버를 거쳐 오므로 '서버 PC에서 부른 요청'이라는 구분을 믿을 수 없다."""
    return os.environ.get('PUBLIC_DEPLOY', '') == '1'


def client_of(request: Request):
    if public():
        # 앞단 서버가 적어 준 사용자 주소로 횟수를 센다. 꾸밀 수 있는 값이라 앞에 표시를 붙여 서버 PC·테스트 주소와 같아지지 않게 한다.
        forwarded = request.headers.get('x-forwarded-for', '').split(',')[0].strip()
        if forwarded:
            return 'fwd:' + forwarded[:60]
        return 'proxy:' + (request.client.host if request.client else '')
    return request.client.host if request.client else ''


def require_admin(request: Request):
    """수집 실행·정책 승인처럼 서버 상태를 바꾸는 관리 기능. 서버 PC에서 부르거나 ADMIN_TOKEN 헤더가 맞아야 한다."""
    token = os.environ.get('ADMIN_TOKEN', '')
    if token and hmac.compare_digest(request.headers.get('x-admin-token', ''), token):
        return
    if public() or client_of(request) not in LOCAL:   # 공개 배포에서는 토큰으로만 연다
        raise HTTPException(403, '이 기능은 서버를 실행한 PC에서만 쓸 수 있습니다.')


def allow(key, limit, window, now=None):
    """최근 window초 동안 limit번까지만 허용한다. 서버 한 대의 메모리에만 기록한다."""
    now = time.monotonic() if now is None else now
    with _lock:
        hits = _hits[key]
        while hits and hits[0] <= now - window:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True


def check_rate(request: Request):
    """제한에 걸리면 안내 문구를, 아니면 None을 돌려준다. 자동 테스트(testclient)는 세지 않는다."""
    host, path, method = client_of(request), request.url.path, request.method
    if host == 'testclient':
        return None
    if method == 'POST' and path.rstrip('/') == '/api/desk/workspaces' and not allow((host, 'new'), *NEW_WORKSPACES):
        return '준비 공간을 너무 많이 만들었습니다. 잠시 뒤 다시 시도해 주세요.'
    for prefix, verb, limit, window in LIMITS:
        if method == verb and path.startswith(prefix):
            return None if allow((host, prefix, verb), limit, window) else '요청이 너무 많습니다. 잠시 뒤 다시 시도해 주세요.'
    return None
