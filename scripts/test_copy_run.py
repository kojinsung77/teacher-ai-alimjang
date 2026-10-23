# -*- coding: utf-8 -*-
"""버전별 테스트 폴더(v1.16.0 등)에서 그 버전을 '따로' 실행한다 — 테스트_실행.bat이 부른다.

설치된 쿨브리핑(선생님들이 쓰는 그 버전)의 데이터는 건드리지 않는다:
- 데이터(DB·설정)는 %LOCALAPPDATA%\\CoolBriefingTest\\<폴더 이름>\\TeacherAlimjang 에만 생긴다
  (OneDrive 바탕화면 폴더 안에 DB를 두면 동기화가 열린 DB 파일을 건드릴 수 있어 밖에 둔다).
- 처음 설정 창과 '컴퓨터 켤 때 자동 시작' 등록을 건너뛴다(설치된 앱의 자동 시작을
  이 테스트 폴더로 바꿔 버리지 않도록).
- 데모 모드(가짜 메시지)로 시작한다. Gemini 키는 Windows 자격 증명에서 그대로 쓴다.
- 구글 콘솔에서 받은 client_secret JSON을 이 버전 폴더나 그 위 '쿨메시저 알림장' 폴더에
  두면(이름은 google_client.json 이든 받은 그대로 client_secret_….json 이든 됨) 테스트 데이터
  폴더로 복사해 구글 캘린더 기능이 켜진다.

설치된 쿨브리핑이 켜져 있으면 테스트 버전이 뜨지 않는다(한 번에 하나만 실행) —
작업 표시줄 트레이의 쿨브리핑 → 종료 후 실행할 것."""

import json
import os
import runpy
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_REAL_LOCAL = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
TEST_BASE = Path(_REAL_LOCAL) / "CoolBriefingTest" / ROOT.name


def find_client_json():
    """버전 폴더 → 그 위 폴더 순으로, google_client.json 또는 client_secret_*.json 중
    구글 '데스크톱 앱' 클라이언트 정보가 든 첫 파일."""
    for folder in (ROOT, ROOT.parent):
        names = [folder / "google_client.json"] + sorted(folder.glob("client_secret_*.json"))
        for path in names:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            info = raw.get("installed") or raw.get("web") or raw
            if isinstance(info, dict) and info.get("client_id"):
                return path
    return None


def main():
    TEST_BASE.mkdir(parents=True, exist_ok=True)
    os.environ["LOCALAPPDATA"] = str(TEST_BASE)   # app.config.app_data_dir()가 여기를 쓴다
    sys.path.insert(0, str(ROOT))

    from app import config, db
    data_dir = config.app_data_dir()
    db.init_db()
    if not db.get_setting("setup_done"):
        db.set_setting("setup_done", "1")      # 첫 설정 창·자동 시작 등록 건너뛰기
    if db.get_setting("demo_mode") is None:
        db.set_setting("demo_mode", "1")

    os.environ["COOLBRIEFING_TEST_COPY"] = str(data_dir)   # 설정 화면이 '테스트 실행' 안내를 보이게
    src = find_client_json()
    dst = data_dir / "google_client.json"
    if src is not None:
        shutil.copyfile(src, dst)

    print(f"[TEST] 쿨브리핑 v{config.APP_VERSION} 테스트 실행")
    print(f"  데이터 폴더: {data_dir}")
    if src is not None:
        print(f"  구글 캘린더: 켜짐 ({src.name} 사용)")
    elif dst.exists():
        print("  구글 캘린더: 켜짐 (전에 넣어 둔 연결 정보 사용)")
    else:
        print("  구글 캘린더: 꺼짐 — 구글 콘솔에서 받은 client_secret_….json 파일을")
        print(f"               '{ROOT.parent.name}' 폴더에 넣고 이 테스트 앱을 다시 켜세요.")
    print("  설치된 쿨브리핑이 켜져 있으면 이 창이 뜨지 않습니다 — 트레이에서 먼저 종료하세요.")

    os.chdir(ROOT)
    sys.argv = [str(ROOT / "main.py")] + sys.argv[1:]
    runpy.run_path(str(ROOT / "main.py"), run_name="__main__")


if __name__ == "__main__":
    main()
