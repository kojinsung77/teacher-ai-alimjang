# -*- coding: utf-8 -*-
"""구글 계정 연결(OAuth 2.0, 데스크톱 앱 + PKCE + 루프백 주소).

- 학교 워크스페이스의 '내부(Internal)' 앱으로 등록된 클라이언트를 쓴다.
  내부 앱이라 구글 심사가 필요 없고, 학교 계정(@jungang.hs.kr)만 로그인할 수
  있으며, 로그인이 7일마다 풀리지 않는다.
- 로그인: 브라우저를 열고 127.0.0.1의 임시 주소로 돌아오는 코드를 받는다.
- 저장: refresh token·받은 권한·이메일만 Windows 자격 증명 관리자(keyring)에
  둔다(Gemini 키와 같은 방식). DB나 파일에는 쓰지 않는다.
- 데이터는 이 PC ↔ 선생님 구글 계정 사이에서만 오간다. 개발자 서버는 없다.

외부 패키지 없이 표준 라이브러리(urllib)만 쓴다 — 설치 파일이 커지지 않고
PyInstaller 묶음에서 빠지는 모듈이 생길 일도 없다.

클라이언트 정보(client_id/secret)를 찾는 순서
1) %LOCALAPPDATA%\\TeacherAlimjang\\google_client.json — 구글 클라우드에서 받은
   JSON을 그대로 둔다(배포 전 테스트용, 또는 바꿔 끼울 때)
2) app/core/google_client_config.py의 상수 — 배포본에 들어가는 값"""

import base64
import hashlib
import http.server
import json
import secrets
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

from .. import config

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

SCOPE_APP_CALENDARS = "https://www.googleapis.com/auth/calendar.app.created"
SCOPE_EVENTS = "https://www.googleapis.com/auth/calendar.events"
SCOPE_CALENDAR_LIST = "https://www.googleapis.com/auth/calendar.calendarlist.readonly"

# 처음 연결할 때 받는 권한 — '쿨브리핑' 전용 캘린더만 다룰 수 있다.
BASE_SCOPES = ["openid", "email", SCOPE_APP_CALENDARS]
# 이미 쓰는 캘린더를 고를 때 한 번 더 받는 권한
EXTRA_SCOPES = [SCOPE_EVENTS, SCOPE_CALENDAR_LIST]

_KEYRING_USERNAME = "google_oauth"
_LOGIN_TIMEOUT_SEC = 300


class GoogleAuthError(Exception):
    """화면에 그대로 보여 줄 수 있는 한국어 메시지를 담는다."""


# ---------- HTTP (테스트에서 바꿔 끼울 수 있게 한곳에 모은다) ----------

def http_request(method: str, url: str, data: bytes = None, headers: dict = None, timeout: float = 20.0):
    """(status, body_bytes)를 돌려준다. 네트워크 오류는 GoogleAuthError로."""
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        raise GoogleAuthError(f"인터넷 연결을 확인해 주세요. ({e})")


def _post_form(url: str, fields: dict):
    body = urllib.parse.urlencode(fields).encode("utf-8")
    status, raw = http_request("POST", url, body, {"Content-Type": "application/x-www-form-urlencoded"})
    try:
        data = json.loads(raw.decode("utf-8") or "{}")
    except ValueError:
        data = {}
    return status, data


# ---------- 클라이언트 정보 ----------

def _user_client_file():
    return config.app_data_dir() / "google_client.json"


def load_client_config() -> dict:
    """{'client_id':..., 'client_secret':...} — 없으면 GoogleAuthError."""
    path = _user_client_file()
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            info = raw.get("installed") or raw.get("web") or raw
            if info.get("client_id"):
                return {"client_id": info["client_id"], "client_secret": info.get("client_secret", "")}
        except (ValueError, OSError):
            pass
    from . import google_client_config as gcc
    if gcc.CLIENT_ID:
        return {"client_id": gcc.CLIENT_ID, "client_secret": gcc.CLIENT_SECRET}
    raise GoogleAuthError(
        "구글 캘린더 연결 정보가 아직 프로그램에 들어 있지 않습니다. 만든 사람에게 문의해 주세요."
    )


def is_available() -> bool:
    try:
        load_client_config()
        return True
    except GoogleAuthError:
        return False


# ---------- 저장(keyring) ----------

def _keyring():
    import keyring
    return keyring


def load_credentials() -> dict:
    """{'refresh_token','scope','email'} 또는 {}."""
    try:
        raw = _keyring().get_password(config.KEYRING_SERVICE, _KEYRING_USERNAME)
    except Exception:
        return {}
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if data.get("refresh_token") else {}
    except ValueError:
        return {}


def _save_credentials(data: dict):
    _keyring().set_password(config.KEYRING_SERVICE, _KEYRING_USERNAME, json.dumps(data))


def _delete_credentials():
    try:
        _keyring().delete_password(config.KEYRING_SERVICE, _KEYRING_USERNAME)
    except Exception:
        pass


def is_connected() -> bool:
    return bool(load_credentials())


def connected_email() -> str:
    return load_credentials().get("email", "")


def granted_scopes() -> set:
    return set((load_credentials().get("scope") or "").split())


def has_scopes(scopes) -> bool:
    return set(scopes) <= granted_scopes()


# ---------- id_token에서 이메일 꺼내기 ----------

def _id_token_claims(id_token: str) -> dict:
    """서명 검증 없이 내용만 읽는다(화면 표시·학교 계정 확인용). 토큰은
    구글 토큰 주소에서 TLS로 직접 받은 것이라 출처는 이미 확인된 셈이다."""
    try:
        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except Exception:
        return {}


# ---------- 로그인 ----------

class _CodeReceiver(http.server.BaseHTTPRequestHandler):
    result = None   # 서버 인스턴스마다 덮어쓴다

    def do_GET(self):  # noqa: N802 (http.server 규칙)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" not in query and "error" not in query:
            self.send_response(404)
            self.end_headers()
            return
        self.server.oauth_result = {k: v[0] for k, v in query.items()}
        ok = "code" in query
        body = (
            "<html><head><meta charset='utf-8'><title>쿨브리핑</title></head>"
            "<body style='font-family:sans-serif;text-align:center;padding-top:80px'>"
            + ("<h2>🐦 쿨브리핑에 구글 계정을 연결했어요</h2><p>이 창은 닫아도 돼요.</p>"
               if ok else "<h2>연결하지 못했어요</h2><p>쿨브리핑으로 돌아가 다시 시도해 주세요.</p>")
            + "</body></html>"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):  # 콘솔에 접속 기록을 남기지 않는다
        pass


def _pkce_pair():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode("ascii")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_auth_url(client_id, redirect_uri, scopes, state, challenge, login_hint=""):
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "hd": config.GOOGLE_WORKSPACE_DOMAIN,
    }
    if login_hint:
        params["login_hint"] = login_hint
    return AUTH_URL + "?" + urllib.parse.urlencode(params)


def connect(extra: bool = False, open_browser=webbrowser.open, timeout: float = _LOGIN_TIMEOUT_SEC) -> dict:
    """브라우저로 로그인해 권한을 받는다. extra=True면 기존 캘린더용 권한까지.
    성공하면 저장된 자격 정보를 돌려준다. 실패하면 GoogleAuthError.
    (백그라운드 스레드에서 부른다 — 로그인을 마칠 때까지 기다린다)"""
    client = load_client_config()
    scopes = BASE_SCOPES + (EXTRA_SCOPES if extra else [])
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)

    server = http.server.HTTPServer(("127.0.0.1", 0), _CodeReceiver)
    server.oauth_result = None
    server.timeout = 1
    redirect_uri = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        url = build_auth_url(client["client_id"], redirect_uri, scopes, state, challenge,
                             login_hint=connected_email())
        open_browser(url)
        deadline = time.monotonic() + timeout
        while server.oauth_result is None and time.monotonic() < deadline:
            server.handle_request()
        result = server.oauth_result
    finally:
        server.server_close()

    if result is None:
        raise GoogleAuthError("로그인 시간이 지났어요. 다시 [구글 계정 연결]을 눌러 주세요.")
    if result.get("state") != state:
        raise GoogleAuthError("로그인 응답이 올바르지 않아요. 다시 시도해 주세요.")
    if "error" in result:
        if result["error"] == "access_denied":
            raise GoogleAuthError("구글에서 [허용]을 누르지 않아 연결하지 않았어요.")
        raise GoogleAuthError(f"구글이 연결을 거부했어요: {result['error']}")

    status, token = _post_form(TOKEN_URL, {
        "code": result["code"],
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    })
    if status != 200 or "access_token" not in token:
        raise GoogleAuthError(f"구글 로그인을 마치지 못했어요: {token.get('error_description') or token.get('error') or status}")

    claims = _id_token_claims(token.get("id_token", ""))
    domain = config.GOOGLE_WORKSPACE_DOMAIN
    if domain and claims.get("hd") != domain:
        _revoke(token.get("refresh_token") or token["access_token"])
        raise GoogleAuthError(f"학교 계정(@{domain})으로 로그인해 주세요. 개인 Gmail은 연결할 수 없어요.")

    previous = load_credentials()
    refresh_token = token.get("refresh_token") or previous.get("refresh_token")
    if not refresh_token:
        raise GoogleAuthError("구글이 로그인 정보를 주지 않았어요. 다시 시도해 주세요.")
    creds = {
        "refresh_token": refresh_token,
        "scope": " ".join(sorted(set(token.get("scope", "").split()) | (set(previous.get("scope", "").split()) if extra else set()))),
        "email": claims.get("email") or previous.get("email", ""),
    }
    _save_credentials(creds)
    _ACCESS.update({"token": token["access_token"], "expires": time.time() + int(token.get("expires_in", 3600)) - 60})
    return creds


# ---------- 접근 토큰 ----------

_ACCESS = {"token": None, "expires": 0.0}
_ACCESS_LOCK = threading.Lock()


def access_token() -> str:
    """유효한 접근 토큰. 필요하면 refresh token으로 새로 받는다."""
    with _ACCESS_LOCK:
        if _ACCESS["token"] and time.time() < _ACCESS["expires"]:
            return _ACCESS["token"]
        creds = load_credentials()
        if not creds:
            raise GoogleAuthError("구글 계정이 연결되어 있지 않아요. 설정 → 구글 캘린더에서 연결해 주세요.")
        client = load_client_config()
        status, token = _post_form(TOKEN_URL, {
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "refresh_token": creds["refresh_token"],
            "grant_type": "refresh_token",
        })
        if status != 200 or "access_token" not in token:
            if token.get("error") == "invalid_grant":
                # 비밀번호 변경·권한 취소·관리자 차단 등 — 다시 연결해야 한다
                _delete_credentials()
                raise GoogleAuthError("구글 연결이 끊겼어요. 설정 → 구글 캘린더에서 다시 연결해 주세요.")
            raise GoogleAuthError(f"구글에 연결하지 못했어요: {token.get('error') or status}")
        _ACCESS.update({"token": token["access_token"], "expires": time.time() + int(token.get("expires_in", 3600)) - 60})
        return _ACCESS["token"]


def forget_access_token():
    with _ACCESS_LOCK:
        _ACCESS.update({"token": None, "expires": 0.0})


# ---------- 연결 해제 ----------

def _revoke(token: str):
    try:
        _post_form(REVOKE_URL, {"token": token})
    except GoogleAuthError:
        pass


def disconnect():
    """구글 쪽 허용을 취소하고 이 PC에 저장된 로그인 정보를 지운다."""
    creds = load_credentials()
    if creds.get("refresh_token"):
        _revoke(creds["refresh_token"])
    _delete_credentials()
    forget_access_token()
