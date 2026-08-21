# -*- coding: utf-8 -*-
"""앱 전역 설정 및 경로."""

import os
import sys
from pathlib import Path

APP_NAME = "교사업무 AI 알림장"
APP_DIR_NAME = "TeacherAlimjang"

# 설치 프로그램(installer/setup.iss의 MyAppVersion)과 항상 맞춰서 올린다.
APP_VERSION = "1.2.0"

# [업데이트 확인]의 [다운로드 페이지 열기] 버튼이 여는 주소 — 사람이 직접
# 파일을 받는 페이지다. 자동으로 다운로드·설치하지 않는 게 이 프로젝트
# 원칙이라, 실제 설치 파일 자체는 여기서 받지 않는다.
DOWNLOAD_PAGE_URL = "https://drive.google.com/drive/folders/1ZbcXl5IDJ9UF2gzGH5t6Sgl625GxM4YU?usp=drive_link"

# 최신 버전 정보(version.json)를 가져올 주소. 구글 드라이브 개별 파일
# 공유 링크 형태 그대로 넣으면 app/core/update_check.py의
# drive_share_link_to_direct()가 다이렉트 다운로드 URL로 알아서 바꿔서
# 쓴다. version.json은 release.ps1이 매번 "같은 파일"에 덮어쓰므로(새
# 리비전으로 저장, 파일 ID·공유 링크는 그대로 유지) 이 URL은 버전이
# 올라가도 다시 바꿀 필요가 없다.
UPDATE_CHECK_URL = "https://drive.google.com/file/d/1PeLDCLP0OlMQZLI0Vfy2DxuOsZZdInB5/view?usp=sharing"

# Windows 자동 시작(레지스트리 Run 키) 관련 상수. 값 이름은 keyring
# 서비스명과 동일하게 APP_DIR_NAME을 재사용해 식별자를 하나로 통일한다.
AUTOSTART_VALUE_NAME = APP_DIR_NAME
AUTOSTART_ARG = "--autostart"

def app_data_dir() -> Path:
    """설정/DB 저장 위치: %LOCALAPPDATA%\\TeacherAlimjang (Windows) 또는 홈 폴더 하위."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    d = Path(base) / APP_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d

def db_path() -> Path:
    return app_data_dir() / "alimjang.sqlite3"

def roster_csv_path() -> Path:
    """학생/교직원 명단 파일 (개인정보 마스킹용). 사용자가 직접 채워 넣는 파일."""
    return app_data_dir() / "roster.csv"


def icon_path() -> Path:
    """공식 앱 아이콘(.ico) 경로 — 창/트레이 아이콘에 공통으로 쓴다.
    PyInstaller onefile로 빌드되면 리소스가 sys._MEIPASS 임시 폴더에
    풀리므로, 개발 중(소스 실행)과 빌드 후(exe 실행) 경로가 다르다."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "app" / "ui" / "assets" / "app_icon.ico"


def checkmark_icon_path() -> Path:
    """체크박스 체크 표시(흰색 ✓ PNG) 경로. icon_path()와 동일한 이유로
    PyInstaller onefile 빌드 시 _MEIPASS 기준 경로를 쓴다."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "app" / "ui" / "assets" / "checkmark.png"

KEYRING_SERVICE = "TeacherAlimjang"
KEYRING_USERNAME = "gemini_api_key"

# Gemini 모델명. "gemini-2.0-flash"는 2026-06-01 지원 종료로 확인되어 교체함.
# "gemini-3.1-flash-lite"가 정식(Stable) 모델명임 — 이름이 비슷한
# "gemini-3.1-flash-lite-preview"는 이미 서비스 종료된 별개 모델이니 혼동 주의.
# 저비용/빠른 분류 작업이라 flash-lite 계열이 기본값.
GEMINI_MODEL = "gemini-3.1-flash-lite"

# 설정 화면의 모델 선택 드롭다운에 노출할 후보 목록. (value, 표시라벨)
GEMINI_MODEL_OPTIONS = [
    ("gemini-3.1-flash-lite", "gemini-3.1-flash-lite (기본, 가장 저렴·빠름)"),
    ("gemini-3.5-flash-lite", "gemini-3.5-flash-lite (더 최신 flash-lite)"),
    ("gemini-3.1-pro-preview", "gemini-3.1-pro-preview (더 정확함, 비용/속도 트레이드오프)"),
]

# 1회 배치당 분석할 메시지 개수
BATCH_SIZE = 15

# Gemini API 키 발급 페이지 (설정 화면의 안내 박스에서 사용)
GOOGLE_AI_STUDIO_KEY_URL = "https://aistudio.google.com/apikey"
