# -*- coding: utf-8 -*-
"""'메신저 설정' 모달 다이얼로그 — 설계 문서(쿨메신저_연동_설계.md) 6~7, 16, 17장 기준.

흐름: 자동 탐색(설치 확인 → 데이터 폴더 확인 → .udb 탐색+검증) → 결과 표시.
자동 탐색이 실패했을 때만 수동 설정(데이터 폴더 선택 → DB 파일 직접 선택)을
노출한다. 일반 사용자에게는 설치/DB 경로를 기본적으로 보여주지 않고,
'메신저 상세 설정 보기'를 눌러야만 드러나게 한다."""

from datetime import datetime
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QFileDialog, QCheckBox, QApplication, QRadioButton, QButtonGroup,
    QWidget
)

from .. import db
from ..adapters.coolmessenger_adapter import (
    CoolMessengerAdapter, UdbCandidate, ValidationResult, describe_error,
)


def _fmt_dt(dt: Optional[datetime]) -> str:
    return dt.strftime("%Y.%m.%d %H:%M") if dt else "알 수 없음"


class MessengerSetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("메신저 설정")
        self.setMinimumWidth(500)
        self.adapter = CoolMessengerAdapter()
        self.candidates: List[UdbCandidate] = []
        self.selected_path: Optional[str] = None
        self.selected_validation: Optional[ValidationResult] = None
        self._advanced_visible = False
        self._build_ui()
        self._run_auto_detect()

    # ---------- 뼈대 ----------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)

        title = QLabel("쿨메신저 연결")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        service_row = QHBoxLayout()
        service_label = QLabel("사용 중인 메신저")
        service_label.setObjectName("FormLabel")
        service_row.addWidget(service_label)
        service_value = QLabel("CoolMessenger Gentoo")
        service_row.addWidget(service_value)
        service_row.addStretch(1)
        root.addLayout(service_row)

        # 자동 탐색 결과가 들어갈 영역 (상태에 따라 내용을 다시 그린다)
        self.result_container = QWidget()
        self.result_layout = QVBoxLayout(self.result_container)
        self.result_layout.setContentsMargins(0, 0, 0, 0)
        self.result_layout.setSpacing(10)
        root.addWidget(self.result_container)

        # 상세 설정 (설치/데이터 경로) — 기본적으로 숨김
        self.advanced_toggle_btn = QPushButton("메신저 상세 설정 보기")
        self.advanced_toggle_btn.setObjectName("GhostButton")
        self.advanced_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.advanced_toggle_btn.clicked.connect(self.on_toggle_advanced)
        root.addWidget(self.advanced_toggle_btn)

        self.advanced_panel = self._build_advanced_panel()
        self.advanced_panel.setVisible(False)
        root.addWidget(self.advanced_panel)

        self.demo_checkbox = QCheckBox("데모 데이터 사용 (실제 쿨메신저 대신 예시 메시지로 동작)")
        self.demo_checkbox.setChecked(db.get_setting("demo_mode", "1") == "1")
        root.addWidget(self.demo_checkbox)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryButton")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self.start_btn = QPushButton("이대로 시작")
        self.start_btn.setObjectName("PrimaryButton")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self.on_start)
        btn_row.addWidget(self.start_btn)
        root.addLayout(btn_row)

    def _build_advanced_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        layout.addWidget(self._advanced_row_label("프로그램 위치"))
        row1 = QHBoxLayout()
        self.install_path_input = QLineEdit()
        self.install_path_input.setReadOnly(True)
        row1.addWidget(self.install_path_input, 1)
        browse_install_btn = QPushButton("변경")
        browse_install_btn.setObjectName("SecondaryButton")
        browse_install_btn.setCursor(Qt.PointingHandCursor)
        browse_install_btn.clicked.connect(self.on_browse_install_path)
        row1.addWidget(browse_install_btn)
        layout.addLayout(row1)

        layout.addWidget(self._advanced_row_label("메시지 데이터 위치"))
        row2 = QHBoxLayout()
        self.data_dir_input = QLineEdit()
        self.data_dir_input.setReadOnly(True)
        row2.addWidget(self.data_dir_input, 1)
        browse_data_btn = QPushButton("변경")
        browse_data_btn.setObjectName("SecondaryButton")
        browse_data_btn.setCursor(Qt.PointingHandCursor)
        browse_data_btn.clicked.connect(self.on_browse_data_dir)
        row2.addWidget(browse_data_btn)
        layout.addLayout(row2)

        layout.addWidget(self._advanced_row_label("사용 중인 DB 파일"))
        row3 = QHBoxLayout()
        self.db_path_input = QLineEdit()
        self.db_path_input.setReadOnly(True)
        row3.addWidget(self.db_path_input, 1)
        browse_db_btn = QPushButton("직접 선택")
        browse_db_btn.setObjectName("SecondaryButton")
        browse_db_btn.setCursor(Qt.PointingHandCursor)
        browse_db_btn.clicked.connect(self.on_browse_db_file)
        row3.addWidget(browse_db_btn)
        layout.addLayout(row3)

        retry_btn = QPushButton("다시 검색")
        retry_btn.setObjectName("SecondaryButton")
        retry_btn.setCursor(Qt.PointingHandCursor)
        retry_btn.clicked.connect(self._run_auto_detect)
        layout.addWidget(retry_btn)

        return panel

    @staticmethod
    def _advanced_row_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("FormLabel")
        return lbl

    def on_toggle_advanced(self):
        self._advanced_visible = not self._advanced_visible
        self.advanced_panel.setVisible(self._advanced_visible)
        self.advanced_toggle_btn.setText(
            "메신저 상세 설정 숨기기" if self._advanced_visible else "메신저 상세 설정 보기"
        )

    def _clear_result(self):
        while self.result_layout.count():
            item = self.result_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    # ---------- 자동 탐색 (설계 문서 3, 15장) ----------

    def _run_auto_detect(self):
        self._show_scanning()
        QApplication.processEvents()

        install_path = self.adapter.detect_installation()
        data_dir = self.adapter.find_data_dir()
        self.install_path_input.setText(install_path or "(찾지 못함)")
        self.data_dir_input.setText(data_dir or "(찾지 못함)")

        self.candidates = self.adapter.find_databases(search_root=data_dir)
        valid = [c for c in self.candidates if c.is_candidate]

        if not valid:
            self._show_failed()
        elif len(valid) == 1:
            self._select_candidate(valid[0])
        else:
            self._show_multi(valid)

        if install_path:
            db.set_setting("install_path", install_path)
        if data_dir:
            db.set_setting("data_dir", data_dir)

    def _select_candidate(self, candidate: UdbCandidate):
        self.selected_path = candidate.path
        self.selected_validation = candidate.validation
        self.db_path_input.setText(candidate.path)
        self._show_success(candidate.validation)

    # ---------- 상태별 화면 ----------

    def _show_scanning(self):
        self._clear_result()
        lbl = QLabel("🔍 쿨메신저를 자동으로 찾는 중...")
        lbl.setObjectName("Muted")
        self.result_layout.addWidget(lbl)

    def _show_success(self, validation: ValidationResult):
        self._clear_result()

        status = QLabel("✅ CoolMessenger를 찾았습니다.")
        status.setObjectName("StatusOk")
        self.result_layout.addWidget(status)

        info = QLabel(
            f"최근 메시지: {_fmt_dt(validation.last_message_at)}\n"
            f"메시지 {validation.message_count or 0}건 · 메시지 데이터 정상 확인"
        )
        info.setObjectName("Muted")
        self.result_layout.addWidget(info)

        if not validation.is_candidate:
            # 관대한 판정: 완벽히 일치하진 않지만 후보로 보임 -> 미리보기로 확인시킨다
            self.result_layout.addWidget(self._build_needs_confirmation_panel(validation))

    def _show_multi(self, valid_candidates: List[UdbCandidate]):
        self._clear_result()
        self.candidates = valid_candidates

        heading = QLabel("메시지 계정을 선택하세요.")
        heading.setObjectName("SectionTitle")
        self.result_layout.addWidget(heading)

        self._radio_group = QButtonGroup(self)
        for idx, c in enumerate(valid_candidates):
            radio = QRadioButton(
                f"{c.account_name_guess}\n"
                f"    최근 메시지: {_fmt_dt(c.last_message_at)} · 메시지 {c.message_count or 0}건"
            )
            radio.setChecked(idx == 0)
            radio.toggled.connect(
                lambda checked, cand=c: self._select_candidate(cand) if checked else None
            )
            self._radio_group.addButton(radio, idx)
            self.result_layout.addWidget(radio)

        # 기본으로 최우선 후보를 선택 상태로 반영
        self._select_candidate_silent(valid_candidates[0])

    def _select_candidate_silent(self, candidate: UdbCandidate):
        self.selected_path = candidate.path
        self.selected_validation = candidate.validation
        self.db_path_input.setText(candidate.path)

    def _show_failed(self):
        self._clear_result()
        info = describe_error("no_database")

        status = QLabel("✗ " + info["title"])
        status.setObjectName("StatusError")
        self.result_layout.addWidget(status)

        if info["causes"]:
            causes_lbl = QLabel("가능한 원인:\n" + "\n".join(f"- {c}" for c in info["causes"]))
            causes_lbl.setObjectName("Muted")
            causes_lbl.setWordWrap(True)
            self.result_layout.addWidget(causes_lbl)

        btn_row = QHBoxLayout()
        retry_btn = QPushButton("다시 검색")
        retry_btn.setObjectName("SecondaryButton")
        retry_btn.setCursor(Qt.PointingHandCursor)
        retry_btn.clicked.connect(self._run_auto_detect)
        btn_row.addWidget(retry_btn)

        folder_btn = QPushButton("데이터 폴더 선택")
        folder_btn.setObjectName("SecondaryButton")
        folder_btn.setCursor(Qt.PointingHandCursor)
        folder_btn.clicked.connect(self.on_browse_data_dir)
        btn_row.addWidget(folder_btn)

        file_btn = QPushButton("DB 파일 직접 선택")
        file_btn.setObjectName("SecondaryButton")
        file_btn.setCursor(Qt.PointingHandCursor)
        file_btn.clicked.connect(self.on_browse_db_file)
        btn_row.addWidget(file_btn)
        btn_row.addStretch(1)
        self.result_layout.addLayout(btn_row)

    def _build_needs_confirmation_panel(self, validation: ValidationResult) -> QFrame:
        """관대한 판정: 완전히 일치하진 않지만 후보로 보이는 경우, 최근 메시지
        제목(마스킹됨) 미리보기를 보여주고 사용자가 직접 확인해서 확정하게 한다."""
        box = QFrame()
        box.setObjectName("InfoBox")
        v = QVBoxLayout(box)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(6)

        warn = QLabel(f"⚠ {validation.reason}")
        warn.setObjectName("InfoBoxWarning")
        warn.setWordWrap(True)
        v.addWidget(warn)

        if validation.preview_titles_masked:
            preview_heading = QLabel("최근 메시지 제목 미리보기 (개인정보는 마스킹됨):")
            preview_heading.setObjectName("InfoBoxStep")
            v.addWidget(preview_heading)
            for t in validation.preview_titles_masked:
                lbl = QLabel(f"· {t}")
                lbl.setObjectName("InfoBoxStep")
                lbl.setWordWrap(True)
                v.addWidget(lbl)

        confirm_btn = QPushButton("이 데이터가 맞습니다")
        confirm_btn.setObjectName("SecondaryButton")
        confirm_btn.setCursor(Qt.PointingHandCursor)
        confirm_btn.clicked.connect(self._force_accept_current)
        v.addWidget(confirm_btn)

        return box

    def _force_accept_current(self):
        if self.selected_validation:
            self.selected_validation.is_candidate = True
        status_widgets = self.result_container.findChildren(QLabel, "InfoBoxWarning")
        for w in status_widgets:
            w.setText("✓ 사용자가 직접 확인했습니다.")
            w.setObjectName("StatusOk")
            w.style().unpolish(w)
            w.style().polish(w)

    # ---------- 수동 설정 (설계 문서 4, 7장 — 자동 탐색 실패 시에만) ----------

    def on_browse_install_path(self):
        folder = QFileDialog.getExistingDirectory(self, "쿨메신저 설치 폴더 선택")
        if folder:
            self.install_path_input.setText(folder)
            db.set_setting("install_path", folder)

    def on_browse_data_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "메시지 데이터 폴더 선택")
        if not folder:
            return
        self.data_dir_input.setText(folder)
        db.set_setting("data_dir", folder)

        self.candidates = self.adapter.find_databases(search_root=folder)
        valid = [c for c in self.candidates if c.is_candidate]
        if not valid:
            # 완전 일치는 없어도, 찾은 파일이 있으면 첫 파일을 '확인 필요' 상태로 보여준다
            if self.candidates:
                self._select_candidate(self.candidates[0])
            else:
                self._show_failed()
        elif len(valid) == 1:
            self._select_candidate(valid[0])
        else:
            self._show_multi(valid)

    def on_browse_db_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "쿨메신저 DB 파일 선택", "", "쿨메신저 DB (*.udb);;모든 파일 (*)"
        )
        if not file_path:
            return
        self.db_path_input.setText(file_path)
        validation = self.adapter.validate_database(file_path)
        self.selected_path = file_path
        self.selected_validation = validation
        if not validation.is_sqlite:
            self._clear_result()
            info = describe_error("not_sqlite")
            status = QLabel("✗ " + info["title"])
            status.setObjectName("StatusError")
            self.result_layout.addWidget(status)
            return
        self._show_success(validation)

    # ---------- 저장/시작 ----------

    def _save(self):
        if self.selected_path:
            db.set_setting("db_path", self.selected_path)
        db.set_setting("messenger_id", "coolmessenger")
        db.set_setting("messenger_label", "CoolMessenger Gentoo")
        db.set_setting("demo_mode", "1" if self.demo_checkbox.isChecked() else "0")
        db.set_setting("setup_done", "1")
        db.set_setting("auto_refresh", db.get_setting("auto_refresh", "false"))

    def on_start(self):
        self._save()
        self.accept()
