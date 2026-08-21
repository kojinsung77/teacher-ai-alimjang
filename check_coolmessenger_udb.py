# -*- coding: utf-8 -*-
"""
쿨메신저 .udb 파일 진단 스크립트
=================================

이 스크립트 하나만 단독으로 실행하면 됩니다. (별도 패키지 설치 필요 없음 — 파이썬 표준 라이브러리만 사용)

무엇을 하는가:
  1. 이 PC에서 쿨메신저가 메시지를 저장하는 .udb 파일을 자동으로 찾습니다.
  2. 찾은 파일이 SQLite 형식인지 확인합니다.
     - SQLite라면: 곧바로 파이썬으로 직접 읽어올 수 있다는 뜻입니다 (Plan A: 직접 파싱).
     - SQLite가 아니라면: 자체 포맷/암호화일 가능성이 높으므로, 쿨메신저가 공식 제공하는
       "메시지 다운로드" 버튼을 자동화하는 방식(Plan B)으로 전환해야 합니다.
  3. SQLite로 확인되면 테이블/컬럼 구조까지 함께 출력해 줍니다. 이 결과를
     app/adapters/coolmessenger_adapter.py 에 그대로 반영하면 됩니다.

실행 방법 (Windows, 쿨메신저 로그아웃 상태 권장):
  python check_coolmessenger_udb.py

주의:
  - 이 스크립트는 원본 파일을 절대 수정하지 않습니다. 항상 임시 폴더로 복사한 뒤
    복사본만 열어봅니다.
  - 쿨메신저가 실행 중이면 파일이 잠겨 있어 복사가 실패할 수 있습니다.
    그럴 경우 쿨메신저를 로그아웃/종료한 뒤 다시 실행해 주세요.
"""

import os
import sys
import glob
import shutil
import sqlite3
import tempfile
from pathlib import Path


# 버전/환경에 따라 다를 수 있는 후보 경로들을 최대한 넓게 훑는다.
def candidate_paths():
    home = Path.home()
    local_appdata = os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local"))
    appdata = os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))
    docs = home / "Documents"

    patterns = [
        str(Path(local_appdata) / "CoolMessenger" / "Memo" / "*.udb"),
        str(Path(local_appdata) / "CoolMessenger" / "**" / "*.udb"),
        str(Path(appdata) / "CoolMessenger" / "**" / "*.udb"),
        str(docs / "CoolMessenger Files" / "**" / "*.udb"),
        # 혹시 모를 다른 드라이브/구버전 대비 - 시간이 오래 걸릴 수 있어 기본은 끔
    ]
    found = []
    for p in patterns:
        found.extend(glob.glob(p, recursive=True))
    # 중복 제거, 존재하는 파일만
    uniq = sorted(set(f for f in found if os.path.isfile(f)))
    return uniq


def sniff_sqlite(path: str) -> bool:
    """SQLite 파일은 항상 앞 16바이트가 'SQLite format 3\\x00' 이다."""
    try:
        with open(path, "rb") as f:
            header = f.read(16)
        return header == b"SQLite format 3\x00"
    except Exception:
        return False


def describe_sqlite(copy_path: str):
    print("   → SQLite 헤더가 확인되었습니다. 테이블 구조를 읽어봅니다...")
    try:
        con = sqlite3.connect(copy_path)
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        tables = [r[0] for r in cur.fetchall()]
        if not tables:
            print("   ⚠ 테이블이 하나도 없습니다 (암호화되었거나 빈 파일일 수 있음).")
            return
        print(f"   ✓ 테이블 {len(tables)}개 발견: {tables}")
        for t in tables:
            try:
                cur.execute(f"PRAGMA table_info('{t}')")
                cols = [(r[1], r[2]) for r in cur.fetchall()]
                cur.execute(f"SELECT COUNT(*) FROM '{t}'")
                cnt = cur.fetchone()[0]
                print(f"     - {t}  (행 {cnt}개)")
                print(f"       컬럼: {cols}")
            except Exception as e:
                print(f"     - {t}: 컬럼 조회 실패 ({e})")
        con.close()
    except sqlite3.DatabaseError as e:
        print(f"   ⚠ SQLite 헤더는 맞지만 열 수 없습니다 (암호화 가능성 높음): {e}")


def first_bytes_hex(path: str, n: int = 32) -> str:
    with open(path, "rb") as f:
        return f.read(n).hex(" ")


def main():
    print("=" * 60)
    print(" 쿨메신저 .udb 파일 진단 스크립트")
    print("=" * 60)

    files = candidate_paths()
    if not files:
        print("\n❌ .udb 파일을 자동으로 찾지 못했습니다.")
        print("   - 쿨메신저를 한 번도 실행하지 않았거나,")
        print("   - 설치 경로가 표준 경로와 다를 수 있습니다.")
        print("   탐색기에서 직접 '*.udb'로 검색해서 경로를 찾은 뒤,")
        print("   이 스크립트의 candidate_paths() 함수에 그 경로를 추가해 다시 실행해 주세요.")
        return

    print(f"\n총 {len(files)}개의 .udb 파일을 찾았습니다.\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        for path in files:
            print("-" * 60)
            print(f"파일: {path}")
            try:
                size = os.path.getsize(path)
                print(f"크기: {size:,} bytes")
            except Exception as e:
                print(f"⚠ 파일 정보를 읽을 수 없습니다: {e}")
                continue

            copy_path = os.path.join(tmpdir, os.path.basename(path))
            try:
                shutil.copy2(path, copy_path)
            except Exception as e:
                print(f"⚠ 복사 실패 (쿨메신저가 실행 중이라 파일이 잠겨있을 수 있음): {e}")
                continue

            print(f"앞 32바이트(hex): {first_bytes_hex(copy_path)}")

            if sniff_sqlite(copy_path):
                print("✅ 판정: SQLite 형식입니다. (Plan A: 직접 파싱 가능)")
                describe_sqlite(copy_path)
            else:
                print("🚫 판정: SQLite 형식이 아닙니다.")
                print("   자체 바이너리 포맷이거나 암호화되어 있을 가능성이 높습니다.")
                print("   → Plan B(공식 '메시지 다운로드' 버튼 자동화)로 전환을 권장합니다.")

    print("\n" + "=" * 60)
    print("진단 완료. 위 결과를 그대로 복사해서 개발 담당자(또는 클로드 코드)에게 전달하면")
    print("app/adapters/coolmessenger_adapter.py 의 SCHEMA_HINT 부분을 바로 채울 수 있습니다.")
    print("=" * 60)


if __name__ == "__main__":
    main()
