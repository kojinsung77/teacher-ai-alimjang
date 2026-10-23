# -*- coding: utf-8 -*-
"""버전별 테스트 폴더(v1.16.0 등)에서 그 버전을 '따로' 실행한다 — 테스트_실행.bat이 부른다.

설치된 쿨브리핑(선생님들이 쓰는 그 버전)의 데이터는 건드리지 않는다:
- 데이터(DB·설정)는 %LOCALAPPDATA%\\CoolBriefingTest\\<폴더 이름>\\TeacherAlimjang 에만 생긴다
  (OneDrive 바탕화면 폴더 안에 DB를 두면 동기화가 열린 DB 파일을 건드릴 수 있어 밖에 둔다).
- 처음 설정 창과 '컴퓨터 켤 때 자동 시작' 등록을 건너뛴다(설치된 앱의 자동 시작을
  이 테스트 폴더로 바꿔 버리지 않도록).
- 데모 모드(가짜 메시지)로 시작한다. Gemini 키는 Windows 자격 증명에서 그대로 쓴다.
- 저장소에 올리지 않는 값(구글 client_secret_….json, NEIS 인증키 neis_api_key.txt)을 이 버전
  폴더나 그 위 '쿨메시저 알림장' 폴더(또는 그 안의 secrets 폴더)에서 찾아, 배포용 빌드와 같은
  방식(scripts/embed_secrets.py)으로 이 폴더의 app/core/_embedded_secrets.py에 섞어 넣는다.

설치된 쿨브리핑이 켜져 있으면 테스트 버전이 뜨지 않는다(한 번에 하나만 실행) —
작업 표시줄 트레이의 쿨브리핑 → 종료 후 실행할 것."""

import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_REAL_LOCAL = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
TEST_BASE = Path(_REAL_LOCAL) / "CoolBriefingTest" / ROOT.name


def embed_secrets():
    """(구글 연결 정보 찾음?, NEIS 키 찾음?) — 값은 찍지 않는다."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("embed_secrets", ROOT / "scripts" / "embed_secrets.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    folders = [ROOT / "secrets", ROOT, ROOT.parent, ROOT.parent / "secrets"]
    g_path, g_val = mod.find_google(folders)
    n_path, n_val = mod.find_neis(folders)
    mod.main([str(f) for f in folders])
    return g_path, n_path


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
    print(f"[TEST] 쿨브리핑 v{config.APP_VERSION} 테스트 실행")
    print(f"  데이터 폴더: {data_dir}")
    g_path, n_path = embed_secrets()
    if g_path is None and not (data_dir / "google_client.json").exists():
        print("  → 구글 캘린더는 꺼져 있습니다: client_secret_….json 파일을")
        print(f"     '{ROOT.parent.name}' 폴더에 넣고 이 테스트 앱을 다시 켜세요.")
    if n_path is None:
        print(f"  → 학사일정(NEIS)을 받으려면 '{ROOT.parent.name}' 폴더에 neis_api_key.txt(인증키 한 줄)를 넣으세요.")
    print("  설치된 쿨브리핑이 켜져 있으면 이 창이 뜨지 않습니다 — 트레이에서 먼저 종료하세요.")

    os.chdir(ROOT)
    sys.argv = [str(ROOT / "main.py")] + sys.argv[1:]
    runpy.run_path(str(ROOT / "main.py"), run_name="__main__")


if __name__ == "__main__":
    main()
