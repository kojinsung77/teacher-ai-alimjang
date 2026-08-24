# -*- coding: utf-8 -*-
"""새 버전 안내를 화면 어디에 있든 보이는 모달형 카드로 띄운다. 예전엔
dashboard_view.py 안에 있는 인라인 배너였는데, "오늘" 탭에 있을 때만
보인다는 문제가 있어 MainWindow가 절대좌표로 띄우는 오버레이로 옮겼다.
레이아웃에 들어가지 않고 항상 스스로 보이기/숨기기와 위치만 관리하며,
실제 다운로드/설치/무시 처리는 시그널로 MainWindow에 위임한다(다운로드·
subprocess·앱 종료 같은 로직을 이 위젯이 몰라도 되게 분리)."""

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

from .common_widgets import apply_card_shadow


def _format_release_date(release_date: str) -> str:
    """"2026-08-24" -> "2026년 8월 24일". release_date가 비어 있거나
    형식이 예상과 다르면 빈 문자열을 돌려줘서, 호출부가 그 줄을 그냥
    생략하고 나머지는 정상 표시하게 한다(구버전 version.json에는 이
    필드 자체가 없을 수 있으므로 죽지 않아야 한다)."""
    if not release_date:
        return ""
    try:
        parsed = datetime.strptime(release_date, "%Y-%m-%d")
    except ValueError:
        return ""
    return f"{parsed.year}년 {parsed.month}월 {parsed.day}일"


class UpdateModal(QFrame):
    download_requested = Signal()
    dismiss_requested = Signal()
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("UpdateModal")
        self.setFixedWidth(380)
        self._build_ui()
        self.hide()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 16, 18)
        outer.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        icon = QLabel("⬇")
        icon.setObjectName("UpdateModalIcon")
        top_row.addWidget(icon)

        title = QLabel("새 버전이 출시되었습니다")
        title.setObjectName("UpdateModalTitle")
        title.setWordWrap(True)
        top_row.addWidget(title, 1)

        close_btn = QPushButton("✕")
        close_btn.setObjectName("ToggleButton")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedWidth(28)
        close_btn.clicked.connect(self.closed.emit)
        top_row.addWidget(close_btn, 0, Qt.AlignTop)

        outer.addLayout(top_row)

        self.version_label = QLabel("")
        self.version_label.setObjectName("UpdateModalVersion")
        outer.addWidget(self.version_label)

        self.date_label = QLabel("")
        self.date_label.setObjectName("UpdateModalDate")
        outer.addWidget(self.date_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.download_btn = QPushButton("⬇ 업데이트 다운로드")
        self.download_btn.setObjectName("PrimaryButton")
        self.download_btn.setCursor(Qt.PointingHandCursor)
        self.download_btn.clicked.connect(self.download_requested.emit)
        btn_row.addWidget(self.download_btn)

        dismiss_btn = QPushButton("다시 안보기")
        dismiss_btn.setObjectName("SecondaryButton")
        dismiss_btn.setCursor(Qt.PointingHandCursor)
        dismiss_btn.clicked.connect(self.dismiss_requested.emit)
        btn_row.addWidget(dismiss_btn)

        outer.addLayout(btn_row)

        apply_card_shadow(self, blur=28, y_offset=10, alpha=26)

    def show_update(self, info: dict):
        version = info.get("version", "")
        self.version_label.setText(f"v{version}")

        formatted_date = _format_release_date(info.get("release_date", ""))
        if formatted_date:
            self.date_label.setText(f"출시일: {formatted_date}")
            self.date_label.show()
        else:
            self.date_label.hide()

        self.set_waiting(False)
        self.adjustSize()
        self.show()
        self.raise_()

    def set_waiting(self, waiting: bool):
        """다운로드가 아직 안 끝난 상태에서 [업데이트 다운로드]를 눌렀을
        때(또는 눌러서 새로 다운로드를 시작했을 때) MainWindow가 호출한다.
        완료되면 자동으로 설치가 진행되므로, 여기서는 버튼 상태만
        보여준다."""
        if waiting:
            self.download_btn.setEnabled(False)
            self.download_btn.setText("받는 중...")
        else:
            self.download_btn.setEnabled(True)
            self.download_btn.setText("⬇ 업데이트 다운로드")
