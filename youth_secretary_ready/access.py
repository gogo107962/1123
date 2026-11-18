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


def client_of(request: Request):
    return request.client.host if request.client else ''


def require_admin(request: Request):
    """수집 실행·정책 승인처럼 서버 상태를 바꾸는 관리 기능. 서버 PC에서 부르거나 ADMIN_TOKEN 헤더가 맞아야 한다."""
    token = os.environ.get('ADMIN_TOKEN', '')
    if token and hmac.compare_digest(request.headers.get('x-admin-token', ''), token):
        return
    if client_of(request) not in LOCAL:
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
