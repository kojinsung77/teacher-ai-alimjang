# -*- coding: utf-8 -*-
"""정기 알림(13:20/16:10) 때 화면 아래쪽을 걸어가는 마스코트(파랑새) 알림.

트레이 풍선은 화면 구석에 작게 떴다 사라져 놓치기 쉬워서, 작업표시줄
바로 위를 파랑새가 말풍선("쿨브리핑 / 오늘 할 일 n건!")을 들고 왼쪽
밖에서 오른쪽 밖까지 한 번 걸어가게 한다. 트레이 풍선은 그대로 함께
보내므로(main_window.py의 _show_reminder_notification), 마스코트를 못 보고
지나쳐도 Windows 알림 센터에는 남는다.

지켜야 할 것:
- 절대 포커스를 뺏지 않는다. 선생님이 한글/웹 문서를 작성하는 중에
  지나가도 타이핑이 끊기면 안 된다 — Tool + WindowDoesNotAcceptFocus
  (Windows에서는 WS_EX_NOACTIVATE) + WA_ShowWithoutActivating.
- 화면이 TV·프로젝터로 공유되고 있을 수 있으므로 말풍선에는 건수만
  쓰고 업무 제목 같은 구체 내용은 절대 쓰지 않는다.
- 투명한 부분은 클릭이 아래 창으로 그대로 통과된다. WA_TranslucentBackground
  창은 Windows에서 레이어드 창(per-pixel alpha)으로 그려지고, 알파가 0인
  픽셀은 OS가 히트 테스트에서 제외한다.

이미지 규격과 배치 좌표는 app/ui/assets/mascot/MASCOT_ASSETS.md와
layout.json에 있다. 모든 수치는 @2x 픽셀 기준이라 devicePixelRatio 2로
그려 화면에는 절반 크기(약 313x229)로 보인다.
"""

import json
import math
import sys

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QImage, QPainter
from PySide6.QtWidgets import QWidget

from .. import config

_FRAME_FILES = [f"mascot_walk_{i}.png" for i in range(4)]
_BUBBLE_FILE = "speech_bubble.png"
_LAYOUT_FILE = "layout.json"

_SCALE = 2  # 이미지·layout.json 좌표가 @2x 기준
_FRAME_INTERVAL_MS = 130  # 걷기 프레임 전환 간격 (MASCOT_ASSETS.md)
_WALK_SPEED_PX_PER_SEC = 80  # 화면(논리 픽셀) 기준 이동 속도
_MOVE_INTERVAL_MS = 16  # 위치 갱신 주기(약 60fps)

_FONT_FAMILY = "NanumGothic"  # 앱 공통 글꼴(main.py가 번들 폰트로 등록)
_TITLE_TEXT = "쿨브리핑"
_TITLE_COLOR = "#1656E8"
_TITLE_PT = 22
_COUNT_COLOR = "#191E2D"
_COUNT_PT = 15
# MASCOT_ASSETS.md의 "1줄/2줄 중심" y좌표(말풍선 기준, @2x)
_TITLE_CENTER_Y = 102
_COUNT_CENTER_Y = 154

# shellapi.h — SHQueryUserNotificationState 결과값
_QUNS_ACCEPTS_NOTIFICATIONS = 5


def desktop_accepts_notifications() -> bool:
    """Windows가 "지금 알림을 띄워도 되는 상태"라고 답하는지 확인한다.

    전체화면 앱, PPT 슬라이드쇼(프레젠테이션 모드), 전체화면 동영상·게임
    (D3D 전체화면), 화면 잠금/화면보호기, 집중 모드(조용한 시간) 등에서는
    QUNS_ACCEPTS_NOTIFICATIONS가 아닌 값이 돌아온다 — 그럴 때는 마스코트를
    띄우지 않는다(트레이 알림은 호출부가 그대로 보낸다).

    Windows가 아니거나 API 호출 자체가 실패하면 True를 돌려준다. 이 판단은
    "발표 중 화면 위로 지나가는 것"을 막기 위한 것이고, 마스코트에는
    건수만 표시되므로 판단 불가 시 띄우는 쪽을 택했다."""
    if not sys.platform.startswith("win"):
        return True
    try:
        import ctypes

        state = ctypes.c_int(0)
        hr = ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state))
        if hr != 0:
            return True
        return state.value == _QUNS_ACCEPTS_NOTIFICATIONS
    except Exception:
        return True


def _load_layout() -> dict | None:
    try:
        with open(config.mascot_asset_dir() / _LAYOUT_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _fit_font(text: str, point_size: float, max_width: float) -> QFont:
    """기본 크기로 그렸을 때 max_width를 넘으면(예: 업무 건수가 세 자리)
    넘지 않을 때까지 조금씩 줄인다. 크기는 @2x 캔버스 기준 픽셀로 잡는다
    (1x pt -> 96dpi 픽셀 -> x2)."""
    font = QFont(_FONT_FAMILY)
    font.setBold(True)
    px = point_size * 96 / 72 * _SCALE
    while True:
        font.setPixelSize(max(1, round(px)))
        if QFontMetricsF(font).horizontalAdvance(text) <= max_width or px <= 16:
            return font
        px -= 2


class MascotWalker(QWidget):
    """한 번 걸어가고 사라지는 마스코트 창. start()로 출발시킨다.

    clicked: 마스코트·말풍선(불투명 부분)을 클릭했을 때. 창은 그 즉시
             사라진다.
    finished: 끝까지 걸어가서 사라졌거나, 클릭으로 사라졌을 때(한 번만)."""

    clicked = Signal()
    finished = Signal()

    def __init__(self, todo_count: int):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)

        self._todo_count = todo_count
        self._frames = self._build_frames()
        self._frame_index = 0
        self._done = False

        if self._frames:
            w, h = self._frames[0].width(), self._frames[0].height()
            self.setFixedSize(math.ceil(w / _SCALE), math.ceil(h / _SCALE))

        self._frame_timer = QTimer(self)
        self._frame_timer.setInterval(_FRAME_INTERVAL_MS)
        self._frame_timer.timeout.connect(self._next_frame)

        self._move_timer = QTimer(self)
        self._move_timer.setTimerType(Qt.PreciseTimer)
        self._move_timer.setInterval(_MOVE_INTERVAL_MS)
        self._move_timer.timeout.connect(self._step)
        self._elapsed = QElapsedTimer()
        self._start_x = 0
        self._end_x = 0

    # ---------- 이미지 합성 ----------

    def _build_frames(self) -> list[QImage]:
        """걷기 프레임 4장 각각에 말풍선과 글자를 미리 합성해 둔다(@2x).
        글자는 출발할 때 정해지면 안 바뀌므로, 매 프레임 다시 그리지 않고
        paintEvent는 합성 이미지 한 장만 그린다. 파일이 하나라도 없으면
        빈 목록 — 호출부(is_ready)가 마스코트를 띄우지 않는다."""
        layout = _load_layout()
        if not layout:
            return []
        asset_dir = config.mascot_asset_dir()
        bubble = QImage(str(asset_dir / _BUBBLE_FILE))
        walk = [QImage(str(asset_dir / name)) for name in _FRAME_FILES]
        if bubble.isNull() or any(img.isNull() for img in walk):
            return []

        cw, ch = layout["composite_size"]
        fx, fy = layout["frame_pos"]
        bx, by = layout["bubble_pos"]
        cx = bx + layout["bubble_text_center"][0]
        box_left, _, box_right, _ = layout["bubble_text_box"]
        max_text_w = (box_right - box_left) - 24  # 좌우 여백 조금

        count_text = f"오늘 할 일 {self._todo_count}건!"
        title_font = _fit_font(_TITLE_TEXT, _TITLE_PT, max_text_w)
        count_font = _fit_font(count_text, _COUNT_PT, max_text_w)

        frames = []
        for frame_img in walk:
            img = QImage(cw, ch, QImage.Format_ARGB32_Premultiplied)
            img.fill(Qt.transparent)
            p = QPainter(img)
            p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
            p.drawImage(QPointF(bx, by), bubble)
            p.drawImage(QPointF(fx, fy), frame_img)
            for text, font, color, center_y in (
                (_TITLE_TEXT, title_font, _TITLE_COLOR, by + _TITLE_CENTER_Y),
                (count_text, count_font, _COUNT_COLOR, by + _COUNT_CENTER_Y),
            ):
                p.setFont(font)
                p.setPen(QColor(color))
                line_h = QFontMetricsF(font).height()
                p.drawText(
                    QRectF(cx - max_text_w / 2, center_y - line_h / 2, max_text_w, line_h),
                    Qt.AlignCenter, text,
                )
            p.end()
            img.setDevicePixelRatio(_SCALE)
            frames.append(img)
        return frames

    def is_ready(self) -> bool:
        return bool(self._frames)

    # ---------- 출발 / 이동 ----------

    def start(self):
        """주 모니터 작업 영역(작업표시줄 제외) 아래쪽에 창 아래쪽을 맞추고,
        화면 왼쪽 밖에서 출발해 오른쪽 밖으로 나가면 사라진다."""
        screen = QGuiApplication.primaryScreen()
        if not self._frames or screen is None:
            self._finish()
            return
        area = screen.availableGeometry()
        self._start_x = area.left() - self.width()
        self._end_x = area.right() + 1
        y = area.bottom() + 1 - self.height()
        self.move(self._start_x, y)
        self.show()
        self._elapsed.start()
        self._frame_timer.start()
        self._move_timer.start()

    def _step(self):
        x = self._start_x + round(self._elapsed.elapsed() * _WALK_SPEED_PX_PER_SEC / 1000)
        if x >= self._end_x:
            self._finish()
            return
        self.move(x, self.y())

    def _next_frame(self):
        self._frame_index = (self._frame_index + 1) % len(self._frames)
        self.update()

    def _finish(self):
        if self._done:
            return
        self._done = True
        self._frame_timer.stop()
        self._move_timer.stop()
        self.hide()
        self.finished.emit()
        self.close()

    # ---------- 그리기 / 클릭 ----------

    def paintEvent(self, event):
        if not self._frames:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(QPointF(0, 0), self._frames[self._frame_index])

    def _is_opaque_at(self, pos) -> bool:
        img = self._frames[self._frame_index] if self._frames else None
        if img is None:
            return False
        x, y = int(pos.x() * _SCALE), int(pos.y() * _SCALE)
        if not (0 <= x < img.width() and 0 <= y < img.height()):
            return False
        return img.pixelColor(x, y).alpha() > 0

    def mousePressEvent(self, event):
        # 알파 0 픽셀은 OS가 이미 아래 창으로 통과시키지만, 혹시 이벤트가
        # 들어와도 투명한 곳이면 반응하지 않는다.
        if event.button() == Qt.LeftButton and self._is_opaque_at(event.position()):
            event.accept()
            self.clicked.emit()
            self._finish()
            return
        event.ignore()
