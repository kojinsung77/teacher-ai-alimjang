# -*- coding: utf-8 -*-
"""파랑새 알림 — 주 모니터 작업표시줄 바로 위를 왔다 갔다 걸어 다니는
마스코트(파랑새 + 말풍선). 아침에 앱이 처음 켜질 때, 정기 알림 시각
(13:20/16:10), 화면 잠금을 풀 때 MainWindow가 내보낸다.

- 화면 밖에서 슬금슬금 들어오지 않고, 주 모니터 왼쪽 끝에 온전한 모습으로
  '짠' 나타나 오른쪽으로 걸어간다.
- 오른쪽 끝에 닿으면 잠깐 서서 뒤돌아 왼쪽으로, 왼쪽 끝에 닿으면 다시
  오른쪽으로 — 클릭할 때까지 계속 왔다 갔다 한다. 뒤돌면 그림과 말풍선이
  함께 좌우로 바뀐다(말풍선 글자는 뒤집히지 않는다).
- 말풍선은 이미지가 아니라 글자 크기에 맞춰 직접 그린다 — 글자보다
  커다란 말풍선이 화면을 가리지 않게.
- 크기는 처음 버전의 약 2/3: @2x 이미지를 배율 3으로 그린다.
- 걷는 동안 발표·전체화면·화면 잠금이 시작되면 잠깐 숨었다가, 끝나면
  같은 자리에 다시 나타난다 — 학생들 앞 화면에 계속 떠 있으면 곤란하다.
- 다른 창의 포커스를 절대 뺏지 않는다: 선생님이 한글 문서에 타이핑하고
  있어도 입력이 끊기면 안 된다(Tool 창 + WindowDoesNotAcceptFocus +
  WA_ShowWithoutActivating).
- 왼쪽 클릭: clicked 시그널을 보내고 사라진다 — MainWindow가 받아서 앱
  창을 띄운다. 오른쪽 클릭: 앱은 열지 않고 그냥 사라진다(수업 중 등).
  파랑새·말풍선 바깥의 투명한 부분은 클릭·마우스 올림으로 치지 않는다.
- 마우스를 파랑새·말풍선 위에 올리면 그 자리에 멈춰 서서 기다린다 —
  움직이는 걸 쫓아가며 누르지 않아도 되게. 마우스를 떼면 다시 걷는다.
- 말풍선에는 "쿨브리핑"과 건수만 쓴다. 업무 제목 같은 구체 내용은 절대
  넣지 않는다 — 교실 TV·프로젝터로 화면이 공유되고 있을 수 있다.
- 할 일이 0건이 되면(MainWindow가 set_count로 알려 줌) 스스로 사라진다.

걷기 이미지·확성기 위치는 app/ui/assets/mascot/MASCOT_ASSETS.md, layout.json
참고. 화면 배치 계산은 Qt 없이 compute_layout()에 모아 두었다(미리보기
그림을 만들 때도 같은 함수를 쓴다)."""

import json
import sys

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QImage, QLinearGradient,
    QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import QWidget

from .. import config

# 걷는 속도(화면 픽셀/초). 1920px 화면이면 끝에서 끝까지 약 40초.
WALK_SPEED_PX_PER_SEC = 45
# 걷기 프레임 한 장을 보여주는 시간(ms).
FRAME_INTERVAL_MS = 220
# 위치를 다시 그리는 주기(ms) — 약 30fps.
MOVE_TICK_MS = 33
# 끝에 닿아 뒤돌 때 잠깐 서 있는 시간(ms) — 갑자기 미끄러지듯 방향이
# 바뀌지 않게.
TURN_PAUSE_MS = 700
# 발표·전체화면 여부와 화면 크기 변화를 다시 확인하는 주기(ms).
GUARD_INTERVAL_MS = 1500

# @2x 이미지를 배율 3으로 그린다 → 처음 버전(배율 2)의 2/3 크기.
SPRITE_DPR = 3.0

# 말풍선 글자 — 크기를 줄였어도 교실 모니터에서 읽히는 선은 지킨다.
TITLE_PX = 18
BODY_PX = 13
BUBBLE_PAD_X = 14
BUBBLE_PAD_Y = 8
LINE_GAP = 2
# 말풍선 폭은 이 문구 기준으로 고정한다 — 건수가 1건→12건으로 바뀌어도
# 창 크기가 출렁이지 않게.
_WIDTH_SAMPLE = "오늘 할 일 99건!"

_TITLE_COLOR = QColor("#1656E8")
_TEXT_COLOR = QColor("#191E2D")
_BUBBLE_BORDER = QColor("#2B78FF")
_BUBBLE_FILL_TOP = QColor("#FFFFFF")
_BUBBLE_FILL_BOTTOM = QColor("#EAF1FF")
_BUBBLE_SHADOW = QColor(20, 60, 160, 45)


def _user_is_presenting() -> bool:
    """전체화면 앱·발표(PPT 슬라이드쇼)·전체화면 동영상·화면 잠금 중이면
    True. 이때는 마스코트를 띄우지 않는다 — 학생들 앞에서 화면에 캐릭터가
    지나가면 곤란하다. Windows가 아니거나 확인에 실패하면 False(=띄워도
    됨)로 본다."""
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


def can_show_now() -> bool:
    """지금 마스코트를 띄워도 되는 상황인지(발표·전체화면·잠금 중이 아닌지)."""
    return not _user_is_presenting()


# ---------- 배치 계산 (Qt 없이) ----------

def compute_layout(frame_w, frame_h, mouth, body_w, body_h):
    """오른쪽을 보고 있을 때의 창 안 배치를 계산한다. 왼쪽을 볼 때는
    창 가운데를 기준으로 좌우를 뒤집어 쓴다(mirror_x).

    창은 파랑새를 가운데에 두고 양옆에 말풍선 자리(span)를 똑같이 둔다 —
    뒤돌 때 창을 옮기지 않아도 파랑새가 제자리에서 돌아선다. 말풍선이
    없는 쪽은 투명해서 보이지도 않고 클릭되지도 않는다.

    mouth: 파랑새 그림(오른쪽을 볼 때) 안에서 확성기 입구 위치.
    반환값의 좌표는 모두 창 왼쪽 위 기준(화면 논리 픽셀)."""
    mx, my = mouth
    pad = 4                      # 말풍선 테두리·그림자 여유
    # 창 크기(setFixedSize)는 정수여야 하므로 배치 기준점은 반올림한다.
    body_w, body_h = int(round(body_w)), int(round(body_h))
    body_x = int(round(mx - 8))      # 말풍선 몸통 왼쪽 (파랑새 기준)
    body_bottom = int(round(my - 12))  # 말풍선 몸통 아래 (파랑새 기준)
    body_y = body_bottom - body_h
    top = min(0, body_y - pad)   # 말풍선이 파랑새 머리보다 위로 나가는 만큼
    span = max(0, body_x + body_w + pad - frame_w)
    W = span + frame_w + span
    H = frame_h - top
    ox, oy = span, -top          # 파랑새 그림의 창 안 위치
    bx, by = ox + body_x, oy + body_y
    tail_base = ((bx + 12, by + body_h - 1), (bx + 30, by + body_h - 1))
    tail_tip = (ox + mx + 1, oy + my - 3)
    return {
        "size": (W, H),
        "span": span,
        "bird": (ox, oy, frame_w, frame_h),
        "body": (bx, by, body_w, body_h),
        "tail": (tail_base[0], tail_tip, tail_base[1]),
    }


def mirror_x(W, x, w=0):
    """창 가운데를 기준으로 좌우를 뒤집은 x(왼쪽 위 기준)."""
    return W - x - w


def walk_bounds(area_left, area_right, W, span):
    """창 왼쪽 x가 움직일 수 있는 범위. area_right는 화면 오른쪽 끝 픽셀.

    - 처음 나타날 때: 파랑새가 화면 왼쪽 끝에 딱 붙도록 창은 span만큼
      화면 밖에서 시작한다(그쪽은 투명한 빈자리라 안 보인다).
    - 오른쪽으로 갈 때: 말풍선(오른쪽)이 화면 끝에 닿으면 뒤돈다.
    - 왼쪽으로 갈 때: 말풍선(왼쪽)이 화면 끝에 닿으면 뒤돈다.
    말풍선 글자가 화면 밖으로 잘려 나가는 일이 없다."""
    start = area_left - span
    right_turn = max(start, area_right + 1 - W)
    left_turn = area_left
    return start, left_turn, right_turn


class MascotWalker(QWidget):
    clicked = Signal()      # 왼쪽 클릭 — 앱 창을 연다
    dismissed = Signal()    # 오른쪽 클릭 — 앱은 열지 않고 닫기만

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
        self.setMouseTracking(True)
        self.setToolTip("누르면 쿨브리핑이 열립니다 · 오른쪽 클릭하면 닫힙니다")

        self._count = max(0, int(todo_count))
        self._load_assets()

        self._frame_index = 0
        self._facing = 1          # 1: 오른쪽으로 걷는 중, -1: 왼쪽으로
        self._hover = False
        self._pressed = None      # 누른 버튼(파랑새·말풍선 위에서 눌렀을 때만)
        self._turn_wait_ms = 0
        self._hidden_for_presenting = False
        self._closed = False
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

        def load(name):
            img = QImage(str(d / name))
            right = QPixmap.fromImage(img)
            right.setDevicePixelRatio(SPRITE_DPR)
            flipped = img.flipped(Qt.Horizontal) if hasattr(img, "flipped") else img.mirrored(True, False)
            left = QPixmap.fromImage(flipped)
            left.setDevicePixelRatio(SPRITE_DPR)
            return right, left

        walk = [load(f"mascot_walk_{i}.png") for i in range(4)]
        self._frames = {1: [r for r, _ in walk], -1: [l for _, l in walk]}
        idle_r, idle_l = load("mascot_idle.png")
        self._idle = {1: idle_r, -1: idle_l}

        fw2, fh2 = L["frame_size"]
        frame_w = round(fw2 / SPRITE_DPR)
        frame_h = round(fh2 / SPRITE_DPR)
        mouth2 = L["megaphone_mouth_in_frame"]
        mouth = (mouth2[0] / SPRITE_DPR, mouth2[1] / SPRITE_DPR)

        self._title_font = QFont("NanumGothic")
        self._title_font.setPixelSize(TITLE_PX)
        self._title_font.setBold(True)
        self._body_font = QFont("NanumGothic")
        self._body_font.setPixelSize(BODY_PX)
        self._body_font.setBold(True)
        tfm = QFontMetrics(self._title_font)
        bfm = QFontMetrics(self._body_font)
        self._title_h = tfm.height()
        self._body_line_h = bfm.height()
        text_w = max(tfm.horizontalAdvance("쿨브리핑"),
                     bfm.horizontalAdvance(_WIDTH_SAMPLE))
        body_w = text_w + BUBBLE_PAD_X * 2
        body_h = BUBBLE_PAD_Y * 2 + self._title_h + LINE_GAP + self._body_line_h

        self._L = compute_layout(frame_w, frame_h, mouth, body_w, body_h)
        self.setFixedSize(*self._L["size"])

    def is_active(self) -> bool:
        """아직 돌아다니는 중인지(닫혔으면 False). 닫힌 뒤 실제로 지워지기
        전 잠깐 사이에 다시 불려도, 숨은 채로 남은 파랑새를 재사용하지
        않고 새로 만들게 하려는 확인용."""
        return not self._closed

    def set_count(self, todo_count: int):
        """MainWindow가 1분마다 최신 건수를 알려 준다. 다 처리해서 0건이
        되면 더 돌아다닐 이유가 없으니 사라진다."""
        n = max(0, int(todo_count))
        if n < 1:
            self.close()
            return
        if n != self._count:
            self._count = n
            self.update()

    # ---------- 출발/이동 ----------

    def _update_area(self):
        """주 모니터의 작업표시줄을 뺀 영역 기준으로 움직일 범위와 높이를
        정한다. 해상도·작업표시줄 위치가 바뀌어도 맞춰지도록 주기적으로
        다시 부른다."""
        area = QGuiApplication.primaryScreen().availableGeometry()
        self._start_x, self._left_turn, self._right_turn = walk_bounds(
            area.left(), area.right(), self.width(), self._L["span"]
        )
        self._y = area.bottom() - self.height() + 1

    def _clamp_x(self):
        lo = self._start_x if self._facing > 0 else self._left_turn
        self._x = min(max(self._x, lo), self._right_turn)

    def start(self):
        self._update_area()
        # 화면 밖이 아니라 왼쪽 끝에 온전한 모습으로 '짠' 나타난다.
        self._facing = 1
        self._x = float(self._start_x)
        self.move(int(self._x), self._y)
        self.show()  # WA_ShowWithoutActivating이라 포커스를 안 가져간다
        self.raise_()
        self._clock.start()
        self._move_timer.start(MOVE_TICK_MS)
        self._frame_timer.start(FRAME_INTERVAL_MS)
        self._guard_timer.start(GUARD_INTERVAL_MS)

    def _standing(self) -> bool:
        return self._hover or self._turn_wait_ms > 0

    def _on_move_tick(self):
        elapsed_ms = self._clock.restart()
        if self._hidden_for_presenting:
            return
        # 걷는 파랑새가 가만히 있는 마우스 밑으로 들어오면 Windows가 마우스
        # 이동 이벤트를 보내 주지 않아 그대로 지나가 버린다 — 커서 위치를
        # 직접 보고 멈춘다.
        self._set_hover(self._hit(self.mapFromGlobal(QCursor.pos())))
        if self._hover:
            return
        if self._turn_wait_ms > 0:
            self._turn_wait_ms -= elapsed_ms
            if self._turn_wait_ms <= 0:
                self._turn_wait_ms = 0
                self.update()
            return
        self._x += self._facing * WALK_SPEED_PX_PER_SEC * elapsed_ms / 1000.0
        if self._facing > 0 and self._x >= self._right_turn:
            self._x = float(self._right_turn)
            self._turn_around(-1)
        elif self._facing < 0 and self._x <= self._left_turn:
            self._x = float(self._left_turn)
            self._turn_around(1)
        self.move(int(self._x), self._y)

    def _turn_around(self, new_facing: int):
        """끝에 닿았다 — 잠깐 서 있다가 반대로 걷는다. 창 자체는 파랑새를
        가운데에 둔 대칭 배치라 옮길 필요 없이 그림만 좌우로 바뀐다."""
        self._facing = new_facing
        self._turn_wait_ms = TURN_PAUSE_MS
        self.update()

    def _on_guard_tick(self):
        """발표·전체화면·잠금이 시작되면 숨고, 끝나면 그 자리에 다시
        나타난다. 화면 크기가 바뀌었으면 범위를 다시 맞춘다."""
        if not can_show_now():
            if not self._hidden_for_presenting:
                self._hidden_for_presenting = True
                self._hover = False  # 숨는 동안 leaveEvent가 안 올 수 있다
                self.hide()
            return
        self._update_area()
        self._clamp_x()
        if self._hidden_for_presenting:
            self._hidden_for_presenting = False
            self.move(int(self._x), self._y)
            self.show()
            self.raise_()
            self._clock.restart()  # 숨어 있던 시간만큼 순간이동하지 않게
        elif self.pos().y() != self._y or self.pos().x() != int(self._x):
            self.move(int(self._x), self._y)

    def _on_frame_tick(self):
        if self._hidden_for_presenting or self._standing():
            return
        self._frame_index = (self._frame_index + 1) % 4
        self.update()

    # ---------- 배치 (방향에 따라 좌우 뒤집기) ----------

    def _rects(self):
        W = self.width()
        bx, by, bw, bh = self._L["bird"]
        cx, cy, cw, ch = self._L["body"]
        (t1x, t1y), (ttx, tty), (t2x, t2y) = self._L["tail"]
        if self._facing < 0:
            bx = mirror_x(W, bx, bw)
            cx = mirror_x(W, cx, cw)
            t1x, ttx, t2x = mirror_x(W, t1x), mirror_x(W, ttx), mirror_x(W, t2x)
        return (QRectF(bx, by, bw, bh), QRectF(cx, cy, cw, ch),
                (QPointF(t1x, t1y), QPointF(ttx, tty), QPointF(t2x, t2y)))

    def _hit(self, pos) -> bool:
        """파랑새나 말풍선 위인지 — 그 바깥 투명한 자리는 무시한다."""
        bird, body, _ = self._rects()
        p = QPointF(pos)
        return bird.adjusted(8, 4, -8, 0).contains(p) or body.adjusted(-2, -2, 2, 2).contains(p)

    # ---------- 그리기 ----------

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        bird, body, (t1, tip, t2) = self._rects()

        # 말풍선: 둥근 몸통 + 확성기 쪽으로 뻗은 꼬리
        radius = min(body.height() * 0.45, 22.0)
        path = QPainterPath()
        path.addRoundedRect(body, radius, radius)
        tail = QPainterPath()
        tail.moveTo(t1)
        tail.lineTo(tip)
        tail.lineTo(t2)
        tail.closeSubpath()
        path = path.united(tail)

        p.save()
        p.translate(0, 1.5)
        p.fillPath(path, _BUBBLE_SHADOW)
        p.restore()
        grad = QLinearGradient(body.topLeft(), body.bottomLeft())
        grad.setColorAt(0.0, _BUBBLE_FILL_TOP)
        grad.setColorAt(1.0, _BUBBLE_FILL_BOTTOM)
        p.fillPath(path, grad)
        p.setPen(QPen(_BUBBLE_BORDER, 2.4))
        p.drawPath(path)

        # 글자(뒤집지 않는다)
        p.setFont(self._title_font)
        p.setPen(_TITLE_COLOR)
        title_rect = QRectF(body.left(), body.top() + BUBBLE_PAD_Y, body.width(), self._title_h)
        p.drawText(title_rect, Qt.AlignCenter, "쿨브리핑")
        p.setFont(self._body_font)
        p.setPen(_TEXT_COLOR)
        body_rect = QRectF(body.left(), title_rect.bottom() + LINE_GAP, body.width(), self._body_line_h)
        p.drawText(body_rect, Qt.AlignCenter, f"오늘 할 일 {self._count}건!")

        # 파랑새
        sprite = self._idle[self._facing] if self._standing() else self._frames[self._facing][self._frame_index]
        p.drawPixmap(bird.topLeft(), sprite)
        p.end()

    # ---------- 마우스 ----------

    def _set_hover(self, hover: bool):
        if hover != self._hover:
            self._hover = hover
            self.setCursor(Qt.PointingHandCursor if hover else Qt.ArrowCursor)
            self._clock.restart()
            self.update()

    def mouseMoveEvent(self, event):
        # 파랑새·말풍선 위에 마우스를 올리면 그 자리에 서서 기다린다 —
        # 움직이는 걸 쫓아가며 누르지 않아도 되게.
        self._set_hover(self._hit(event.position()))

    def leaveEvent(self, _event):
        self._set_hover(False)

    def mousePressEvent(self, event):
        if event.button() in (Qt.LeftButton, Qt.RightButton) and self._hit(event.position()):
            self._pressed = event.button()
        else:
            self._pressed = None

    def mouseReleaseEvent(self, event):
        # 누름과 뗌이 둘 다 파랑새·말풍선 위에서 같은 버튼으로 일어나야
        # 클릭으로 본다 — 다른 곳에서 누르고 끌어오다 여기서 뗀 것까지
        # 클릭으로 치면 선생님 의도와 상관없이 앱 창이 튀어나올 수 있다.
        pressed, self._pressed = self._pressed, None
        if pressed is None or event.button() != pressed or not self._hit(event.position()):
            return
        if pressed == Qt.LeftButton:
            self.clicked.emit()
        else:
            self.dismissed.emit()
        self.close()

    def contextMenuEvent(self, event):
        event.accept()  # 오른쪽 클릭은 닫기로만 쓴다(메뉴 안 띄움)

    def closeEvent(self, event):
        self._closed = True
        self._move_timer.stop()
        self._frame_timer.stop()
        self._guard_timer.stop()
        super().closeEvent(event)
