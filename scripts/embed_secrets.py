# -*- coding: utf-8 -*-
"""저장소에 올리지 않는 값(NEIS 인증키, 구글 클라이언트 JSON)을 찾아
app/core/_embedded_secrets.py(커밋 안 함)로 섞어 넣는다. 값 자체는 화면에 찍지 않는다.

    python scripts/embed_secrets.py [--require] 폴더 [폴더 ...]

폴더들을 앞에서부터 찾아 먼저 나온 것을 쓴다.
- 구글: google_client.json 또는 client_secret_*.json ('installed' 데스크톱 클라이언트)
- NEIS: neis_api_key.txt 의 첫 줄
--require: 둘 중 하나라도 없으면 종료 코드 2 (build.ps1이 배포용 빌드를 멈춘다)"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.core import secrets_store  # noqa: E402

OUT = ROOT / "app" / "core" / "_embedded_secrets.py"


def find_google(folders):
    for folder in folders:
        for path in [folder / "google_client.json"] + sorted(folder.glob("client_secret_*.json")):
            try:
                raw = path.read_text(encoding="utf-8")
                data = json.loads(raw)
            except (OSError, ValueError):
                continue
            info = data.get("installed") or data.get("web") or data
            if isinstance(info, dict) and info.get("client_id"):
                slim = {"installed": {"client_id": info["client_id"],
                                      "client_secret": info.get("client_secret", "")}}
                return path, json.dumps(slim)
    return None, ""


def find_neis(folders):
    for folder in folders:
        path = folder / "neis_api_key.txt"
        try:
            lines = [l.strip() for l in path.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
        except OSError:
            continue
        if lines and re.fullmatch(r"[0-9A-Za-z]{16,64}", lines[0]):
            return path, lines[0]
    return None, ""


def main(argv):
    require = "--require" in argv
    folders = [Path(a) for a in argv if a != "--require"] or [ROOT / "secrets"]
    g_path, g_val = find_google(folders)
    n_path, n_val = find_neis(folders)
    data = {}
    if g_val:
        data["google_client"] = secrets_store.encode(g_val)
    if n_val:
        data["neis_api_key"] = secrets_store.encode(n_val)
    lines = ["# 자동 생성 파일 — 커밋하지 않는다(.gitignore). scripts/embed_secrets.py가 만든다.",
             "DATA = {"] + [f"    {k!r}: {v!r}," for k, v in data.items()] + ["}", ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"  구글 연결 정보: {'있음 (' + g_path.name + ')' if g_path else '없음'}")
    print(f"  NEIS 인증키:   {'있음 (' + n_path.name + ')' if n_path else '없음'}")
    if require and not (g_path and n_path):
        print("  ※ 배포용 빌드에는 둘 다 필요합니다. secrets 폴더를 확인하세요.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
