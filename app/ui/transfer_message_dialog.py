# -*- coding: utf-8 -*-
"""[📨 전달 메시지 ▾] → 학생/학부모/교사를 고르면 뜨는 창.

- 위: 받는 사람(학생·학부모·교사) 버튼 — 바꾸면 그 대상용으로 다시 만든다
  (이미 만든 대상은 다시 부르지 않고 저장해 둔 결과를 보여 준다)
- 가운데: AI에 보낼 내용(이름·전화번호 등은 이미 가린 상태). 고쳐서 다시
  만들 수 있다
- 아래: 만들어진 메시지 — 그 자리에서 고친 뒤 [복사]
AI 호출은 백그라운드 스레드에서 한다(창이 멈추지 않게). 계산·프롬프트는
app/core/transfer_message.py에 있다."""

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QDialog, QHBoxLayout, QLabel, QMenu,
    QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout
)

from ..core import transfer_message as tm

# 창을 닫아도 아직 돌고 있는 스레드가 파이썬 쪽에서 먼저 사라져 앱이 죽지
# 않게, 끝날 때까지 여기 붙잡아 둔다.
_RUNNING_THREADS = set()


class _GenerateThread(QThread):
    finished_ok = Signal(int, str, str)     # seq, audience, text
    failed = Signal(int, str, str)          # seq, audience, error

    def __init__(self, seq, audience, source_text, parent=None):
        super().__init__(parent)
        self._seq = seq
        self._audience = audience
        self._source = source_text

    def run(self):
        try:
            text = tm.generate(self._audience, self._source)
            self.finished_ok.emit(self._seq, self._audience, text)
        except Exception as e:  # GeminiKeyError 포함 — 화면에 그대로 안내
            self.failed.emit(self._seq, self._audience, str(e))


def build_audience_menu(parent, on_pick) -> QMenu:
    """카드의 [📨 전달 메시지 ▾]가 띄우는 메뉴. on_pick(audience)를 부른다."""
    menu = QMenu(parent)
    menu.setObjectName("CompleteMenu")  # 업무 화면 [완료 처리] 메뉴와 같은 모양
    for key, _name, label in tm.AUDIENCES:
        action = menu.addAction(label)
        action.triggered.connect(lambda _=False, k=key: on_pick(k))
    return menu


class TransferMessageDialog(QDialog):
    def __init__(self, source: dict, audience: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("전달 메시지 만들기")
        self.setMinimumSize(640, 680)

        self._source = source
        self._audience = audience
        self._results = {}          # audience -> 만든 글(선생님이 고친 것 포함)
        self._seq = 0
        self._busy_audience = None

        self._build_ui()
        self._select_audience(audience, auto=not source.get("sensitive"))
        if source.get("sensitive"):
            self._set_status(
                "⚠ 상담·민감 정보가 있을 수 있는 메시지라 자동으로 보내지 않았어요. "
                "가운데 내용을 확인하고 [✨ 만들기]를 눌러 주세요.", warn=True
            )

    # ---------- 화면 ----------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(10)

        title = QLabel("전달 메시지 만들기")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        if self._source.get("label"):
            sub = QLabel(self._source["label"])
            sub.setObjectName("Muted")
            sub.setWordWrap(True)
            root.addWidget(sub)

        # 받는 사람
        row = QHBoxLayout()
        row.setSpacing(6)
        who = QLabel("받는 사람")
        who.setObjectName("BulkFieldLabel")
        row.addWidget(who)
        row.addSpacing(6)
        self._aud_group = QButtonGroup(self)
        self._aud_group.setExclusive(True)
        self._aud_buttons = {}
        for key, name, _label in tm.AUDIENCES:
            b = QPushButton(name)
            b.setObjectName("SegButton")
            b.setCheckable(True)
            b.setAutoDefault(False)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._select_audience(k))
            self._aud_group.addButton(b)
            self._aud_buttons[key] = b
            row.addWidget(b)
        row.addStretch(1)
        root.addLayout(row)

        # AI에 보낼 내용
        src_head = QHBoxLayout()
        src_label = QLabel("AI에 보낼 내용 — 이름·전화번호 등은 가려서 보내요. 고쳐서 다시 만들 수 있어요.")
        src_label.setObjectName("Muted")
        src_label.setWordWrap(True)
        src_head.addWidget(src_label, 1)
        root.addLayout(src_head)
        self.source_edit = QPlainTextEdit()
        self.source_edit.setObjectName("TransferSource")
        self.source_edit.setPlainText(self._source.get("text", ""))
        self.source_edit.setMinimumHeight(120)
        self.source_edit.setMaximumHeight(170)
        root.addWidget(self.source_edit)

        # 만든 메시지
        res_head = QHBoxLayout()
        self.result_label = QLabel("")
        self.result_label.setObjectName("BulkFieldLabel")
        res_head.addWidget(self.result_label)
        res_head.addStretch(1)
        self.generate_btn = QPushButton("✨ 만들기")
        self.generate_btn.setObjectName("SecondaryButton")
        self.generate_btn.setAutoDefault(False)
        self.generate_btn.setCursor(Qt.PointingHandCursor)
        self.generate_btn.clicked.connect(self._on_generate_clicked)
        res_head.addWidget(self.generate_btn)
        root.addLayout(res_head)

        self.result_edit = QPlainTextEdit()
        self.result_edit.setObjectName("TransferResult")
        self.result_edit.setPlaceholderText("여기에 전달 메시지가 만들어져요. 그대로 고칠 수 있어요.")
        self.result_edit.setMinimumHeight(260)
        self.result_edit.textChanged.connect(self._on_result_edited)
        root.addWidget(self.result_edit, 1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("Muted")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        foot = QHBoxLayout()
        foot.addStretch(1)
        close_btn = QPushButton("닫기")
        close_btn.setObjectName("SecondaryButton")
        close_btn.setAutoDefault(False)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        foot.addWidget(close_btn)
        self.copy_btn = QPushButton("📋 복사")
        self.copy_btn.setObjectName("PrimaryButton")
        self.copy_btn.setAutoDefault(False)
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.clicked.connect(self._on_copy)
        foot.addWidget(self.copy_btn)
        root.addLayout(foot)

    # ---------- 상태 ----------

    def _set_status(self, text, warn=False):
        self.status_label.setText(text)
        self.status_label.setObjectName("BulkWarn" if warn else "Muted")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _refresh_controls(self):
        busy = self._busy_audience == self._audience
        name = tm.AUDIENCE_NAMES[self._audience]
        self.result_label.setText(f"{name}용 전달 메시지")
        has_result = bool(self.result_edit.toPlainText().strip())
        self.generate_btn.setEnabled(not busy)
        self.generate_btn.setText("만드는 중…" if busy else ("🔄 다시 만들기" if has_result else "✨ 만들기"))
        self.copy_btn.setEnabled(has_result and not busy)
        self.result_edit.setReadOnly(busy)

    def _select_audience(self, audience, auto=True):
        self._audience = audience
        for k, b in self._aud_buttons.items():
            b.setChecked(k == audience)
        self._show_result(self._results.get(audience, ""))
        # 상담 등 민감 메시지는 확인창에서 [예]를 누르기 전까지 어떤 경로로도
        # 자동으로 보내지 않는다(받는 사람 버튼으로 바꿔도 마찬가지).
        if self._source.get("sensitive"):
            auto = False
        if audience not in self._results and auto and self._busy_audience != audience:
            self._start_generate()
        else:
            self._refresh_controls()

    def _show_result(self, text):
        self.result_edit.blockSignals(True)
        self.result_edit.setPlainText(text)
        self.result_edit.blockSignals(False)
        self._refresh_controls()

    # ---------- 만들기 ----------

    def _on_generate_clicked(self):
        if self._source.get("sensitive"):
            answer = QMessageBox.question(
                self, "민감 정보 확인",
                "상담·민감 정보가 있을 수 있는 메시지입니다.\n"
                "이름·전화번호 등은 가려서 보내지만, 내용 자체는 AI(Gemini)로 보내집니다.\n"
                "가운데 내용을 확인하셨으면 계속할까요?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
            self._source = dict(self._source, sensitive=False)
        self._start_generate()

    def _start_generate(self):
        source_text = self.source_edit.toPlainText()
        if not source_text.strip():
            self._set_status("AI에 보낼 내용이 비어 있어요.", warn=True)
            return
        self._seq += 1
        audience = self._audience
        self._busy_audience = audience
        self._set_status("✨ AI가 전달 메시지를 만드는 중이에요… (몇 초 걸려요)")
        self._refresh_controls()
        thread = _GenerateThread(self._seq, audience, source_text)
        thread.finished_ok.connect(self._on_generated)
        thread.failed.connect(self._on_failed)
        _RUNNING_THREADS.add(thread)
        thread.finished.connect(lambda t=thread: _RUNNING_THREADS.discard(t))
        thread.start()

    def _on_generated(self, seq, audience, text):
        if seq != self._seq:
            return  # 더 새로운 요청이 있었다
        self._busy_audience = None
        self._results[audience] = text
        if audience == self._audience:
            self._show_result(text)
        self._set_status(f"{tm.AUDIENCE_NAMES[audience]}용 메시지를 만들었어요. 원문에 없는 말이 들어가지 않았는지 "
            "한 번 읽어 보고, 고칠 곳은 고친 뒤 [📋 복사]를 누르세요.")
        self._refresh_controls()

    def _on_failed(self, seq, audience, error):
        if seq != self._seq:
            return
        self._busy_audience = None
        self._set_status(f"만들지 못했어요: {error}", warn=True)
        self._refresh_controls()

    def _on_result_edited(self):
        # 선생님이 고친 글을 그 대상의 결과로 기억 — 대상을 바꿨다 돌아와도 남는다
        if self._busy_audience != self._audience:
            self._results[self._audience] = self.result_edit.toPlainText()
        self._refresh_controls()

    def _on_copy(self):
        text = self.result_edit.toPlainText().strip()
        if not text:
            return
        QApplication.clipboard().setText(text)
        self._set_status("📋 복사했어요. 쿨메신저나 문자에 붙여 넣으세요.")

    # ---------- 닫기 ----------

    def done(self, result):
        # 아직 만드는 중이면 결과가 와도 무시되게 한다(스레드는 끝나면 스스로 정리)
        self._seq += 1
        super().done(result)
