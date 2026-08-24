# -*- coding: utf-8 -*-
"""새 버전 확인/다운로드/검증 — version.json을 가져와 현재 APP_VERSION과
비교하고, 새 버전이 있으면 배경에서 조용히 받아 SHA256으로 무결성을
검증한다. Qt에 의존하지 않는 순수 로직만 담고, 배너/스레드 등 UI·
스케줄링은 app/ui 쪽이 맡는다.

안전 원칙: 해시가 일치하는 파일만 "설치 준비 완료"로 취급한다 — 검증
전 파일로는 설치를 진행하지 않는다. 실행 자체(조용한 설치 실행)는
app/ui/main_window.py가 맡고, 사람이 직접 받을 수 있는 경로
(DOWNLOAD_PAGE_URL)도 항상 병행해서 남겨 둔다(자동 설치가 실패했을 때의
대비책)."""

import hashlib
import json
import shutil
import urllib.request
from datetime import datetime
from pathlib import Path

from .. import config, db

_SETTING_KEY_IGNORED_VERSION = "update_ignored_version"


def _parse_version(version: str) -> tuple:
    """"1.10.2" -> (1, 10, 2). 파싱할 수 없는 조각은 0으로 취급해서
    버전 문자열이 살짝 이상해도 비교 자체는 죽지 않게 한다."""
    parts = []
    for piece in str(version).strip().split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def is_newer(remote_version: str, local_version: str) -> bool:
    return _parse_version(remote_version) > _parse_version(local_version)


def log_update_event(reason: str):
    """업데이트 확인/다운로드/설치 흐름에서 생긴 일을 update_check.log에
    한 줄 남긴다(이 함수 자체 이름은 "확인" 실패용으로 시작했지만,
    main_window.py의 조용한 설치 실행 단계에서도 그대로 재사용한다 —
    둘 다 "사용자 화면엔 안 띄우고 로그만 남기는" 같은 원칙이라 로그
    파일을 굳이 나눌 이유가 없다). 사용자 화면엔 아무것도 안 띄우는
    조용한 실패 원칙은 그대로 유지하되(팝업 없음), 나중에 "왜 안 됐는지"
    진단할 방법이 전혀 없었던 문제를 해결하기 위한 것 — 로그 남기기
    자체가 실패해도(디스크 꽉 참 등) 절대 앱을 죽이면 안 되므로 여기서도
    예외를 전부 삼킨다."""
    try:
        log_path = config.app_data_dir() / "update_check.log"
        timestamp = datetime.now().isoformat(timespec="seconds")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {reason}\n")
    except Exception:
        pass


def fetch_latest_version_info(timeout: float = 4.0) -> dict | None:
    """UPDATE_CHECK_URL에서 version.json을 가져와 dict로 반환한다.
    URL이 비어 있거나, 네트워크 오류·타임아웃·JSON 파싱 실패 등 무슨
    이유로든 실패하면 조용히 None을 반환한다 — 호출부(앱 시작 경로)가
    이 실패로 절대 죽지 않아야 하기 때문이다. 실패 이유는 화면에는 안
    띄우고 update_check.log에만 남긴다(진단용)."""
    url = config.UPDATE_CHECK_URL
    if not url:
        log_update_event("UPDATE_CHECK_URL이 비어 있음")
        return None
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict) or "version" not in data:
            log_update_event(f"version.json 형식이 이상함: {raw[:200]!r}")
            return None
        return data
    except Exception as e:
        log_update_event(f"{type(e).__name__}: {e}")
        return None


def check_for_update() -> dict | None:
    """새 버전이 있으면 {"version": "...", "notes": "..."}를 반환하고,
    없거나 확인할 수 없으면 None을 반환한다."""
    info = fetch_latest_version_info()
    if not info:
        return None
    if is_newer(info["version"], config.APP_VERSION):
        return info
    return None


def is_version_ignored(version: str) -> bool:
    """이 버전(또는 그 이하)을 사용자가 이미 [나중에]로 넘긴 적이
    있으면 True. 더 새로운 버전이 나오면 다시 알려줘야 하므로 False."""
    ignored = db.get_setting(_SETTING_KEY_IGNORED_VERSION, "")
    if not ignored:
        return False
    return _parse_version(version) <= _parse_version(ignored)


def set_ignored_version(version: str):
    db.set_setting(_SETTING_KEY_IGNORED_VERSION, version)


def updates_dir() -> Path:
    """다운로드해둔 설치 파일을 저장하는 위치
    (%LOCALAPPDATA%\\TeacherAlimjang\\updates\\)."""
    d = config.app_data_dir() / "updates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download_and_verify_update(info: dict, timeout: float = 30.0) -> Path | None:
    """info(version.json에서 온 dict)의 download_url을 받아 updates_dir()에
    저장하고, sha256 필드와 실제 받은 파일의 해시가 일치할 때만 그 경로를
    반환한다. download_url/sha256이 없거나, 다운로드·해시 검증 중 무슨
    이유로든 실패하면 조용히 None을 반환하고 받다 만 파일은 지운다 —
    호출부가 실패 원인을 사용자에게 알릴 필요가 전혀 없도록(팝업 없는
    조용한 실패 원칙) 여기서 전부 흡수한다."""
    download_url = (info or {}).get("download_url", "")
    expected_sha256 = ((info or {}).get("sha256") or "").strip().lower()
    if not download_url or not expected_sha256:
        return None

    updates_folder = updates_dir()
    # 이전에 받다 만 파일이 남아있으면 지우고 새로 받는다 — 여러 버전의
    # 부분 다운로드가 쌓이는 것을 막는다.
    for old in updates_folder.glob("*.exe"):
        try:
            old.unlink()
        except OSError:
            pass

    version = (info or {}).get("version", "update")
    dest = updates_folder / f"TeacherAlimjang_Setup_v{version}.exe"

    try:
        with urllib.request.urlopen(download_url, timeout=timeout) as resp, open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)

        actual_sha256 = _sha256_of_file(dest)
        if actual_sha256.lower() != expected_sha256:
            dest.unlink(missing_ok=True)
            return None
        return dest
    except Exception:
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        return None
