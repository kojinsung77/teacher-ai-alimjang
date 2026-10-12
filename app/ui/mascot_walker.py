# -*- coding: utf-8 -*-
"""정기 알림(13:20/16:10)과 화면 잠금 해제 때 주 모니터 작업표시줄 바로
위를 걸어가는 마스코트(파랑새 + 말풍선).

- 화면 밖에서 슬금슬금 들어오지 않고, 주 모니터 왼쪽 끝에 온전한 모습으로
  '짠' 나타나 오른쪽으로 걸어간다.
- 오른쪽 끝에 닿아도 사라지지 않는다. 그 자리에 멈춰 서서(서 있는 자세)
  클릭될 때까지 기다린다 — 자리를 비웠다 돌아와도 놓치지 않게.
- 기다리는 동안 발표·전체화면·화면 잠금이 시작되면 잠깐 숨었다가, 끝나면
  같은 자리에 다시 나타난다 — 학생들 앞 화면에 계속 떠 있으면 곤란하다.

- 다른 창의 포커스를 절대 뺏지 않는다: 선생님이 한글 문서에 타이핑하고
  있어도 입력이 끊기면 안 된다(Tool 창 + WindowDoesNotAcceptFocus +
  WA_ShowWithoutActivating).
- 마스코트나 말풍선을 클릭하면 clicked 시그널을 보내고 바로 사라진다 —
  MainWindow가 받아서 앱 창을 띄운다. 투명한 부분은 Windows가 알아서
  아래 창으로 클릭을 통과시킨다(반투명 레이어드 윈도우의 기본 동작).
- 마우스를 올리면 그 자리에 멈춰 서서 기다린다 — 움직이는 걸 쫓아가며
  누르지 않아도 되게. 마우스를 떼면 다시 걷는다(오른쪽 끝에 도착한
  뒤에는 계속 서 있다).
- 말풍선에는 "쿨브리핑"과 건수만 쓴다. 업무 제목 같은 구체 내용은 절대
  넣지 않는다 — 교실 TV·프로젝터로 화면이 공유되고 있을 수 있다.

이미지·좌표 규격은 app/ui/assets/mascot/MASCOT_ASSETS.md, layout.json 참고.
이미지는 @2x로 만들어져 있어 devicePixelRatio 2로 그린다."""

import json
import sys

from PySide6.QtCore import QElapsedTimer, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from .. import config

# 걷는 속도(화면 픽셀/초). 1920px 화면이면 왼쪽 끝 → 오른쪽 끝까지 약
# 50초 걸린다. 처음 값(80)은 "너무 빨리 지나간다"는 의견이 있어 낮췄다.
WALK_SPEED_PX_PER_SEC = 45
# 걷기 프레임 한 장을 보여주는 시간(ms). 속도를 낮춘 만큼 발걸음도
# 느리게 해야 미끄러지듯 보이지 않는다.
FRAME_INTERVAL_MS = 220
# 위치를 다시 그리는 주기(ms) — 약 30fps.
MOVE_TICK_MS = 33
# 발표·전체화면 여부와 화면 크기 변화를 다시 확인하는 주기(ms). 오른쪽
# 끝에서 클릭을 기다리는 동안 PPT 슬라이드쇼가 시작되면 이 주기 안에 숨는다.
GUARD_INTERVAL_MS = 1500

_TITLE_COLOR = QColor("#1656E8")
_TEXT_COLOR = QColor("#191E2D")


def _user_is_presenting() -> bool:
    """전체화면 앱·발표(PPT 슬라이드쇼)·전체화면 동영상·화면 잠금 중이면
    True. 이때는 마스코트를 띄우지 않고 트레이 알림만 보낸다 — 학생들
    앞에서 화면에 캐릭터가 지나가면 곤란하다. Windows가 아니거나 확인에
    실패하면 False(=띄워도 됨)로 본다."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        state = ctypes.c_int(0)
        hr = ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state))
        if hr != 0:
            return False
        # 1 NOT_PRESENT(잠금·화면보호기) 2 BUSY(전체화면 앱)
        # 3 RUNNING_D3D_FULL_SCREEN(전체화면 게임·동영상) 4 PRESENTATION_MODE
        # 5 ACCEPTS_NOTIFICATIONS 6 QUIET_TIME 7 APP(전체화면 스토어 앱)
        # Windows가 "지금 알림 받아도 됨"(5)이라고 답할 때만 띄운다 —
        # 나중에 Windows에 새 상태값이 생겨도 안전한 쪽(안 띄움)으로 간다.
        return state.value != 5
    except Exception:
        return False


class MascotWalker(QWidget):
    clicked = Signal()

    def __init__(self, todo_count: int, parent=None):
        super().__init__(
            parent,
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
        self.setMouseTracking(True)

        self._count = todo_count
        self._load_assets()

        self._frame_index = 0
        self._paused = False
        self._pressed = False
        self._arrived = False   # 오른쪽 끝에 도착해 클릭을 기다리는 중
        self._hidden_for_presenting = False
        self._x = 0.0

        self._move_timer = QTimer(self)
        self._move_timer.timeout.connect(self._on_move_tick)
        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._on_frame_tick)
        self._guard_timer = QTimer(self)
        self._guard_timer.timeout.connect(self._on_guard_tick)
        self._clock = QElapsedTimer()

    # ---------- 준비 ----------

    def _load_assets(self):
        d = config.mascot_dir()
        with open(d / "layout.json", encoding="utf-8") as f:
            L = json.load(f)
        # layout.json 좌표는 @2x 픽셀 → 화면 좌표는 절반
        half = lambda v: [round(n / 2) for n in v]  # noqa: E731
        self._size = half(L["composite_size"])
        self._frame_pos = half(L["frame_pos"])
        self._bubble_pos = half(L["bubble_pos"])
        self._text_center = half(L["bubble_text_center"])

        def load(name):
            pm = QPixmap(str(d / name))
            pm.setDevicePixelRatio(2.0)
            return pm

        self._frames = [load(f"mascot_walk_{i}.png") for i in range(4)]
        self._idle = load("mascot_idle.png")
        self._bubble = load("speech_bubble.png")
        self.setFixedSize(*self._size)

    # ---------- 출발/종료 ----------

    def _update_area(self):
        """주 모니터의 작업표시줄을 뺀 영역 기준으로 출발점·도착점·높이를
        정한다. 해상도·작업표시줄 위치가 바뀌어도 맞춰지도록 주기적으로
        다시 부른다."""
        area = QGuiApplication.primaryScreen().availableGeometry()
        self._area = area
        self._x_start = float(area.left())
        # 오른쪽 끝에서 말풍선까지 화면 안에 온전히 보이는 마지막 위치
        self._x_end = float(max(area.left(), area.right() - self.width() + 1))
        self._y = area.bottom() - self.height() + 1

    def start(self):
        self._update_area()
        # 화면 밖이 아니라 왼쪽 끝에 온전한 모습으로 '짠' 나타난다.
        self._x = self._x_start
        self.move(int(self._x), self._y)
        self.show()  # WA_ShowWithoutActivating이라 포커스를 안 가져간다
        self.raise_()
        self._clock.start()
        self._move_timer.start(MOVE_TICK_MS)
        self._frame_timer.start(FRAME_INTERVAL_MS)
        self._guard_timer.start(GUARD_INTERVAL_MS)

    def _on_move_tick(self):
        elapsed_ms = self._clock.restart()
        if self._paused or self._arrived or self._hidden_for_presenting:
            return
        self._x += WALK_SPEED_PX_PER_SEC * elapsed_ms / 1000.0
        if self._x >= self._x_end:
            self._arrive()
            return
        self.move(int(self._x), self._y)

    def _arrive(self):
        """오른쪽 끝 도착 — 멈춰 서서(서 있는 자세) 클릭을 기다린다.
        걷기 타이머는 끄고, 숨김 확인(_guard_timer)만 남긴다."""
        self._x = self._x_end
        self._arrived = True
        self._move_timer.stop()
        self._frame_timer.stop()
        self.move(int(self._x), self._y)
        self.update()

    def _on_guard_tick(self):
        """발표·전체화면·잠금이 시작되면 숨고, 끝나면 그 자리에 다시
        나타난다. 화면 크기가 바뀌었으면 위치를 다시 맞춘다."""
        if not can_show_now():
            if not self._hidden_for_presenting:
                self._hidden_for_presenting = True
                self._paused = False  # 숨는 동안 leaveEvent가 안 올 수 있다
                self.hide()
            return
        self._update_area()
        if self._arrived:
            self._x = self._x_end
        else:
            self._x = min(max(self._x, self._x_start), self._x_end)
        if self._hidden_for_presenting:
            self._hidden_for_presenting = False
            self.move(int(self._x), self._y)
            self.show()
            self.raise_()
            self._clock.restart()  # 숨어 있던 시간만큼 순간이동하지 않게
        elif self.pos().y() != self._y:
            self.move(int(self._x), self._y)

    def _on_frame_tick(self):
        if self._paused or self._arrived or self._hidden_for_presenting:
            return
        self._frame_index = (self._frame_index + 1) % len(self._frames)
        self.update()

    # ---------- 그리기 ----------

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        p.drawPixmap(QPoint(*self._bubble_pos), self._bubble)
        standing = self._paused or self._arrived
        body = self._idle if standing else self._frames[self._frame_index]
        p.drawPixmap(QPoint(*self._frame_pos), body)

        cx = self._bubble_pos[0] + self._text_center[0]
        cy = self._bubble_pos[1] + self._text_center[1]
        box_w = 172

        title_font = QFont("NanumGothic")
        title_font.setPixelSize(26)
        title_font.setBold(True)
        p.setFont(title_font)
        p.setPen(_TITLE_COLOR)
        p.drawText(QRect(cx - box_w // 2, cy - 31, box_w, 34), Qt.AlignCenter, "쿨브리핑")

        body_font = QFont("NanumGothic")
        body_font.setPixelSize(17)
        body_font.setBold(True)
        p.setFont(body_font)
        p.setPen(_TEXT_COLOR)
        p.drawText(QRect(cx - box_w // 2, cy + 4, box_w, 26), Qt.AlignCenter,
                   f"오늘 할 일 {self._count}건!")
        p.end()

    # ---------- 마우스 ----------

    def enterEvent(self, _event):
        # 마우스를 올리면 그 자리에 서서 기다린다 — 움직이는 걸 쫓아가며
        # 누르지 않아도 되게.
        self._paused = True
        self.update()

    def leaveEvent(self, _event):
        self._paused = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pressed = True

    def mouseReleaseEvent(self, event):
        # 누름과 뗌이 둘 다 마스코트 위에서 일어나야 클릭으로 본다 — 다른
        # 곳에서 누르고 끌어오다 마스코트 위에서 뗀 것까지 클릭으로 치면
        # 선생님 의도와 상관없이 앱 창이 튀어나올 수 있다.
        pressed, self._pressed = self._pressed, False
        if (event.button() == Qt.LeftButton and pressed
                and self.rect().contains(event.position().toPoint())):
            self.clicked.emit()
            self.close()

    def closeEvent(self, event):
        self._move_timer.stop()
        self._frame_timer.stop()
        self._guard_timer.stop()
        super().closeEvent(event)


def can_show_now() -> bool:
    """지금 마스코트를 띄워도 되는 상황인지(발표·전체화면 중이 아닌지)."""
    return not _user_is_presenting()
