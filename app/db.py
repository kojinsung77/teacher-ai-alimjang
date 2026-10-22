# -*- coding: utf-8 -*-
"""SQLite 로컬 저장소. API Key는 여기에 저장하지 않는다 (keyring 사용)."""

import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional, Iterable

from . import config


SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    message_id       TEXT PRIMARY KEY,
    message_hash      TEXT NOT NULL,
    sender            TEXT,
    department        TEXT,
    title             TEXT,
    body              TEXT,
    received_at       TEXT,
    analyzed          INTEGER DEFAULT 0,
    sensitivity       TEXT DEFAULT 'NONE',      -- NONE | SENSITIVE
    classification    TEXT DEFAULT NULL,        -- ACTION | REFERENCE | IGNORE
    created_at        TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_hash ON messages(message_hash);

CREATE TABLE IF NOT EXISTS tasks (
    task_id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    title                      TEXT NOT NULL,
    summary                    TEXT,
    category                   TEXT,
    deadline                   TEXT,             -- ISO date, nullable
    deadline_confidence        TEXT DEFAULT 'HIGH',
    priority                   TEXT DEFAULT 'MEDIUM',
    requires_reply             INTEGER DEFAULT 0,
    requires_attachment_check  INTEGER DEFAULT 0,
    student_related            INTEGER DEFAULT 0,
    completed                  INTEGER DEFAULT 0,
    completed_at               TEXT,
    created_at                 TEXT DEFAULT (datetime('now')),
    confidence                 REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS task_messages (
    task_id     INTEGER NOT NULL,
    message_id  TEXT NOT NULL,
    PRIMARY KEY (task_id, message_id)
);

CREATE TABLE IF NOT EXISTS daily_summary (
    date        TEXT PRIMARY KEY,
    summary     TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT
);

CREATE TABLE IF NOT EXISTS holidays (
    date        TEXT PRIMARY KEY,          -- ISO 날짜 (yyyy-MM-dd)
    source      TEXT DEFAULT 'manual',     -- 'api'(학사일정 자동 채움) | 'manual'(선생님이 직접 추가)
    name        TEXT,                      -- API가 채워준 경우 "여름방학", "리더십캠프" 등. manual이면 NULL 가능
    is_dayoff   INTEGER NOT NULL DEFAULT 1 -- 1=등교하지 않는 날(자동 알림장 건너뜀), 0=등교하지만 행사가 있는 날
);

-- 구글 캘린더에 넣은 일정 ↔ 쿨브리핑 업무/메시지 연결 (1.16.0)
CREATE TABLE IF NOT EXISTS gcal_links (
    calendar_id  TEXT NOT NULL,
    event_id     TEXT NOT NULL,
    task_id      INTEGER,            -- 업무와 연결된 일정이면(휴대폰에서 날짜를 옮기면 마감일도 따라감)
    message_id   TEXT,
    msg_key      TEXT,               -- 메시지 해시 — 다른 PC에서 넣은 일정도 알아본다
    title        TEXT,               -- ✓ 없는 원래 제목
    last_date    TEXT,               -- 마지막으로 맞춘 일정 날짜(YYYY-MM-DD)
    created_at   TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (calendar_id, event_id)
);

-- '일정' 화면에 보여 줄 구글 캘린더 일정 사본(몇 분마다 새로 받아 바꾼다)
CREATE TABLE IF NOT EXISTS gcal_events (
    calendar_id  TEXT NOT NULL,
    event_id     TEXT NOT NULL,
    title        TEXT,
    date         TEXT,
    time         TEXT,
    is_app       INTEGER DEFAULT 0,   -- 쿨브리핑이 넣은 일정이면 1
    PRIMARY KEY (calendar_id, event_id)
);
"""


@contextmanager
def get_conn():
    # timeout을 기본값(5초)보다 넉넉하게 주고 WAL 저널 모드를 쓴다 — 이 앱은
    # 자동 확인 타이머(백그라운드 스레드)와 화면 조작(메인 스레드)이 동시에
    # 각자 별도 연결로 같은 DB 파일에 접근할 수 있는 구조라, 기본 롤백
    # 저널 모드보다 동시 접근에 안전한 WAL이 더 적합하다. journal_mode는
    # DB 파일에 영구히 저장되는 설정이라 매번 설정해도 이미 WAL이면
    # 비용이 거의 없다.
    conn = sqlite3.connect(config.db_path(), timeout=15.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate_holidays_is_dayoff(conn):
    """CREATE TABLE IF NOT EXISTS는 이미 있는 테이블에 새 컬럼을 추가해
    주지 않으므로, is_dayoff 도입 이전(NEIS 학사일정 API 전환 이전)에
    만들어진 holidays 테이블에는 이 컬럼이 없을 수 있다 — 있으면 조용히
    건너뛴다."""
    cols = [row["name"] for row in conn.execute("PRAGMA table_info(holidays)").fetchall()]
    if "is_dayoff" not in cols:
        conn.execute("ALTER TABLE holidays ADD COLUMN is_dayoff INTEGER NOT NULL DEFAULT 1")


def _migrate_messages_starred(conn):
    """1.16.0 — 메시지 즐겨찾기(★). 예전 DB에는 열이 없어 추가한다."""
    cols = [row["name"] for row in conn.execute("PRAGMA table_info(messages)").fetchall()]
    if "starred" not in cols:
        conn.execute("ALTER TABLE messages ADD COLUMN starred INTEGER NOT NULL DEFAULT 0")


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        _migrate_holidays_is_dayoff(conn)
        _migrate_messages_starred(conn)


# ---------- messages ----------

def message_exists(message_hash: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM messages WHERE message_hash = ? LIMIT 1", (message_hash,)
        ).fetchone()
        return row is not None


def insert_message(msg, sensitivity="NONE", classification=None, analyzed=0):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO messages
               (message_id, message_hash, sender, department, title, body,
                received_at, analyzed, sensitivity, classification)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                msg.id, msg.content_hash(), msg.sender, msg.department,
                msg.title, msg.body, msg.received_at.isoformat(),
                analyzed, sensitivity, classification,
            ),
        )


def mark_analyzed(message_id: str, classification: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE messages SET analyzed = 1, classification = ? WHERE message_id = ?",
            (classification, message_id),
        )


def unanalyzed_messages():
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM messages WHERE analyzed = 0 ORDER BY received_at"
        ).fetchall()


def messages_for_task(task_id: int):
    with get_conn() as conn:
        return conn.execute(
            """SELECT m.* FROM messages m
               JOIN task_messages tm ON tm.message_id = m.message_id
               WHERE tm.task_id = ?""",
            (task_id,),
        ).fetchall()


# ---------- tasks ----------

def insert_task(task_dict: dict, source_message_ids: Iterable[str]) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO tasks
               (title, summary, category, deadline, deadline_confidence, priority,
                requires_reply, requires_attachment_check, student_related, confidence)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                task_dict["title"], task_dict.get("summary", ""),
                task_dict.get("category", "기타"), task_dict.get("deadline"),
                task_dict.get("deadline_confidence", "HIGH"),
                task_dict.get("priority", "MEDIUM"),
                int(task_dict.get("requires_reply", False)),
                int(task_dict.get("requires_attachment_check", False)),
                int(task_dict.get("student_related", False)),
                float(task_dict.get("confidence", 0.0)),
            ),
        )
        task_id = cur.lastrowid
        for mid in source_message_ids:
            conn.execute(
                "INSERT OR IGNORE INTO task_messages (task_id, message_id) VALUES (?,?)",
                (task_id, mid),
            )
        return task_id


def list_tasks(include_completed: bool = False):
    """tasks.* 전부 + 연결된 원본 메시지의 department(발신 부서)·received_at(받은
    날짜)을 함께 반환한다. 메시지가 여러 건 연결된 업무는 가장 먼저 받은
    메시지를 기준으로 한다(MIN — SQLite는 이때 department·sender도 그 행에서 가져온다).
    (tasks 테이블 자체엔 department 컬럼이 없어 task_messages/messages를 LEFT JOIN;
    한 업무가 보통 메시지 1건에서 만들어지므로 GROUP BY로 안전하게 한 행씩만 남긴다.)
    정렬은 여기서 세밀하게 하지 않는다 — 화면단(app/core/stats.py)에서
    마감일/중요도/생성일 다중 기준으로 다시 정렬한다."""
    base = """
        SELECT t.*, m.department as department, m.sender as sender,
               MIN(m.received_at) as received_at
        FROM tasks t
        LEFT JOIN task_messages tm ON tm.task_id = t.task_id
        LEFT JOIN messages m ON m.message_id = tm.message_id
    """
    with get_conn() as conn:
        if include_completed:
            q = base + " GROUP BY t.task_id ORDER BY (t.deadline IS NULL), t.deadline ASC"
        else:
            q = base + " WHERE t.completed = 0 GROUP BY t.task_id ORDER BY (t.deadline IS NULL), t.deadline ASC"
        return conn.execute(q).fetchall()


def set_task_completed(task_id: int, completed: bool):
    with get_conn() as conn:
        conn.execute(
            "UPDATE tasks SET completed = ?, completed_at = ? WHERE task_id = ?",
            (int(completed), datetime.now().isoformat() if completed else None, task_id),
        )


def complete_tasks_bulk(task_ids) -> str:
    """'업무' 화면의 [전체 완료] — 여러 업무를 한 번에(하나의 트랜잭션으로)
    완료 처리한다. 모두 똑같은 completed_at을 기록하고 그 값을 돌려준다 —
    [되돌리기]가 이 값으로 '방금 한꺼번에 완료한 묶음'만 정확히 골라낸다.
    이미 완료된 업무는 건드리지 않는다(원래 완료 시각을 지킨다)."""
    ids = [int(t) for t in task_ids]
    stamp = datetime.now().isoformat()
    if not ids:
        return stamp
    marks = ",".join("?" * len(ids))
    with get_conn() as conn:
        conn.execute(
            f"UPDATE tasks SET completed = 1, completed_at = ? "
            f"WHERE completed = 0 AND task_id IN ({marks})",
            [stamp, *ids],
        )
    return stamp


def undo_bulk_complete(task_ids, stamp: str) -> int:
    """complete_tasks_bulk()를 되돌린다. 그 묶음(같은 completed_at)으로
    완료된 채 그대로 있는 업무만 미완료로 돌린다 — 그사이 선생님이 하나를
    직접 미완료로 돌렸다가 다시 완료한 업무 등은 건드리지 않는다.
    되돌린 건수를 돌려준다."""
    ids = [int(t) for t in task_ids]
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    with get_conn() as conn:
        cur = conn.execute(
            f"UPDATE tasks SET completed = 0, completed_at = NULL "
            f"WHERE completed = 1 AND completed_at = ? AND task_id IN ({marks})",
            [stamp, *ids],
        )
        return cur.rowcount


# ---------- settings (API Key 제외) ----------

def get_setting(key: str, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


# ---------- 메시지 화면용 조회 ----------

def list_messages(days: Optional[int] = None, search: Optional[str] = None,
                  starred_only: bool = False):
    """'메시지' 화면용 범용 조회.
    days: 최근 N일로 제한(None이면 전체). search: 제목/발신자/본문 부분 일치.
    starred_only: ⭐ 즐겨찾기한 메시지만."""
    query = "SELECT * FROM messages WHERE 1=1"
    params: list = []
    if starred_only:
        query += " AND starred = 1"
    if days is not None:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        query += " AND received_at >= ?"
        params.append(cutoff)
    if search:
        like = f"%{search}%"
        query += " AND (title LIKE ? OR sender LIKE ? OR body LIKE ?)"
        params.extend([like, like, like])
    query += " ORDER BY received_at DESC"
    with get_conn() as conn:
        return conn.execute(query, params).fetchall()


def set_message_starred(message_id: str, starred: bool):
    """메시지 즐겨찾기(★) 켜고 끄기. 즐겨찾기한 메시지는 오래돼도 지우지 않는다
    (지금은 메시지를 자동으로 지우는 기능이 없지만, 생기면 starred=1은 빼야 한다)."""
    with get_conn() as conn:
        conn.execute("UPDATE messages SET starred = ? WHERE message_id = ?",
                     (1 if starred else 0, message_id))


def starred_message_count() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) c FROM messages WHERE starred = 1").fetchone()["c"]


def tasks_for_message(message_id: str):
    """메시지 하나에 연결된 업무 목록 (messages_for_task()의 역방향)."""
    with get_conn() as conn:
        return conn.execute(
            """SELECT t.* FROM tasks t
               JOIN task_messages tm ON tm.task_id = t.task_id
               WHERE tm.message_id = ?""",
            (message_id,),
        ).fetchall()


# ---------- 지난 알림장 (daily_summary) ----------

def save_daily_summary(date_str: str, summary: dict):
    """'오늘 알림장 만들기' 클릭 시점의 업무 그룹 스냅샷을 저장한다.
    같은 날짜에 다시 만들면 그날 것을 최신 스냅샷으로 덮어쓴다."""
    payload = json.dumps(summary, ensure_ascii=False)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO daily_summary (date, summary) VALUES (?, ?) "
            "ON CONFLICT(date) DO UPDATE SET summary = excluded.summary",
            (date_str, payload),
        )


def get_daily_summary(date_str: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT summary FROM daily_summary WHERE date = ?", (date_str,)
        ).fetchone()
    if not row:
        return None
    return json.loads(row["summary"])


def list_daily_summary_dates():
    """'지난 알림장' 목록 화면용: 최신 날짜부터, 각 날짜의 미완료/완료 건수 포함."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT date, summary FROM daily_summary ORDER BY date DESC"
        ).fetchall()
    result = []
    for r in rows:
        data = json.loads(r["summary"])
        result.append({
            "date": r["date"],
            "total_open": data.get("total_open", 0),
            "total_completed": data.get("total_completed", 0),
        })
    return result


# ---------- 휴일 (holidays) ----------

def is_holiday(date_str: str) -> bool:
    """자동 알림장 생성을 건너뛸지 판단하는 기준. is_dayoff=1인 행만
    True로 본다 — 모의고사·리더십캠프처럼 등교는 하는 학사일정
    (is_dayoff=0)이 실수로 자동 알림장을 건너뛰는 날로 처리되면 안 되기
    때문이다."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM holidays WHERE date = ? AND is_dayoff = 1 LIMIT 1", (date_str,)
        ).fetchone()
        return row is not None


def add_holiday(date_str: str, source: str = "manual", name: str = None, is_dayoff: bool = True):
    """upsert — 이미 있으면 source/name/is_dayoff를 최신 값으로 덮어쓴다
    (예: 선생님이 수동으로 지정해둔 날짜를 나중에 학사일정 자동 채움이
    이름까지 채워 주는 경우)."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO holidays (date, source, name, is_dayoff) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(date) DO UPDATE SET source = excluded.source, name = excluded.name, "
            "is_dayoff = excluded.is_dayoff",
            (date_str, source, name, int(is_dayoff)),
        )


def get_holiday(date_str: str):
    """해당 날짜의 holidays 행을 그대로 돌려준다(없으면 None) — [일정]
    화면이 행사 이름(name)을 보여줄 때 쓴다."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM holidays WHERE date = ?", (date_str,)
        ).fetchone()


def remove_holiday(date_str: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM holidays WHERE date = ?", (date_str,))


def list_holidays_in_year(year: int) -> list:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM holidays WHERE date LIKE ? ORDER BY date",
            (f"{year}-%",),
        ).fetchall()


# ---------- 업무 하나 ----------

def get_task(task_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()


def set_task_deadline(task_id: int, deadline: str):
    """구글 캘린더에서 날짜를 옮겼을 때 업무 마감일도 따라 바꾼다."""
    with get_conn() as conn:
        conn.execute("UPDATE tasks SET deadline = ?, deadline_confidence = 'HIGH' WHERE task_id = ?",
                     (deadline, task_id))


def get_message(message_id: str):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM messages WHERE message_id = ?", (message_id,)).fetchone()


# ---------- 구글 캘린더 연결 ----------

def upsert_gcal_link(calendar_id, event_id, task_id, message_id, msg_key, title, last_date):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO gcal_links (calendar_id, event_id, task_id, message_id, msg_key, title, last_date)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(calendar_id, event_id) DO UPDATE SET
                 task_id = COALESCE(excluded.task_id, gcal_links.task_id),
                 message_id = COALESCE(excluded.message_id, gcal_links.message_id),
                 msg_key = excluded.msg_key, title = excluded.title, last_date = excluded.last_date""",
            (calendar_id, event_id, task_id, message_id, msg_key, title, last_date),
        )


def list_gcal_links(calendar_id: str):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM gcal_links WHERE calendar_id = ?", (calendar_id,)).fetchall()


def update_gcal_link(calendar_id, event_id, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    with get_conn() as conn:
        conn.execute(f"UPDATE gcal_links SET {cols} WHERE calendar_id = ? AND event_id = ?",
                     (*fields.values(), calendar_id, event_id))


def delete_gcal_link(calendar_id, event_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM gcal_links WHERE calendar_id = ? AND event_id = ?", (calendar_id, event_id))


def move_gcal_links(old_calendar_id: str, new_calendar_id: str, event_ids):
    """일정을 다른 캘린더로 옮긴 뒤 연결도 옮긴다(옮겨도 일정 id는 그대로)."""
    with get_conn() as conn:
        for event_id in event_ids:
            conn.execute("UPDATE OR REPLACE gcal_links SET calendar_id = ? WHERE calendar_id = ? AND event_id = ?",
                         (new_calendar_id, old_calendar_id, event_id))


def task_has_gcal_link(task_id: int, calendar_id: str) -> bool:
    with get_conn() as conn:
        return conn.execute("SELECT 1 FROM gcal_links WHERE task_id = ? AND calendar_id = ? LIMIT 1",
                            (task_id, calendar_id)).fetchone() is not None


def message_has_gcal_link(message_id: str, calendar_id: str) -> bool:
    with get_conn() as conn:
        return conn.execute("SELECT 1 FROM gcal_links WHERE message_id = ? AND calendar_id = ? LIMIT 1",
                            (message_id, calendar_id)).fetchone() is not None


def replace_gcal_events(calendar_id: str, rows):
    """'일정' 화면용 사본을 통째로 바꾼다. rows: [(event_id, title, date, time, is_app)]"""
    with get_conn() as conn:
        conn.execute("DELETE FROM gcal_events WHERE calendar_id = ?", (calendar_id,))
        conn.executemany(
            "INSERT OR REPLACE INTO gcal_events (calendar_id, event_id, title, date, time, is_app) VALUES (?,?,?,?,?,?)",
            [(calendar_id, *r) for r in rows],
        )


def gcal_events_on(calendar_id: str, date_str: str):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM gcal_events WHERE calendar_id = ? AND date = ? ORDER BY time = '', time",
            (calendar_id, date_str),
        ).fetchall()


def gcal_event_dates(calendar_id: str, include_other: bool = True) -> set:
    q = "SELECT DISTINCT date FROM gcal_events WHERE calendar_id = ?"
    if not include_other:
        q += " AND is_app = 1"
    with get_conn() as conn:
        return {r["date"] for r in conn.execute(q, (calendar_id,)).fetchall()}
