# -*- coding: utf-8 -*-
"""구글 캘린더 연동의 판단 부분(화면과 분리).

- 설정: 어느 캘린더에 넣을지(전용/내 캘린더/ID), 연동 선택 사항
- 일정 후보 찾기: Gemini가 메시지에서 날짜 있는 일을 뽑는다(가린 글만 보낸다)
- 넣기: 같은 메시지·같은 날짜 일정이 이미 있으면(다른 PC에서 넣은 것 포함)
  새로 만들지 않고 고친다
- 맞추기(sync): 몇 분마다
  · 캘린더 일정을 받아 '일정' 화면용 사본을 바꾼다
  · 휴대폰에서 날짜를 옮긴 일정 → 연결된 업무 마감일도 따라 바꾼다
  · 휴대폰에서 지운 일정 → 업무는 두고 연결만 끊는다
  · 쿨브리핑에서 완료한 업무 → 일정 제목 앞에 ✓ (되돌리면 뺀다)
  · 제목·시간은 휴대폰에서 고친 것을 그대로 둔다(나중에 고친 쪽을 따른다)"""

from datetime import date, datetime, timedelta
from typing import Optional

from .. import db
from ..privacy import masking
from . import gcal_api, google_auth

DONE_PREFIX = "✓ "

# 설정 키
K_MODE = "gcal_mode"              # app | list | id
K_CAL_ID = "gcal_calendar_id"
K_CAL_NAME = "gcal_calendar_name"
K_SHOW_OTHER = "gcal_show_other"
K_FOLLOW = "gcal_follow_dates"
K_MARK_DONE = "gcal_mark_done"
K_LAST_SYNC = "gcal_last_sync"
K_APP_CAL_ID = "gcal_app_calendar_id"   # 한 번 만든 '쿨브리핑' 캘린더 — 다시 고르면 새로 만들지 않고 쓴다

SYNC_PAST_DAYS = 60
SYNC_FUTURE_DAYS = 365


# ---------- 설정 ----------

def calendar_id() -> str:
    return db.get_setting(K_CAL_ID, "") or ""


def calendar_name() -> str:
    return db.get_setting(K_CAL_NAME, "") or ""


def mode() -> str:
    return db.get_setting(K_MODE, "app") or "app"


def option(key: str) -> bool:
    return db.get_setting(key, "1") == "1"


def set_option(key: str, on: bool):
    db.set_setting(key, "1" if on else "0")


def set_calendar(mode_: str, cal_id: str, name: str):
    db.set_setting(K_MODE, mode_)
    db.set_setting(K_CAL_ID, cal_id)
    db.set_setting(K_CAL_NAME, name)


def is_ready() -> bool:
    """연결돼 있고 일정을 넣을 캘린더까지 정해졌는지."""
    return bool(calendar_id()) and google_auth.is_connected()


def needs_extra_scope(mode_: str) -> bool:
    return mode_ in ("list", "id") and not google_auth.has_scopes(google_auth.EXTRA_SCOPES)


# ---------- 일정 후보 찾기 ----------

_WEEKDAYS = "월화수목금토일"

EXTRACT_SYSTEM = (
    "당신은 고등학교 교사의 업무 메시지에서 캘린더에 넣을 일정을 찾는 도우미입니다. "
    "반드시 JSON 배열만 출력합니다."
)


def _kdate(d: date) -> str:
    return f"{d.year}년 {d.month}월 {d.day}일({_WEEKDAYS[d.weekday()]})"


def build_extract_prompt(source_text: str, today: date) -> str:
    return (
        f"오늘은 {_kdate(today)}입니다.\n"
        "아래 메시지에서 교사가 캘린더에 넣으면 좋을 일정(제출 마감, 행사, 회의, 시험, 배부, 신청 기간 등 "
        "날짜가 있는 일)을 찾아 JSON 배열로 답하세요.\n"
        '각 항목: {"title": "25자 이내 짧은 제목", "date": "YYYY-MM-DD", "time": "HH:MM" 또는 null, '
        '"kind": "마감" | "행사" | "회의" | "기타"}\n'
        "규칙:\n"
        "- 날짜가 분명하지 않은 일은 넣지 마세요. 연도가 없으면 오늘 이후 가장 가까운 날짜로 하세요.\n"
        "- '~까지' 제출은 그 날짜의 마감으로 하세요. 같은 일을 두 번 넣지 마세요.\n"
        "- 원문에 없는 날짜·시간을 지어내지 마세요. 없으면 [] 를 출력하세요.\n"
        "- [학생1], [전화번호]처럼 가려진 표시는 그대로 두세요.\n\n"
        "----- 메시지 -----\n" + source_text.strip() + "\n----- 끝 -----"
    )


def _valid_date(s) -> Optional[str]:
    try:
        return date.fromisoformat(str(s)[:10]).isoformat()
    except (TypeError, ValueError):
        return None


def _valid_time(s) -> str:
    s = (s or "").strip() if isinstance(s, str) else ""
    try:
        return datetime.strptime(s, "%H:%M").strftime("%H:%M")
    except ValueError:
        return ""


def _get(row, key):
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return None


def message_source_text(messages) -> str:
    """Gemini로 보낼 메시지 글(보내기 직전에 가린다)."""
    blocks = []
    for m in messages:
        blocks.append("\n".join(b for b in [
            "보낸 곳: " + " / ".join(x for x in (_get(m, "department"), _get(m, "sender")) if x),
            "받은 날: " + str(_get(m, "received_at") or "")[:10],
            "제목: " + (_get(m, "title") or ""),
            "내용:\n" + (_get(m, "body") or ""),
        ] if b))
    return masking.mask_text("\n\n".join(blocks))


def normalize_candidates(raw, task=None) -> list:
    """Gemini 결과를 다듬는다. 업무에서 연 경우 업무 마감일 후보를 맨 앞에 둔다.
    반환: [{'title','date','time','task_id'}]"""
    out, seen = [], set()
    task_id = _get(task, "task_id")
    task_deadline = _valid_date(_get(task, "deadline"))
    if task is not None and task_deadline:
        out.append({"title": masking.mask_text(_get(task, "title") or "")[:60], "date": task_deadline,
                    "time": "", "task_id": task_id})
        seen.add(task_deadline)
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        d = _valid_date(item.get("date"))
        title = masking.mask_text(str(item.get("title") or "").strip())[:60]
        if not d or not title or d in seen:
            continue
        seen.add(d)
        out.append({"title": title, "date": d, "time": _valid_time(item.get("time")), "task_id": None})
    return out


def link_tasks(candidates, message_tasks) -> list:
    """메시지 카드에서 연 경우: 후보 날짜가 그 메시지 업무의 마감일과 같으면 그 업무와 잇는다."""
    by_date = {}
    for t in message_tasks or []:
        d = _valid_date(_get(t, "deadline"))
        if d and d not in by_date:
            by_date[d] = _get(t, "task_id")
    for c in candidates:
        if c.get("task_id") is None and c["date"] in by_date:
            c["task_id"] = by_date[c["date"]]
    return candidates


def find_candidates(messages, task=None, today: Optional[date] = None) -> list:
    """Gemini로 일정 후보를 찾는다(백그라운드 스레드에서 부른다)."""
    from ..ai import gemini_client
    today = today or date.today()
    raw = []
    text = message_source_text(messages)
    if text.strip():
        raw = gemini_client.classify_batch(EXTRACT_SYSTEM, build_extract_prompt(text, today))
        # 모델이 {"events": [...]}처럼 감싸 보내면 안쪽 목록을 쓴다
        if len(raw) == 1 and isinstance(raw[0], dict) and "date" not in raw[0]:
            inner = [v for v in raw[0].values() if isinstance(v, list)]
            raw = inner[0] if inner else []
    message_tasks = []
    for m in messages:
        message_tasks.extend(db.tasks_for_message(_get(m, "message_id")))
    return link_tasks(normalize_candidates(raw, task), message_tasks)


def mark_duplicates(candidates, existing_events) -> list:
    """같은 메시지로 이미 넣은 일정 중 날짜가 같은 것을 'dup'으로 표시."""
    by_date = {}
    for ev in existing_events or []:
        by_date.setdefault(gcal_api.event_date(ev), ev)
    for c in candidates:
        ev = by_date.get(c["date"])
        c["dup_event_id"] = ev.get("id") if ev else None
    return candidates


# ---------- 넣기 ----------

def msg_key_for(messages) -> str:
    for m in messages:
        key = _get(m, "message_hash")
        if key:
            return key
    return ""


def build_event_body(title: str, date_str: str, time_str: str, msg_key: str, message=None, done=False) -> dict:
    title = masking.mask_text(title.strip())
    summary = (DONE_PREFIX if done else "") + title
    desc_bits = ["쿨브리핑에서 넣은 일정"]
    if message is not None:
        origin = masking.mask_text(_get(message, "title") or "")
        dept = _get(message, "department") or ""
        desc_bits.append(f"쿨메신저: {origin}" + (f" ({dept})" if dept else ""))
    body = {
        "summary": summary,
        "description": "\n".join(desc_bits),
        "extendedProperties": {"private": {gcal_api.PROP_APP: gcal_api.APP_VALUE,
                                           gcal_api.PROP_MSG: msg_key or ""}},
    }
    if time_str:
        start = datetime.fromisoformat(f"{date_str}T{time_str}:00")
        end = start + timedelta(hours=1)
        body["start"] = {"dateTime": start.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": gcal_api.TIMEZONE}
        body["end"] = {"dateTime": end.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": gcal_api.TIMEZONE}
    else:
        d = date.fromisoformat(date_str)
        body["start"] = {"date": d.isoformat()}
        body["end"] = {"date": (d + timedelta(days=1)).isoformat()}
    return body


def save_events(chosen, messages, cal_id: Optional[str] = None) -> dict:
    """확인 창에서 고른 일정을 넣는다(또는 같은 일정을 고친다).
    chosen: [{'title','date','time','task_id','dup_event_id'}]
    반환: {'added': n, 'updated': n}"""
    cal_id = cal_id or calendar_id()
    msg_key = msg_key_for(messages)
    message = messages[0] if messages else None
    message_id = _get(message, "message_id")
    added = updated = 0
    for c in chosen:
        task = db.get_task(c["task_id"]) if c.get("task_id") else None
        done = bool(task and task["completed"]) and option(K_MARK_DONE)
        body = build_event_body(c["title"], c["date"], c.get("time") or "", msg_key, message, done=done)
        if c.get("dup_event_id"):
            ev = gcal_api.patch_event(cal_id, c["dup_event_id"], body)
            updated += 1
        else:
            ev = gcal_api.insert_event(cal_id, body)
            added += 1
        db.upsert_gcal_link(cal_id, ev["id"], c.get("task_id"), message_id, msg_key,
                            masking.mask_text(c["title"].strip()), c["date"])
        if task is not None and task["deadline"] != c["date"]:
            db.set_task_deadline(task["task_id"], c["date"])
    return {"added": added, "updated": updated}


# ---------- 맞추기 ----------

def _window(today: date):
    t_min = datetime.combine(today - timedelta(days=SYNC_PAST_DAYS), datetime.min.time())
    t_max = datetime.combine(today + timedelta(days=SYNC_FUTURE_DAYS), datetime.min.time())
    return t_min.strftime("%Y-%m-%dT%H:%M:%S+09:00"), t_max.strftime("%Y-%m-%dT%H:%M:%S+09:00")


def sync(today: Optional[date] = None) -> Optional[dict]:
    """구글 캘린더와 맞춘다. 연결 전이면 None.
    반환: {'moved': n, 'unlinked': n, 'marked': n, 'events': n}"""
    if not is_ready():
        return None
    today = today or date.today()
    cal_id = calendar_id()
    t_min, t_max = _window(today)
    items = gcal_api.list_events(cal_id, t_min, t_max)
    by_id = {ev["id"]: ev for ev in items if ev.get("status") != "cancelled"}

    moved = unlinked = marked = 0
    follow, mark_done = option(K_FOLLOW), option(K_MARK_DONE)
    for link in db.list_gcal_links(cal_id):
        event_id = link["event_id"]
        ev = by_id.get(event_id) or gcal_api.get_event(cal_id, event_id)
        if ev is None:
            # 휴대폰 등에서 지웠다 — 업무는 그대로 두고 연결만 끊는다
            db.delete_gcal_link(cal_id, event_id)
            unlinked += 1
            continue
        new_date = gcal_api.event_date(ev)
        if new_date and new_date != link["last_date"]:
            if link["task_id"] and follow:
                task = db.get_task(link["task_id"])
                if task is not None and task["deadline"] != new_date:
                    db.set_task_deadline(link["task_id"], new_date)
                    moved += 1
            db.update_gcal_link(cal_id, event_id, last_date=new_date)
        if link["task_id"] and mark_done:
            task = db.get_task(link["task_id"])
            if task is not None:
                summary = ev.get("summary") or ""
                has_mark = summary.startswith(DONE_PREFIX)
                want = bool(task["completed"])
                if want != has_mark:
                    new_summary = DONE_PREFIX + summary if want else summary[len(DONE_PREFIX):]
                    gcal_api.patch_event(cal_id, event_id, {"summary": new_summary})
                    ev["summary"] = new_summary
                    marked += 1
        by_id[event_id] = ev

    rows = []
    for ev in by_id.values():
        d = gcal_api.event_date(ev)
        if d:
            rows.append((ev["id"], ev.get("summary") or "(제목 없음)", d, gcal_api.event_time(ev),
                         1 if gcal_api.is_app_event(ev) else 0))
    db.replace_gcal_events(cal_id, rows)
    db.set_setting(K_LAST_SYNC, datetime.now().isoformat(timespec="minutes"))
    return {"moved": moved, "unlinked": unlinked, "marked": marked, "events": len(rows)}


# ---------- 캘린더 바꾸기 ----------

def ensure_app_calendar() -> dict:
    """'쿨브리핑' 전용 캘린더. 예전에 만든 게 아직 있으면 그걸 쓰고, 없으면 만든다."""
    old = db.get_setting(K_APP_CAL_ID, "")
    if old:
        try:
            gcal_api.check_calendar(old)
            return {"id": old, "summary": "쿨브리핑", "reused": True}
        except gcal_api.GCalError:
            pass  # 지워졌다 — 새로 만든다
    cal = gcal_api.create_app_calendar("쿨브리핑")
    db.set_setting(K_APP_CAL_ID, cal["id"])
    return {"id": cal["id"], "summary": "쿨브리핑", "reused": False}


def change_calendar(new_mode: str, new_id: str, new_name: str, move_existing: bool) -> dict:
    """일정을 넣을 캘린더를 바꾼다. move_existing이면 이미 넣은 일정을 새 캘린더로 옮긴다."""
    old_id = calendar_id()
    moved, failed = [], 0
    if move_existing and old_id and old_id != new_id:
        for link in db.list_gcal_links(old_id):
            try:
                gcal_api.move_event(old_id, link["event_id"], new_id)
                moved.append(link["event_id"])
            except gcal_api.GCalError:
                failed += 1
        db.move_gcal_links(old_id, new_id, moved)
    set_calendar(new_mode, new_id, new_name)
    return {"moved": len(moved), "failed": failed}


def existing_link_count() -> int:
    cal = calendar_id()
    return len(db.list_gcal_links(cal)) if cal else 0
