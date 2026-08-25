# -*- coding: utf-8 -*-
"""학사일정 자동 채움 — NEIS(나이스 교육정보 개방 포털, open.neis.go.kr)의
'학교급별 학사일정'(SchoolSchedule) API로 학교의 방학·재량휴업일·수요/금요
대체일 같은 휴업일뿐 아니라 모의고사·리더십캠프 같은 등교일 행사까지 연 1회
가져와 holidays 테이블에 source='api'로 채워 넣는다.

이전에는 공공데이터포털(data.go.kr)의 한국천문연구원 '특일 정보' API로
전국 공통 공휴일만 채워 넣었는데, 그건 방학·재량휴업일·토요휴업일처럼
학교마다 다른 자체 일정은 전혀 알지 못한다는 한계가 있었다. NEIS 학사일정
API는 시도교육청코드+학교코드만 넣으면 그 학교의 휴업일과 개별 행사를
통째로 내려줘서 이 한계를 없앤다.

인증키는 Gemini API 키(app/ai/gemini_client.py)와 동일한 방식으로 이 PC의
Windows 자격 증명 관리자(keyring)에만 저장한다 — 이 저장소가 GitHub에
공개돼 있어 app/config.py에 평문으로 넣으면 그대로 노출되기 때문이다.
시도교육청코드/학교코드는 API 키와 달리 민감하지 않으므로 settings
테이블(key-value)에 평문으로 둔다 — 다른 학교 선생님도 이 앱을 쓸 수
있으므로 기본값(전주중앙여자고등학교)만 두고 설정 화면에서 자기 학교
코드로 바꿀 수 있게 한다.

이 모듈이 채워 넣는 각 행의 is_dayoff는 NEIS의 SBTR_DD_SC_NM(수업공제일
구분명)을 기준으로 정한다 — "해당없음"이면 등교하는 날(행사만 있음,
is_dayoff=0), 그 외(실측으로 확인된 값은 "공휴일"/"휴업일" 두 가지뿐이지만
화이트리스트가 아니라 "해당없음일 때만 등교"로 판정해서 문서에 없는 새
구분값이 나와도 안전하게 "쉬는 날" 쪽으로 보수적으로 처리한다)는 등교하지
않는 날(is_dayoff=1)로 저장한다. 이 값은 [일정] 화면 표시뿐 아니라
db.is_holiday()가 자동 알림장 생성을 건너뛸지 판단하는 기준으로도 그대로
쓰인다 — 모의고사처럼 등교하는 행사일에 자동 알림장을 건너뛰면 안 되므로
이 구분이 가장 중요하다.

실패(인증키 미설정, 네트워크 없음, API 오류 등)는 전부 조용히 무시한다 —
holidays_synced_year를 갱신하지 않으므로 다음에 앱을 켤 때 다시 시도된다."""

import json
import urllib.request
from datetime import date
from urllib.parse import urlencode

import keyring

from .. import config, db

_KEYRING_USERNAME = "neis_api_key"
_API_URL = "https://open.neis.go.kr/hub/SchoolSchedule"
_SETTING_KEY_SYNCED_YEAR = "holidays_synced_year"

_SETTING_KEY_ATPT_CODE = "neis_atpt_code"
_SETTING_KEY_SCHOOL_CODE = "neis_school_code"

# 전주중앙여자고등학교(전북특별자치도교육청) — open.neis.go.kr의
# "학교기본정보"(schoolInfo) API를 SCHUL_NM=전주중앙여자고등학교로 직접
# 조회해서 확인한 값이다(2026-08-25 확인:
# ATPT_OFCDC_SC_CODE=P10 "전북특별자치도교육청",
# SD_SCHUL_CODE=8321103 "전주중앙여자고등학교"). 다른 학교 선생님은
# 설정 화면에서 자기 학교 코드로 바꿔 쓸 수 있도록 기본값으로만 둔다.
_DEFAULT_ATPT_CODE = "P10"
_DEFAULT_SCHOOL_CODE = "8321103"

# NEIS SBTR_DD_SC_NM(수업공제일구분명)이 이 값일 때만 "등교는 하지만
# 행사가 있는 날"이다. 그 외 값은 전부 "등교하지 않는 날"로 취급한다.
_ATTEND_SBTR_VALUE = "해당없음"


def save_api_key(key: str):
    keyring.set_password(config.KEYRING_SERVICE, _KEYRING_USERNAME, key)


def load_api_key() -> str | None:
    return keyring.get_password(config.KEYRING_SERVICE, _KEYRING_USERNAME)


def get_atpt_code() -> str:
    return db.get_setting(_SETTING_KEY_ATPT_CODE, _DEFAULT_ATPT_CODE)


def get_school_code() -> str:
    return db.get_setting(_SETTING_KEY_SCHOOL_CODE, _DEFAULT_SCHOOL_CODE)


def set_school(atpt_code: str, school_code: str):
    """학교 코드 설정을 저장한다. 코드가 바뀌면 이전 학교 기준으로 이미
    채워진 학사일정이 남아있으면 안 되므로, 다음 동기화 때(또는 앱을
    다시 켤 때) 새 학교 기준으로 처음부터 다시 받아오도록
    holidays_synced_year를 비운다."""
    db.set_setting(_SETTING_KEY_ATPT_CODE, atpt_code)
    db.set_setting(_SETTING_KEY_SCHOOL_CODE, school_code)
    db.set_setting(_SETTING_KEY_SYNCED_YEAR, "")


def _fetch_schedule(year: int, api_key: str, atpt_code: str, school_code: str) -> list:
    """해당 연도(1/1~12/31) 학사일정 전체를 NEIS에서 받아온다."""
    query = urlencode({
        "KEY": api_key,
        "Type": "json",
        "ATPT_OFCDC_SC_CODE": atpt_code,
        "SD_SCHUL_CODE": school_code,
        "AA_FROM_YMD": f"{year}0101",
        "AA_TO_YMD": f"{year}1231",
        "pIndex": 1,
        "pSize": 1000,
    })
    url = f"{_API_URL}?{query}"

    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    schedule = data.get("SchoolSchedule")
    if not schedule:
        # 그 해에 등록된 학사일정이 아예 없거나(RESULT.CODE가
        # "데이터 없음"인 경우 SchoolSchedule 키 자체가 없다), 학교
        # 코드가 잘못됐을 수 있다 — 어느 쪽이든 빈 목록으로 조용히
        # 취급한다.
        return []

    header = schedule[0].get("head", [{}])
    result = header[1].get("RESULT", {}) if len(header) > 1 else {}
    if result.get("CODE") not in ("INFO-000", None):
        raise RuntimeError(f"NEIS 학사일정 API 오류: {result.get('MESSAGE')}")

    if len(schedule) < 2:
        return []
    return schedule[1].get("row", [])


def sync_if_needed():
    """앱 시작 시 호출. 올해 이미 받아왔으면(holidays_synced_year가 올해와
    일치) 아무것도 하지 않는다. 어떤 이유로든 실패하면 예외를 밖으로
    내보내지 않고 조용히 넘어간다."""
    year = date.today().year
    if db.get_setting(_SETTING_KEY_SYNCED_YEAR) == str(year):
        return
    try:
        api_key = load_api_key()
        if not api_key:
            return
        atpt_code = get_atpt_code()
        school_code = get_school_code()
        rows = _fetch_schedule(year, api_key, atpt_code, school_code)

        # 하루에 행사가 여러 건 겹칠 수 있어(예: "선택과목설명회"+"진로
        # 탐색의 날") 날짜별로 먼저 모은다. is_dayoff는 그날의 어느 한
        # 건이라도 "해당없음"이 아니면 True로 — 보수적으로 "쉬는 날"
        # 쪽에 둔다.
        by_date: dict[str, dict] = {}
        for row in rows:
            aa_ymd = str(row.get("AA_YMD", ""))
            if len(aa_ymd) != 8:
                continue
            date_str = f"{aa_ymd[0:4]}-{aa_ymd[4:6]}-{aa_ymd[6:8]}"
            entry = by_date.setdefault(date_str, {"names": [], "is_dayoff": False})
            name = (row.get("EVENT_NM") or "").strip()
            if name and name not in entry["names"]:
                entry["names"].append(name)
            if row.get("SBTR_DD_SC_NM") != _ATTEND_SBTR_VALUE:
                entry["is_dayoff"] = True

        for date_str, entry in by_date.items():
            db.add_holiday(
                date_str,
                source="api",
                name=" · ".join(entry["names"]) or None,
                is_dayoff=entry["is_dayoff"],
            )
        db.set_setting(_SETTING_KEY_SYNCED_YEAR, str(year))
    except Exception:
        pass
