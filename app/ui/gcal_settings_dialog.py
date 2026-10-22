# -*- coding: utf-8 -*-
"""설정 → [📅 구글 캘린더] 창.

1) [구글 계정 연결] — 브라우저에서 학교 계정으로 로그인
2) 일정을 넣을 캘린더
   ① 쿨브리핑 전용 캘린더 만들기(추천, 좁은 권한)
   ② 내 캘린더에서 고르기 ③ 캘린더 ID 직접 입력 — 기존 캘린더라 추가 허용이 필요
3) 선택 사항: 다른 일정도 보기 · 마감일 따라 바꾸기 · 완료하면 ✓
4) [연결 해제]
네트워크 일은 모두 백그라운드(bg_task)에서 한다."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QRadioButton, QVBoxLayout, QWidget
)

from ..core import gcal_api, gcal_service as svc, google_auth
from .bg_task import run_in_background


class GCalSettingsDialog(QDialog):
    calendarChanged = Signal()   # 연결·캘린더가 바뀌면 — 메인 창이 바로 맞추기를 돌린다

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("구글 캘린더")
        self.setMinimumWidth(600)
        self._busy = False
        self._calendars = []
        # 어디서 열었든(설정 화면·일정 넣기 창·일정 화면) 바뀌면 메인 창이 맞추기를 돌린다
        from .app_events import hub
        self.calendarChanged.connect(hub.calendarChanged.emit)
        self._build_ui()
        self._refresh()

    # ---------- 화면 ----------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 20)
        root.setSpacing(10)

        title = QLabel("📅 구글 캘린더")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        desc = QLabel("학교 구글 계정으로 연결해요. 일정은 이 PC와 선생님 구글 계정 사이에서만 오가요.")
        desc.setObjectName("Muted")
        desc.setWordWrap(True)
        root.addWidget(desc)

        # 계정
        acct = QFrame()
        acct.setObjectName("GcalAccount")
        ah = QHBoxLayout(acct)
        ah.setContentsMargins(14, 10, 14, 10)
        self.acct_label = QLabel("")
        self.acct_label.setWordWrap(True)
        self.acct_label.setTextFormat(Qt.RichText)
        ah.addWidget(self.acct_label, 1)
        self.connect_btn = QPushButton("구글 계정 연결")
        self.connect_btn.setObjectName("PrimaryButton")
        self.connect_btn.setCursor(Qt.PointingHandCursor)
        self.connect_btn.setAutoDefault(False)
        self.connect_btn.clicked.connect(self._on_connect)
        ah.addWidget(self.connect_btn)
        self.disconnect_btn = QPushButton("연결 해제")
        self.disconnect_btn.setObjectName("SecondaryButton")
        self.disconnect_btn.setCursor(Qt.PointingHandCursor)
        self.disconnect_btn.setAutoDefault(False)
        self.disconnect_btn.clicked.connect(self._on_disconnect)
        ah.addWidget(self.disconnect_btn)
        root.addWidget(acct)

        # 캘린더 고르기
        self.cal_box = QWidget()
        cv = QVBoxLayout(self.cal_box)
        cv.setContentsMargins(0, 6, 0, 0)
        cv.setSpacing(8)
        head = QLabel("일정을 넣을 캘린더")
        head.setObjectName("BulkFieldLabel")
        cv.addWidget(head)
        self.current_label = QLabel("")
        self.current_label.setObjectName("GcalCurrent")
        self.current_label.setWordWrap(True)
        cv.addWidget(self.current_label)

        self.mode_group = QButtonGroup(self)
        self.radio_app = QRadioButton("쿨브리핑 전용 캘린더 만들기 (추천)")
        self.radio_list = QRadioButton("내 캘린더에서 고르기")
        self.radio_id = QRadioButton("캘린더 ID 직접 입력")
        for i, r in enumerate((self.radio_app, self.radio_list, self.radio_id)):
            self.mode_group.addButton(r, i)
        self.mode_group.idClicked.connect(lambda _id: self._on_mode_changed())

        cv.addWidget(self.radio_app)
        self.app_hint = self._hint("내 계정에 '쿨브리핑' 캘린더를 새로 만들어요. 휴대폰에서 이 캘린더만 켜고 끌 수 있고, 쿨브리핑은 다른 캘린더를 볼 수 없어요.")
        cv.addWidget(self.app_hint)
        self.make_btn = QPushButton("쿨브리핑 캘린더 만들기")
        self.make_btn.setObjectName("PrimaryButton")
        self.make_btn.setAutoDefault(False)
        self.make_btn.setCursor(Qt.PointingHandCursor)
        self.make_btn.clicked.connect(self._on_make_calendar)
        cv.addWidget(self._indent(self.make_btn))

        cv.addWidget(self.radio_list)
        cv.addWidget(self._hint("이미 쓰는 캘린더 목록에서 골라요. ID를 몰라도 돼요."))
        list_row = QHBoxLayout()
        self.cal_combo = QComboBox()
        self.cal_combo.setMinimumWidth(320)
        list_row.addWidget(self.cal_combo, 1)
        self.list_btn = QPushButton("목록 불러오기")
        self.list_btn.setObjectName("SecondaryButton")
        self.list_btn.setAutoDefault(False)
        self.list_btn.clicked.connect(self._on_load_list)
        list_row.addWidget(self.list_btn)
        self.use_list_btn = QPushButton("이 캘린더 쓰기")
        self.use_list_btn.setObjectName("PrimaryButton")
        self.use_list_btn.setAutoDefault(False)
        self.use_list_btn.clicked.connect(self._on_use_list)
        list_row.addWidget(self.use_list_btn)
        self.list_row = self._indent_layout(list_row)
        cv.addWidget(self.list_row)

        cv.addWidget(self.radio_id)
        cv.addWidget(self._hint("구글 캘린더 → 설정 → 캘린더 통합의 '캘린더 ID'를 붙여 넣으세요."))
        id_row = QHBoxLayout()
        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("예) abc123@group.calendar.google.com")
        id_row.addWidget(self.id_input, 1)
        self.use_id_btn = QPushButton("확인")
        self.use_id_btn.setObjectName("PrimaryButton")
        self.use_id_btn.setAutoDefault(False)
        self.use_id_btn.clicked.connect(self._on_use_id)
        id_row.addWidget(self.use_id_btn)
        self.id_row = self._indent_layout(id_row)
        cv.addWidget(self.id_row)

        self.perm_note = QLabel("🔐 기존 캘린더에 일정을 쓰려면 구글 허용 창이 한 번 더 떠요(\"캘린더 일정 보기·편집\"). "
                                "학교 내부 앱이라 심사는 필요 없어요. 공유 캘린더를 고르면 함께 보는 선생님들께도 일정이 보여요.")
        self.perm_note.setObjectName("BulkWarn")
        self.perm_note.setWordWrap(True)
        cv.addWidget(self.perm_note)

        opts = QLabel("연동")
        opts.setObjectName("BulkFieldLabel")
        cv.addSpacing(4)
        cv.addWidget(opts)
        self.mask_check = QCheckBox("일정 제목에 학생 이름 가리기 (항상)")
        self.mask_check.setChecked(True)
        self.mask_check.setEnabled(False)
        cv.addWidget(self.mask_check)
        self.follow_check = QCheckBox("휴대폰에서 날짜를 옮기면 업무 마감일도 따라 바꾸기")
        self.done_check = QCheckBox("업무를 완료하면 일정 제목 앞에 ✓ 붙이기")
        self.other_check = QCheckBox("'일정' 화면에 그 캘린더의 다른 일정도 보기")
        for chk, key in ((self.follow_check, svc.K_FOLLOW), (self.done_check, svc.K_MARK_DONE),
                         (self.other_check, svc.K_SHOW_OTHER)):
            chk.setChecked(svc.option(key))
            chk.toggled.connect(lambda on, k=key: (svc.set_option(k, on), self.calendarChanged.emit()))
            cv.addWidget(chk)
        root.addWidget(self.cal_box)

        self.status_label = QLabel("")
        self.status_label.setObjectName("Muted")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        foot = QHBoxLayout()
        foot.addStretch(1)
        close_btn = QPushButton("닫기")
        close_btn.setObjectName("SecondaryButton")
        close_btn.setAutoDefault(False)
        close_btn.clicked.connect(self.accept)
        foot.addWidget(close_btn)
        root.addLayout(foot)

    def _hint(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("Muted")
        lbl.setWordWrap(True)
        lbl.setContentsMargins(26, 0, 0, 0)
        return lbl

    def _indent(self, widget):
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(26, 0, 0, 0)
        h.addWidget(widget)
        h.addStretch(1)
        return box

    def _indent_layout(self, layout):
        box = QWidget()
        layout.setContentsMargins(26, 0, 0, 0)
        box.setLayout(layout)
        return box

    # ---------- 상태 ----------

    def _set_status(self, text, warn=False):
        self.status_label.setText(text)
        self.status_label.setObjectName("BulkWarn" if warn else "Muted")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _selected_mode(self):
        return {0: "app", 1: "list", 2: "id"}.get(self.mode_group.checkedId(), svc.mode())

    def _refresh(self):
        available = google_auth.is_available()
        connected = google_auth.is_connected()
        if not available:
            self.acct_label.setText("<b>준비 중</b><br><span style='color:#6D7890'>이 버전에는 구글 연결 정보가 아직 들어 있지 않아요.</span>")
        elif connected:
            self.acct_label.setText(f"<b>{google_auth.connected_email()}</b><br>"
                                    "<span style='color:#3D986B'>● 연결됨 — 로그인 정보는 이 PC의 Windows 자격 증명에만 저장돼요</span>")
        else:
            domain = google_auth.config.GOOGLE_WORKSPACE_DOMAIN
            self.acct_label.setText(f"<b>연결 안 됨</b><br><span style='color:#6D7890'>@{domain} 학교 계정만 연결할 수 있어요.</span>")
        self.connect_btn.setVisible(available and not connected)
        self.disconnect_btn.setVisible(connected)
        self.cal_box.setVisible(connected)
        for w in (self.connect_btn, self.disconnect_btn, self.cal_box):
            w.setEnabled(not self._busy)
        if not connected:
            return

        cal_id, name = svc.calendar_id(), svc.calendar_name()
        self.current_label.setText(f"✓ 지금 넣는 캘린더: <b>{name or cal_id}</b>" if cal_id else
                                   "아직 정하지 않았어요 — 아래에서 하나를 골라 주세요.")
        self.current_label.setTextFormat(Qt.RichText)
        if self.mode_group.checkedId() < 0:
            {"app": self.radio_app, "list": self.radio_list, "id": self.radio_id}[svc.mode()].setChecked(True)
        mode = self._selected_mode()
        self.make_btn.setVisible(mode == "app")
        made_before = bool(svc.db.get_setting(svc.K_APP_CAL_ID, ""))
        self.make_btn.setText("쿨브리핑 캘린더를 쓰고 있어요 ✓" if (mode == "app" and svc.mode() == "app" and cal_id)
                              else ("쿨브리핑 캘린더 다시 쓰기" if made_before else "쿨브리핑 캘린더 만들기"))
        self.make_btn.setEnabled(not (svc.mode() == "app" and cal_id) and not self._busy)
        self.list_row.setVisible(mode == "list")
        self.id_row.setVisible(mode == "id")
        self.perm_note.setVisible(mode in ("list", "id"))
        if mode == "id" and svc.mode() == "id" and not self.id_input.text():
            self.id_input.setText(cal_id)

    def _on_mode_changed(self):
        self._refresh()

    # ---------- 일 ----------

    def _run(self, status, fn, on_done):
        self._busy = True
        self._set_status(status)
        self._refresh()

        def done(result):
            self._busy = False
            on_done(result)
            self._refresh()

        def failed(msg):
            self._busy = False
            self._set_status(f"⚠ {msg}", warn=True)
            self._refresh()

        run_in_background(fn, done, failed)

    def _on_connect(self):
        self._run("🌐 브라우저에서 학교 계정으로 로그인하고 [허용]을 눌러 주세요… (5분 안에)",
                  lambda: google_auth.connect(),
                  lambda creds: (self._set_status(f"✅ {creds.get('email', '')} 계정을 연결했어요. 일정을 넣을 캘린더를 골라 주세요."),
                                 self.calendarChanged.emit()))

    def _on_disconnect(self):
        if QMessageBox.question(
            self, "연결 해제",
            "구글 캘린더 연결을 해제할까요?\n이 PC에 저장된 로그인 정보를 지우고, 구글 쪽 허용도 취소해요.\n"
            "캘린더에 이미 넣은 일정은 그대로 남아요.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self._run("연결을 해제하는 중…", google_auth.disconnect,
                  lambda _r: (self._set_status("연결을 해제했어요."), self.calendarChanged.emit()))

    def _ask_move(self) -> bool:
        n = svc.existing_link_count()
        if n == 0 or not svc.calendar_id():
            return False
        return QMessageBox.question(
            self, "이미 넣은 일정",
            f"쿨브리핑으로 넣은 일정 {n}개가 지금 캘린더에 있어요.\n새 캘린더로 옮길까요?\n"
            "([아니요]를 누르면 지금 캘린더에 그대로 두고, 앞으로 넣는 일정만 새 캘린더에 들어가요.)",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) == QMessageBox.Yes

    def _apply(self, mode, cal_id, name):
        move = self._ask_move() if cal_id != svc.calendar_id() else False

        def work():
            return svc.change_calendar(mode, cal_id, name, move)

        def done(r):
            extra = f" 이미 넣은 일정 {r['moved']}개를 옮겼어요." if r["moved"] else ""
            if r["failed"]:
                extra += f" {r['failed']}개는 옮기지 못해 그대로 두었어요."
            self._set_status(f"✅ 이제 '{name}' 캘린더에 일정을 넣어요.{extra}")
            self.calendarChanged.emit()

        self._run("캘린더를 바꾸는 중…", work, done)

    def _ensure_extra_then(self, then):
        """기존 캘린더용 권한이 없으면 한 번 더 로그인해 받고 then()."""
        if not svc.needs_extra_scope("list"):
            then()
            return
        self._run("🔐 브라우저에서 \"캘린더 일정 보기·편집\"을 [허용]해 주세요…",
                  lambda: google_auth.connect(extra=True), lambda _c: then())

    def _on_make_calendar(self):
        self._run("'쿨브리핑' 캘린더를 준비하는 중…", svc.ensure_app_calendar,
                  lambda cal: self._apply("app", cal["id"], "쿨브리핑"))

    def _on_load_list(self):
        def load():
            self._run("내 캘린더 목록을 불러오는 중…", gcal_api.list_writable_calendars, self._fill_list)
        self._ensure_extra_then(load)

    def _fill_list(self, calendars):
        self._calendars = calendars
        self.cal_combo.clear()
        for c in calendars:
            self.cal_combo.addItem(("⭐ " if c["primary"] else "") + c["summary"], c["id"])
        idx = self.cal_combo.findData(svc.calendar_id())
        if idx >= 0:
            self.cal_combo.setCurrentIndex(idx)
        self._set_status(f"캘린더 {len(calendars)}개를 불러왔어요. 고른 뒤 [이 캘린더 쓰기]를 누르세요.")

    def _on_use_list(self):
        cal_id = self.cal_combo.currentData()
        if not cal_id:
            self._set_status("먼저 [목록 불러오기]를 누르고 캘린더를 골라 주세요.", warn=True)
            return
        name = self.cal_combo.currentText().replace("⭐ ", "")
        self._apply("list", cal_id, name)

    def _on_use_id(self):
        cal_id = self.id_input.text().strip()
        if not cal_id:
            self._set_status("캘린더 ID를 넣어 주세요.", warn=True)
            return

        def check():
            def work():
                gcal_api.check_calendar(cal_id)
                return cal_id
            self._run("캘린더를 확인하는 중…", work, lambda _r: self._apply("id", cal_id, cal_id))
        self._ensure_extra_then(check)
