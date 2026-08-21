# -*- coding: utf-8 -*-
"""release.ps1 전용 헬퍼 — version.json의 version/sha256만 갱신하고
notes/download_url은 그대로 둔다. PowerShell의 ConvertTo-Json/Set-Content는
한글을 \\uXXXX로 이스케이프하거나 UTF-8 BOM을 붙이는 경우가 있어(BOM이
붙으면 앱의 json.loads()가 깨진다), JSON 파일 자체는 항상 이 스크립트로만
고친다.

사용법: python scripts/bump_version_json.py <version> <sha256>"""
import json
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 3:
        print("usage: bump_version_json.py <version> <sha256>", file=sys.stderr)
        sys.exit(1)

    version, sha256 = sys.argv[1], sys.argv[2]
    path = Path(__file__).resolve().parent.parent / "version.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"] = version
    data["sha256"] = sha256
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"version.json 갱신됨: version={version} sha256={sha256}")


if __name__ == "__main__":
    main()
