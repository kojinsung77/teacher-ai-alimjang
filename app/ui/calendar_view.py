# -*- coding: utf-8 -*-
"""'일정' 화면 — 달력 중심. QCalendarWidget을 재스타일링해서 쓰고,
오른쪽에 선택한 날짜의 업무 목록을 보여준다.

업무 마감일(tasks.deadline)과 학사일정(db.holidays)을 함께 달력에
표시한다. 별도 이벤트 테이블은 만들지 않고, 학사일정도 holidays 테이블
하나로 관리한다 — 각 행의 is_dayoff로 "등교하지 않는 날"(휴업일/공휴일,
회색)과 "등교하지만 행사가 있는 날"(모의고사·리더십캠프 등, 보라색)을
구분해서 칠한다. NEIS 학사일정 자동 채움(app/core/holidays_sync.py)이
채워준 날짜와 선생님이 직접 체크박스로 지정한 날짜가 함께 들어간다.

QCalendarWidget은 날짜 칸에 배경색/밑줄을 입히는 setDateTextFormat()만
지원하고 칸 안에 별도 텍스트(이름)를 넣는 기능은 없다 — 그래서 달을 한눈에
훑어볼 때 무슨 일정인지 색깔만으로는 알기 어려운 한계가 있다. 이를
보완하려고 캘린더 아래에 "이번 달 학사일정" 목록(월 이동 시 함께
갱신)을 별도로 둔다. 캘린더를 직접 그리는 방식으로 새로 만드는 대신 이
방식을 택한 이유는 지금 잘 작동하는 캘린더 부품(월 이동/날짜 클릭/업무
마감일 색칠)을 전혀 건드리지 않아도 되기 때문이다."""

from PySide6.QtCore import QDate
from PySide6.QtGui import QTextCharFormat, QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QCalendarWidget,
    QScrollArea, QCheckBox, QSizePolicy
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
        # "이번 달 학사일정" 목록에서 날짜별 줄(QFrame)을 찾아 강조/스크롤
        # 하기 위한 인덱스. _clear_month_events_list()가 월 이동 때마다
        # 다시 초기화한다.
        self._month_event_rows = {}
        self._highlighted_month_event_date = None
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
        # QCalendarWidget 기본 정책은 세로 Expanding이라, 화면(창) 높이가
        # 컴퓨터마다 다르면(_resize_to_screen()이 화면 해상도에 따라
        # 900x600~1200x800 사이에서 창 크기를 정함) 캘린더 세로 크기도
        # 그만큼 들쭉날쭉해진다 — 실측 결과 900x600 창에서는 214px,
        # 1200x800 창에서는 414px까지 벌어졌다. Maximum으로 바꾸면 "남는
        # 공간이 있어도 자기 고유 크기(사실상 최소 크기) 이상으로는
        # 늘어나지 않게" 되어 화면 크기와 무관하게 항상 같은 높이(실측
        # 199px)로 고정된다 — 날짜 칸이 작아지는 하한 걱정은 없다(상한만
        # 걸 뿐 하한은 강제하지 않는데, 실측상 900x600 하한에서도 199px
        # 그대로였다).
        self.calendar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        calendar_col = QVBoxLayout()
        calendar_col.setSpacing(16)
        calendar_col.addWidget(self.calendar)

        self.month_events_box = QFrame()
        self.month_events_box.setObjectName("Card")
        # 캘린더 높이를 고정했으니, 컴퓨터마다 남는(혹은 모자란) 세로
        # 공간은 이제 이 카드가 흡수해야 한다 — Expanding으로 바꿔서
        # calendar_col의 남는 공간을 이 카드가 가져가게 한다(기존
        # Maximum 정책은 카드를 항상 자기 내용 크기로만 고정해서, 캘린더가
        # 작아진 만큼 생기는 여유 공간이 목록이 아니라 빈 여백으로
        # 버려졌다).
        self.month_events_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        month_events_layout = QVBoxLayout(self.month_events_box)
        month_events_layout.setContentsMargins(18, 16, 18, 16)
        month_events_layout.setSpacing(10)

        month_events_title = QLabel("이번 달 학사일정")
        month_events_title.setObjectName("SectionTitle")
        month_events_layout.addWidget(month_events_title)

        # 날짜 클릭 시 해당 줄로 스크롤하려면(ensureWidgetVisible) 이
        # 스크롤 영역 자체를 인스턴스 속성으로 들고 있어야 한다.
        self.month_events_scroll = QScrollArea()
        self.month_events_scroll.setWidgetResizable(True)
        self.month_events_scroll.setFrameShape(QFrame.NoFrame)
        # 예전엔 200을 상한이자 사실상 고정값으로 썼다(카드 자체가
        # Maximum이라 늘 200 그대로였음). 이제 카드가 Expanding이라 남는
        # 공간만큼 커질 수 있으니, 200은 "최소한 이만큼은 보장" 정도의
        # 여유 있는 상한으로 올려 둔다 — 그래도 화면이 극단적으로 커지는
        # 경우를 대비해 무한정 늘어나지는 않게 상한 자체는 유지한다.
        self.month_events_scroll.setMaximumHeight(500)
        month_events_container = QWidget()
        self.month_events_list_layout = QVBoxLayout(month_events_container)
        self.month_events_list_layout.setContentsMargins(0, 0, 0, 0)
        self.month_events_list_layout.setSpacing(6)
        self.month_events_scroll.setWidget(month_events_container)
        month_events_layout.addWidget(self.month_events_scroll, 1)

        calendar_col.addWidget(self.month_events_box)
        content_row.addLayout(calendar_col, 2)

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

    def _clear_month_events_list(self):
        while self.month_events_list_layout.count():
            item = self.month_events_list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        # 기존 줄이 전부 삭제되므로 인덱스와 강조 상태도 함께 비운다 —
        # 안 비우면 이미 deleteLater()된(곧 없어질) 프레임을 가리키는
        # 죽은 참조가 남는다.
        self._month_event_rows = {}
        self._highlighted_month_event_date = None

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
        self._render_month_events(holiday_rows)

    def _render_month_events(self, holiday_rows):
        """캘린더 아래 "이번 달 학사일정" 목록을 채운다. holiday_rows는
        _mark_calendar_dates()가 이미 조회해 둔 그 해 전체 목록을 그대로
        받아서 여기서 다시 쿼리하지 않는다 — 지금 보이는 달(연/월)로만
        걸러서 날짜순으로 나열한다. 상세 패널(_render_selected_day)과
        똑같은 🚫(등교 안 함)/📌(등교하지만 행사 있음) 아이콘 규칙을
        그대로 쓴다."""
        self._clear_month_events_list()

        year = self.calendar.yearShown()
        month = self.calendar.monthShown()
        month_prefix = f"{year}-{month:02d}-"
        rows = sorted(
            (r for r in holiday_rows if r["name"] and r["date"].startswith(month_prefix)),
            key=lambda r: r["date"],
        )

        if not rows:
            empty = QLabel("이번 달은 등록된 학사일정이 없습니다.")
            empty.setObjectName("Muted")
            self.month_events_list_layout.addWidget(empty)
            self.month_events_list_layout.addStretch(1)
            return

        for r in rows:
            qdate = QDate.fromString(r["date"], "yyyy-MM-dd")
            if not qdate.isValid():
                continue
            weekday = _WEEKDAY_KR[qdate.dayOfWeek() - 1]
            is_dayoff = bool(r["is_dayoff"])
            icon = "🚫" if is_dayoff else "📌"

            # 줄마다 작은 QFrame으로 한 번 감싼다 — 라벨 자체의 objectName은
            # 기존 색상 규칙(Muted/EventLabel)을 위해 그대로 두고, "선택된
            # 날짜" 강조는 이 감싸는 프레임의 objectName만 바꿔서 준다
            # (_highlight_month_event 참고). 날짜별로 찾을 수 있게
            # _month_event_rows에 저장해 둔다.
            row_frame = QFrame()
            row_frame.setObjectName("MonthEventRow")
            row_frame_layout = QVBoxLayout(row_frame)
            row_frame_layout.setContentsMargins(6, 3, 6, 3)
            row_frame_layout.setSpacing(0)

            row_label = QLabel(f"{qdate.month()}/{qdate.day()}({weekday}) {icon} {r['name']}")
            row_label.setObjectName("Muted" if is_dayoff else "EventLabel")
            row_label.setWordWrap(True)
            row_frame_layout.addWidget(row_label)

            self.month_events_list_layout.addWidget(row_frame)
            self._month_event_rows[r["date"]] = row_frame

        self.month_events_list_layout.addStretch(1)

    def _highlight_month_event(self, date_str: str):
        """"이번 달 학사일정" 목록에서 date_str에 해당하는 줄을 강조하고
        화면에 보이도록 스크롤한다. 이전에 강조돼 있던 줄이 있으면 먼저
        해제한다. date_str이 목록에 없으면(그 날짜에 학사일정이 없거나,
        다른 달로 넘어가 목록 자체가 새로 만들어진 경우) 강조 해제만 하고
        조용히 넘어간다 — 에러를 내지 않는다."""
        if self._highlighted_month_event_date is not None:
            prev_frame = self._month_event_rows.get(self._highlighted_month_event_date)
            if prev_frame is not None:
                prev_frame.setObjectName("MonthEventRow")
                prev_frame.style().unpolish(prev_frame)
                prev_frame.style().polish(prev_frame)
            self._highlighted_month_event_date = None

        frame = self._month_event_rows.get(date_str)
        if frame is None:
            return

        frame.setObjectName("MonthEventRowHighlight")
        frame.style().unpolish(frame)
        frame.style().polish(frame)
        self._highlighted_month_event_date = date_str
        self.month_events_scroll.ensureWidgetVisible(frame)

    def _render_selected_day(self):
        self._clear_panel_list()
        qdate = self.calendar.selectedDate()
        date_str = qdate.toString("yyyy-MM-dd")
        weekday = _WEEKDAY_KR[qdate.dayOfWeek() - 1]
        self.panel_date_label.setText(f"{qdate.year()}년 {qdate.month()}월 {qdate.day()}일 ({weekday})")
        self._highlight_month_event(date_str)

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
