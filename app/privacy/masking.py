# -*- coding: utf-8 -*-
"""개인정보 로컬 마스킹.

Gemini로 원문을 보내기 전, 이 모듈을 반드시 거친다.
1) 정규식: 전화번호/이메일/주민등록번호형/계좌번호 같이 '패턴'이 뚜렷한 것
2) 명단 매칭: 학생/교직원 '이름'은 정규식으로 안정적으로 잡기 어렵기 때문에,
   학교가 이미 가진 명단(roster.csv)에 대해 정확히 일치하는 토큰만 치환한다.
   (일반 한국어 이름 NER보다 오탐/누락이 훨씬 적다)
"""

import csv
import re
from typing import List, Tuple

from .. import config

# ---------- 1) 정규식 기반 (구조적 패턴) ----------

_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("[전화번호]", re.compile(r"01[016789]-?\d{3,4}-?\d{4}")),
    ("[전화번호]", re.compile(r"0\d{1,2}-\d{3,4}-\d{4}")),  # 일반전화
    ("[이메일]", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("[주민등록번호]", re.compile(r"\d{6}-?[1-4]\d{6}")),
    ("[계좌번호]", re.compile(r"\d{2,6}-?\d{2,6}-?\d{2,10}")),
]


def _mask_patterns(text: str) -> str:
    for placeholder, pattern in _PATTERNS:
        text = pattern.sub(placeholder, text)
    return text


# ---------- 2) 명단 기반 이름 매칭 ----------

_JOSA = ["은", "는", "이", "가", "을", "를", "의", "에게", "께서", "님"]


def _load_roster() -> List[Tuple[str, str]]:
    """roster.csv의 (name, type) 목록을 반환한다. type은 'student'|'teacher' 등
    roster_sample.csv 형식을 따르며, 마스킹 라벨([학생N] vs [관계자N])을 결정한다."""
    path = config.roster_csv_path()
    if not path.exists():
        return []
    entries = {}
    # utf-8-sig: BOM이 있어도(엑셀에서 저장한 CSV는 보통 BOM이 붙는다) 없어도
    # 둘 다 올바르게 읽는다. 그냥 "utf-8"로 열면 BOM이 첫 헤더 앞에 그대로
    # 남아 "name"이 "﻿name"이 되어 매칭이 조용히 실패한다.
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("name") or row.get("이름") or "").strip()
            rtype = (row.get("type") or row.get("구분") or "").strip().lower()
            if name:
                entries[name] = rtype
    # 긴 이름부터 치환해야 부분 겹침 오류가 줄어든다
    return sorted(entries.items(), key=lambda kv: len(kv[0]), reverse=True)


def _mask_roster_names(text: str, roster: List[Tuple[str, str]]) -> str:
    for idx, (name, rtype) in enumerate(roster):
        if name and name in text:
            label = f"[학생{idx+1}]" if rtype == "student" else f"[관계자{idx+1}]"
            # 이름 뒤에 조사가 붙어도 자연스럽게 치환되도록 이름만 치환
            text = text.replace(name, label)
    return text


def roster_entry_count() -> int:
    """설정 화면에서 '현재 N명 등록' 표시용. roster.csv 로딩 로직을 그대로 재사용한다."""
    return len(_load_roster())


def validate_roster_header(csv_path) -> bool:
    """업로드 전 형식 검증: 'name' 또는 '이름' 헤더 컬럼이 있는지만 확인한다
    (내용은 검사하지 않음 — 학교마다 다른 이름이 들어있을 뿐 형식만 맞으면 됨)."""
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
    except (OSError, UnicodeDecodeError):
        return False
    return "name" in fieldnames or "이름" in fieldnames


def mask_text(text: str) -> str:
    """Gemini로 보내기 전 반드시 이 함수를 통과시킨다."""
    if not text:
        return text
    text = _mask_patterns(text)
    roster = _load_roster()
    if roster:
        text = _mask_roster_names(text, roster)
    return text


# ---------- 3) 민감정보 메시지 판별 (내용 자체를 AI에 보내지 않을지 결정) ----------

_SENSITIVE_KEYWORDS = [
    "상담", "징계", "학교폭력", "학폭", "장애", "성적표", "가정형편",
    "생활교육위원회", "치료", "질환", "정신건강", "심리검사",
]


def is_sensitive(title: str, body: str) -> bool:
    combined = f"{title} {body}"
    return any(kw in combined for kw in _SENSITIVE_KEYWORDS)
