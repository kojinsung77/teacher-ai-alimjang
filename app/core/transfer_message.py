# -*- coding: utf-8 -*-
"""[📨 전달 메시지] — 쿨메신저 메시지·업무를 학생/학부모/교사에게 보낼
안내 문구로 바꿔 준다(Gemini).

- 업무 카드: 그 업무가 나온 원본 메시지 + 업무 제목·마감일
- 메시지 화면 카드: 그 메시지 하나

개인정보: Gemini로 보내기 직전에 masking.mask_text()를 반드시 거친다
(선생님이 창에서 내용을 고쳐 이름을 써 넣었어도 다시 가린다). 민감 키워드가
있는 메시지(상담·학교폭력 등)는 자동으로 보내지 않고, 선생님이 내용을
확인한 뒤 직접 [만들기]를 눌러야 보낸다(화면 쪽에서 처리)."""

from datetime import date
from typing import Optional

from ..privacy import masking

STUDENT = "student"
PARENT = "parent"
TEACHER = "teacher"

# (key, 짧은 이름, 메뉴 문구)
AUDIENCES = [
    (STUDENT, "학생", "👩‍🎓  학생에게"),
    (PARENT, "학부모", "👨‍👩‍👧  학부모님께"),
    (TEACHER, "교사", "👩‍🏫  선생님들께"),
]
AUDIENCE_NAMES = {k: name for k, name, _ in AUDIENCES}

_EMOJI_GUIDE = """## 항목별 이모지 가이드 (참고용)
- 수업·시간표 변경: 📅
- 제출·과제: 📝
- 신청·접수: 📋
- 급식·석식: 🍚
- 행사·활동: 🎯
- 생활지도: ✏️
- 출결·공문: 📌
- 가정통신문: 📨
- 공지·안내: 📢
- 링크: 🔗"""

# 학생용은 선생님이 주신 프롬프트 그대로다.
STUDENT_PROMPT = """당신은 고등학교 교사의 학생용 알림장을 작성하는 도우미입니다.
## 역할
교사가 입력한 날것의 메모나 전달 내용을 받아, 학생들에게 보내는 알림장 형식으로 깔끔하게 정리합니다.
## 출력 형식
아래 형식으로 출력하세요.

안녕하세요! 오늘 전달 사항입니다. 꼭 확인해 주세요 😊
━━━━━━━━━━━━━━━━━━━
[항목 이모지] [항목 제목]
1. [전달 내용 1]
2. [전달 내용 2]
━━━━━━━━━━━━━━━━━━━
(항목이 여러 개면 구분선으로 나눠 반복)
문의 사항은 담임 선생님께 연락 주세요 🙏
## 작성 규칙
1. 말투는 학생에게 친근하고 정중하게 (경어체 유지)
2. 항목별로 관련 이모지를 앞에 붙여 가독성을 높임
3. 날짜·기한이 있는 항목은 반드시 날짜를 명시 (예: 3월 17일(월)까지)
4. 링크가 포함된 경우 별도 줄에 표시
5. 내용이 복잡한 경우 체크리스트(✅) 형식으로 정리
6. 불필요한 문장은 제거하고 핵심만 간결하게 작성
7. 교사의 메모에 담긴 모든 항목을 빠짐없이 포함
""" + _EMOJI_GUIDE

PARENT_PROMPT = """당신은 고등학교 담임교사가 학부모님께 보내는 안내 메시지를 작성하는 도우미입니다.
## 역할
교사가 입력한 날것의 메모나 전달 내용을 받아, 학부모님께 보내는 안내 메시지 형식으로 정중하고 깔끔하게 정리합니다.
## 출력 형식
아래 형식으로 출력하세요.

안녕하십니까, 학부모님. 담임교사입니다. 아래 사항을 안내드립니다.
━━━━━━━━━━━━━━━━━━━
[항목 이모지] [항목 제목]
1. [안내 내용 1]
2. [안내 내용 2]
━━━━━━━━━━━━━━━━━━━
(항목이 여러 개면 구분선으로 나눠 반복)
가정에서도 자녀와 함께 확인해 주시면 감사하겠습니다.
문의 사항은 담임교사에게 연락 주시기 바랍니다. 감사합니다 🙏
## 작성 규칙
1. 말투는 학부모님께 예의 바르고 정중한 경어체(~습니다, ~바랍니다)
2. 항목별로 관련 이모지를 앞에 하나씩 붙이되 과하지 않게
3. 날짜·기한이 있는 항목은 반드시 날짜를 명시 (예: 3월 17일(월)까지)
4. 학부모님이 직접 해 주셔야 할 일(동의서 서명, 회신, 비용 납부, 가정 지도 등)은 체크리스트(✅)로 분명하게 구분
5. 링크가 포함된 경우 별도 줄에 표시
6. 교직원 내부 업무나 학생에게만 필요한 세부 지시는 빼고, 학부모님이 알아야 할 핵심만 간결하게 작성
7. 교사의 메모에 담긴 학부모 관련 항목은 빠짐없이 포함
""" + _EMOJI_GUIDE

TEACHER_PROMPT = """당신은 고등학교 교사가 동료 선생님들께 업무 내용을 전달하는 메신저 공지를 작성하는 도우미입니다.
## 역할
교사가 입력한 공문·부서 안내·메모를 받아, 동료 선생님들께 보내는 업무 전달 메시지로 간결하게 정리합니다.
## 출력 형식
아래 형식으로 출력하세요.

선생님들, 안녕하세요. 아래 내용 전달드립니다.
━━━━━━━━━━━━━━━━━━━
[항목 이모지] [항목 제목]
- 내용: [해야 할 일]
- 기한: [날짜·시각]
- 제출·회신: [제출처·방법]
━━━━━━━━━━━━━━━━━━━
(항목이 여러 개면 구분선으로 나눠 반복)
바쁘시겠지만 기한 내 협조 부탁드립니다. 감사합니다.
## 작성 규칙
1. 말투는 동료 교사에게 정중하고 간결한 업무 말투(~입니다, ~부탁드립니다)
2. 무엇을 / 언제까지 / 어떻게(제출처·방법) 해야 하는지가 먼저 보이게 정리
3. 날짜·기한은 반드시 명시 (예: 3월 17일(월) 16:30까지). 원문에 기한이나 제출 방법이 없으면 그 줄은 빼기
4. 담임 선생님만 해당하는 일, 학생에게 전달할 내용 등 대상이 나뉘면 구분해서 표시
5. 링크·첨부 확인이 필요하면 별도 줄에 표시
6. 이모지는 항목 제목 앞에만 최소한으로 사용
7. 원문의 모든 업무 항목을 빠짐없이 포함하되 인사말·중복 문장은 제거
""" + _EMOJI_GUIDE

SYSTEM_PROMPTS = {STUDENT: STUDENT_PROMPT, PARENT: PARENT_PROMPT, TEACHER: TEACHER_PROMPT}

_WEEKDAYS = "월화수목금토일"


def korean_date(d: date) -> str:
    return f"{d.year}년 {d.month}월 {d.day}일({_WEEKDAYS[d.weekday()]})"


def _get(row, key):
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def _message_block(row) -> str:
    lines = []
    sender_bits = [b for b in (_get(row, "department"), _get(row, "sender")) if b]
    if sender_bits:
        lines.append("보낸 곳: " + " / ".join(sender_bits))
    received = _get(row, "received_at")
    if received:
        try:
            lines.append("받은 날: " + korean_date(date.fromisoformat(str(received)[:10])))
        except ValueError:
            pass
    lines.append("제목: " + (_get(row, "title") or "(제목 없음)"))
    lines.append("내용:\n" + (_get(row, "body") or "(본문 없음)").strip())
    return "\n".join(lines)


def source_for_messages(messages, task=None) -> dict:
    """AI에 보낼 원문을 만든다(아직 가리기 전 — 화면에 보여 줄 때도 가린 뒤 보여 준다).
    반환: {"text": 가린 원문, "sensitive": 민감 키워드 여부, "label": 창 제목용 문구}"""
    blocks = []
    if task is not None:
        head = ["[업무]", "업무: " + (_get(task, "title") or "")]
        deadline = _get(task, "deadline")
        if deadline:
            try:
                head.append("마감: " + korean_date(date.fromisoformat(str(deadline)[:10])))
            except ValueError:
                head.append("마감: " + str(deadline))
        summary = _get(task, "summary")
        if summary:
            head.append("요약: " + summary)
        blocks.append("\n".join(head))
    for i, m in enumerate(messages, 1):
        title = f"[원본 메시지 {i}]" if len(messages) > 1 else "[원본 메시지]"
        blocks.append(title + "\n" + _message_block(m))
    raw = "\n\n".join(blocks).strip()
    sensitive = any(
        masking.is_sensitive(_get(m, "title") or "", _get(m, "body") or "") for m in messages
    ) or (str(_get(messages[0], "sensitivity") or "") == "SENSITIVE" if messages else False)
    label = (_get(task, "title") if task is not None else None) or (
        _get(messages[0], "title") if messages else ""
    ) or ""
    return {"text": masking.mask_text(raw), "sensitive": sensitive, "label": label}


def build_user_prompt(source_text: str, today: Optional[date] = None) -> str:
    today = today or date.today()
    return (
        f"오늘은 {korean_date(today)}입니다. 날짜에 요일을 붙일 때 이 날짜를 기준으로 계산하세요.\n"
        "아래 전달 내용을 위의 형식으로 정리해 주세요.\n"
        "- 완성된 메시지 본문만 출력하고, 설명이나 머리말·코드블록은 붙이지 마세요.\n"
        "- 원문에 없는 날짜·시간·장소·금액 등은 지어내지 마세요.\n"
        "- 원문에 없는 사실이나 경위(예: '개별적으로 안내드린 바와 같이', '지난번에 말씀드린 대로')를 덧붙이지 마세요.\n"
        "- [학생1], [관계자1], [전화번호]처럼 가려진 표시는 그대로 두세요.\n\n"
        "----- 전달 내용 -----\n"
        f"{source_text.strip()}\n"
        "----- 끝 -----"
    )


def clean_output(text: str) -> str:
    """모델이 코드블록으로 감싸 보내는 경우 벗겨 낸다."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        first_nl = t.find("\n")
        if first_nl != -1 and len(t[:first_nl].strip()) <= 10:
            t = t[first_nl + 1:]
        t = t.strip()
    return t


def generate(audience: str, source_text: str, today: Optional[date] = None) -> str:
    """전달 메시지를 만든다. 보내기 직전에 다시 한 번 가린다(선생님이 창에서
    고친 내용에 이름이 들어갔을 수 있으므로)."""
    from ..ai import gemini_client  # keyring 등 무거운 의존성은 쓸 때 불러온다
    if audience not in SYSTEM_PROMPTS:
        raise ValueError(f"알 수 없는 대상: {audience}")
    safe_text = masking.mask_text(source_text or "")
    if not safe_text.strip():
        raise ValueError("보낼 내용이 비어 있습니다.")
    out = gemini_client.generate_text(SYSTEM_PROMPTS[audience], build_user_prompt(safe_text, today))
    out = clean_output(out)
    if not out:
        raise RuntimeError("AI 응답이 비어 있습니다. 잠시 후 다시 시도해 주세요.")
    return out
