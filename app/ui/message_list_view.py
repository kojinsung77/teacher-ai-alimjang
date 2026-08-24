# -*- coding: utf-8 -*-
"""'메시지' 화면 — CoolMessenger에서 읽어온 원본 메시지 확인 화면.
메시지는 '원재료'다: 원문 조회, 기간 필터, 검색, AI 분석 상태(ACTION/
REFERENCE/IGNORE/분석 전), 연결된 업무 보기를 담당한다. 업무 추출/완료
처리는 다루지 않는다(그건 '업무' 화면의 역할)."""

import html
import re
import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QFrame, QLineEdit, QMessageBox, QDialog
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

# 링크가 이만큼을 넘으면 한꺼번에 새 탭으로 열지 않고 "원문 보기"로 안내한다
# (탭이 우르르 열려서 오히려 혼란스러워지는 걸 막기 위함).
_MAX_AUTO_OPEN_LINKS = 5

_URL_RE = re.compile(r"https?://\S+")
# URL 뒤에 문장이 공백 없이 바로 이어붙는 경우까지는 다루지 않는다 — 공백/개행
# 기준으로 끊고, 문장 끝에 흔히 붙는 문장부호만 잘라내는 정도로 충분하다.
_URL_TRAILING_PUNCT = ".,;:!?)]}'\"”’》』】〉"


def _find_urls(text: str) -> list[str]:
    """본문에서 http(s):// 로 시작하는 URL을 전부 찾아 반환한다."""
    urls = []
    for m in _URL_RE.finditer(text or ""):
        url = m.group(0).rstrip(_URL_TRAILING_PUNCT)
        if url:
            urls.append(url)
    return urls


def _body_to_html(text: str) -> str:
    """본문 텍스트를 안전한 HTML로 변환한다: escape → 개행을 <br>로 → URL을
    <a>로 감싸기. 이 순서를 지켜야 이스케이프된 & 등이 다시 깨지지 않는다."""
    escaped = html.escape(text or "")
    urls = _find_urls(escaped)
    body_html = escaped.replace("\n", "<br>")
    for url in sorted(set(urls), key=len, reverse=True):
        body_html = body_html.replace(url, f'<a href="{url}">{url}</a>')
    return body_html


class _MessageOriginalDialog(QDialog):
    """"원문 보기" 창. QMessageBox 대신 직접 만든 이유는 _DailyNoteResultDialog와
    동일: QMessageBox는 본문에 스크롤 영역이 없어서 본문이 길면 창이 화면 밖으로
    밀려나 확인 버튼이 안 눌리는 경우가 있다. 여기서는 본문만 QScrollArea에 넣고
    확인 버튼은 항상 스크롤 영역 밖 하단에 고정한다."""

    def __init__(self, row, parent=None):
        super().__init__(parent)
        self.setWindowTitle("원문 메시지")
        self.setMinimumWidth(480)
        self.setMaximumHeight(640)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)

        title = QLabel(row["title"] or "(제목 없음)")
        title.setObjectName("PageTitle")
        title.setWordWrap(True)
        root.addWidget(title)

        meta_bits = [row["sender"] or "(발신자 없음)"]
        if row["department"]:
            meta_bits.append(row["department"])
        meta_label = QLabel("  ·  ".join(meta_bits))
        meta_label.setObjectName("Muted")
        root.addWidget(meta_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body_label = QLabel(_body_to_html(row["body"] or ""))
        body_label.setTextFormat(Qt.RichText)
        body_label.setWordWrap(True)
        body_label.setOpenExternalLinks(True)
        scroll.setWidget(body_label)
        root.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        ok_btn = QPushButton("확인")
        ok_btn.setObjectName("PrimaryButton")
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        root.addLayout(btn_row)


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

        urls = _find_urls(row["body"])
        if urls:
            label = "🔗 링크 열기" if len(urls) == 1 else f"🔗 링크 열기 ({len(urls)}개)"
            link_btn = QPushButton(label)
            link_btn.setObjectName("GhostButton")
            link_btn.setCursor(Qt.PointingHandCursor)
            link_btn.clicked.connect(lambda checked=False, u=urls, r=row: self._open_links(u, r))
            btn_row.addWidget(link_btn)

        btn_row.addStretch(1)
        v.addLayout(btn_row)

        return card

    def _open_links(self, urls: list[str], row):
        if len(urls) == 1:
            webbrowser.open(urls[0])
            return
        if len(urls) > _MAX_AUTO_OPEN_LINKS:
            QMessageBox.information(
                self, "링크가 너무 많습니다",
                f"이 메시지에 링크가 {len(urls)}개 있습니다.\n"
                "한꺼번에 열면 혼란스러울 수 있어 '원문 보기'를 대신 엽니다.\n"
                "본문 안의 링크를 하나씩 눌러주세요."
            )
            self._show_original(row)
            return
        for url in urls:
            webbrowser.open(url)

    def _show_original(self, row):
        _MessageOriginalDialog(row, self).exec()

    def _show_linked_tasks(self, message_id: str):
        tasks = db.tasks_for_message(message_id)
        if not tasks:
            QMessageBox.information(self, "연결된 업무", "이 메시지에서 추출된 업무가 없습니다.")
            return
        lines = [f"• {t['title']}" + (f" ({t['deadline']})" if t["deadline"] else "") for t in tasks]
        QMessageBox.information(self, f"연결된 업무 ({len(tasks)}건)", "\n".join(lines))
