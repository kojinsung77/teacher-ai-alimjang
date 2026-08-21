# -*- coding: utf-8 -*-
"""대시보드/업무 화면이 공통으로 쓰는 통계·정렬 계산. 화면(뷰) 코드에서
SQL이나 분류 로직을 중복해서 짜지 않도록 여기에 모아둔다.

마감일 그룹 분류는 전부 deadline_classifier.classify_deadline() 하나만
쓴다 — 탭 배지 숫자, 대시보드 카드, TaskCard 색상이 서로 다른 기준으로
어긋나는 일이 없도록 하기 위함."""

from datetime import date, datetime, timedelta

from .. import db
from .deadline_classifier import DeadlineGroup, classify_deadline

_PRIORITY_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def todo_tasks():
    """미완료 업무 목록 (db.list_tasks(include_completed=False) 그대로)."""
    return db.list_tasks(include_completed=False)


def completed_tasks():
    """완료된 업무만."""
    return [t for t in db.list_tasks(include_completed=True) if t["completed"]]


def group_todo_tasks(tasks=None) -> dict:
    """미완료 업무를 DeadlineGroup별로 묶는다. {DeadlineGroup: [row, ...]}
    (완료 업무는 마감일 그룹과 무관한 별도 상태라 여기 들어오지 않는다.)"""
    if tasks is None:
        tasks = todo_tasks()
    today = date.today()
    grouped = {g: [] for g in DeadlineGroup}
    for t in tasks:
        grouped[classify_deadline(t["deadline"], today)].append(t)
    return grouped


def task_filter_counts() -> dict:
    """'업무' 화면 탭 배지 숫자. 키: "all", DeadlineGroup.value(6개), "completed"."""
    todo = todo_tasks()
    grouped = group_todo_tasks(todo)
    counts = {"all": len(todo)}
    for g in DeadlineGroup:
        counts[g.value] = len(grouped[g])
    counts["completed"] = len(completed_tasks())
    return counts


def sort_deadline_group(tasks: list) -> list:
    """일반 마감일 그룹(기한 지남/오늘까지/7일 이내/그 이후) 정렬:
    1) 마감일 빠른 순 2) 중요도 높은 순 3) 최근 생성 순.
    Python sorted()는 안정 정렬이므로 우선순위가 낮은 키부터 차례로 적용한다."""
    tasks = sorted(tasks, key=lambda t: t["created_at"] or "", reverse=True)
    tasks = sorted(tasks, key=lambda t: _PRIORITY_RANK.get(t["priority"], 1))
    tasks = sorted(tasks, key=lambda t: t["deadline"] or "9999-12-31")
    return tasks


def sort_no_deadline(tasks: list) -> list:
    """'기한 없음' 탭: 최근 생성 순."""
    return sorted(tasks, key=lambda t: t["created_at"] or "", reverse=True)


def sort_completed(tasks: list) -> list:
    """'완료' 탭: 최근 완료 순."""
    return sorted(tasks, key=lambda t: t["completed_at"] or "", reverse=True)


def sort_for_group(group: DeadlineGroup, tasks: list) -> list:
    if group == DeadlineGroup.NO_DEADLINE:
        return sort_no_deadline(tasks)
    return sort_deadline_group(tasks)


def priority_tasks(limit: int = 7) -> list:
    """대시보드 '우선 확인할 업무': 기한 지남 → 오늘까지 → 7일 이내 순으로
    각 그룹 안에서는 sort_deadline_group() 정렬을 적용해 최대 limit개."""
    grouped = group_todo_tasks()
    ordered = []
    for g in (DeadlineGroup.OVERDUE, DeadlineGroup.TODAY, DeadlineGroup.WITHIN_7_DAYS):
        ordered.extend(sort_deadline_group(grouped[g]))
        if len(ordered) >= limit:
            break
    return ordered[:limit]


def analyze_days_setting() -> int:
    """'업무' 화면의 [AI 다시 분석]이 참고하는 분석 기간(일). 설정이 없으면
    1일. 대시보드 '새 메시지' 카드도 이 기준과 반드시 통일해서 세야
    한다 — 화면마다 기간 기준이 다르면 숫자가 서로 안 맞아 혼란스럽다."""
    return int(db.get_setting("analyze_days", "1"))


def new_messages_count(days: int = None) -> int:
    """대시보드 '새 메시지' 카드: 분석 기간(analyze_days) 내 수신된
    메시지 건수. db.list_messages()의 rolling-window 방식과 동일하게
    '오늘 00시' 같은 달력 경계가 아니라 '지금부터 N일 전'을 기준으로
    센다 (전에는 정확히 오늘 날짜만 세서, 분석 기간이 하루보다 길거나
    당일 수신분이 없으면 실제로 새 메시지가 있어도 0건으로 보였다)."""
    if days is None:
        days = analyze_days_setting()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    with db.get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) c FROM messages WHERE received_at >= ?",
            (cutoff,),
        ).fetchone()["c"]


def dashboard_stats() -> dict:
    """대시보드 통계 카드 4개: 기한 지남 / 오늘까지 / 7일 이내 / 새 메시지."""
    grouped = group_todo_tasks()
    return {
        "overdue": len(grouped[DeadlineGroup.OVERDUE]),
        "today": len(grouped[DeadlineGroup.TODAY]),
        "within_7_days": len(grouped[DeadlineGroup.WITHIN_7_DAYS]),
        "new_messages": new_messages_count(),
    }


def message_classification_counts() -> dict:
    """업무 화면 하단 상태 표시줄용: 전체 메시지/참고/제외 건수."""
    with db.get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM messages").fetchone()["c"]
        reference_c = conn.execute(
            "SELECT COUNT(*) c FROM messages WHERE classification='REFERENCE'"
        ).fetchone()["c"]
        ignore_c = conn.execute(
            "SELECT COUNT(*) c FROM messages WHERE classification='IGNORE'"
        ).fetchone()["c"]
    return {"total": total, "reference": reference_c, "ignore": ignore_c}
