# -*- coding: utf-8 -*-
"""구글 캘린더 API(v3)를 urllib로 직접 부르는 얇은 층.

쓰는 기능만 둔다: 전용 캘린더 만들기, 내 캘린더 목록, 일정 목록·찾기·
넣기·고치기·옮기기·하나 읽기. 인증은 google_auth.access_token()."""

import json
import urllib.parse

from . import google_auth

API = "https://www.googleapis.com/calendar/v3"
TIMEZONE = "Asia/Seoul"

# 쿨브리핑이 넣은 일정에 숨겨 두는 표시(extendedProperties.private)
PROP_APP = "cbApp"          # 값: "coolbriefing"
PROP_MSG = "cbMsg"          # 값: 쿨메신저 메시지 해시 — PC가 여러 대여도 같다
APP_VALUE = "coolbriefing"


class GCalError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def _call(method: str, path: str, params: dict = None, body: dict = None, retry_auth: bool = True):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    headers = {"Authorization": "Bearer " + google_auth.access_token()}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    status, raw = google_auth.http_request(method, url, data, headers)
    if status == 401 and retry_auth:
        google_auth.forget_access_token()
        return _call(method, path, params, body, retry_auth=False)
    if status == 204:
        return {}
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except ValueError:
        payload = {}
    if status >= 400:
        raise GCalError(_error_message(status, payload, method, path), status)
    return payload


def _error_reasons(payload) -> set:
    """구글 오류 응답의 이유 코드들(accessNotConfigured, SERVICE_DISABLED 등)."""
    err = (payload.get("error") or {}) if isinstance(payload, dict) else {}
    if not isinstance(err, dict):
        return set()
    out = {str(err.get("status") or "")}
    for e in err.get("errors") or []:
        if isinstance(e, dict):
            out.add(str(e.get("reason") or ""))
    for d in err.get("details") or []:
        if isinstance(d, dict):
            out.add(str(d.get("reason") or ""))
    return {r for r in out if r}


def _error_message(status: int, payload, method: str, path: str) -> str:
    """화면에 보일 한국어 안내 + 끝에 구글이 준 이유 코드(어느 단계 문제인지 짚을 수 있게)."""
    err = (payload.get("error") or {}) if isinstance(payload, dict) else {}
    message = (err.get("message") if isinstance(err, dict) else "") or ""
    reasons = _error_reasons(payload)
    code = f" (구글 응답: {status} {', '.join(sorted(reasons)) or '-'})"
    low = message.lower()
    print(f"[구글 캘린더 API 오류] {method} {path} → {status} {sorted(reasons)} {message}")
    if reasons & {"accessNotConfigured", "SERVICE_DISABLED"} or "has not been used" in low or "is disabled" in low:
        return ("구글 클라우드 프로젝트에서 'Google Calendar API'가 아직 켜져 있지 않아요. "
                "구글 클라우드 → API 및 서비스 → 라이브러리에서 Google Calendar API [사용]을 누르고, "
                "켠 직후라면 5분쯤 뒤에 다시 해 보세요." + code)
    if reasons & {"insufficientPermissions", "ACCESS_TOKEN_SCOPE_INSUFFICIENT"} or "insufficient" in low:
        return "구글에 허용한 권한이 모자라요. 설정 → 구글 캘린더에서 [연결 해제] 후 다시 연결해 주세요." + code
    if reasons & {"rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded", "RATE_LIMIT_EXCEEDED"}:
        return "구글 캘린더 요청이 잠시 너무 많았어요. 1분쯤 뒤에 다시 해 주세요." + code
    if reasons & {"domainPolicy", "forbiddenForNonOrganizer"} or "admin" in low:
        return "학교 구글 관리자 설정 때문에 막혔어요. 정보부에 구글 캘린더 API 사용을 문의해 주세요." + code
    if path == "/calendars" and method == "POST":
        return "쿨브리핑 캘린더를 만들지 못했어요." + code
    if status == 404:
        return "캘린더나 일정을 찾을 수 없어요. 캘린더 ID를 확인해 주세요." + code
    if status == 403:
        return "이 캘린더에 일정을 쓸 권한이 없어요. 내가 쓸 수 있는 캘린더인지 확인해 주세요." + code
    return f"구글 캘린더 오류: {message or status}" + code


def _q(calendar_id: str) -> str:
    return urllib.parse.quote(calendar_id, safe="")


# ---------- 캘린더 ----------

def create_app_calendar(summary: str = "쿨브리핑") -> dict:
    """선생님 계정에 '쿨브리핑' 캘린더를 새로 만든다(앱이 만든 캘린더 권한만으로 된다)."""
    return _call("POST", "/calendars", body={
        "summary": summary,
        "description": "쿨브리핑이 쿨메신저 메시지에서 넣은 일정",
        "timeZone": TIMEZONE,
    })


def list_writable_calendars() -> list:
    """[{'id','summary','primary'}] — 일정을 쓸 수 있는 캘린더만."""
    out, token = [], None
    while True:
        params = {"minAccessRole": "writer", "maxResults": 250}
        if token:
            params["pageToken"] = token
        data = _call("GET", "/users/me/calendarList", params)
        for c in data.get("items", []):
            out.append({"id": c["id"], "summary": c.get("summaryOverride") or c.get("summary", c["id"]),
                        "primary": bool(c.get("primary"))})
        token = data.get("nextPageToken")
        if not token:
            return out


def check_calendar(calendar_id: str):
    """캘린더 ID가 맞고 일정을 읽을 수 있는지 확인(틀리면 GCalError)."""
    _call("GET", f"/calendars/{_q(calendar_id)}/events", {"maxResults": 1})


# ---------- 일정 ----------

def list_events(calendar_id: str, time_min: str, time_max: str) -> list:
    """기간 안의 일정(반복 일정은 하나씩 펼친다)."""
    out, token = [], None
    while True:
        params = {"timeMin": time_min, "timeMax": time_max, "singleEvents": "true",
                  "maxResults": 2500, "showDeleted": "false"}
        if token:
            params["pageToken"] = token
        data = _call("GET", f"/calendars/{_q(calendar_id)}/events", params)
        out.extend(data.get("items", []))
        token = data.get("nextPageToken")
        if not token:
            return out


def find_events_by_message(calendar_id: str, msg_key: str) -> list:
    """같은 쿨메신저 메시지로 이미 넣은 일정(다른 PC에서 넣은 것 포함)."""
    data = _call("GET", f"/calendars/{_q(calendar_id)}/events",
                 {"privateExtendedProperty": f"{PROP_MSG}={msg_key}", "maxResults": 50, "showDeleted": "false"})
    return data.get("items", [])


def get_event(calendar_id: str, event_id: str):
    """일정 하나. 지워졌으면 None."""
    try:
        ev = _call("GET", f"/calendars/{_q(calendar_id)}/events/{_q(event_id)}")
    except GCalError as e:
        if e.status in (404, 410):
            return None
        raise
    return None if ev.get("status") == "cancelled" else ev


def insert_event(calendar_id: str, body: dict) -> dict:
    return _call("POST", f"/calendars/{_q(calendar_id)}/events", body=body)


def patch_event(calendar_id: str, event_id: str, body: dict) -> dict:
    return _call("PATCH", f"/calendars/{_q(calendar_id)}/events/{_q(event_id)}", body=body)


def move_event(calendar_id: str, event_id: str, destination: str) -> dict:
    return _call("POST", f"/calendars/{_q(calendar_id)}/events/{_q(event_id)}/move",
                 {"destination": destination})


# ---------- 일정 모양 ----------

def event_date(ev: dict) -> str:
    """일정 시작 날짜(YYYY-MM-DD)."""
    start = ev.get("start") or {}
    return (start.get("date") or start.get("dateTime") or "")[:10]


def event_time(ev: dict) -> str:
    """시작 시각 HH:MM, 하루 종일이면 ''."""
    start = ev.get("start") or {}
    dt = start.get("dateTime") or ""
    return dt[11:16] if len(dt) >= 16 else ""


def event_msg_key(ev: dict) -> str:
    return ((ev.get("extendedProperties") or {}).get("private") or {}).get(PROP_MSG, "")


def is_app_event(ev: dict) -> bool:
    return ((ev.get("extendedProperties") or {}).get("private") or {}).get(PROP_APP) == APP_VALUE
