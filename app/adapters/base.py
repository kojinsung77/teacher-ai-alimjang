# -*- coding: utf-8 -*-
"""MessengerAdapter 공통 인터페이스.

쿨메신저든 향후 다른 메신저든, 이 인터페이스만 구현하면
AI 분석/업무 추출/UI 코드는 전혀 손댈 필요가 없다."""

from abc import ABC, abstractmethod
from typing import List
from ..models import RawMessage


class MessengerAdapter(ABC):
    name: str = "base"

    @abstractmethod
    def is_available(self) -> bool:
        """이 어댑터가 현재 환경에서 사용 가능한지 (예: 쿨메신저 설치 여부)."""
        raise NotImplementedError

    @abstractmethod
    def fetch_recent_messages(self, days: int = 1) -> List[RawMessage]:
        """최근 N일치 메시지를 공통 포맷(RawMessage)으로 반환."""
        raise NotImplementedError
