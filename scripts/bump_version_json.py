# -*- coding: utf-8 -*-
"""release.ps1 전용 헬퍼 — version.json의 네 필드(version/sha256/
download_url/notes)를 전부 갱신한다. PowerShell의 ConvertTo-Json/
Set-Content는 한글을 \\uXXXX로 이스케이프하거나 UTF-8 BOM을 붙이는
경우가 있어(BOM이 붙으면 앱의 json.loads()가 깨진다), JSON 파일 자체는
항상 이 스크립트로만 고친다.

download_url이 깃허브 릴리스 첨부파일 주소로 바뀐 뒤로는(버전마다 파일명이
달라 매번 새 URL) notes와 마찬가지로 매 릴리스 실행 시점에 그대로
전달받는 값을 쓴다 — 예전처럼 "이전 값 보존"이 아니다.

사용법: python scripts/bump_version_json.py <version> <sha256> <download_url> <notes>"""
import json
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 5:
        print("usage: bump_version_json.py <version> <sha256> <download_url> <notes>", file=sys.stderr)
        sys.exit(1)

    version, sha256, download_url, notes = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    path = Path(__file__).resolve().parent.parent / "version.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"] = version
    data["sha256"] = sha256
    data["download_url"] = download_url
    data["notes"] = notes
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"version.json 갱신됨: version={version} sha256={sha256}")
    print(f"  download_url={download_url}")
    print(f"  notes={notes}")


if __name__ == "__main__":
    main()
