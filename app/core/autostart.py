# -*- coding: utf-8 -*-
"""Windows 로그인 시 자동 실행 등록/해제.

HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run 에
값을 쓰거나 지운다. 이 키는 사용자별 설정이라 관리자 권한이 필요 없고,
표준 라이브러리 winreg만으로 충분해 pywin32 같은 추가 의존성이
필요 없다.

레지스트리 자체를 "진실의 소스"로 삼는다 — '자동 시작 켜짐' 여부를
DB에 별도 불리언으로 중복 저장하지 않는다. 그래야 설치 프로그램이
미리 등록해 둔 값이든 설정 화면에서 나중에 바꾼 값이든 항상 같은
곳(레지스트리)에서 하나의 정답을 읽게 되어, 두 곳의 상태가 어긋나는
일이 없다."""

import sys
import winreg
from pathlib import Path

from .. import config

_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _executable_command() -> str:
    """자동 시작 시 실행할 커맨드 문자열.
    PyInstaller onefile로 빌드된 exe면 그 exe 자체(+ --autostart)를
    가리키고, 개발 환경(python main.py로 실행 중)이면 콘솔 창이 뜨지
    않도록 python.exe 대신 pythonw.exe를 우선 사용한다."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" {config.AUTOSTART_ARG}'

    python_exe = Path(sys.executable)
    pythonw = python_exe.with_name("pythonw.exe")
    interpreter = str(pythonw) if pythonw.exists() else str(python_exe)
    main_py = Path(__file__).resolve().parent.parent.parent / "main.py"
    return f'"{interpreter}" "{main_py}" {config.AUTOSTART_ARG}'


def is_enabled() -> bool:
    """현재 이 사용자 계정에 자동 시작이 등록되어 있는지."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_READ
        ) as key:
            winreg.QueryValueEx(key, config.AUTOSTART_VALUE_NAME)
        return True
    except OSError:
        return False


def set_enabled(enabled: bool):
    """자동 시작을 켜거나 끈다. 켤 때마다 현재 실행 파일 경로로 다시
    쓰므로, 프로그램을 재설치/이동한 뒤 설정을 다시 저장하면 경로가
    저절로 최신 상태로 갱신된다."""
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE
    ) as key:
        if enabled:
            winreg.SetValueEx(
                key, config.AUTOSTART_VALUE_NAME, 0, winreg.REG_SZ,
                _executable_command(),
            )
        else:
            try:
                winreg.DeleteValue(key, config.AUTOSTART_VALUE_NAME)
            except OSError:
                pass
