# -*- coding: utf-8 -*-
"""공간이 모자라면 다음 줄로 넘기는 레이아웃 (Qt 공식 Flow Layout 예제를 옮김).

'업무' 화면의 탭 줄이 QHBoxLayout일 때는 창을 줄이면 탭 상자가 같이
찌그러져 글자·숫자 배지가 잘렸다. 이 레이아웃은 각 탭을 원래 크기
그대로 두고, 한 줄에 안 들어가면 다음 줄로 넘긴다."""

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QSizePolicy, QWidget


class FlowLayout(QLayout):
    def __init__(self, parent=None, h_spacing: int = 8, v_spacing: int = 8):
        super().__init__(parent)
        self._items = []
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self.setContentsMargins(0, 0, 0, 0)

    # ---- QLayout 필수 메서드 ----
    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        # 가장 큰 항목 하나만 들어가면 된다 — 이래야 창을 좁힐 수 있다.
        size = QSize()
        for item in self._items:
            if not item.isEmpty():
                size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    # ---- 배치 ----
    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_height = area.x(), area.y(), 0
        for item in self._items:
            if item.isEmpty():  # 숨긴 위젯은 자리를 차지하지 않는다
                continue
            hint = item.sizeHint()
            next_x = x + hint.width() + self._h_spacing
            if next_x - self._h_spacing > area.right() + 1 and line_height > 0:
                x = area.x()
                y += line_height + self._v_spacing
                next_x = x + hint.width() + self._h_spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + m.bottom()


class FlowContainer(QWidget):
    """FlowLayout을 담는 위젯. 너비에 맞춰 필요한 높이를 부모 레이아웃에
    알려 준다(heightForWidth) — 탭이 두 줄이 되면 아래 목록이 그만큼
    내려간다."""

    def __init__(self, parent=None, h_spacing: int = 8, v_spacing: int = 8):
        super().__init__(parent)
        self.flow = FlowLayout(self, h_spacing, v_spacing)
        policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def addWidget(self, widget):
        self.flow.addWidget(widget)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.flow.heightForWidth(width)

    def sizeHint(self):
        # 한 줄에 다 놓았을 때의 너비를 바람직한 크기로 알려 준다.
        w = 0
        h = 0
        for i in range(self.flow.count()):
            item = self.flow.itemAt(i)
            if item.isEmpty():
                continue
            hint = item.sizeHint()
            w += hint.width() + (self.flow._h_spacing if w else 0)
            h = max(h, hint.height())
        return QSize(w, h)

    def minimumSizeHint(self):
        return self.flow.minimumSize()
