# -*- coding: utf-8 -*-
"""메시지·업무 카드의 [📅 일정에 넣기] 창.

1) 아직 연결·캘린더가 안 정해졌으면 안내 + [설정 열기]
2) Gemini가 메시지에서 일정 후보를 찾는다(가린 글만). 상담 등 민감 메시지는
   보내기 전에 한 번 묻는다
3) 같은 메시지로 이미 넣은 일정(다른 PC 포함)과 날짜가 같으면 '이미 있음' —
   [넣기]를 누르면 새로 만들지 않고 그 일정을 고친다
4) 선생님이 제목·날짜·시간을 확인·수정하고 넣을 것만 체크해서 [넣기]"""

from datetime import date

from PySide6.QtCore import QDate, QTime, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDateEdit, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QTimeEdit, QVBoxLayout, QWidget
)

from ..core import gcal_api, gcal_service as svc
from ..privacy import masking
from .bg_task import run_in_background

_WEEKDAYS = "월화수목금토일"


def _qdate(s: str) -> QDate:
    d = date.fromisoformat(s)
    return QDate(d.year, d.month, d.day)


def _kday(qd: QDate) -> str:
    return f"{qd.month()}월 {qd.day()}일({_WEEKDAYS[qd.dayOfWeek() - 1]})"


class _CandidateRow(QFrame):
    changed = Signal()

    def __init__(self, index: int, cand: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.cand = cand
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 14, 12)
        v.setSpacing(8)

        head = QHBoxLayout()
        self.include = QCheckBox(f"일정 {index}")
        self.include.setChecked(True)
        self.include.toggled.connect(self._on_toggle)
        head.addWidget(self.include)
        if cand.get("dup_event_id"):
            tag = QLabel("이미 캘린더에 있음 — 넣으면 그 일정을 고쳐요")
            tag.setObjectName("GcalDupTag")
            head.addWidget(tag)
        if cand.get("task_id"):
            tag2 = QLabel("업무와 연결")
            tag2.setObjectName("GcalTaskTag")
            tag2.setToolTip("휴대폰에서 날짜를 옮기면 이 업무의 마감일도 따라 바뀌어요")
            head.addWidget(tag2)
        head.addStretch(1)
        v.addLayout(head)

        self.body = QWidget()
        b = QVBoxLayout(self.body)
        b.setContentsMargins(0, 0, 0, 0)
        b.setSpacing(6)
        title_row = QHBoxLayout()
        title_row.addWidget(self._label("제목"))
        self.title = QLineEdit(cand["title"])
        self.title.textChanged.connect(self.changed.emit)
        title_row.addWidget(self.title, 1)
        b.addLayout(title_row)

        when = QHBoxLayout()
        when.addWidget(self._label("날짜"))
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        self.date.setDate(_qdate(cand["date"]))
        self.date.dateChanged.connect(self._on_date)
        when.addWidget(self.date)
        self.day_label = QLabel(_kday(self.date.date()))
        self.day_label.setObjectName("Muted")
        when.addWidget(self.day_label)
        when.addSpacing(10)
        self.allday = QCheckBox("하루 종일")
        self.allday.setChecked(not cand.get("time"))
        self.allday.toggled.connect(self._on_allday)
        when.addWidget(self.allday)
        self.time = QTimeEdit()
        self.time.setDisplayFormat("HH:mm")
        t = cand.get("time") or "09:00"
        self.time.setTime(QTime(int(t[:2]), int(t[3:5])))
        self.time.setVisible(bool(cand.get("time")))
        when.addWidget(self.time)
        when.addStretch(1)
        b.addLayout(when)
        v.addWidget(self.body)

    def _label(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("BulkFieldLabel")
        lbl.setFixedWidth(34)
        return lbl

    def _on_toggle(self, on):
        self.body.setEnabled(on)
        self.changed.emit()

    def _on_date(self, qd):
        self.day_label.setText(_kday(qd))
        self.changed.emit()

    def _on_allday(self, on):
        self.time.setVisible(not on)

    def value(self) -> dict:
        qd = self.date.date()
        c = dict(self.cand)
        c["title"] = self.title.text().strip() or self.cand["title"]
        c["date"] = date(qd.year(), qd.month(), qd.day()).isoformat()
        c["time"] = "" if self.allday.isChecked() else self.time.time().toString("HH:mm")
        # 확인 창에서 날짜를 바꾸면 '이미 있음' 짝도 바뀔 수 있다 — 원래 날짜일 때만 고치기
        if c["date"] != self.cand["date"]:
            c["dup_event_id"] = None
        return c


class GCalEventDialog(QDialog):
    saved = Signal(dict)   # {'added','updated'}

    def __init__(self, messages, task=None, label: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("구글 캘린더에 일정 넣기")
        self.setMinimumSize(640, 560)
        self._messages = [m for m in messages if m is not None]
        self._task = task
        self._rows = []
        self._busy = False
        self._build_ui(label)
        self._start()

    def _build_ui(self, label):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18)
        root.setSpacing(10)
        title = QLabel("📅 구글 캘린더에 일정 넣기")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        if label:
            sub = QLabel(label)
            sub.setObjectName("Muted")
            sub.setWordWrap(True)
            root.addWidget(sub)

        self.target_label = QLabel("")
        self.target_label.setObjectName("GcalCurrent")
        self.target_label.setTextFormat(Qt.RichText)
        root.addWidget(self.target_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.list_box = QWidget()
        self.list_layout = QVBoxLayout(self.list_box)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.scroll.setWidget(self.list_box)
        root.addWidget(self.scroll, 1)

        note = QLabel("🔒 일정 제목에는 학생 이름이 가려져 들어가요. AI가 읽은 날짜가 맞는지 꼭 확인해 주세요.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        root.addWidget(note)
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        foot = QHBoxLayout()
        foot.addStretch(1)
        self.cancel_btn = QPushButton("취소")
        self.cancel_btn.setObjectName("SecondaryButton")
        self.cancel_btn.setAutoDefault(False)
        self.cancel_btn.clicked.connect(self.reject)
        foot.addWidget(self.cancel_btn)
        self.ok_btn = QPushButton("넣기")
        self.ok_btn.setObjectName("PrimaryButton")
        self.ok_btn.setAutoDefault(False)
        self.ok_btn.clicked.connect(self._on_ok)
        foot.addWidget(self.ok_btn)
        root.addLayout(foot)

    # ---------- 단계 ----------

    def _set_status(self, text, warn=False):
        self.status.setText(text)
        self.status.setObjectName("BulkWarn" if warn else "Muted")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def _clear(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows = []

    def _start(self):
        self._clear()
        if not svc.is_ready():
            self._mode = "setup"
            self.target_label.setText("")
            box = QLabel("🔗 아직 구글 캘린더가 연결되지 않았어요.<br>"
                         "<span style='color:#6D7890'>설정 → 구글 캘린더에서 학교 계정을 연결하고, "
                         "일정을 넣을 캘린더를 정하면 바로 쓸 수 있어요.</span>")
            box.setTextFormat(Qt.RichText)
            box.setWordWrap(True)
            box.setObjectName("GcalCurrent")
            self.list_layout.addWidget(box)
            self.list_layout.addStretch(1)
            self.ok_btn.setText("설정 열기")
            self.ok_btn.setEnabled(True)
            return

        self.target_label.setText(f"넣을 캘린더: <b>{svc.calendar_name() or svc.calendar_id()}</b>")
        sensitive = any(masking.is_sensitive(m["title"] or "", m["body"] or "") or
                        (("sensitivity" in m.keys()) and m["sensitivity"] == "SENSITIVE")
                        for m in self._messages)
        if sensitive and QMessageBox.question(
            self, "민감 정보 확인",
            "상담·민감 정보가 있을 수 있는 메시지입니다.\n이름·전화번호 등은 가려서 보내지만, "
            "일정을 찾기 위해 내용이 AI(Gemini)로 보내집니다.\n계속할까요?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            self._show_manual_only("AI로 보내지 않았어요. [직접 만들기]로 일정을 넣을 수 있어요.")
            return

        self._mode = "loading"
        self.ok_btn.setEnabled(False)
        self.ok_btn.setText("넣기")
        self._set_status("✨ AI가 메시지에서 일정을 찾는 중이에요…")
        messages, task, cal_id = self._messages, self._task, svc.calendar_id()
        key = svc.msg_key_for(messages)

        def work():
            cands = svc.find_candidates(messages, task)
            existing = gcal_api.find_events_by_message(cal_id, key) if key else []
            return svc.mark_duplicates(cands, existing)

        run_in_background(work, self._show_candidates, self._on_error)

    def _show_manual_only(self, text):
        self._mode = "manual"
        self._clear()
        self.list_layout.addStretch(1)
        self.ok_btn.setText("직접 만들기")
        self.ok_btn.setEnabled(True)
        self._set_status(text)

    def _on_error(self, msg):
        self._busy = False
        self._set_status(f"⚠ {msg}", warn=True)
        if self._mode == "loading":
            self._show_manual_only(f"⚠ {msg}")
            self._set_status(f"⚠ 일정을 찾지 못했어요: {msg}  [직접 만들기]로 넣을 수 있어요.", warn=True)
        else:
            self.ok_btn.setEnabled(True)

    def _show_candidates(self, cands):
        self._mode = "form"
        self._clear()
        if not cands:
            self._show_manual_only("이 메시지에서는 날짜가 있는 일정을 찾지 못했어요. [직접 만들기]로 넣을 수 있어요.")
            return
        if len(cands) > 1:
            hint = QLabel(f"이 메시지에서 일정 {len(cands)}개를 찾았어요. 넣을 것만 체크하세요.")
            hint.setObjectName("Muted")
            self.list_layout.addWidget(hint)
        for i, c in enumerate(cands, 1):
            row = _CandidateRow(i, c)
            row.changed.connect(self._update_ok)
            self.list_layout.addWidget(row)
            self._rows.append(row)
        self.list_layout.addStretch(1)
        self._set_status("")
        self._update_ok()

    def _chosen(self):
        return [r.value() for r in self._rows if r.include.isChecked()]

    def _update_ok(self):
        chosen = self._chosen()
        n = len(chosen)
        dup = sum(1 for c in chosen if c.get("dup_event_id"))
        if n == 0:
            text = "넣기"
        elif dup == n:
            text = f"{n}개 일정 고치기"
        elif dup:
            text = f"{n}개 넣기·고치기"
        else:
            text = f"{n}개 일정 넣기"
        self.ok_btn.setText(text)
        self.ok_btn.setEnabled(n > 0 and not self._busy)

    # ---------- 버튼 ----------

    def _on_ok(self):
        if self._mode == "setup":
            from .gcal_settings_dialog import GCalSettingsDialog
            dlg = GCalSettingsDialog(self)
            dlg.exec()
            self._start()
            return
        if self._mode == "manual":
            title = ""
            if self._task is not None:
                title = self._task["title"] or ""
            elif self._messages:
                title = self._messages[0]["title"] or ""
            day = (self._task["deadline"] if self._task is not None and self._task["deadline"] else date.today().isoformat())
            try:
                date.fromisoformat(day)
            except ValueError:
                day = date.today().isoformat()
            self._show_candidates([{"title": masking.mask_text(title)[:60], "date": day, "time": "",
                                    "task_id": self._task["task_id"] if self._task is not None else None,
                                    "dup_event_id": None}])
            return
        chosen = self._chosen()
        if not chosen:
            return
        self._busy = True
        self.ok_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self._set_status("📅 구글 캘린더에 넣는 중…")
        messages = self._messages

        def done(result):
            self._busy = False
            self.saved.emit(result)
            self.accept()

        def failed(msg):
            self._busy = False
            self.cancel_btn.setEnabled(True)
            self._on_error(msg)
            self._update_ok()

        run_in_background(lambda: svc.save_events(chosen, messages), done, failed)
