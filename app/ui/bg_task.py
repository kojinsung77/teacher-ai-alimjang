# -*- coding: utf-8 -*-
"""네트워크 일(구글 로그인·캘린더·Gemini)을 화면이 멈추지 않게 백그라운드에서
돌리는 작은 도우미.

    run_in_background(fn, on_done, on_error)

fn은 백그라운드 스레드에서, on_done(결과)/on_error(메시지)는 화면 스레드에서
불린다. 창을 닫아도 스레드가 파이썬 쪽에서 먼저 사라져 앱이 죽지 않게
끝날 때까지 붙잡아 둔다. on_done/on_error를 가진 창이 이미 닫혔으면 결과는
조용히 버려진다(PySide6가 지워진 객체로 가는 신호를 끊는다)."""

from PySide6.QtCore import QObject, QThread, Signal

_RUNNING = set()


class _Worker(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn())
        except Exception as e:  # 화면에 그대로 보여 줄 한국어 메시지가 담긴 예외들
            self.failed.emit(str(e) or e.__class__.__name__)


def run_in_background(fn, on_done=None, on_error=None, receiver: QObject = None):
    worker = _Worker(fn)
    if on_done is not None:
        worker.done.connect(on_done)
    if on_error is not None:
        worker.failed.connect(on_error)
    _RUNNING.add(worker)
    worker.finished.connect(lambda w=worker: _RUNNING.discard(w))
    worker.start()
    return worker
