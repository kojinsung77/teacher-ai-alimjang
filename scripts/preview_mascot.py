# -*- coding: utf-8 -*-
"""마스코트 미리보기 — 13:20/16:10을 기다리지 않고 지금 바로 파랑새가
화면 아래를 걸어가는 모습을 확인한다. 앱 DB나 설정은 전혀 건드리지
않는다(말풍선 숫자는 아래 [TEST] 값을 쓴다).

실행: 프로젝트 폴더에서
    python scripts/preview_mascot.py          # "오늘 할 일 3건!"
    python scripts/preview_mascot.py 7        # 숫자 바꿔 보기

마스코트를 누르면 "클릭됨"이 출력되고 끝난다(실제 앱에서는 이때 창이
열린다). 마우스를 올리면 멈춰 서는지, 속도가 적당한지 확인용."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.ui import mascot_walker  # noqa: E402

TEST_COUNT = int(sys.argv[1]) if len(sys.argv) > 1 else 3


def main():
    app = QApplication(sys.argv)
    for f in ("NanumGothic-Regular.ttf", "NanumGothic-Bold.ttf"):
        p = ROOT / "app" / "ui" / "assets" / "fonts" / f
        if p.exists():
            QFontDatabase.addApplicationFont(str(p))

    print(f"[TEST] 발표·전체화면 중인가? {not mascot_walker.can_show_now()}")
    w = mascot_walker.MascotWalker(TEST_COUNT)
    w.clicked.connect(lambda: print("클릭됨 — 실제 앱에서는 여기서 창이 열립니다"))
    w.destroyed.connect(app.quit)
    w.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
