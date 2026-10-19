# -*- coding: utf-8 -*-
"""가운데 업데이트 카드 미리보기 — 실제 새 버전이 나오기를 기다리지 않고
화면 가운데에 카드가 어떻게 뜨는지 바로 본다. 앱 DB·설정·설치는 전혀
건드리지 않는다(버튼을 누르면 무엇이 눌렸는지만 출력하고 끝난다).

실행: 프로젝트 폴더에서
    python scripts/preview_update_popup.py"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.ui.styles import STYLESHEET  # noqa: E402
from app.ui.update_popup import UpdatePopup  # noqa: E402

TEST_INFO = {
    "version": "9.9.9",
    "release_date": "2026-10-12",
    # 한 줄이 '이번 업데이트'의 한 항목이다(release.ps1 -Notes에서는 \n으로 나눔)
    "notes": "• [TEST] 앱 아이콘이 파랑새로 바뀌었어요\n"
             "• [TEST] 업무·메시지에서 [📨 전달 메시지]로 안내문을 만들어요\n"
             "• [TEST] 설정에서 파랑새가 나오는 때를 고를 수 있어요",
}


def main():
    app = QApplication(sys.argv)
    for f in ("NanumGothic-Regular.ttf", "NanumGothic-Bold.ttf"):
        p = ROOT / "app" / "ui" / "assets" / "fonts" / f
        if p.exists():
            QFontDatabase.addApplicationFont(str(p))
    app.setStyleSheet(STYLESHEET)

    popup = UpdatePopup()

    def done(label):
        print(label)
        popup.hide()
        app.quit()

    popup.install_requested.connect(lambda: done("[지금 업데이트] 눌림 — 실제 앱에서는 여기서 설치가 시작됩니다"))
    popup.later_requested.connect(lambda: done("[나중에] 눌림 — 실제 앱에서는 오늘은 다시 안 뜹니다"))
    popup.show_update(TEST_INFO)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
