# 쿨브리핑 (MVP)

쿨메신저로 받는 하루 30~40건의 메시지 중 "내가 실제로 해야 할 일"만 AI가 추출해
마감일순으로 보여주는 Windows 데스크톱 앱입니다.

## 지금 이 코드로 뭐가 되는가 (정직하게 밝힙니다)

이 코드는 클로드(웹 채팅)가 **네트워크도, Windows도, 실제 쿨메신저 데이터도 없는
리눅스 샌드박스**에서 작성했습니다. 그래서:

- ✅ **문법 검증 완료**: 모든 `.py` 파일이 `py_compile`을 통과했습니다.
- ✅ **핵심 로직 실제 동작 검증 완료**: DB 저장/중복 방지, 업무 완료 처리, D-Day 계산,
  개인정보 마스킹(정규식+명단 매칭)은 실제로 실행해서 결과까지 확인했습니다
  (아래 "검증된 부분" 참고).
- ⚠ **GUI(PySide6)와 Gemini API 호출은 실행해 본 적이 없습니다.** PySide6가
  설치된 환경이 없어서, 화면이 실제로 어떻게 뜨는지는 이 환경에서 볼 수 없었습니다.
  코드 자체는 PySide6 표준 API 패턴을 따랐지만, Windows PC에서 처음 실행했을 때
  오탈자 수준의 에러가 날 가능성이 있습니다. 그럴 땐 에러 메시지를 그대로
  클로드 코드에 붙여넣으면 바로 고칠 수 있는 수준일 겁니다.
- ⚠ **쿨메신저 실제 연동은 아직 완성되지 않았습니다.** 아래 "1단계"를 반드시
  먼저 진행해 주세요. 그 전까지는 **데모 모드**로 전체 화면과 흐름을 확인할 수 있습니다.

## 1단계 — 가장 먼저 할 일: .udb 진단

```
python check_coolmessenger_udb.py
```

이 스크립트는 패키지 설치 없이 바로 실행됩니다. 실행 결과가:

- **"SQLite 형식입니다"** → `app/adapters/coolmessenger_adapter.py` 상단의
  `SCHEMA_HINT` 딕셔너리를, 진단 스크립트가 출력한 실제 테이블명/컬럼명으로
  교체하세요. (이 부분은 실제 파일을 보기 전까지 정확히 알 수 없어 추정값으로 남겨뒀습니다.)
- **"SQLite 형식이 아닙니다"** → `app/adapters/coolmessenger_export_adapter.py`
  (Plan B: 쿨메신저 공식 "메시지 다운로드" 버튼 자동화)를 완성하세요.
  `trigger_official_download()` 안에 pywinauto로 실제 버튼을 찾아 클릭하는
  코드를 채워야 합니다 (골격만 준비되어 있음).

두 경우 모두, 진단 스크립트 출력 결과를 클로드 코드에 그대로 붙여넣으면
이어서 자동으로 완성시킬 수 있습니다.

## 2단계 — 실행

```
pip install -r requirements.txt
python main.py
```

처음 실행하면 **데모 모드**가 기본 켜져 있어서, 실제 쿨메신저 없이도
가상의 학교 메시지로 전체 기능(AI 분류 → 업무 카드 → 완료 처리 → 원문 확인 →
알림장 만들기)을 바로 체험할 수 있습니다. (단, Gemini API Key는 실제로 입력해야
AI 분석이 동작합니다 — Google AI Studio에서 무료로 발급 가능)

최초 실행 시 '메신저 설정' → 'AI 설정' 다이얼로그가 순서대로 뜹니다. 이후에는
사이드바 [⚙ 설정]을 누르면 'AI 설정' 다이얼로그가 다시 열립니다.
1. AI 설정에서 Gemini API Key 입력 → 연결 테스트 → OK
2. AI 설정 안의 [메신저 다시 설정...] → 데모 모드 체크박스 해제 → 실제 쿨메신저 연동 사용 (1단계 완료 후)

## 3단계 — 개인정보 마스킹 명단 설정 (선택, 권장)

`%LOCALAPPDATA%\TeacherAlimjang\roster.csv` 파일을 만들고 아래 형식으로
학생/교직원 이름을 넣어두면, AI로 전송하기 전에 이름이 `[학생1]`처럼
자동으로 마스킹됩니다. (샘플: `app/privacy/roster_sample.csv` 참고)

```csv
name,type
홍길동,student
김민지,student
```

## 검증된 부분 (실제로 실행해서 확인함)

- 메시지 저장 시 내용 해시 기반 중복 방지 (같은 메시지 재분석 안 함)
- 업무 저장 → 조회 → 완료 처리 → 원문 메시지 역추적
- D-Day 계산 (오늘/내일/D-2.../기한 지남/마감일 확인 필요)
- 정규식 기반 마스킹 (전화번호, 이메일)
- 명단 기반 이름 마스킹 (roster.csv의 이름을 `[학생N]`으로 치환)

## 이번 MVP에 포함된 것 / 안 된 것

**포함**: 메시지 읽기(어댑터 구조), 목록 표시, API Key 입력/테스트, ACTION/REFERENCE/IGNORE
분류, 업무 추출, 마감일 추출, 업무 목록(오늘 화면), 완료 처리, 원문 확인, 데모 모드,
개인정보 마스킹, 알림장 클립보드 복사

**미포함 (기획안 2~4차 항목, 다음 단계)**: 미처리 업무 자동 이월, 중복 메시지 AI 통합,
Windows 트레이 상주/알림, 지난 알림장 검색, 설치 프로그램(EXE), 자동 업데이트

## 폴더 구조

```
main.py                              실행 진입점
check_coolmessenger_udb.py           .udb 진단 스크립트 (1단계)
app/
  db.py                              SQLite 스키마/CRUD
  models.py                          RawMessage, Task 데이터 모델
  config.py                          경로/상수
  adapters/
    base.py                          MessengerAdapter 공통 인터페이스
    coolmessenger_adapter.py         Plan A: 직접 SQLite 파싱
    coolmessenger_export_adapter.py  Plan B: 공식 다운로드 자동화 (뼈대)
    mock_adapter.py                  데모용 가짜 데이터
  privacy/
    masking.py                       정규식 + 명단 기반 개인정보 마스킹
    roster_sample.csv                명단 파일 샘플
  ai/
    gemini_client.py                 Gemini API 호출 (BYOK, keyring 저장)
    prompts.py                       시스템 프롬프트
  core/
    task_manager.py                  수집→마스킹→분류→저장 파이프라인
    dday.py                          마감일 표시 로직
  ui/
    main_window.py                   사이드바 + 화면 전환
    today_view.py                    '오늘' 메인 화면
    messenger_setup_dialog.py        '메신저 설정' 모달 (자동 탐색/다중 계정/수동 선택)
    ai_settings_dialog.py            'AI 설정' 모달
    privacy_masking_dialog.py        '개인정보 마스킹 명단 설정' 모달 (샘플/업로드)
    task_card.py                     업무 카드 위젯
    styles.py                        색상 팔레트 / QSS 스타일시트
```
