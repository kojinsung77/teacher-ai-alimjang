# -*- coding: utf-8 -*-
"""개발/데모용 가짜 데이터 어댑터.

실제 쿨메신저 연동이 완성되기 전에도 UI, AI 분류, 업무 관리 파이프라인
전체를 바로 확인해 볼 수 있도록 실제와 비슷한 학교 메시지를 생성한다.
설정 화면에서 '데모 모드'를 켜면 이 어댑터가 사용된다."""

import random
from datetime import datetime, timedelta
from typing import List

from .base import MessengerAdapter
from ..models import RawMessage


_SAMPLE_MESSAGES = [
    dict(sender="보건교사 김OO", department="보건실",
         title="건강검진 미수검 학생 확인 요청",
         body="3학년 담임 선생님께서는 건강검진 미수검 학생을 확인하시고 "
              "8월 19일까지 해당 학생에게 검진을 안내해 주시기 바랍니다."),
    dict(sender="교육과정부 이OO", department="교육과정부",
         title="2학기 수행평가 계획서 수정 안내",
         body="2학기 수행평가 계획서 양식이 변경되어 8월 20일까지 수정본을 "
              "제출해 주시기 바랍니다. 첨부파일을 확인해 주세요."),
    dict(sender="3학년부장 박OO", department="3학년부",
         title="졸업앨범 최종 확인 요청",
         body="졸업앨범 학급 사진 최종본을 확인하시고 8월 18일까지 이상 유무를 "
              "회신해 주시기 바랍니다."),
    dict(sender="교무부 최OO", department="교무부",
         title="2학기 연수 참석 여부 조사",
         body="다음 주 예정된 교직원 연수 참석 여부를 8월 18일까지 회신 바랍니다."),
    dict(sender="입시정보부 정OO", department="입시정보부",
         title="수능 관련 자료 배부 안내",
         body="수능 관련 최신 자료를 배부하니 8월 20일까지 확인해 주시기 바랍니다."),
    dict(sender="교무부 최OO", department="교무부",
         title="교직원 연수 신청 안내",
         body="9월 예정 교직원 연수 신청을 8월 21일까지 완료해 주세요."),
    dict(sender="시설관리팀", department="행정실",
         title="본관 엘리베이터 공사 안내",
         body="내일부터 본관 엘리베이터 공사가 진행됩니다. 계단 이용 부탁드립니다."),
    dict(sender="행정실 안OO", department="행정실",
         title="주차장 임시 폐쇄 안내",
         body="금일 오후 주차장 일부가 임시 폐쇄됩니다. 참고 바랍니다."),
    dict(sender="교육과정부 이OO", department="교육과정부",
         title="(재안내) 수행평가 계획서 제출",
         body="어제 안내드린 수행평가 계획서 제출 관련 재안내입니다. "
              "8월 20일까지 제출 부탁드립니다."),
    dict(sender="시스템", department="시스템",
         title="정기 점검 안내",
         body="시스템 정기 점검이 있을 예정입니다."),
]


class MockMessengerAdapter(MessengerAdapter):
    name = "mock"

    def is_available(self) -> bool:
        return True

    def fetch_recent_messages(self, days: int = 1) -> List[RawMessage]:
        now = datetime.now()
        today_tag = now.strftime("%Y-%m-%d")
        results = []
        for i, m in enumerate(_SAMPLE_MESSAGES):
            received_at = now - timedelta(hours=random.randint(0, 20))
            results.append(RawMessage(
                id=f"MOCK-{now.strftime('%Y%m%d')}-{i:03d}",
                sender=m["sender"],
                department=m["department"],
                title=m["title"],
                # content_hash가 sender|title|body로 계산되는데 샘플 내용이
                # 고정이라, 오늘 날짜를 본문에 섞지 않으면 최초 1회 동기화
                # 이후로는 매번 "새 메시지 0건"이 나온다(중복으로 걸러짐).
                body=f"{m['body']} [{today_tag}]",
                received_at=received_at,
            ))
        return results
