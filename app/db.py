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
    date    TEXT PRIMARY KEY,          -- ISO 날짜 (yyyy-MM-dd)
    source  TEXT DEFAULT 'manual',     -- 'api'(공휴일 자동 채움) | 'manual'(선생님이 직접 추가)
    name    TEXT                       -- API가 채워준 경우 "신정", "어린이날" 등. manual이면 NULL 가능
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


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


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
    """tasks.* 전부 + 연결된 원본 메시지의 department(발신 부서)를 함께 반환한다.
    (tasks 테이블 자체엔 department 컬럼이 없어 task_messages/messages를 LEFT JOIN;
    한 업무가 보통 메시지 1건에서 만들어지므로 GROUP BY로 안전하게 한 행씩만 남긴다.)
    정렬은 여기서 세밀하게 하지 않는다 — 화면단(app/core/stats.py)에서
    마감일/중요도/생성일 다중 기준으로 다시 정렬한다."""
    base = """
        SELECT t.*, m.department as department, m.sender as sender
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

def list_messages(days: Optional[int] = None, search: Optional[str] = None):
    """'메시지' 화면용 범용 조회.
    days: 최근 N일로 제한(None이면 전체). search: 제목/발신자/본문 부분 일치."""
    query = "SELECT * FROM messages WHERE 1=1"
    params: list = []
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
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM holidays WHERE date = ? LIMIT 1", (date_str,)
        ).fetchone()
        return row is not None


def add_holiday(date_str: str, source: str = "manual", name: str = None):
    """upsert — 이미 있으면 source/name을 최신 값으로 덮어쓴다(예: 선생님이
    수동으로 지정해둔 날짜를 나중에 공휴일 API 자동 채움이 이름까지 채워
    주는 경우)."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO holidays (date, source, name) VALUES (?, ?, ?) "
            "ON CONFLICT(date) DO UPDATE SET source = excluded.source, name = excluded.name",
            (date_str, source, name),
        )


def remove_holiday(date_str: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM holidays WHERE date = ?", (date_str,))


def list_holidays_in_year(year: int) -> list:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM holidays WHERE date LIKE ? ORDER BY date",
            (f"{year}-%",),
        ).fetchall()
