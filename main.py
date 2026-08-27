# -*- coding: utf-8 -*-
"""교사업무 AI 알림장 — 실행 진입점.

실행: python main.py
"""

import sys
from pathlib import Path

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QMessageBox

from app import config, db
from app.core import autostart
from app.core.single_instance import SingleInstanceGuard, hold_install_mutex
from app.ui.styles import STYLESHEET
from app.ui.main_window import MainWindow
from app.ui.messenger_setup_dialog import MessengerSetupDialog
from app.ui.ai_settings_dialog import AISettingsDialog

SETUP_DONE_KEY = "setup_done"  # 설계 문서(쿨메신저_연동_설계.md) 14장 settings 키와 통일

_FONT_DIR = Path(__file__).resolve().parent / "app" / "ui" / "assets" / "fonts"
# 나눔고딕(Naver, OFL) 하나로 앱 전체 폰트를 통일한다 — 제목/인사말 전용
# 학교안심 알림장 + 본문용 Pretendard로 이원화했던 예전 체계는 정리했다
# (app/ui/styles.py의 FONT_FAMILY 참고, HEADING_FONT_FAMILY는 더 이상 없음).
_FONT_FILES = ["NanumGothic-Regular.ttf", "NanumGothic-Bold.ttf"]


def _register_bundled_fonts():
    """번들 폰트(전부 OFL 라이선스)를 앱 시작 시 등록한다. 파일이 없는
    환경(수동 배포 등)이면 조용히 건너뛴다 — styles.py의 fallback 체인이
    시스템에 이미 설치된 폰트를 대신 잡아준다."""
    for filename in _FONT_FILES:
        path = _FONT_DIR / filename
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))


def main():
    is_autostart = config.AUTOSTART_ARG in sys.argv

    db.init_db()

    app = QApplication(sys.argv)
    # 창을 닫는 게 아니라 숨기기만 하는 트레이 앱이라, "마지막 창이
    # 닫히면 앱 종료"라는 Qt 기본 동작을 꺼야 트레이로 숨긴 상태에서
    # 앱이 조용히 죽는 일이 없다. 실제 종료는 트레이 메뉴에서만.
    app.setQuitOnLastWindowClosed(False)
    _register_bundled_fonts()
    app.setStyleSheet(STYLESHEET)

    # 중복 실행 방지: 이미 떠 있는 인스턴스가 있으면 그쪽에 "창 보여줘"
    # 신호만 보내고 이번 프로세스는 곧바로 끝낸다.
    guard = SingleInstanceGuard()
    if not guard.try_acquire():
        return
    hold_install_mutex()  # 설치/제거 프로그램이 "실행 중" 여부를 감지할 수 있게

    if not db.get_setting(SETUP_DONE_KEY):
        MessengerSetupDialog().exec()
        AISettingsDialog().exec()

        # 자동 시작 기본값을 켜짐으로 한다 — 체크박스 기본 표시값만
        # 바꾸는 게 아니라 실제로 지금 레지스트리에 등록해야, 사람이
        # 설정 화면을 한 번도 안 열어도 다음 로그인부터 진짜 자동
        # 실행된다(app/core/autostart.py는 DB에 별도 플래그를 안 두고
        # 레지스트리 자체를 정답으로 삼으므로, 여기서 실제로
        # set_enabled(True)를 불러야만 "기본값 켜짐"이 의미가 있다).
        # 사용자 모르게 조용히 켜두지 않도록 안내 문구를 함께 띄운다.
        autostart.set_enabled(True)
        QMessageBox.information(
            None, "자동 시작 설정",
            "컴퓨터를 켤 때 자동으로 실행되도록 설정됩니다.\n"
            "(설정 > 일반에서 언제든 끌 수 있습니다)"
        )

        db.set_setting(SETUP_DONE_KEY, "1")

    window = MainWindow()
    window.single_instance_guard = guard  # guard가 window와 함께 계속 살아있게
    guard.showRequested.connect(window.show_and_activate)

    if is_autostart:
        # Windows 로그인 자동 실행. 사용자가 설정 > 일반에서 "시스템
        # 트레이에서 실행"(autostart_hide_window)을 명시적으로 켠 경우에만
        # 창을 띄우지 않고 트레이에서 조용히 시작한다. 그 외(기본값 포함,
        # DB에 키가 아예 없는 경우)에는 창을 화면 맨 앞으로 띄운다 —
        # 이 옵션을 안 만졌는데도 자동 실행 시 창이 안 보이던 문제를 막는다.
        # 최초 설정이 아직 안 끝난 상태로 자동 시작될 일은 없지만(자동
        # 시작은 최초 설정을 마친 뒤 켜지는 옵션이므로), 방어적으로 그런
        # 경우엔 그냥 창을 보여준다.
        if (
            db.get_setting(SETUP_DONE_KEY) == "1"
            and db.get_setting("autostart_hide_window", "0") == "1"
        ):
            window.start_hidden_in_tray()
        else:
            window.show_and_activate()
    else:
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
