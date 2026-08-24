# -*- coding: utf-8 -*-
"""오늘 알림장 텍스트/스냅샷 생성. 이 순간에 AI(Gemini)를 새로 호출하지
않는다 — 이미 로컬 DB에 분석돼 있는 업무 목록을 모아서 텍스트로 정리할
뿐이라 가볍고 네트워크에 의존하지 않는다.

'업무' 화면의 수동 [오늘 알림장 만들기] 버튼(task_list_view.py)과
main_window.py의 평일 자동 생성이 이 모듈을 함께 쓴다 — 로직이 두 곳에
따로 있으면 나중에 한쪽만 고치는 실수가 생기기 쉽다."""

from datetime import date

from .. import db
from . import stats
from .deadline_classifier import GROUP_ORDER, GROUP_LABELS


def build_daily_note(today: date = None) -> dict:
    """오늘 알림장 텍스트와 daily_summary 저장용 데이터를 만든다(저장은
    하지 않는다 — 호출부가 필요하면 db.save_daily_summary()로 저장)."""
    if today is None:
        today = date.today()

    grouped = stats.group_todo_tasks()
    completed = stats.completed_tasks()

    lines = [f"📋 {today.month}월 {today.day}일 업무 알림장", ""]
    summary_groups = []
    total_open = 0

    for g in GROUP_ORDER:
        rows = stats.sort_for_group(g, grouped[g])
        total_open += len(rows)
        if not rows:
            continue
        label = GROUP_LABELS[g]
        lines.append(label)
        items = []
        for t in rows:
            suffix = f" - {t['deadline']}" if t["deadline"] else ""
            lines.append(f"• {t['title']}{suffix}")
            items.append({"title": t["title"], "deadline": t["deadline"]})
        lines.append("")
        summary_groups.append({"key": g.value, "label": label, "items": items})

    if completed:
        label = "✅ 완료"
        lines.append(label)
        items = []
        for t in stats.sort_completed(completed):
            lines.append(f"• {t['title']}")
            items.append({"title": t["title"]})
        lines.append("")
        summary_groups.append({"key": "completed", "label": label, "items": items})

    lines.append(f"📌 현재 미처리 업무: {total_open}건")
    note_text = "\n".join(lines)

    return {
        "date_str": today.isoformat(),
        "note_text": note_text,
        "summary": {
            "groups": summary_groups,
            "total_open": total_open,
            "total_completed": len(completed),
            "note_text": note_text,
        },
    }


def generate_and_save_daily_note(today: date = None) -> dict:
    """build_daily_note() 결과를 daily_summary에 저장까지 한다. 같은
    날짜에 여러 번 호출해도(자동 생성 후 수동으로 다시 만들기 등)
    db.save_daily_summary()가 upsert라 안전하게 최신 것으로 덮어쓴다."""
    result = build_daily_note(today)
    db.save_daily_summary(result["date_str"], result["summary"])
    return result
