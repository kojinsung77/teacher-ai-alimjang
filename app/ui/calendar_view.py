# -*- coding: utf-8 -*-
"""'일정' 화면 — 달력 중심. QCalendarWidget을 재스타일링해서 쓰고,
오른쪽에 선택한 날짜의 업무 목록을 보여준다.

업무 마감일(tasks.deadline)과 학사일정(db.holidays)을 함께 달력에
표시한다. 별도 이벤트 테이블은 만들지 않고, 학사일정도 holidays 테이블
하나로 관리한다 — 각 행의 is_dayoff로 "등교하지 않는 날"(휴업일/공휴일,
회색)과 "등교하지만 행사가 있는 날"(모의고사·리더십캠프 등, 보라색)을
구분해서 칠한다. NEIS 학사일정 자동 채움(app/core/holidays_sync.py)이
채워준 날짜와 선생님이 직접 체크박스로 지정한 날짜가 함께 들어간다."""

from PySide6.QtCore import QDate
from PySide6.QtGui import QTextCharFormat, QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QCalendarWidget,
    QScrollArea, QCheckBox
)

from .. import db
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
        self.calendar.currentPageChanged.connect(self._mark_calendar_dates)
        content_row.addWidget(self.calendar, 2)

        panel = QFrame()
        panel.setObjectName("Card")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 16, 18, 16)
        panel_layout.setSpacing(10)

        self.panel_date_label = QLabel("")
        self.panel_date_label.setObjectName("SectionTitle")
        panel_layout.addWidget(self.panel_date_label)

        # NEIS 학사일정이 채워준 행사 이름("여름방학", "모의고사(3학년)" 등)
        # 표시 전용 — 이름이 없는 날엔 숨긴다.
        self.day_event_label = QLabel("")
        self.day_event_label.setWordWrap(True)
        self.day_event_label.setVisible(False)
        panel_layout.addWidget(self.day_event_label)

        self.holiday_checkbox = QCheckBox("🚫 이 날은 알림장 자동 생성 안 함")
        self.holiday_checkbox.toggled.connect(self._on_holiday_toggled)
        panel_layout.addWidget(self.holiday_checkbox)

        # 날짜 제목은 스크롤 밖 상단에 고정하고, 업무 카드 목록만
        # QScrollArea로 감싼다 — 다른 화면들과 동일한 패턴(예:
        # dashboard_view.py의 _build_ui()). 이렇게 안 하면 업무가 많은
        # 날짜를 선택했을 때 목록이 패널 밖으로 넘쳐서 잘린다.
        panel_scroll = QScrollArea()
        panel_scroll.setWidgetResizable(True)
        panel_scroll.setFrameShape(QFrame.NoFrame)
        panel_list_container = QWidget()
        self.panel_list_layout = QVBoxLayout(panel_list_container)
        self.panel_list_layout.setContentsMargins(0, 0, 0, 0)
        self.panel_list_layout.setSpacing(8)
        panel_scroll.setWidget(panel_list_container)
        panel_layout.addWidget(panel_scroll, 1)

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
        self._mark_calendar_dates()
        self._render_selected_day()

    def _mark_calendar_dates(self, *_args):
        """업무 마감일 + 휴일 지정 날짜를 함께 달력에 칠한다. QCalendarWidget은
        날짜 하나에 서식을 하나만 가질 수 있어서, 두 집합을 각각 칠하면
        나중에 칠한 쪽이 앞의 것을 덮어써 버린다 — 그래서 항상 두 집합을
        먼저 합쳐 계산한 뒤, 겹치는 날짜는 업무 마감일 서식에 밑줄만
        더해서 한 번에 칠한다.
        *_args: QCalendarWidget.currentPageChanged(year, month) 시그널에도
        그대로 연결해 쓰므로 인자를 받되 쓰지는 않는다."""
        # 이전에 칠했던 날짜들 원상복구 후 다시 칠한다 (완료 처리 등으로
        # 집합이 바뀔 수 있으므로 매번 다시 계산).
        for d_str in self._marked_dates:
            qdate = QDate.fromString(d_str, "yyyy-MM-dd")
            if qdate.isValid():
                self.calendar.setDateTextFormat(qdate, QTextCharFormat())

        tasks = stats.todo_tasks()
        task_dates = {t["deadline"] for t in tasks if t["deadline"]}

        # holidays 테이블은 날짜당 한 행뿐이라(PRIMARY KEY) is_dayoff로
        # 두 집합이 서로 겹치지 않게 나뉜다 — 등교하지 않는 날(휴업일/
        # 공휴일)과 등교는 하지만 행사가 있는 날(모의고사 등)을 구분해서
        # 칠한다.
        holiday_rows = db.list_holidays_in_year(self.calendar.yearShown())
        dayoff_dates = {r["date"] for r in holiday_rows if r["is_dayoff"]}
        event_dates = {r["date"] for r in holiday_rows if not r["is_dayoff"]}

        task_font = QFont()
        task_font.setBold(True)

        task_fmt = QTextCharFormat()
        task_fmt.setBackground(QColor(COLORS["accent"]))
        task_fmt.setForeground(QColor("white"))
        task_fmt.setFont(task_font)

        task_holiday_fmt = QTextCharFormat(task_fmt)
        task_holiday_fmt.setFontUnderline(True)

        task_event_fmt = QTextCharFormat(task_fmt)
        task_event_fmt.setFontUnderline(True)
        task_event_fmt.setUnderlineColor(QColor(COLORS["event_accent"]))

        holiday_fmt = QTextCharFormat()
        holiday_fmt.setBackground(QColor(COLORS["holiday_bg"]))
        holiday_fmt.setForeground(QColor(COLORS["text_secondary"]))

        event_font = QFont()
        event_font.setBold(True)
        event_fmt = QTextCharFormat()
        event_fmt.setBackground(QColor(COLORS["event_bg"]))
        event_fmt.setForeground(QColor(COLORS["event_accent"]))
        event_fmt.setFont(event_font)

        all_dates = task_dates | dayoff_dates | event_dates
        for d_str in all_dates:
            qdate = QDate.fromString(d_str, "yyyy-MM-dd")
            if not qdate.isValid():
                continue
            if d_str in task_dates and d_str in dayoff_dates:
                fmt = task_holiday_fmt
            elif d_str in task_dates and d_str in event_dates:
                fmt = task_event_fmt
            elif d_str in task_dates:
                fmt = task_fmt
            elif d_str in dayoff_dates:
                fmt = holiday_fmt
            else:
                fmt = event_fmt
            self.calendar.setDateTextFormat(qdate, fmt)

        self._marked_dates = all_dates

    def _render_selected_day(self):
        self._clear_panel_list()
        qdate = self.calendar.selectedDate()
        date_str = qdate.toString("yyyy-MM-dd")
        weekday = _WEEKDAY_KR[qdate.dayOfWeek() - 1]
        self.panel_date_label.setText(f"{qdate.year()}년 {qdate.month()}월 {qdate.day()}일 ({weekday})")

        # setChecked()가 toggled를 다시 울려 _on_holiday_toggled()가
        # 도로 db.add_holiday/remove_holiday를 부르지 않도록 신호를 잠깐 끈다.
        self.holiday_checkbox.blockSignals(True)
        self.holiday_checkbox.setChecked(db.is_holiday(date_str))
        self.holiday_checkbox.blockSignals(False)

        # NEIS 학사일정이 채워준 이름("여름방학", "모의고사(3학년)" 등)이
        # 있으면 등교 여부와 무관하게 항상 보여준다 — 등교하는 행사일은
        # 휴일 체크박스가 꺼져 있어도 무슨 날인지 알 수 있어야 한다.
        holiday_row = db.get_holiday(date_str)
        if holiday_row and holiday_row["name"]:
            is_dayoff = bool(holiday_row["is_dayoff"])
            self.day_event_label.setText(
                ("🚫 " if is_dayoff else "📌 ") + holiday_row["name"]
            )
            self.day_event_label.setObjectName("Muted" if is_dayoff else "EventLabel")
            self.day_event_label.setVisible(True)
        else:
            self.day_event_label.setVisible(False)

        tasks = [t for t in stats.todo_tasks() if t["deadline"] == date_str]
        if not tasks:
            empty = QLabel("이 날짜에 마감인 업무가 없습니다.")
            empty.setObjectName("Muted")
            self.panel_list_layout.addWidget(empty)
            self.panel_list_layout.addStretch(1)
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

        self.panel_list_layout.addStretch(1)

    # ---------- 액션 ----------

    def _on_holiday_toggled(self, checked: bool):
        """체크박스를 사람이 직접 눌렀을 때만 불린다(_render_selected_day의
        setChecked()는 blockSignals로 이 핸들러를 건너뛴다). 국경일 자동
        채움이 넣어준 날짜라도 선생님이 체크 해제하면 그대로 지워진다 —
        예: '이 공휴일엔 어차피 알림장을 만들 예정'인 경우."""
        date_str = self.calendar.selectedDate().toString("yyyy-MM-dd")
        if checked:
            # NEIS가 채워준 이름이 이미 있으면(예: 등교하는 행사일을
            # 선생님이 직접 "쉬는 날"로 바꾸는 경우) 그 이름은 그대로
            # 남기고 is_dayoff만 켠다 — 덮어써서 이름을 지우지 않는다.
            existing = db.get_holiday(date_str)
            name = existing["name"] if existing else None
            db.add_holiday(date_str, source="manual", name=name)
        else:
            db.remove_holiday(date_str)
        self._mark_calendar_dates()
        self._render_selected_day()
