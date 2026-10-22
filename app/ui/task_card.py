# -*- coding: utf-8 -*-
"""업무 하나를 표시하는 공통 카드 위젯. '업무' 화면의 모든 탭이 이 카드 하나를
그대로 재사용한다(탭마다 카드 코드를 따로 만들지 않음)."""

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton
)

from .styles import COLORS
from .. import db
from ..core import transfer_message
from .transfer_message_dialog import TransferMessageDialog
from ..core import gcal_service, google_auth
from .app_events import hub
from ..core import bulk_complete, dday
from ..core.deadline_classifier import DeadlineGroup, classify_deadline

_GROUP_COLOR = {
    # 급함 정도가 색으로 단계적으로 구분되도록: 기한 지남=빨강 →
    # 오늘까지=코랄 → 7일 이내=호박색 → 그 이후=파랑.
    DeadlineGroup.OVERDUE: COLORS["today"],
    DeadlineGroup.TODAY: COLORS["tomorrow"],
    DeadlineGroup.WITHIN_7_DAYS: COLORS["amber"],
    DeadlineGroup.LATER: COLORS["this_week"],
    DeadlineGroup.NO_DEADLINE: COLORS["later"],
}

_CATEGORY_ICON = {
    "학교행정": "🏫", "학생지도": "👩‍🎓", "학부모": "👨‍👩‍👧",
    "수업평가": "📚", "진학": "🎓", "일정": "📅",
    "자료확인": "📎", "참고": "📢", "민감정보": "🔒",
}


class TaskCard(QFrame):
    completedToggled = Signal(int, bool)   # task_id, completed
    viewOriginalRequested = Signal(int)    # task_id

    def __init__(self, task_row, parent=None):
        super().__init__(parent)
        self.task_id = task_row["task_id"]
        self._task_row = task_row
        self.setObjectName("Card")
        self.setMinimumHeight(74)

        is_completed = bool(task_row["completed"])
        if is_completed:
            strip_color = COLORS["success"]
        else:
            group = classify_deadline(task_row["deadline"])
            strip_color = _GROUP_COLOR.get(group, COLORS["later"])

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 14, 0)
        outer.setSpacing(0)

        strip = QFrame()
        strip.setFixedWidth(5)
        strip.setStyleSheet(
            f"background-color: {strip_color}; border-top-left-radius: 12px; "
            f"border-bottom-left-radius: 12px;"
        )
        outer.addWidget(strip)

        body = QVBoxLayout()
        body.setContentsMargins(16, 12, 0, 12)
        body.setSpacing(4)

        top_row = QHBoxLayout()
        icon = _CATEGORY_ICON.get(task_row["category"], "📌")
        title = QLabel(f"{icon}  {task_row['title']}")
        title.setObjectName("TaskTitle")
        title.setWordWrap(True)
        top_row.addWidget(title, 1)
        body.addLayout(top_row)

        if task_row["summary"]:
            summary = QLabel(task_row["summary"])
            summary.setObjectName("Muted")
            summary.setWordWrap(True)
            body.addWidget(summary)

        meta_bits = [task_row["category"] or "기타"]
        department = task_row["department"] if "department" in task_row.keys() else None
        if department:
            meta_bits.append(department)
        dday_label = dday.dday_label(task_row["deadline"], task_row["deadline_confidence"])
        meta_bits.append(dday_label)
        # 받은 날짜 — '기간을 정해서 완료'에서 받은 날짜로 고를 때 참고할 수 있게
        received = bulk_complete.received_date(task_row)
        if received:
            meta_bits.append(f"받은 날 {bulk_complete.short_date(received)}")
        if task_row["requires_attachment_check"]:
            meta_bits.append("📎 첨부 확인 필요")
        if task_row["requires_reply"]:
            meta_bits.append("↩ 회신 필요")
        meta = QLabel("  ·  ".join(meta_bits))
        meta.setObjectName("TaskMeta")
        body.addWidget(meta)

        outer.addLayout(body, 1)

        actions = QVBoxLayout()
        actions.setContentsMargins(0, 12, 0, 12)
        actions.setSpacing(8)
        actions.setAlignment(Qt.AlignTop)

        complete_btn = QPushButton("완료" if not is_completed else "완료됨 ✓")
        complete_btn.setObjectName("CompleteButton")
        complete_btn.setCursor(Qt.PointingHandCursor)
        complete_btn.clicked.connect(
            lambda: self.completedToggled.emit(self.task_id, not is_completed)
        )
        actions.addWidget(complete_btn)

        origin_btn = QPushButton("원문 보기")
        origin_btn.setObjectName("GhostButton")
        origin_btn.setCursor(Qt.PointingHandCursor)
        origin_btn.clicked.connect(lambda: self.viewOriginalRequested.emit(self.task_id))
        actions.addWidget(origin_btn)

        # 학생·학부모·교사에게 보낼 안내 문구를 AI로 만든다
        self.transfer_btn = QPushButton("📨 전달 메시지")
        self.transfer_btn.setObjectName("GhostButton")
        self.transfer_btn.setCursor(Qt.PointingHandCursor)
        self.transfer_btn.setToolTip("이 업무를 학생·학부모·선생님께 보낼 안내 문구로 만듭니다")
        self.transfer_btn.clicked.connect(self._open_transfer)
        actions.addWidget(self.transfer_btn)

        # 구글 캘린더에 일정 넣기 — 이미 넣었으면 초록 "캘린더에 있음 ✓".
        # 구글 연결 정보가 없는 빌드에서는 버튼 자체를 두지 않는다.
        self.cal_btn = None
        if google_auth.is_available():
            in_cal = gcal_service.is_ready() and db.task_has_gcal_link(self.task_id, gcal_service.calendar_id())
            self.cal_btn = QPushButton("📅 캘린더에 있음 ✓" if in_cal else "📅 일정에 넣기")
            self.cal_btn.setObjectName("GcalDoneButton" if in_cal else "GcalButton")
            self.cal_btn.setCursor(Qt.PointingHandCursor)
            self.cal_btn.setToolTip("구글 캘린더에 이 업무 일정을 넣습니다(이미 있으면 고쳐요)")
            self.cal_btn.clicked.connect(self._open_calendar)
            actions.addWidget(self.cal_btn)

        outer.addLayout(actions)

    # ---------- 전달 메시지 ----------

    def _open_transfer(self):
        messages = list(db.messages_for_task(self.task_id))
        source = transfer_message.source_for_messages(messages, task=self._task_row)
        TransferMessageDialog(source, parent=self.window()).exec()

    # ---------- 구글 캘린더 ----------

    def _open_calendar(self):
        from .gcal_event_dialog import GCalEventDialog
        messages = list(db.messages_for_task(self.task_id))
        task = db.get_task(self.task_id) or self._task_row
        dlg = GCalEventDialog(messages, task=task, label=self._task_row["title"], parent=self.window())
        dlg.saved.connect(lambda _r: hub.calendarChanged.emit())
        dlg.exec()
