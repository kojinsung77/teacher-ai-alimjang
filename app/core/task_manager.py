# -*- coding: utf-8 -*-
"""메시지 수집 → 마스킹 → AI 분류 → 업무 저장까지의 전체 파이프라인."""

from datetime import date

from .. import db
from ..ai import gemini_client, prompts
from ..ai.gemini_client import GeminiKeyError
from ..privacy import masking
from .. import config


def sync_messages(adapter, days: int = 1) -> tuple[int, dict]:
    """어댑터로부터 메시지를 가져와 DB에 새로 들어온 것만 저장.
    반환값: (신규 저장 건수, image_map).

    image_map은 {message_id: [(image_bytes, mime_type), ...]} 형태로,
    이미지 첨부를 실제로 읽을 수 있었던 메시지만 담는다 — DB에는 이미지를
    저장하지 않으므로(app/core/task_manager.py 자체는 여기서 텍스트만
    db.insert_message에 넘긴다) 이 딕셔너리가 이미지 바이트가 살아있는
    유일한 곳이다. 호출부가 곧바로 analyze_unanalyzed(image_map=...)에
    넘기고 나면 참조가 사라져 가비지 컬렉션된다 — 디스크에는 전혀
    쓰지 않는다."""
    raw_messages = adapter.fetch_recent_messages(days=days)
    new_count = 0
    image_map = {}
    for msg in raw_messages:
        if db.message_exists(msg.content_hash()):
            continue  # 재분석 방지: 이미 저장된 메시지는 건너뜀
        sensitivity = "SENSITIVE" if masking.is_sensitive(msg.title, msg.body) else "NONE"
        db.insert_message(msg, sensitivity=sensitivity)
        new_count += 1

        images = [
            (a["image_bytes"], a["mime_type"])
            for a in (msg.attachments or [])
            if isinstance(a, dict) and a.get("image_bytes")
        ]
        if images:
            image_map[msg.id] = images

    return new_count, image_map


def analyze_unanalyzed(allow_sensitive: bool = False, image_map: dict | None = None) -> dict:
    """분석 안 된 메시지를 배치로 묶어 Gemini에 전송하고 결과를 반영.
    반환값: {"ACTION": n, "REFERENCE": n, "IGNORE": n, "SKIPPED_SENSITIVE": n}

    image_map: sync_messages()가 돌려준 {message_id: [(image_bytes, mime_type), ...]}.
    이 함수는 DB의 unanalyzed_messages()로 대상을 다시 조회하므로(방금 막
    들어온 메시지뿐 아니라 이전에 분석 실패해서 남아있던 메시지도 포함),
    image_map에 없는(=이미지 바이트를 못 구했거나 애초에 이미지가 없는)
    메시지는 그냥 텍스트만 보내는 기존 동작 그대로다."""
    image_map = image_map or {}
    rows = db.unanalyzed_messages()
    counts = {"ACTION": 0, "REFERENCE": 0, "IGNORE": 0, "SKIPPED_SENSITIVE": 0}

    targets = []
    for r in rows:
        if r["sensitivity"] == "SENSITIVE" and not allow_sensitive:
            counts["SKIPPED_SENSITIVE"] += 1
            continue
        targets.append(r)

    today_iso = date.today().isoformat()

    for i in range(0, len(targets), config.BATCH_SIZE):
        batch = targets[i:i + config.BATCH_SIZE]
        payload = [
            {
                "id": r["message_id"],
                "sender": masking.mask_text(r["sender"] or ""),
                "department": r["department"] or "",
                "title": masking.mask_text(r["title"] or ""),
                "body": masking.mask_text(r["body"] or ""),
            }
            for r in batch
        ]
        user_prompt = prompts.build_user_prompt(today_iso, payload)

        batch_images = [
            (r["message_id"], image_bytes, mime_type)
            for r in batch
            for image_bytes, mime_type in image_map.get(r["message_id"], [])
        ]

        try:
            results = gemini_client.classify_batch(
                prompts.SYSTEM_PROMPT, user_prompt, images=batch_images
            )
        except GeminiKeyError:
            raise
        except Exception as e:
            # 배치 하나가 실패해도 나머지는 계속 진행 (교사가 원문 확인으로 대응 가능)
            print(f"[분석 오류] 배치 {i}~{i+len(batch)} 처리 실패: {e}")
            continue

        for item in results:
            mid = item.get("message_id")
            cls = item.get("classification", "IGNORE")
            counts[cls] = counts.get(cls, 0) + 1
            db.mark_analyzed(mid, cls)

            if cls == "ACTION" and item.get("task"):
                db.insert_task(item["task"], source_message_ids=[mid])

    return counts
