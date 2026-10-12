# -*- coding: utf-8 -*-
"""새 버전이 나오면 모니터 한가운데에 띄우는 업데이트 안내 카드.

앱 창 안의 UpdateModal(우측 상단 오버레이)은 앱 창을 열어야만 보여서,
Windows 시작 시 트레이로 숨어 있는 대부분의 선생님은 새 버전이 나온
줄도 몰랐다. 이 카드는 앱 창과 상관없이 화면 가운데에 따로 뜬다.

- [지금 업데이트]를 누르면 MainWindow가 미리 받아 검증해 둔 설치 파일로
  조용히 설치하고 앱을 다시 켠다(기존 _on_install_requested 흐름 그대로).
- [나중에](또는 ✕)를 누르면 오늘은 다시 안 띄운다. 내일 앱이 확인하면
  다시 뜬다 — 버그 수정이 담긴 업데이트를 영영 놓치지 않게, 이 카드에는
  '다시 안 보기'를 두지 않는다(앱 창 안의 카드에는 그대로 있다).
- 다른 창의 포커스를 뺏지 않는다(WA_ShowWithoutActivating) — 한글
  문서에 타이핑 중이어도 입력이 끊기지 않는다. 버튼은 그대로 누를 수 있다.
- 발표·전체화면·화면 잠금 중에는 MainWindow가 아예 띄우지 않고 기다렸다가
  돌아오면 띄운다(마스코트와 같은 판정 사용)."""

import webbrowser

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
)

from .. import config
from .common_widgets import apply_card_shadow
from .update_modal import _format_release_date

_SHADOW_MARGIN = 28  # 카드 그림자가 잘리지 않도록 바깥에 두는 투명 여백
_NOTES_MAX_CHARS = 140


class UpdatePopup(QWidget):
    install_requested = Signal()
    later_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._build_ui()
        self.hide()

    # ---------- 화면 구성 ----------

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(_SHADOW_MARGIN, _SHADOW_MARGIN, _SHADOW_MARGIN, _SHADOW_MARGIN)

        card = QFrame()
        card.setObjectName("UpdatePopupCard")
        card.setFixedWidth(460)
        outer.addWidget(card)
        apply_card_shadow(card, blur=40, y_offset=12, alpha=60)

        root = QVBoxLayout(card)
        root.setContentsMargins(26, 18, 18, 22)
        root.setSpacing(0)

        # 닫기(✕) — [나중에]와 같다
        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_btn = QPushButton("✕")
        close_btn.setObjectName("ToggleButton")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedWidth(28)
        close_btn.setToolTip("나중에 (오늘은 다시 안 보입니다)")
        close_btn.clicked.connect(self.later_requested.emit)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

        body = QHBoxLayout()
        body.setSpacing(18)

        mascot = QLabel()
        pm = QPixmap(str(config.mascot_dir() / "mascot_idle.png"))
        if not pm.isNull():
            # 원본은 @2x(311x312) — 실제 픽셀 240으로 줄인 뒤 배율 2로
            # 표시하면 화면에서는 120px 크기로 선명하게 보인다.
            small = pm.scaledToHeight(240, Qt.SmoothTransformation)
            small.setDevicePixelRatio(2.0)
            mascot.setPixmap(small)
        body.addWidget(mascot, 0, Qt.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(6)

        title = QLabel("새 버전이 나왔어요!")
        title.setObjectName("UpdatePopupTitle")
        text_col.addWidget(title)

        self.version_label = QLabel("")
        self.version_label.setObjectName("UpdatePopupVersion")
        text_col.addWidget(self.version_label)

        self.notes_label = QLabel("")
        self.notes_label.setObjectName("UpdatePopupNotes")
        self.notes_label.setWordWrap(True)
        text_col.addWidget(self.notes_label)

        hint = QLabel("버튼을 누르면 잠깐 꺼졌다가 새 버전으로 다시 켜집니다.\n"
                      "설정과 기록은 그대로 남아요.")
        hint.setObjectName("UpdatePopupHint")
        hint.setWordWrap(True)
        text_col.addWidget(hint)
        text_col.addStretch(1)

        body.addLayout(text_col, 1)
        root.addLayout(body)

        root.addSpacing(16)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        manual = QLabel('<a href="#">문제가 있으면 직접 받기</a>')
        manual.setObjectName("UpdatePopupManualLink")
        manual.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        manual.linkActivated.connect(lambda _=None: webbrowser.open(config.DOWNLOAD_PAGE_URL))
        btn_row.addWidget(manual, 0, Qt.AlignVCenter)
        btn_row.addStretch(1)

        later_btn = QPushButton("나중에")
        later_btn.setObjectName("SecondaryButton")
        later_btn.setCursor(Qt.PointingHandCursor)
        later_btn.clicked.connect(self.later_requested.emit)
        btn_row.addWidget(later_btn)

        self.install_btn = QPushButton("지금 업데이트")
        self.install_btn.setObjectName("PrimaryButton")
        self.install_btn.setCursor(Qt.PointingHandCursor)
        self.install_btn.clicked.connect(self.install_requested.emit)
        btn_row.addWidget(self.install_btn)

        root.addLayout(btn_row)

    # ---------- 표시 ----------

    def show_update(self, info: dict):
        version = info.get("version", "")
        date_text = _format_release_date(info.get("release_date", ""))
        self.version_label.setText(f"v{version}" + (f"  ·  {date_text}" if date_text else ""))

        notes = (info.get("notes") or "").strip()
        if len(notes) > _NOTES_MAX_CHARS:
            notes = notes[:_NOTES_MAX_CHARS].rstrip() + "…"
        self.notes_label.setText(notes)
        self.notes_label.setVisible(bool(notes))

        self.set_waiting(False)
        self.adjustSize()
        self._center_on_screen()
        self.show()  # WA_ShowWithoutActivating — 포커스를 가져가지 않는다
        self.raise_()

    def _center_on_screen(self):
        area = QGuiApplication.primaryScreen().availableGeometry()
        self.move(
            area.center().x() - self.width() // 2,
            area.center().y() - self.height() // 2,
        )

    def set_waiting(self, waiting: bool):
        """설치 파일을 아직 받는 중일 때 [지금 업데이트]를 누른 경우.
        받기가 끝나면 MainWindow가 자동으로 이어서 설치한다."""
        if waiting:
            self.install_btn.setEnabled(False)
            self.install_btn.setText("받는 중…")
        else:
            self.install_btn.setEnabled(True)
            self.install_btn.setText("지금 업데이트")
