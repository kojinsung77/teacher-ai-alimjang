# -*- coding: utf-8 -*-
"""Windows 화면 잠금/해제 감지.

13:20/16:10 정기 알림 때 화면이 잠겨 있어 못 띄운 파랑새(마스코트)를
"잠금이 풀리는 순간" 내보내기 위한 것이다(main_window.py의
_on_screen_unlocked 참고). 잠금 해제 = 선생님이 방금 자리로 돌아와 컴퓨터
앞에 있다는 뜻이다. 앱 창은 띄우지 않는다 — 작업 중인 화면을 가로채지
않는다는 원칙.

감지 방식은 문서화된 세션 알림 API(WTSRegisterSessionNotification +
WM_WTSSESSION_CHANGE)만 쓴다. "지금 잠겨 있는가?"를 폴링으로 추정하는
방법(OpenInputDesktop/SwitchDesktop 시도, LogonUI.exe 프로세스 확인 등)은
문서화되지 않았거나 상황에 따라 오판이 나서, 수업 중에 창이 잘못 뜨는
위험을 감수할 수 없어 채택하지 않았다.

Windows 전용이다. 다른 OS(개발용 macOS/Linux)에서는 install()이 조용히
아무것도 하지 않고 False만 돌려준다 — 실제 배포 대상은 Windows뿐이다.
"""

import sys

from PySide6.QtCore import QAbstractNativeEventFilter

# winuser.h
_WM_WTSSESSION_CHANGE = 0x02B1
_WTS_SESSION_LOCK = 0x7
_WTS_SESSION_UNLOCK = 0x8
# wtsapi32.h — 이 세션(콘솔)에서 일어나는 이벤트만 받는다
_NOTIFY_FOR_THIS_SESSION = 0

# PySide6가 Windows 메시지를 네이티브 이벤트 필터로 넘길 때의 타입 식별자
_WIN_MSG_TYPE = b"windows_generic_MSG"


class WindowsSessionMonitor(QAbstractNativeEventFilter):
    """주어진 창 핸들(HWND)로 세션 잠금/해제 알림을 등록하고, 잠금은
    on_lock, 해제는 on_unlock 콜백으로 넘긴다. 콜백은 Qt 메인 스레드에서
    호출된다(Windows 메시지 펌프가 곧 메인 스레드이므로)."""

    def __init__(self, hwnd, on_lock=None, on_unlock=None):
        super().__init__()
        self._hwnd = int(hwnd)
        self._on_lock = on_lock
        self._on_unlock = on_unlock
        self._registered = False
        self._app = None
        self._MSG = None  # ctypes.wintypes.MSG (Windows에서만 채워진다)

    def install(self, app) -> bool:
        """네이티브 이벤트 필터를 app에 걸고 세션 알림을 등록한다.
        Windows가 아니거나 등록에 실패하면 아무 영향도 남기지 않고
        False를 돌려준다 — 호출부는 이 기능만 꺼진 상태로 계속 정상
        동작하면 된다."""
        if not sys.platform.startswith("win"):
            return False
        try:
            import ctypes
            from ctypes import wintypes

            wtsapi = ctypes.windll.wtsapi32
            wtsapi.WTSRegisterSessionNotification.argtypes = [wintypes.HWND, wintypes.DWORD]
            wtsapi.WTSRegisterSessionNotification.restype = wintypes.BOOL
            ok = wtsapi.WTSRegisterSessionNotification(
                wintypes.HWND(self._hwnd), _NOTIFY_FOR_THIS_SESSION
            )
            if not ok:
                return False
            self._MSG = wintypes.MSG
        except Exception:
            return False

        self._app = app
        self._registered = True
        app.installNativeEventFilter(self)
        return True

    def remove(self):
        """등록을 해제한다. 프로세스가 끝나면 OS가 어차피 정리하지만,
        완전 종료 절차에서 명시적으로 풀어 둔다."""
        if not self._registered:
            return
        try:
            import ctypes
            from ctypes import wintypes

            if self._app is not None:
                self._app.removeNativeEventFilter(self)
            wtsapi = ctypes.windll.wtsapi32
            wtsapi.WTSUnRegisterSessionNotification.argtypes = [wintypes.HWND]
            wtsapi.WTSUnRegisterSessionNotification.restype = wintypes.BOOL
            wtsapi.WTSUnRegisterSessionNotification(wintypes.HWND(self._hwnd))
        except Exception:
            pass
        self._registered = False

    def nativeEventFilter(self, event_type, message):
        # 앱에 들어오는 모든 Windows 메시지가 여기를 지나므로 가볍게 유지한다:
        # 타입 바이트 비교로 먼저 걸러내고, 그다음에만 구조체를 들여다본다.
        if event_type != _WIN_MSG_TYPE or self._MSG is None:
            return False
        try:
            msg = self._MSG.from_address(int(message))
            if msg.message == _WM_WTSSESSION_CHANGE:
                if msg.wParam == _WTS_SESSION_LOCK:
                    if self._on_lock:
                        self._on_lock()
                elif msg.wParam == _WTS_SESSION_UNLOCK:
                    if self._on_unlock:
                        self._on_unlock()
        except Exception:
            pass
        # 우리는 메시지를 소비하지 않는다 — Qt가 평소대로 계속 처리하게 둔다.
        return False
