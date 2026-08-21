# -*- coding: utf-8 -*-
"""'개인정보 마스킹 명단 설정' 모달 다이얼로그.

roster.csv 상태 표시, 샘플 다운로드, 업로드(형식 검증 포함)를 다룬다.
실제 이름은 여기서도 화면에 표시하지 않는다 — 등록 인원 '수'만 보여준다."""

import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QMessageBox
)

from .. import config
from ..privacy import masking

_SAMPLE_PATH = Path(__file__).resolve().parent.parent / "privacy" / "roster_sample.csv"


class PrivacyMaskingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("개인정보 마스킹 명단 설정")
        self.setMinimumWidth(460)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)

        title = QLabel("개인정보 마스킹 명단 설정")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        desc = QLabel(
            "학생/교직원 이름을 AI 전송 전에 마스킹하려면 아래에서 명단 CSV 파일을\n"
            "등록해 주세요. (name 컬럼에 이름을 한 줄씩 입력)"
        )
        desc.setObjectName("Muted")
        desc.setWordWrap(True)
        root.addWidget(desc)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        self._refresh_status()

        btn_row = QHBoxLayout()
        download_btn = QPushButton("샘플 다운로드")
        download_btn.setObjectName("SecondaryButton")
        download_btn.setCursor(Qt.PointingHandCursor)
        download_btn.clicked.connect(self.on_download_sample)
        btn_row.addWidget(download_btn)

        upload_btn = QPushButton("업로드")
        upload_btn.setObjectName("PrimaryButton")
        upload_btn.setCursor(Qt.PointingHandCursor)
        upload_btn.clicked.connect(self.on_upload)
        btn_row.addWidget(upload_btn)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        root.addStretch(1)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_btn = QPushButton("닫기")
        close_btn.setObjectName("SecondaryButton")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

    def _refresh_status(self):
        roster_path = config.roster_csv_path()
        if roster_path.exists():
            count = masking.roster_entry_count()
            self.status_label.setObjectName("StatusOk")
            self.status_label.setText(f"✓ 파일 확인됨 — 현재 {count}명 등록")
        else:
            self.status_label.setObjectName("StatusError")
            self.status_label.setText("⚠ 아직 파일이 없습니다.")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def on_download_sample(self):
        save_path, _ = QFileDialog.getSaveFileName(
            self, "샘플 저장 위치 선택", "roster_sample.csv", "CSV 파일 (*.csv)"
        )
        if not save_path:
            return
        try:
            # BOM 없는 UTF-8로 저장되면 엑셀에서 한글이 깨져 보이므로,
            # 항상 utf-8-sig(BOM 포함)로 다시 인코딩해서 저장한다.
            text = _SAMPLE_PATH.read_text(encoding="utf-8")
            Path(save_path).write_text(text, encoding="utf-8-sig", newline="")
        except OSError as e:
            QMessageBox.critical(self, "저장 실패", f"샘플 파일을 저장하지 못했습니다.\n{e}")
            return
        QMessageBox.information(self, "저장 완료", "샘플 파일을 저장했습니다.")

    def on_upload(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "명단 CSV 파일 선택", "", "CSV 파일 (*.csv)"
        )
        if not file_path:
            return

        if not masking.validate_roster_header(file_path):
            QMessageBox.warning(
                self, "형식 오류",
                "형식이 맞지 않습니다. 샘플을 참고해 주세요.\n"
                "(CSV 파일에 'name' 또는 '이름' 컬럼이 있어야 합니다.)"
            )
            return

        try:
            shutil.copyfile(file_path, config.roster_csv_path())
        except OSError as e:
            QMessageBox.critical(self, "업로드 실패", f"파일을 복사하지 못했습니다.\n{e}")
            return

        self._refresh_status()
        QMessageBox.information(self, "업로드 완료", "명단이 등록되었습니다.")
