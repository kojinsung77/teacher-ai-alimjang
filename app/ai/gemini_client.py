# -*- coding: utf-8 -*-
"""Gemini API 클라이언트. 교사 개인 API Key(BYOK)를 사용한다.
API Key는 절대 SQLite/설정파일에 평문 저장하지 않고 Windows 자격 증명
관리자(keyring)에만 저장한다."""

import json
import keyring
from keyring.errors import PasswordDeleteError

from .. import config, db


class GeminiKeyError(Exception):
    pass


def save_api_key(api_key: str):
    keyring.set_password(config.KEYRING_SERVICE, config.KEYRING_USERNAME, api_key)


def load_api_key() -> str | None:
    return keyring.get_password(config.KEYRING_SERVICE, config.KEYRING_USERNAME)


def delete_api_key():
    try:
        keyring.delete_password(config.KEYRING_SERVICE, config.KEYRING_USERNAME)
    except PasswordDeleteError:
        pass


def current_model() -> str:
    """설정 화면에서 사용자가 고른 모델. 저장된 값이 없으면 기본값(config.GEMINI_MODEL)."""
    return db.get_setting("gemini_model", config.GEMINI_MODEL)


def set_current_model(model: str):
    db.set_setting("gemini_model", model)


def test_connection(api_key: str | None = None, model: str | None = None) -> tuple[bool, str]:
    """연결 테스트. 설정 화면의 [연결 테스트] 버튼에서 사용."""
    key = api_key or load_api_key()
    if not key:
        return False, "API Key가 입력되지 않았습니다."
    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        gen_model = genai.GenerativeModel(model or current_model())
        resp = gen_model.generate_content("안녕하세요. 연결 테스트입니다. '정상'이라고만 답하세요.")
        if resp and resp.text:
            return True, "정상적으로 연결되었습니다."
        return False, "응답이 비어 있습니다. Key를 다시 확인해 주세요."
    except Exception as e:
        return False, f"연결 실패: {e}"


def classify_batch(system_prompt: str, user_prompt: str, images: list | None = None) -> list:
    """배치 단위로 Gemini에 분류 요청. 실패 시 예외를 그대로 올린다
    (호출부인 classifier.py에서 배치 단위 재시도/스킵 처리).

    images: [(message_id, image_bytes, mime_type), ...] — 캡처 이미지 첨부가
    있는 메시지의 실제 이미지 바이트(app/core/task_manager.py가 채워서
    넘긴다). 어느 이미지가 어느 메시지 것인지 모델이 헷갈리지 않도록,
    이미지 앞에 "[메시지 id=... 첨부 이미지]" 텍스트 라벨을 붙여서 함께
    보낸다. 비어 있으면 기존과 완전히 동일하게 텍스트만 보낸다."""
    key = load_api_key()
    if not key:
        raise GeminiKeyError("Gemini API Key가 설정되어 있지 않습니다. 설정 화면에서 입력해 주세요.")

    import google.generativeai as genai
    genai.configure(api_key=key)
    model = genai.GenerativeModel(
        current_model(),
        system_instruction=system_prompt,
        generation_config={"response_mime_type": "application/json"},
    )

    contents = [user_prompt]
    for message_id, image_bytes, mime_type in (images or []):
        contents.append(f"[메시지 id={message_id} 첨부 이미지]")
        contents.append({"mime_type": mime_type, "data": image_bytes})

    resp = model.generate_content(contents)
    text = resp.text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 모델이 코드블록으로 감싸서 응답하는 경우 대비
        cleaned = text.strip("`").removeprefix("json").strip()
        data = json.loads(cleaned)

    if isinstance(data, dict):
        data = [data]
    return data
