# -*- coding: utf-8 -*-
"""사이드바 [📖 사용설명서] 화면 — 왼쪽 목차·검색, 오른쪽 내용.

내용은 app/core/manual_content.py에 있다. 인터넷 없이 보인다.
다른 화면에서 open_section("gcal")처럼 특정 장으로 바로 열 수 있다."""

import html
import re
import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QTextBrowser, QVBoxLayout, QWidget
)

from ..core import manual_content

_TAG_RE = re.compile(r"<[^>]+>")

# QTextBrowser는 CSS를 일부만 지원한다 — 글자 크기·색·여백 정도만 쓴다.
_DOC_CSS = """
h2 { font-size: 20px; font-weight: 800; color: #17243B; margin-bottom: 8px; }
h3 { font-size: 15px; font-weight: 800; color: #17243B; margin-top: 16px; margin-bottom: 4px; }
p, li { font-size: 14px; color: #2A364D; line-height: 150%; }
a { color: #4F76F5; text-decoration: none; font-weight: bold; }
.tip { background-color: #EEF3FF; color: #17243B; padding: 8px; }
"""


def plain_text(html_text: str) -> str:
    return html.unescape(_TAG_RE.sub(" ", html_text or ""))


def highlight(html_text: str, query: str) -> str:
    """태그 밖의 글자에서만 query를 노란색으로 칠한다."""
    if not query:
        return html_text
    pattern = re.compile(re.escape(html.escape(query)))

    def mark_text(segment):
        return pattern.sub(lambda m: f'<span style="background-color:#FFF1A8">{m.group(0)}</span>', segment)

    out, pos = [], 0
    for m in _TAG_RE.finditer(html_text):
        out.append(mark_text(html_text[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(mark_text(html_text[pos:]))
    return "".join(out)


def matching_keys(query: str) -> list:
    """검색어가 목차 제목이나 본문에 들어 있는 장 key 목록(순서대로)."""
    q = (query or "").strip()
    keys = []
    for key, title, _ in manual_content.SECTIONS:
        body = manual_content.section_html(key)
        if not q or q in title or q in plain_text(body):
            keys.append(key)
    return keys


class ManualView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current = manual_content.SECTIONS[0][0]
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        title = QLabel("📖 사용설명서")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        sub = QLabel("인터넷 없이도 볼 수 있어요. 업데이트할 때 함께 고쳐져요.")
        sub.setObjectName("Muted")
        root.addWidget(sub)

        body = QHBoxLayout()
        body.setSpacing(14)

        left = QFrame()
        left.setObjectName("Card")
        left.setFixedWidth(250)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(10, 10, 10, 10)
        lv.setSpacing(6)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 찾기 (예: API 키)")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search)
        lv.addWidget(self.search_input)
        self.toc = QListWidget()
        self.toc.setObjectName("ManualToc")
        self.toc.currentItemChanged.connect(self._on_toc_changed)
        lv.addWidget(self.toc, 1)
        body.addWidget(left)

        self.doc = QTextBrowser()
        self.doc.setObjectName("ManualDoc")
        self.doc.setOpenLinks(False)              # 장 이동(#key)과 외부 링크를 직접 처리
        self.doc.anchorClicked.connect(self._on_link)
        self.doc.document().setDefaultStyleSheet(_DOC_CSS)
        body.addWidget(self.doc, 1)

        root.addLayout(body, 1)

    # ---------- 표시 ----------

    def refresh(self):
        self._fill_toc(matching_keys(self.search_input.text()))
        self._show(self._current)

    def _fill_toc(self, keys):
        self.toc.blockSignals(True)
        self.toc.clear()
        for key, title, _ in manual_content.SECTIONS:
            if key not in keys:
                continue
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, key)
            self.toc.addItem(item)
            if key == self._current:
                self.toc.setCurrentItem(item)
        self.toc.blockSignals(False)

    def _show(self, key):
        self._current = key
        query = self.search_input.text().strip()
        self.doc.setHtml(highlight(manual_content.section_html(key), query))
        for i in range(self.toc.count()):
            item = self.toc.item(i)
            if item.data(Qt.UserRole) == key:
                self.toc.blockSignals(True)
                self.toc.setCurrentItem(item)
                self.toc.blockSignals(False)

    def open_section(self, key: str):
        """다른 화면에서 특정 장으로 바로 열 때."""
        self.search_input.blockSignals(True)
        self.search_input.clear()
        self.search_input.blockSignals(False)
        self._current = key
        self.refresh()

    # ---------- 이벤트 ----------

    def _on_toc_changed(self, current, _previous):
        if current is not None:
            self._show(current.data(Qt.UserRole))

    def _on_search(self, text):
        keys = matching_keys(text)
        if keys and self._current not in keys:
            self._current = keys[0]
        self._fill_toc(keys)
        if keys:
            self._show(self._current)
        else:
            self.doc.setHtml("<p>찾는 내용이 없어요. 다른 말로 찾아 보세요.</p>")

    def _on_link(self, url):
        target = url.toString()
        if target.startswith("#"):
            self.open_section(target[1:])
        elif target.startswith("http"):
            webbrowser.open(target)
