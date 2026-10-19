# -*- coding: utf-8 -*-
"""파랑새 알림을 '언제' 내보낼지 — 설정 → 일반에서 시점마다 켜고 끈다.

맨 위 [파랑새 알림](mascot_enabled)이 전체 스위치이고, 그 아래 네 시점을
따로 고를 수 있다. 전체 스위치가 꺼져 있으면 시점 설정과 상관없이 안 나온다.
13:20·16:10의 오른쪽 아래(트레이) 알림은 이 설정과 상관없이 그대로 온다."""

from .. import db

MASTER_KEY = "mascot_enabled"

STARTUP = "startup"
UNLOCK = "unlock"
AT_1320 = "13:20"
AT_1610 = "16:10"

# (시점, 설정 키, 설정 화면 문구) — 설정 화면이 이 순서대로 그린다.
TRIGGERS = [
    (STARTUP, "mascot_trigger_startup", "아침에 처음 켤 때"),
    (UNLOCK, "mascot_trigger_unlock", "화면 잠금을 풀 때"),
    (AT_1320, "mascot_trigger_1320", "13:20"),
    (AT_1610, "mascot_trigger_1610", "16:10"),
]
_KEYS = {trigger: key for trigger, key, _ in TRIGGERS}


def master_on() -> bool:
    return db.get_setting(MASTER_KEY, "1") == "1"


def trigger_setting(trigger: str) -> bool:
    """시점 하나의 체크 상태(전체 스위치와 상관없이). 처음엔 모두 켜져 있다."""
    return db.get_setting(_KEYS[trigger], "1") == "1"


def is_on(trigger: str) -> bool:
    """이 시점에 파랑새를 내보내도 되는지 = 전체 스위치 AND 시점 체크."""
    return master_on() and trigger_setting(trigger)


def save(master: bool, triggers: dict):
    """설정 화면 [저장] — triggers는 {시점: bool}."""
    db.set_setting(MASTER_KEY, "1" if master else "0")
    for trigger, key, _ in TRIGGERS:
        if trigger in triggers:
            db.set_setting(key, "1" if triggers[trigger] else "0")
