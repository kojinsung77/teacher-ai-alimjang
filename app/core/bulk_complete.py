# -*- coding: utf-8 -*-
"""'업무' 화면 [✓ 완료 처리 ▾] 메뉴의 계산 부분 — 화면(Qt)과 분리해 둔다.

- 전체 완료: 지금 탭에 보이는 미완료 업무 전부
- 기간을 정해서 완료: 마감일 또는 받은 날짜가 고른 기간 안에 있는 업무

메뉴가 있는 탭은 '전체'·'기한 지남'·'기한 없음' 세 개다. '기한 없음' 탭은
마감일이 없으므로 받은 날짜로만 고른다. 업무를 실제로 완료로 바꾸는 일은
db.complete_tasks_bulk() / db.undo_bulk_complete()가 한다."""

from calendar import monthrange
from collections import namedtuple
from datetime import date, timedelta
from typing import List, Optional

from .dday import parse_deadline
from .deadline_classifier import GROUP_LABELS, DeadlineGroup, classify_deadline

BASIS_DEADLINE = "deadline"
BASIS_RECEIVED = "received"

# [✓ 완료 처리 ▾] 메뉴를 보여 주는 탭 (task_list_view의 탭 key)
MENU_TABS = ("all", "overdue", "no_deadline")

GROUP_ORDER = (
    DeadlineGroup.OVERDUE, DeadlineGroup.TODAY, DeadlineGroup.WITHIN_7_DAYS,
    DeadlineGroup.LATER, DeadlineGroup.NO_DEADLINE,
)
_NOT_DUE_GROUPS = (DeadlineGroup.TODAY, DeadlineGroup.WITHIN_7_DAYS, DeadlineGroup.LATER)

NO_DEADLINE_WARNING = "※ 마감 없는 진행 중 업무도 함께 완료됩니다."
UNDO_HINT = "완료한 업무는 '완료' 탭으로 옮겨지고,\n처리 직후 나타나는 [되돌리기]로 한 번에 취소할 수 있어요."

Preset = namedtuple("Preset", "key label start end")


# ---------- 날짜 ----------

def _get(row, key):
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def received_date(row) -> Optional[date]:
    """업무가 들어온 날 = 연결된 메시지를 받은 날(messages.received_at).
    메시지 연결이 없으면 업무가 만들어진 날(tasks.created_at)로 대신한다."""
    for key in ("received_at", "created_at"):
        value = _get(row, key)
        if value:
            try:
                return date.fromisoformat(str(value)[:10])
            except ValueError:
                continue
    return None


def basis_date(row, basis: str) -> Optional[date]:
    if basis == BASIS_DEADLINE:
        return parse_deadline(_get(row, "deadline"))
    return received_date(row)


def short_date(d: Optional[date]) -> str:
    return f"{d.month}/{d.day}" if d else ""


def long_date(d: Optional[date]) -> str:
    return f"{d.month}월 {d.day}일" if d else ""


# ---------- 기준·빠른 선택 ----------

def bases_for(tab_key: str) -> tuple:
    """탭마다 고를 수 있는 기준. 기한 없음 탭은 받은 날짜뿐."""
    if tab_key == "no_deadline":
        return (BASIS_RECEIVED,)
    return (BASIS_DEADLINE, BASIS_RECEIVED)


def _last_week(today: date):
    monday = today - timedelta(days=today.weekday())
    return monday - timedelta(days=7), monday - timedelta(days=1)


def _last_month(today: date):
    first_this = today.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    return last_prev.replace(day=1), last_prev


def _one_month_ago(today: date) -> date:
    year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return date(year, month, min(today.day, monthrange(year, month)[1]))


def presets_for(tab_key: str, basis: str, today: Optional[date] = None) -> List[Preset]:
    """기간 빠른 선택. start가 None이면 '처음부터'."""
    today = today or date.today()
    lw_start, lw_end = _last_week(today)
    lm_start, lm_end = _last_month(today)
    if basis == BASIS_DEADLINE and tab_key == "overdue":
        return [
            Preset("od_all", "기한 지난 것 전부", None, today - timedelta(days=1)),
            Preset("od_week", "일주일 넘게 지난 것", None, today - timedelta(days=8)),
            Preset("od_last_week", "지난주 마감", lw_start, lw_end),
            Preset("od_last_month", f"지난달({lm_start.month}월) 마감", lm_start, lm_end),
        ]
    if basis == BASIS_DEADLINE:
        this_sunday = today + timedelta(days=6 - today.weekday())
        return [
            Preset("dl_yesterday", "어제까지 (기한 지남)", None, today - timedelta(days=1)),
            Preset("dl_today", "오늘까지", None, today),
            Preset("dl_this_week", "이번 주까지", None, this_sunday),
            Preset("dl_last_week", "지난주 마감", lw_start, lw_end),
        ]
    return [
        Preset("rc_week", "일주일보다 오래된 것", None, today - timedelta(days=7)),
        Preset("rc_2weeks", "2주보다 오래된 것", None, today - timedelta(days=14)),
        Preset("rc_month", "한 달보다 오래된 것", None, _one_month_ago(today)),
        Preset("rc_last_month", f"지난달({lm_start.month}월)에 받은 것", lm_start, lm_end),
    ]


# ---------- 거르기·정렬 ----------

def filter_by_range(tasks, basis: str, start: Optional[date], end: Optional[date]) -> list:
    """basis 날짜가 start~end(양 끝 포함) 안에 있는 업무. 날짜가 없는
    업무(마감일 기준일 때 기한 없는 업무)는 들어가지 않는다."""
    out = []
    for t in tasks:
        d = basis_date(t, basis)
        if d is None:
            continue
        if start is not None and d < start:
            continue
        if end is not None and d > end:
            continue
        out.append(t)
    return out


def sort_for_preview(tasks, today: Optional[date] = None) -> list:
    """미리 보기 목록: 급한 구간 먼저, 같은 구간은 마감일 빠른 순, 받은 날 최근 순."""
    today = today or date.today()

    def key(t):
        group = classify_deadline(_get(t, "deadline"), today)
        d = parse_deadline(_get(t, "deadline")) or date.max
        r = received_date(t) or date.min
        return (GROUP_ORDER.index(group), d, -r.toordinal())

    return sorted(tasks, key=key)


# ---------- 안내 문구 ----------

def breakdown(tasks, today: Optional[date] = None) -> list:
    """[(DeadlineGroup, 건수), ...] — 건수가 있는 구간만, 급한 순."""
    today = today or date.today()
    counts = {}
    for t in tasks:
        g = classify_deadline(_get(t, "deadline"), today)
        counts[g] = counts.get(g, 0) + 1
    return [(g, counts[g]) for g in GROUP_ORDER if counts.get(g)]


def breakdown_text(tasks, today: Optional[date] = None) -> str:
    return " · ".join(f"{GROUP_LABELS[g]} {n}" for g, n in breakdown(tasks, today))


def not_due_warning(tasks, today: Optional[date] = None) -> str:
    """아직 마감 전(오늘까지·7일 이내·그 이후)인 업무가 섞였을 때의 경고.
    섞인 구간 이름만 괄호에 적는다."""
    parts = [(g, n) for g, n in breakdown(tasks, today) if g in _NOT_DUE_GROUPS]
    if not parts:
        return ""
    total = sum(n for _, n in parts)
    names = "·".join(GROUP_LABELS[g] for g, _ in parts)
    return f"⚠ 아직 마감 전인 업무 {total}건({names})도 함께 완료됩니다."


def has_no_deadline(tasks) -> bool:
    return any(parse_deadline(_get(t, "deadline")) is None for t in tasks)


def warnings_for(tasks, today: Optional[date] = None) -> List[str]:
    out = []
    w = not_due_warning(tasks, today)
    if w:
        out.append(w)
    if has_no_deadline(tasks):
        out.append(NO_DEADLINE_WARNING)
    return out


def all_confirm_text(tab_label: str, tasks, today: Optional[date] = None) -> str:
    """[전체 완료] 확인창 본문."""
    lines = [f"'{tab_label}' 업무 {len(tasks)}건을 모두 완료로 바꿀까요?"]
    bd = breakdown_text(tasks, today)
    if bd:
        lines += ["", bd]
    warns = warnings_for(tasks, today)
    if warns:
        lines += [""] + warns
    lines += ["", UNDO_HINT]
    return "\n".join(lines)


def range_text(basis: str, start: Optional[date], end: Optional[date]) -> str:
    name = "마감일" if basis == BASIS_DEADLINE else "받은 날짜"
    left = long_date(start) if start else "처음부터"
    right = long_date(end) if end else "끝까지"
    return f"{name} {left} ~ {right}"
