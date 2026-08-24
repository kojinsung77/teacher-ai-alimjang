# -*- coding: utf-8 -*-
"""국가 공휴일 자동 채움 — 공공데이터포털(data.go.kr)의 한국천문연구원
'특일 정보' API(SpcdeInfoService/getRestDeInfo)로 국경일/공휴일을 연 1회만
가져와 holidays 테이블에 source='api'로 채워 넣는다.

서비스키는 Gemini API 키(app/ai/gemini_client.py)와 동일한 방식으로 이
PC의 Windows 자격 증명 관리자(keyring)에만 저장한다 — 이 저장소가
GitHub에 공개돼 있어 app/config.py에 평문으로 넣으면 그대로 노출되기
때문이다.

이 모듈이 하는 자동 채움은 "이 날엔 자동 알림장을 만들지 않는다"는
용도로만 쓰인다 — 방학·재량휴업일 같은 학교 자체 휴일은 이 API가 절대
알 수 없고, 그건 [일정] 화면의 수동 지정(app/ui/calendar_view.py)으로
보완한다.

실패(서비스키 미설정, 네트워크 없음, API 오류 등)는 전부 조용히
무시한다 — holidays_synced_year를 갱신하지 않으므로 다음에 앱을 켤 때
다시 시도된다."""

import json
import urllib.error
import urllib.request
from datetime import date
from urllib.parse import quote, unquote, urlencode

import keyring

from .. import config, db

_KEYRING_USERNAME = "data_go_kr_service_key"
_API_URL = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"
_SETTING_KEY_SYNCED_YEAR = "holidays_synced_year"


def save_service_key(key: str):
    keyring.set_password(config.KEYRING_SERVICE, _KEYRING_USERNAME, key)


def load_service_key() -> str | None:
    return keyring.get_password(config.KEYRING_SERVICE, _KEYRING_USERNAME)


def _fetch_holidays(year: int, service_key: str) -> list:
    """해당 연도의 국경일/공휴일 목록을 API에서 받아온다.

    공공데이터포털은 키를 '인코딩'/'디코딩' 두 가지 형태로 발급하는데,
    사용자가 어느 쪽을 붙여넣었는지 알 수 없다. unquote()로 일단 원문으로
    되돌린 뒤 quote()로 다시 인코딩해서, 어느 쪽을 넣어도 정확히 한 번만
    인코딩되게 한다(이중 인코딩되면 인증에 실패한다)."""
    key_encoded = quote(unquote(service_key), safe="")
    query = urlencode({"solYear": year, "numOfRows": 100, "pageNo": 1, "_type": "json"})
    url = f"{_API_URL}?ServiceKey={key_encoded}&{query}"

    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    header = data.get("response", {}).get("header", {})
    if header.get("resultCode") != "00":
        raise RuntimeError(f"특일 정보 API 오류: {header.get('resultMsg')}")

    body = data.get("response", {}).get("body", {})
    items = body.get("items") or ""
    if not items:
        return []
    item = items.get("item", [])
    if isinstance(item, dict):
        item = [item]
    return item


def sync_if_needed():
    """앱 시작 시 호출. 올해 이미 받아왔으면(holidays_synced_year가 올해와
    일치) 아무것도 하지 않는다. 어떤 이유로든 실패하면 예외를 밖으로
    내보내지 않고 조용히 넘어간다."""
    year = date.today().year
    if db.get_setting(_SETTING_KEY_SYNCED_YEAR) == str(year):
        return
    try:
        service_key = load_service_key()
        if not service_key:
            return
        items = _fetch_holidays(year, service_key)
        for it in items:
            if it.get("isHoliday") != "Y":
                continue
            locdate = str(it.get("locdate", ""))
            if len(locdate) != 8:
                continue
            date_str = f"{locdate[0:4]}-{locdate[4:6]}-{locdate[6:8]}"
            db.add_holiday(date_str, source="api", name=it.get("dateName"))
        db.set_setting(_SETTING_KEY_SYNCED_YEAR, str(year))
    except Exception:
        pass
