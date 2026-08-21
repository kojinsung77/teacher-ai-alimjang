# -*- coding: utf-8 -*-
"""업무를 마감일 기준으로 분류하는 단일 진실 공급원(Single Source of Truth).

'업무' 화면의 탭 필터, '오늘' 대시보드의 통계 카드, TaskCard의 강조 색상이
전부 이 모듈 하나만 참조한다 — 화면마다 분류 기준이 중복/불일치하지 않도록.

완료 여부(completed)는 마감일 그룹과 무관한 별도 상태이므로 이 모듈에서
다루지 않는다 (호출부에서 completed=True인 업무는 애초에 여기 넣지 않거나,
넣더라도 '완료' 탭은 그룹과 별개로 취급한다)."""

from datetime import date, datetime
from enum import Enum
from typing import Optional, Union


class DeadlineGroup(Enum):
    OVERDUE = "overdue"
    TODAY = "today"
    WITHIN_7_DAYS = "within_7_days"
    LATER = "later"
    NO_DEADLINE = "no_deadline"


# 화면 표시용 한글 라벨 (탭 이름 등에서 재사용)
GROUP_LABELS = {
    DeadlineGroup.OVERDUE: "기한 지남",
    DeadlineGroup.TODAY: "오늘까지",
    DeadlineGroup.WITHIN_7_DAYS: "7일 이내",
    DeadlineGroup.LATER: "그 이후",
    DeadlineGroup.NO_DEADLINE: "기한 없음",
}

# 탭이 나열되는 고정 순서 (요청하신 순서 그대로)
GROUP_ORDER = [
    DeadlineGroup.OVERDUE,
    DeadlineGroup.TODAY,
    DeadlineGroup.WITHIN_7_DAYS,
    DeadlineGroup.LATER,
    DeadlineGroup.NO_DEADLINE,
]


def _to_date(value: Optional[Union[str, date, datetime]]) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def classify_deadline(deadline: Optional[Union[str, date]], today: Optional[date] = None) -> DeadlineGroup:
    """마감일 하나를 DeadlineGroup 중 정확히 하나로 분류한다.

    deadline: ISO 날짜 문자열("YYYY-MM-DD") 또는 date 객체 또는 None/빈 문자열.
    today: 기준 날짜. 생략하면 date.today() (호출 시점 기준으로 매번 새로 계산되므로
           '밤새 실행' 시나리오에서도 다음 refresh() 때 자동으로 재분류된다).
    """
    if today is None:
        today = date.today()

    d = _to_date(deadline)
    if d is None:
        return DeadlineGroup.NO_DEADLINE

    delta = (d - today).days
    if delta < 0:
        return DeadlineGroup.OVERDUE
    if delta == 0:
        return DeadlineGroup.TODAY
    if delta <= 7:
        return DeadlineGroup.WITHIN_7_DAYS
    return DeadlineGroup.LATER
