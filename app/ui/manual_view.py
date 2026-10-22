# -*- coding: utf-8 -*-
"""사이드바 [📖 사용설명서] 화면 — 왼쪽 목차·검색, 오른쪽 내용.

내용은 app/core/manual_content.py에 있다(앱 안에 묶여 있어 인터넷 없이 보인다).
검색하면 해당하는 장만 목차에 남기고, 본문에서 찾은 말을 노란색으로 칠한다.
본문의 <a href="#키"> 링크는 그 장으로 넘어간다."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QTextBrowser,
    QTextEdit, QVBoxLayout, QWidget
)

from ..core import manual_content as mc


class ManualView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current = mc.SECTION_KEYS[0]
        self._build_ui()
        self._fill_toc(mc.SECTION_KEYS)
        self.show_section(self._current)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        title = QLabel("📖 사용설명서")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        sub = QLabel("쿨브리핑 사용법을 화면별로 정리했어요. 업데이트할 때 함께 고쳐져요.")
        sub.setObjectName("Muted")
        root.addWidget(sub)

        body = QHBoxLayout()
        body.setSpacing(14)

        left = QVBoxLayout()
        left.setSpacing(8)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 찾기 (예: API 키)")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search)
        left.addWidget(self.search_input)
        self.toc = QListWidget()
        self.toc.setObjectName("ManualToc")
        self.toc.setFixedWidth(240)
        self.toc.currentItemChanged.connect(self._on_toc_changed)
        left.addWidget(self.toc, 1)
        self.no_result = QLabel("찾는 내용이 없어요.")
        self.no_result.setObjectName("Muted")
        self.no_result.hide()
        left.addWidget(self.no_result)
        body.addLayout(left)

        self.doc = QTextBrowser()
        self.doc.setObjectName("ManualDoc")
        self.doc.setOpenLinks(False)          # 우리가 직접 처리(내부 링크·바깥 링크)
        self.doc.anchorClicked.connect(self._on_link)
        self.doc.document().setDefaultStyleSheet(
            "h2 { font-size: 20px; } h3 { font-size: 15px; margin-top: 14px; }"
            " p, li, td { font-size: 14px; line-height: 150%; } a { color: #4F76F5; }"
        )
        body.addWidget(self.doc, 1)
        root.addLayout(body, 1)

    # ---------- 목차 ----------

    def _fill_toc(self, keys):
        self.toc.blockSignals(True)
        self.toc.clear()
        for key, title, _html in mc.SECTIONS:
            if key in keys:
                item = QListWidgetItem(title)
                item.setData(Qt.UserRole, key)
                self.toc.addItem(item)
                if key == self._current:
                    self.toc.setCurrentItem(item)
        self.toc.blockSignals(False)
        self.no_result.setVisible(not keys)

    def _on_toc_changed(self, item, _prev=None):
        if item is not None:
            self.show_section(item.data(Qt.UserRole))

    def show_section(self, key: str):
        """다른 화면에서 '이 부분 설명 보기'로 바로 열 때도 쓴다."""
        if key not in mc.SECTION_KEYS:
            return
        self._current = key
        html = next(h for k, _t, h in mc.SECTIONS if k == key)
        self.doc.setHtml(html)
        self.doc.verticalScrollBar().setValue(0)
        for i in range(self.toc.count()):
            item = self.toc.item(i)
            if item.data(Qt.UserRole) == key and self.toc.currentItem() is not item:
                self.toc.blockSignals(True)
                self.toc.setCurrentItem(item)
                self.toc.blockSignals(False)
        self._highlight(self.search_input.text().strip())

    # ---------- 검색 ----------

    def _on_search(self, text):
        q = text.strip()
        keys = mc.search(q)
        if keys and self._current not in keys:
            self._current = keys[0]
        self._fill_toc(keys)
        if keys:
            self.show_section(self._current)
        else:
            self._highlight("")

    def _highlight(self, query: str):
        if not query:
            self.doc.setExtraSelections([])
            return
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#FFF1A8"))
        selections = []
        cursor = QTextCursor(self.doc.document())
        while True:
            cursor = self.doc.document().find(query, cursor)
            if cursor.isNull():
                break
            sel = QTextEdit.ExtraSelection()
            sel.cursor = cursor
            sel.format = fmt
            selections.append(sel)
        self.doc.setExtraSelections(selections)
        if selections:
            self.doc.setTextCursor(selections[0].cursor)
            self.doc.ensureCursorVisible()

    # ---------- 링크 ----------

    def _on_link(self, url):
        target = url.toString()
        if target.startswith("#"):
            self.search_input.blockSignals(True)
            self.search_input.clear()
            self.search_input.blockSignals(False)
            self._fill_toc(mc.SECTION_KEYS)
            self.show_section(target[1:])
            return
        import webbrowser
        webbrowser.open(target)

    def refresh(self):
        pass
