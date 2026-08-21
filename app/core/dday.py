# -*- coding: utf-8 -*-
"""마감일 표시 로직 (D-Day 계산)."""

from datetime import date
from typing import Optional


def parse_deadline(deadline_str: Optional[str]) -> Optional[date]:
    if not deadline_str:
        return None
    try:
        return date.fromisoformat(deadline_str)
    except ValueError:
        return None


def dday_label(deadline_str: Optional[str], confidence: str = "HIGH") -> str:
    if confidence == "LOW":
        return "⚠ 마감일 확인 필요"
    d = parse_deadline(deadline_str)
    if d is None:
        return "기한 없음"

    delta = (d - date.today()).days
    if delta < 0:
        return f"🚨 기한 지남 D+{abs(delta)}"
    if delta == 0:
        return "오늘"
    if delta == 1:
        return "내일"
    if delta <= 6:
        return f"D-{delta}"
    return "그 이후"


def urgency_bucket(deadline_str: Optional[str], confidence: str = "HIGH") -> str:
    """메인 화면 그룹핑용: TODAY | TOMORROW | THIS_WEEK | LATER | UNKNOWN"""
    if confidence == "LOW":
        return "UNKNOWN"
    d = parse_deadline(deadline_str)
    if d is None:
        return "LATER"
    delta = (d - date.today()).days
    if delta <= 0:
        return "TODAY"
    if delta == 1:
        return "TOMORROW"
    if delta <= 6:
        return "THIS_WEEK"
    return "LATER"
