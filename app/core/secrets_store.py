# -*- coding: utf-8 -*-
"""저장소(GitHub)에 올리지 않는 값을 꺼내 주는 곳 — NEIS 인증키, 구글 OAuth 클라이언트.

v1.16.3부터 이 값들은 코드에 적지 않는다.
- 원본: 빌드하는 PC의 `secrets\\` 폴더(저장소 루트, .gitignore로 커밋 안 됨)
    secrets\\neis_api_key.txt          NEIS 인증키 한 줄
    secrets\\client_secret_….json      구글 콘솔에서 받은 그대로 (google_client.json 이름도 됨)
- 설치 파일을 만들 때 build.ps1 → scripts/embed_secrets.py가 이 값들을 섞어서(난독화)
  app/core/_embedded_secrets.py(역시 커밋 안 됨)로 써 넣고, PyInstaller가 그 파일을 exe에 묶는다.
- 버전별 테스트 폴더에서는 테스트_실행.bat이 같은 스크립트로 그 폴더용 파일을 만든다.

주의(정직하게): 설치 파일 안에 들어가는 값은 프로그램이 스스로 풀어 써야 하므로 완전한
암호화는 불가능하다. 여기서 하는 일은 ① 공개 저장소에 아예 안 올라가게 하고 ② exe 안에서
평문 문자열로 바로 보이지 않게 하는 것까지다. 그래서 구글 클라이언트는 '내부' 앱(학교 계정만
로그인)으로, NEIS 키는 조회 전용 키로 위험을 작게 유지한다."""

import base64
import json

_MASK = b"CoolBriefing/secrets/v1"


def encode(text: str) -> str:
    raw = text.encode("utf-8")
    mixed = bytes(b ^ _MASK[i % len(_MASK)] for i, b in enumerate(raw))
    return base64.b64encode(mixed[::-1]).decode("ascii")


def decode(blob: str) -> str:
    mixed = base64.b64decode(blob.encode("ascii"))[::-1]
    return bytes(b ^ _MASK[i % len(_MASK)] for i, b in enumerate(mixed)).decode("utf-8")


def _data() -> dict:
    try:
        from . import _embedded_secrets
    except ImportError:
        return {}
    return getattr(_embedded_secrets, "DATA", {}) or {}


def get(name: str) -> str:
    blob = _data().get(name)
    if not blob:
        return ""
    try:
        return decode(blob)
    except Exception:
        return ""


def neis_api_key() -> str:
    return get("neis_api_key").strip()


def google_client():
    """{'client_id','client_secret'} 또는 None."""
    raw = get("google_client")
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    info = data.get("installed") or data.get("web") or data
    if not isinstance(info, dict) or not info.get("client_id"):
        return None
    return {"client_id": info["client_id"], "client_secret": info.get("client_secret", "")}
