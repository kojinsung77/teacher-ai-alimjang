# -*- coding: utf-8 -*-
"""핵심 데이터 모델."""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional


@dataclass
class RawMessage:
    """MessengerAdapter가 반환하는 공통 메시지 구조.
    어떤 메신저(쿨메신저/향후 다른 메신저)를 읽든 이 형태로 통일해서 넘어온다."""
    id: str
    sender: str
    department: str
    title: str
    body: str
    received_at: datetime
    # 각 원소: {"filename": str, "image_bytes": bytes | None, "mime_type": str | None}.
    # image_bytes/mime_type은 이미지 확장자 첨부이고 로컬에서 실제로 읽을 수
    # 있었을 때만 채워진다(대부분의 쿨메신저 첨부는 로컬에 캐시되지 않고
    # 원격 파일 서버에서 온디맨드로 받아오는 구조라 보통 None이다 —
    # app/adapters/coolmessenger_adapter.py의 _resolve_local_attachment_path
    # 주석 참고). None이면 파일명만 아는 상태로, 기존 동작과 동일하게
    # AI에게는 "첨부파일 있음" 정도로만 전달된다.
    attachments: list = field(default_factory=list)

    def content_hash(self) -> str:
        import hashlib
        raw = f"{self.sender}|{self.title}|{self.body}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


@dataclass
class Task:
    """AI가 ACTION으로 분류해 추출한 업무."""
    id: Optional[int]
    title: str
    summary: str
    category: str
    deadline: Optional[date]
    deadline_confidence: str  # "HIGH" | "LOW" | "NONE"
    priority: str  # "HIGH" | "MEDIUM" | "LOW"
    requires_reply: bool
    requires_attachment_check: bool
    student_related: bool
    completed: bool
    completed_at: Optional[datetime]
    created_at: datetime
    confidence: float
    source_message_ids: list = field(default_factory=list)
