# -*- coding: utf-8 -*-
"""여러 화면이 공유하는 작은 위젯. 화면마다 같은 걸 다시 만들지 않기 위함."""

from PySide6.QtCore import Qt, Signal, QPoint, QPropertyAnimation, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QVBoxLayout, QLabel
)


class ClickableCard(QFrame):
    """클릭 가능한 QFrame. 통계 타일/필터 탭처럼 카드·pill 전체가
    버튼처럼 동작해야 할 때 사용한다."""
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class HoverLiftCard(ClickableCard):
    """호버 시 그림자가 진해지고 살짝 위로 뜨는 클릭 가능 카드.

    history_view.py의 날짜 카드는 클릭할 때마다 dynamic property +
    unpolish/polish로 "선택됨" 상태를 다시 칠하는데, 그 restyle이
    QGraphicsEffect가 붙어 있는 상태에서 일어나면 자식 QLabel이 안
    그려지는 실측 확인된 렌더링 버그가 있어 그쪽은 순수 QSS로 hover를
    처리한다. 이 카드는 선택 상태 자체가 없어 unpolish/polish를 전혀
    쓰지 않으므로 그 버그 조건에 해당하지 않는다 — 그래서 여기서는
    QGraphicsDropShadowEffect를 hover 동안 계속 붙여둔 채 애니메이션한다."""

    _BASE_BLUR = 18
    _HOVER_BLUR = 34
    _BASE_Y_OFFSET = 6
    _HOVER_Y_OFFSET = 14
    _LIFT_PX = 4
    _DURATION_MS = 160

    def __init__(self, parent=None):
        super().__init__(parent)
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(self._BASE_BLUR)
        self._shadow.setOffset(0, self._BASE_Y_OFFSET)
        self._shadow.setColor(QColor(26, 44, 78, 30))
        self.setGraphicsEffect(self._shadow)
        self._base_pos = None
        self._anims = []

    def enterEvent(self, event):
        self._animate(hover=True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate(hover=False)
        super().leaveEvent(event)

    def _animate(self, hover: bool):
        if self._base_pos is None:
            self._base_pos = self.pos()

        blur_anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        blur_anim.setDuration(self._DURATION_MS)
        blur_anim.setStartValue(self._shadow.blurRadius())
        blur_anim.setEndValue(self._HOVER_BLUR if hover else self._BASE_BLUR)

        offset_anim = QPropertyAnimation(self._shadow, b"yOffset", self)
        offset_anim.setDuration(self._DURATION_MS)
        offset_anim.setStartValue(self._shadow.yOffset())
        offset_anim.setEndValue(self._HOVER_Y_OFFSET if hover else self._BASE_Y_OFFSET)

        pos_anim = QPropertyAnimation(self, b"pos", self)
        pos_anim.setDuration(self._DURATION_MS)
        pos_anim.setStartValue(self.pos())
        target_y = self._base_pos.y() - self._LIFT_PX if hover else self._base_pos.y()
        pos_anim.setEndValue(QPoint(self._base_pos.x(), target_y))

        self._anims = [blur_anim, offset_anim, pos_anim]
        for a in self._anims:
            a.start()


class Toast(QLabel):
    """화면 상단에 잠깐 떴다가 자동으로 사라지는 작은 알림 pill. 백그라운드
    자동 확인처럼 사용자가 직접 누른 동작이 아닌 결과를 팝업(모달) 없이
    조용히 알릴 때 쓴다.

    이 위젯은 unpolish/polish로 다시 그리는 "선택 상태"가 전혀 없으므로
    (history_view.py의 카드와 달리) QGraphicsOpacityEffect를 페이드인·
    페이드아웃 양쪽에 그대로 계속 붙여둬도 안전하다 — 그 문서화된 렌더링
    버그는 이펙트 자체가 아니라 이펙트가 붙은 채로 restyle이 일어날 때만
    발생했다."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAlignment(Qt.AlignCenter)
        # QGraphicsEffect가 붙은 위젯은 WA_StyledBackground가 없으면 QSS
        # background-color가 이펙트 합성 과정에서 빠지는 경우가 있다
        # (실측 확인: 이 속성 없이는 grab() 결과가 완전히 투명하게 나옴).
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self.hide()

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)

        self._anim_in = None
        self._anim_out = None

    def show_message(self, text: str, duration_ms: int = 3200):
        self.setText(text)
        self.adjustSize()
        self._reposition()

        self._effect.setOpacity(0.0)
        self.show()
        self.raise_()

        self._anim_in = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim_in.setDuration(200)
        self._anim_in.setStartValue(0.0)
        self._anim_in.setEndValue(1.0)
        self._anim_in.start()

        self._hide_timer.start(duration_ms)

    def _reposition(self):
        parent = self.parentWidget()
        if parent is None:
            return
        x = (parent.width() - self.width()) // 2
        self.move(max(x, 0), 18)

    def _fade_out(self):
        self._anim_out = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim_out.setDuration(300)
        self._anim_out.setStartValue(1.0)
        self._anim_out.setEndValue(0.0)
        self._anim_out.finished.connect(self.hide)
        self._anim_out.start()


def apply_card_shadow(widget, blur: int = 26, y_offset: int = 8, alpha: int = 22):
    """카드형 위젯에 아주 은은한 그림자를 준다 (QSS는 box-shadow를 지원하지
    않아 QGraphicsDropShadowEffect로 대신한다). 과하지 않게 alpha를 낮게 쓴다."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y_offset)
    effect.setColor(QColor(26, 44, 78, alpha))
    widget.setGraphicsEffect(effect)
    return effect


def build_empty_state(icon: str, title_text: str, desc_text: str, extra_widget=None) -> QFrame:
    """데이터가 없을 때 화면 전체가 비어 보이지 않도록 쓰는 공통 카드형
    Empty State (화면마다 텍스트 한 줄만 중앙에 띄우던 방식을 대체)."""
    box = QFrame()
    box.setObjectName("EmptyState")
    v = QVBoxLayout(box)
    v.setContentsMargins(24, 34, 24, 34)
    v.setSpacing(6)
    v.setAlignment(Qt.AlignCenter)

    icon_lbl = QLabel(icon)
    icon_lbl.setObjectName("EmptyStateIcon")
    icon_lbl.setAlignment(Qt.AlignCenter)
    v.addWidget(icon_lbl)

    title_lbl = QLabel(title_text)
    title_lbl.setObjectName("EmptyStateTitle")
    title_lbl.setAlignment(Qt.AlignCenter)
    v.addWidget(title_lbl)

    desc_lbl = QLabel(desc_text)
    desc_lbl.setObjectName("EmptyStateDesc")
    desc_lbl.setAlignment(Qt.AlignCenter)
    desc_lbl.setWordWrap(True)
    v.addWidget(desc_lbl)

    if extra_widget is not None:
        v.addSpacing(8)
        v.addWidget(extra_widget, 0, Qt.AlignHCenter)

    return box
