# -*- coding: utf-8 -*-
"""'일정' 화면 — 달력 중심. QCalendarWidget을 재스타일링해서 쓰고,
오른쪽에 선택한 날짜의 업무 목록을 보여준다.

이번 범위에서는 회의/행사/연수 같은 업무 외 일정은 다루지 않는다 — 업무
마감일(tasks.deadline)만 달력에 표시한다. 별도 이벤트 테이블은 만들지 않았다."""

from PySide6.QtCore import QDate
from PySide6.QtGui import QTextCharFormat, QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QCalendarWidget
)

from ..core import stats
from .styles import COLORS

_WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]

_CATEGORY_ICON = {
    "학교행정": "🏫", "학생지도": "👩‍🎓", "학부모": "👨‍👩‍👧",
    "수업평가": "📚", "진학": "🎓", "일정": "📅",
    "자료확인": "📎", "참고": "📢", "민감정보": "🔒",
}


class CalendarView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._marked_dates = set()
        self._build_ui()
        self.refresh()

    # ---------- UI 구성 ----------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        header = QVBoxLayout()
        header.setSpacing(2)
        title = QLabel("일정")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        subtitle = QLabel("업무 마감일을 달력으로 확인합니다.")
        subtitle.setObjectName("Muted")
        header.addWidget(subtitle)
        root.addLayout(header)

        content_row = QHBoxLayout()
        content_row.setSpacing(16)

        self.calendar = QCalendarWidget()
        self.calendar.setObjectName("AppCalendar")
        self.calendar.setGridVisible(True)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.calendar.setHorizontalHeaderFormat(QCalendarWidget.ShortDayNames)
        self.calendar.selectionChanged.connect(self._render_selected_day)
        content_row.addWidget(self.calendar, 2)

        panel = QFrame()
        panel.setObjectName("Card")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 16, 18, 16)
        panel_layout.setSpacing(10)

        self.panel_date_label = QLabel("")
        self.panel_date_label.setObjectName("SectionTitle")
        panel_layout.addWidget(self.panel_date_label)

        self.panel_list_layout = QVBoxLayout()
        self.panel_list_layout.setSpacing(8)
        panel_layout.addLayout(self.panel_list_layout)
        panel_layout.addStretch(1)

        content_row.addWidget(panel, 1)
        root.addLayout(content_row)

    def _clear_panel_list(self):
        while self.panel_list_layout.count():
            item = self.panel_list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    # ---------- 데이터 로딩/표시 ----------

    def refresh(self):
        self._mark_task_dates()
        self._render_selected_day()

    def _mark_task_dates(self):
        # 이전에 칠했던 날짜들 원상복구 후 다시 칠한다 (완료 처리 등으로
        # 마감일 집합이 바뀔 수 있으므로 매번 다시 계산).
        for d_str in self._marked_dates:
            qdate = QDate.fromString(d_str, "yyyy-MM-dd")
            if qdate.isValid():
                self.calendar.setDateTextFormat(qdate, QTextCharFormat())

        tasks = stats.todo_tasks()
        dates_with_tasks = {t["deadline"] for t in tasks if t["deadline"]}

        fmt = QTextCharFormat()
        fmt.setBackground(QColor(COLORS["accent"]))
        fmt.setForeground(QColor("white"))
        font = QFont()
        font.setBold(True)
        fmt.setFont(font)

        for d_str in dates_with_tasks:
            qdate = QDate.fromString(d_str, "yyyy-MM-dd")
            if qdate.isValid():
                self.calendar.setDateTextFormat(qdate, fmt)

        self._marked_dates = dates_with_tasks

    def _render_selected_day(self):
        self._clear_panel_list()
        qdate = self.calendar.selectedDate()
        date_str = qdate.toString("yyyy-MM-dd")
        weekday = _WEEKDAY_KR[qdate.dayOfWeek() - 1]
        self.panel_date_label.setText(f"{qdate.year()}년 {qdate.month()}월 {qdate.day()}일 ({weekday})")

        tasks = [t for t in stats.todo_tasks() if t["deadline"] == date_str]
        if not tasks:
            empty = QLabel("이 날짜에 마감인 업무가 없습니다.")
            empty.setObjectName("Muted")
            self.panel_list_layout.addWidget(empty)
            return

        for t in tasks:
            row = QFrame()
            row.setObjectName("Card")
            v = QVBoxLayout(row)
            v.setContentsMargins(12, 10, 12, 10)
            v.setSpacing(3)

            icon = _CATEGORY_ICON.get(t["category"], "📌")
            title = QLabel(f"{icon}  {t['title']}")
            title.setObjectName("TaskTitle")
            title.setWordWrap(True)
            v.addWidget(title)

            meta_bits = [t["category"] or "기타"]
            department = t["department"] if "department" in t.keys() else None
            if department:
                meta_bits.append(department)
            meta = QLabel("  ·  ".join(meta_bits))
            meta.setObjectName("TaskMeta")
            v.addWidget(meta)

            self.panel_list_layout.addWidget(row)
