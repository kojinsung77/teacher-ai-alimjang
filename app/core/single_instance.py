# -*- coding: utf-8 -*-
"""중복 실행 방지(Single Instance) + 이미 실행 중인 인스턴스에게 '창을
보여줘' 신호를 보내는 최소 IPC. Qt 내장 QLocalServer/QLocalSocket만
쓰므로 pywin32 같은 추가 의존성이 필요 없다.

동작:
1) 앱 시작 시 고유 이름의 로컬 소켓에 연결을 시도한다.
2) 연결에 성공하면 이미 다른 인스턴스가 실행 중인 것 — 'show' 메시지를
   보내고(기존 인스턴스가 자기 창을 복원하도록 유도) False를 반환해
   이번 프로세스는 곧바로 종료하도록 한다.
3) 연결에 실패하면 자신이 최초 인스턴스 — 서버를 열고, 이후 들어오는
   연결마다 showRequested 시그널을 쏜다. MainWindow가 이 시그널을
   받아 자기 자신을 앞으로 가져온다."""

import ctypes

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .. import config

_SERVER_NAME = f"{config.APP_DIR_NAME}_SingleInstance"

# installer/setup.iss의 [Setup] AppMutex와 이름이 반드시 일치해야 한다.
# 이건 QLocalServer 중복 실행 방지와는 목적이 다르다 — 이 Win32
# 뮤텍스는 "지금 이 프로그램이 실행 중이다"를 설치/제거 프로그램이
# 감지해서 재설치·업데이트 전에 종료를 요청할 수 있게 하기 위한 것.
_INSTALL_MUTEX_NAME = "TeacherAlimjangRunningMutex"
_mutex_handle = None


def hold_install_mutex():
    """트레이 상주 중에 재설치/업데이트하다가 exe 파일이 잠겨 있어
    실패하는 일이 없도록, Inno Setup이 감지할 수 있는 이름 있는
    뮤텍스를 하나 만들어 둔다. 프로세스가 끝나면 OS가 자동으로
    회수하므로 명시적으로 닫을 필요는 없다. Single Instance 승자
    (실제로 창을 띄우는 쪽)만 호출해야 한다."""
    global _mutex_handle
    _mutex_handle = ctypes.windll.kernel32.CreateMutexW(
        None, False, _INSTALL_MUTEX_NAME
    )


def release_install_mutex():
    """자동 업데이트로 조용한 설치를 실행하기 직전에 명시적으로
    뮤텍스를 닫는다. 프로세스가 끝나면 OS가 어차피 회수하지만, Inno
    Setup의 AppMutex 체크가 우리 프로세스의 나머지 종료 절차(트레이
    아이콘 숨기기 등)보다 먼저 실행될 수 있으므로 최대한 빨리
    명시적으로 풀어서 설치 프로그램이 "실행 중" 상태로 오인하지
    않게 한다."""
    global _mutex_handle
    if _mutex_handle:
        ctypes.windll.kernel32.CloseHandle(_mutex_handle)
        _mutex_handle = None


class SingleInstanceGuard(QObject):
    showRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server: QLocalServer = None
        self._pending_sockets = []

    def try_acquire(self) -> bool:
        """이미 실행 중이면 그쪽에 '보여줘' 신호를 보내고 False를 반환한다.
        아무도 없으면 자신이 서버가 되어 True를 반환한다."""
        socket = QLocalSocket()
        socket.connectToServer(_SERVER_NAME)
        if socket.waitForConnected(200):
            socket.write(b"show")
            socket.waitForBytesWritten(200)
            socket.disconnectFromServer()
            return False

        # 연결 실패 = 아무도 없음. 이전 비정상 종료로 소켓 이름이
        # 남아있을 수 있으니 한 번 정리하고 새로 연다.
        QLocalServer.removeServer(_SERVER_NAME)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        self._server.listen(_SERVER_NAME)
        return True

    def _on_new_connection(self):
        socket = self._server.nextPendingConnection()
        if socket is None:
            return
        self._pending_sockets.append(socket)
        socket.readyRead.connect(lambda s=socket: self._on_ready_read(s))
        socket.disconnected.connect(lambda s=socket: self._cleanup_socket(s))

    def _on_ready_read(self, socket):
        if bytes(socket.readAll()) == b"show":
            self.showRequested.emit()

    def _cleanup_socket(self, socket):
        if socket in self._pending_sockets:
            self._pending_sockets.remove(socket)
        socket.deleteLater()
