# -*- coding: utf-8 -*-
"""화면 여러 곳이 함께 알아야 하는 일을 알리는 신호 모음.

카드 안의 버튼(업무 카드·메시지 카드)이 연 창에서 일이 끝났을 때, 그 카드가
메인 창을 몰라도 메인 창이 알아서 화면을 다시 그리고 구글 캘린더와 맞추게
한다."""

from PySide6.QtCore import QObject, Signal


class _AppEvents(QObject):
    # 일정을 넣었거나 연결·캘린더 설정이 바뀌었다 → 맞추기 + 화면 다시 그리기
    calendarChanged = Signal()
    # '일정' 화면의 [🔄 지금 맞추기] → 메인 창이 맞추기를 돌린다
    syncRequested = Signal()
    # 맞추기가 끝났다: dict(결과) 또는 None(연결 전) / 실패 메시지
    syncFinished = Signal(object)
    syncFailed = Signal(str)


hub = _AppEvents()
