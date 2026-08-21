# -*- coding: utf-8 -*-
"""'메시지' 화면 — CoolMessenger에서 읽어온 원본 메시지 확인 화면.
메시지는 '원재료'다: 원문 조회, 기간 필터, 검색, AI 분석 상태(ACTION/
REFERENCE/IGNORE/분석 전), 연결된 업무 보기를 담당한다. 업무 추출/완료
처리는 다루지 않는다(그건 '업무' 화면의 역할)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QFrame, QLineEdit, QMessageBox
)

from .. import db
from .common_widgets import build_empty_state

_PERIOD_TABS = [
    ("today", "오늘", 1),
    ("3d", "최근 3일", 3),
    ("7d", "최근 7일", 7),
    ("all", "전체", None),
]

_STATUS_BADGE = {
    "ACTION": ("ACTION", "MsgBadgeAction"),
    "REFERENCE": ("REFERENCE", "MsgBadgeReference"),
    "IGNORE": ("IGNORE", "MsgBadgeIgnore"),
    None: ("분석 전", "MsgBadgePending"),
}


class MessageListView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.active_period = "today"
        self._period_buttons = {}
        self._build_ui()
        self.refresh()

    # ---------- UI 구성 ----------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("메시지")
        title.setObjectName("PageTitle")
        title_col.addWidget(title)
        subtitle = QLabel("쿨메신저에서 읽어온 원본 메시지입니다.")
        subtitle.setObjectName("Muted")
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch(1)
        root.addLayout(header)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(8)
        for key, label, _days in _PERIOD_TABS:
            btn = QPushButton(label)
            btn.setObjectName("PeriodTab")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("active", key == self.active_period)
            btn.clicked.connect(lambda checked=False, k=key: self.select_period(k))
            controls_row.addWidget(btn)
            self._period_buttons[key] = btn
        controls_row.addStretch(1)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("메시지 검색")
        self.search_input.setFixedWidth(220)
        self.search_input.returnPressed.connect(self.refresh)
        controls_row.addWidget(self.search_input)

        search_btn = QPushButton("검색")
        search_btn.setObjectName("SecondaryButton")
        search_btn.setCursor(Qt.PointingHandCursor)
        search_btn.clicked.connect(self.refresh)
        controls_row.addWidget(search_btn)

        root.addLayout(controls_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setSpacing(10)
        self.list_layout.setContentsMargins(0, 4, 0, 0)
        self.scroll.setWidget(self.list_container)
        root.addWidget(self.scroll, 1)

    def _clear_list(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    # ---------- 필터 ----------

    def select_period(self, key: str):
        self.active_period = key
        for k, btn in self._period_buttons.items():
            btn.setProperty("active", k == key)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.refresh()

    # ---------- 데이터 로딩/표시 ----------

    def refresh(self):
        self._clear_list()

        days = next(d for k, _, d in _PERIOD_TABS if k == self.active_period)
        search = self.search_input.text().strip() or None
        rows = db.list_messages(days=days, search=search)

        if not rows:
            empty = build_empty_state(
                "📭", "표시할 메시지가 없습니다.",
                "CoolMessenger 메시지를 분석하면\nAI가 해야 할 일을 정리해드립니다."
            )
            self.list_layout.addWidget(empty)
        else:
            for row in rows:
                self.list_layout.addWidget(self._build_message_item(row))

        self.list_layout.addStretch(1)

    def _build_message_item(self, row) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(4)

        top_row = QHBoxLayout()
        title = QLabel(row["title"] or "(제목 없음)")
        title.setObjectName("TaskTitle")
        title.setWordWrap(True)
        top_row.addWidget(title, 1)

        status_text, status_style = _STATUS_BADGE.get(row["classification"], _STATUS_BADGE[None])
        badge = QLabel(status_text)
        badge.setObjectName(status_style)
        top_row.addWidget(badge)
        v.addLayout(top_row)

        meta_bits = [row["sender"] or "(발신자 없음)"]
        if row["department"]:
            meta_bits.append(row["department"])
        if row["received_at"]:
            meta_bits.append(str(row["received_at"])[:16].replace("T", " "))
        meta = QLabel("  ·  ".join(meta_bits))
        meta.setObjectName("TaskMeta")
        v.addWidget(meta)

        btn_row = QHBoxLayout()
        origin_btn = QPushButton("원문 보기")
        origin_btn.setObjectName("GhostButton")
        origin_btn.setCursor(Qt.PointingHandCursor)
        origin_btn.clicked.connect(lambda: self._show_original(row))
        btn_row.addWidget(origin_btn)

        if row["classification"] == "ACTION":
            linked_btn = QPushButton("연결된 업무 보기")
            linked_btn.setObjectName("GhostButton")
            linked_btn.setCursor(Qt.PointingHandCursor)
            linked_btn.clicked.connect(lambda: self._show_linked_tasks(row["message_id"]))
            btn_row.addWidget(linked_btn)

        btn_row.addStretch(1)
        v.addLayout(btn_row)

        return card

    def _show_original(self, row):
        text = f"[{row['sender']} · {row['department']}]\n{row['title']}\n\n{row['body']}"
        QMessageBox.information(self, "원문 메시지", text)

    def _show_linked_tasks(self, message_id: str):
        tasks = db.tasks_for_message(message_id)
        if not tasks:
            QMessageBox.information(self, "연결된 업무", "이 메시지에서 추출된 업무가 없습니다.")
            return
        lines = [f"• {t['title']}" + (f" ({t['deadline']})" if t["deadline"] else "") for t in tasks]
        QMessageBox.information(self, f"연결된 업무 ({len(tasks)}건)", "\n".join(lines))
