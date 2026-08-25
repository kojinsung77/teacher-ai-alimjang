# -*- coding: utf-8 -*-
"""전역 색상 팔레트와 QSS 스타일시트. UI 전체가 이 한 파일을 기준으로 통일된
톤을 갖는다 (짙은 네이비 사이드바 + 블루 프라이머리 + 파스텔 상태 카드,
teacher_ai_dashboard_preview.html 레퍼런스 기준)."""

from .. import config

# QSS의 url()은 백슬래시를 못 읽으므로 슬래시로 바꿔서 넣는다.
_CHECKMARK_URL = str(config.checkmark_icon_path()).replace("\\", "/")
_SPIN_UP_ARROW_URL = str(config.spin_arrow_icon_path("up")).replace("\\", "/")
_SPIN_DOWN_ARROW_URL = str(config.spin_arrow_icon_path("down")).replace("\\", "/")

COLORS = {
    "bg": "#F5F7FB",
    "sidebar_bg": "#10264A",
    "sidebar_bg2": "#152F57",
    "sidebar_text": "#C8D2E3",
    "sidebar_text_active": "#FFFFFF",
    "sidebar_subtext": "#AEBBD0",
    "card_bg": "#FFFFFF",
    "text_primary": "#17243B",
    "text_secondary": "#6D7890",
    "border": "#E7EBF3",
    "accent": "#4F76F5",
    "accent2": "#6784F8",
    "accent_hover": "#3D63E8",
    "indigo": "#4F46E5",
    "today": "#E25555",
    "tomorrow": "#EF725F",
    "amber": "#C38B1B",
    "this_week": "#4F76F5",
    "later": "#9AA5B5",
    "unknown": "#A78BFA",
    "holiday_bg": "#EDEFF4",
    # 등교는 하지만 행사가 있는 날(모의고사, 리더십캠프 등) — 휴일(회색)과
    # 시각적으로 구분되도록 보라 계열을 쓴다.
    "event_bg": "#F1EDFC",
    "event_accent": "#8B5CF6",
    "success": "#3D986B",
    "success_bg": "#F0FAF5",
    # 파스텔 스탯 카드
    "stat_red_bg": "#FFF4F4", "stat_red_border": "#FFE0E0",
    "stat_coral_bg": "#FFF5F1", "stat_coral_border": "#FFE4DD",
    "stat_orange_bg": "#FFF8EF", "stat_orange_border": "#FCE7CE",
    "stat_blue_bg": "#EEF3FF", "stat_blue_border": "#DCE6FF",
}

# 본문/제목 구분 없이 앱 전체가 나눔고딕 하나로 통일되어 있다 — 예전에는
# 제목/인사말 전용 학교안심 알림장 + 본문용 Pretendard로 나뉘어 있었지만
# (HEADING_FONT_FAMILY), 그 구분을 없애고 FONT_FAMILY 하나로 합쳤다.
FONT_FAMILY = "'NanumGothic', 'Malgun Gothic', 'Segoe UI', sans-serif"

STYLESHEET = f"""
QWidget {{
    background-color: {COLORS['bg']};
    color: {COLORS['text_primary']};
    font-family: {FONT_FAMILY};
    font-size: 14px;
}}
QLabel {{
    background-color: transparent;
}}
QPushButton {{
    color: {COLORS['text_primary']};
}}

/* ---------- 사이드바 ---------- */
#Sidebar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {COLORS['sidebar_bg']}, stop:1 {COLORS['sidebar_bg2']});
    min-width: 268px;
    max-width: 268px;
}}
#SidebarBrandIcon {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #5C80F8, stop:1 #7C92FF);
    border-radius: 14px;
    color: white;
    font-size: 20px;
    font-weight: 900;
    qproperty-alignment: AlignCenter;
}}
#SidebarTitle {{
    color: {COLORS['sidebar_text_active']};
    font-size: 15px;
    font-weight: 800;
}}
#SidebarSubtitle {{
    color: {COLORS['sidebar_subtext']};
    font-size: 11px;
}}
QLabel#TestBadge {{
    background-color: rgba(195, 139, 27, 0.22);
    color: #F0C36D;
    border: 1px solid rgba(195, 139, 27, 0.45);
    border-radius: 9px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 700;
    margin-top: 6px;
}}
QPushButton#SidebarFeedbackButton {{
    background-color: transparent;
    color: {COLORS['sidebar_text']};
    border: 1px solid rgba(255, 255, 255, 0.13);
    border-radius: 10px;
    text-align: center;
    padding: 9px 12px;
    font-size: 12px;
}}
QPushButton#SidebarFeedbackButton:hover {{
    background-color: rgba(255, 255, 255, 0.08);
    color: {COLORS['sidebar_text_active']};
}}
#SidebarCredit {{
    color: #FFFFFF;
    font-size: 11px;
    padding: 0 4px;
}}
QPushButton#NavButton {{
    background-color: transparent;
    color: {COLORS['sidebar_text']};
    text-align: left;
    padding: 12px 14px;
    border: none;
    border-radius: 12px;
    font-size: 14px;
}}
QPushButton#NavButton:hover {{
    background-color: rgba(255, 255, 255, 0.08);
    color: {COLORS['sidebar_text_active']};
}}
QPushButton#NavButton[active="true"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {COLORS['accent']}, stop:1 {COLORS['accent2']});
    color: {COLORS['sidebar_text_active']};
    font-weight: 700;
}}

/* ---------- 메인 콘텐츠 ---------- */
#ContentArea {{
    background-color: {COLORS['bg']};
}}
#PageTitle {{
    font-size: 22px;
    font-weight: 800;
    color: {COLORS['text_primary']};
}}
#PageSubtitle {{
    font-size: 14px;
    color: {COLORS['text_secondary']};
}}
#Eyebrow {{
    font-size: 11px;
    font-weight: 800;
    color: {COLORS['text_secondary']};
    letter-spacing: 1px;
}}

/* ---------- 카드 ---------- */
QFrame#Card {{
    background-color: {COLORS['card_bg']};
    border: 1px solid {COLORS['border']};
    border-radius: 16px;
}}
QFrame#Panel {{
    background-color: {COLORS['card_bg']};
    border: 1px solid {COLORS['border']};
    border-radius: 20px;
}}
QFrame#StatBar {{
    background-color: {COLORS['card_bg']};
    border: 1px solid {COLORS['border']};
    border-radius: 14px;
}}

/* ---------- 토스트 알림 (자동 확인 결과 등, 잠깐 떴다 사라짐) ---------- */
QLabel#Toast {{
    background-color: {COLORS['text_primary']};
    color: white;
    border-radius: 18px;
    padding: 10px 20px;
    font-size: 13px;
    font-weight: 600;
}}

/* ---------- 새 버전 안내 모달 카드 (창 우측 상단 오버레이) ---------- */
QFrame#UpdateModal {{
    background-color: {COLORS['stat_blue_bg']};
    border: 1px solid {COLORS['stat_blue_border']};
    border-radius: 16px;
}}
QLabel#UpdateModalIcon {{
    font-size: 18px;
}}
QLabel#UpdateModalTitle {{
    color: {COLORS['text_primary']};
    font-size: 14px;
    font-weight: 700;
}}
QLabel#UpdateModalVersion {{
    color: {COLORS['text_primary']};
    font-size: 20px;
    font-weight: 800;
}}
QLabel#UpdateModalDate {{
    color: {COLORS['text_secondary']};
    font-size: 12px;
}}
QLabel#DemoModeBadge {{
    background-color: {COLORS['stat_orange_bg']};
    color: {COLORS['amber']};
    border: 1px solid {COLORS['stat_orange_border']};
    border-radius: 8px;
    padding: 6px 12px;
    font-weight: 600;
    font-size: 12px;
}}

/* ---------- 설정 화면 카드 (일반/Gemini AI/메신저/개인정보 마스킹) ---------- */
QFrame#SettingsCard {{
    background-color: {COLORS['card_bg']};
    border: 1px solid {COLORS['border']};
    border-radius: 16px;
}}
QLabel#SettingsCardIcon {{
    font-size: 26px;
}}
QLabel#SettingsCardTitle {{
    font-size: 16px;
    font-weight: 700;
    color: {COLORS['text_primary']};
}}
QLabel#SettingsCardDesc {{
    font-size: 13px;
    color: {COLORS['text_secondary']};
}}
QLabel#SettingsCardArrow {{
    font-size: 20px;
    color: {COLORS['text_secondary']};
}}
QLabel#StatusBadgeOk {{
    background-color: {COLORS['success_bg']};
    color: {COLORS['success']};
    border-radius: 9px;
    padding: 3px 10px;
    font-weight: 700;
    font-size: 12px;
}}
QLabel#StatusBadgeWarn {{
    background-color: {COLORS['stat_orange_bg']};
    color: {COLORS['amber']};
    border-radius: 9px;
    padding: 3px 10px;
    font-weight: 700;
    font-size: 12px;
}}

/* ---------- 섹션 헤더 배지 ---------- */
QLabel#SectionBadgeToday {{
    background-color: {COLORS['today']};
    color: white;
    border-radius: 9px;
    padding: 3px 10px;
    font-weight: 700;
    font-size: 12px;
}}
QLabel#SectionBadgeTomorrow {{
    background-color: {COLORS['tomorrow']};
    color: white;
    border-radius: 9px;
    padding: 3px 10px;
    font-weight: 700;
    font-size: 12px;
}}
QLabel#SectionBadgeWeek {{
    background-color: {COLORS['this_week']};
    color: white;
    border-radius: 9px;
    padding: 3px 10px;
    font-weight: 700;
    font-size: 12px;
}}
QLabel#SectionBadgeLater {{
    background-color: {COLORS['later']};
    color: white;
    border-radius: 9px;
    padding: 3px 10px;
    font-weight: 700;
    font-size: 12px;
}}
QLabel#SectionTitle {{
    font-size: 18px;
    font-weight: 800;
    color: {COLORS['text_primary']};
}}

/* ---------- 버튼 ---------- */
QPushButton#PrimaryButton {{
    background-color: {COLORS['accent']};
    color: white;
    border: none;
    border-radius: 10px;
    padding: 11px 20px;
    font-weight: 700;
    font-size: 14px;
}}
QPushButton#PrimaryButton:hover {{
    background-color: {COLORS['accent_hover']};
}}
QPushButton#SecondaryButton {{
    background-color: {COLORS['card_bg']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
    padding: 11px 20px;
    font-weight: 600;
}}
QPushButton#SecondaryButton:hover {{
    background-color: #F0F3FA;
}}
QPushButton#GhostButton {{
    background-color: {COLORS['card_bg']};
    color: {COLORS['text_secondary']};
    border: 1px solid {COLORS['border']};
    border-radius: 9px;
    padding: 7px 13px;
    font-size: 12px;
    font-weight: 700;
}}
QPushButton#GhostButton:hover {{
    background-color: #F0F3FA;
    color: {COLORS['text_primary']};
}}
QPushButton#CompleteButton {{
    background-color: {COLORS['accent']};
    color: white;
    border: none;
    border-radius: 9px;
    padding: 7px 14px;
    font-size: 12px;
    font-weight: 700;
}}
QPushButton#CompleteButton:hover {{
    background-color: {COLORS['accent_hover']};
}}

/* ---------- 입력창 ---------- */
QLineEdit, QComboBox, QSpinBox {{
    background-color: white;
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
    padding: 9px 12px;
    font-size: 14px;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border: 1.5px solid {COLORS['accent']};
}}
QComboBox::drop-down {{
    border: none;
    width: 28px;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    width: 24px;
    border: none;
    background-color: transparent;
}}
/* ::up-button/::down-button만 커스터마이징하면 Qt가 기본 화살표를 안
   그려주므로, ::up-arrow/::down-arrow에 직접 삼각형 PNG를 지정해야
   화살표가 보인다(체크박스 체크 표시와 동일한 이미지 방식). */
QSpinBox::up-arrow {{
    image: url({_SPIN_UP_ARROW_URL});
    width: 14px;
    height: 14px;
}}
QSpinBox::down-arrow {{
    image: url({_SPIN_DOWN_ARROW_URL});
    width: 14px;
    height: 14px;
}}
QComboBox QAbstractItemView {{
    background-color: white;
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 4px;
    outline: none;
    selection-background-color: {COLORS['accent']};
    selection-color: white;
}}

/* ---------- 체크박스 ---------- */
QCheckBox {{
    spacing: 10px;
    font-size: 14px;
    color: {COLORS['text_primary']};
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1.5px solid {COLORS['border']};
    background-color: white;
}}
QCheckBox::indicator:hover {{
    border: 1.5px solid {COLORS['accent']};
}}
QCheckBox::indicator:checked {{
    border: 1.5px solid {COLORS['indigo']};
    background-color: {COLORS['indigo']};
    image: url({_CHECKMARK_URL});
}}
QCheckBox:disabled {{
    color: {COLORS['text_secondary']};
}}
QCheckBox::indicator:disabled {{
    border: 1.5px solid {COLORS['border']};
    background-color: #F0F1F5;
}}
QCheckBox::indicator:checked:disabled {{
    border: 1.5px solid {COLORS['border']};
    background-color: {COLORS['border']};
}}

/* ---------- 라디오 버튼 ----------
   커스텀 스타일을 안 주면 Qt 기본(네이티브) 렌더링을 쓰는데, 이 앱의
   전역 스타일시트와 결합하면 "선택된" 상태의 원 안쪽 점이 아예 안
   보이는 문제가 실측 확인됐다 — 체크박스와 통일된 accent 색 채우기
   방식으로 명시적으로 그려서 항상 또렷하게 보이게 한다. */
QRadioButton {{
    spacing: 10px;
    font-size: 14px;
    color: {COLORS['text_primary']};
}}
QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 9px;
    border: 1.5px solid {COLORS['border']};
    background-color: white;
}}
QRadioButton::indicator:hover {{
    border: 1.5px solid {COLORS['accent']};
}}
QRadioButton::indicator:checked {{
    border: 5px solid {COLORS['accent']};
    background-color: white;
}}
QRadioButton:disabled {{
    color: {COLORS['text_secondary']};
}}
QRadioButton::indicator:disabled {{
    border: 1.5px solid {COLORS['border']};
    background-color: #F0F1F5;
}}
QRadioButton::indicator:checked:disabled {{
    border: 5px solid {COLORS['border']};
    background-color: #F0F1F5;
}}

/* ---------- 스크롤바 ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
}}
QScrollBar::handle:vertical {{
    background: #D5DAE8;
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QLabel#Muted {{
    color: {COLORS['text_secondary']};
    font-size: 12px;
}}
QLabel#EventLabel {{
    color: {COLORS['event_accent']};
    font-size: 12px;
    font-weight: 700;
}}
QLabel#TaskTitle {{
    font-size: 15px;
    font-weight: 700;
    color: {COLORS['text_primary']};
}}
QLabel#TaskMeta {{
    color: {COLORS['text_secondary']};
    font-size: 12px;
}}

/* ---------- 설정 화면: 폼 라벨/상태 텍스트 ---------- */
QLabel#FormLabel {{
    color: {COLORS['text_secondary']};
    font-size: 13px;
    font-weight: 600;
}}
QLabel#StatusOk {{
    color: {COLORS['success']};
    font-size: 12px;
    font-weight: 600;
}}
QLabel#StatusError {{
    color: {COLORS['today']};
    font-size: 12px;
    font-weight: 600;
}}

/* ---------- 작은 토글 버튼 (API 키 보기/숨기기 등) ---------- */
QPushButton#ToggleButton {{
    background-color: {COLORS['card_bg']};
    color: {COLORS['text_secondary']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 9px 8px;
    font-size: 14px;
}}
QPushButton#ToggleButton:hover {{
    background-color: #F0F3FA;
}}

/* ---------- '오늘' 대시보드 히어로 ---------- */
QLabel#GreetingTitle {{
    font-size: 30px;
    font-weight: 800;
    color: {COLORS['text_primary']};
    letter-spacing: -0.5px;
}}
QLabel#GreetingName {{
    color: {COLORS['accent']};
}}
QFrame#DateBadge {{
    background-color: {COLORS['card_bg']};
    border: 1px solid {COLORS['border']};
    border-radius: 14px;
}}
QLabel#DashboardDate {{
    font-size: 13px;
    font-weight: 800;
    color: {COLORS['text_primary']};
}}

/* ---------- 통계 카드 (파스텔) ---------- */
QLabel#StatTileIcon {{
    font-size: 20px;
}}
QLabel#StatIconBadge {{
    background-color: rgba(255, 255, 255, 0.73);
    border-radius: 10px;
    font-size: 15px;
    font-weight: 800;
    qproperty-alignment: AlignCenter;
}}
QLabel#StatCardLabel {{
    font-size: 13px;
    font-weight: 800;
    color: {COLORS['text_primary']};
}}
QLabel#StatCardNumber {{
    font-size: 32px;
    font-weight: 900;
    color: {COLORS['text_primary']};
}}
QLabel#StatCardDesc {{
    font-size: 12px;
    color: {COLORS['text_secondary']};
}}
QFrame#StatCard {{
    border-radius: 18px;
    border: 1px solid transparent;
}}
QFrame#StatCard[variant="red"] {{
    background-color: {COLORS['stat_red_bg']};
    border-color: {COLORS['stat_red_border']};
}}
QFrame#StatCard[variant="coral"] {{
    background-color: {COLORS['stat_coral_bg']};
    border-color: {COLORS['stat_coral_border']};
}}
QFrame#StatCard[variant="orange"] {{
    background-color: {COLORS['stat_orange_bg']};
    border-color: {COLORS['stat_orange_border']};
}}
QFrame#StatCard[variant="blue"] {{
    background-color: {COLORS['stat_blue_bg']};
    border-color: {COLORS['stat_blue_border']};
}}
QFrame#StatCard:hover {{
    border-color: {COLORS['accent']};
}}

QFrame#PriorityItem {{
    background-color: {COLORS['card_bg']};
    border: 1px solid {COLORS['border']};
    border-radius: 14px;
}}
QFrame#PriorityItem:hover {{
    border: 1.5px solid {COLORS['accent']};
}}

/* ---------- Empty State ---------- */
QFrame#EmptyState {{
    background-color: {COLORS['card_bg']};
    border: 1px dashed {COLORS['border']};
    border-radius: 16px;
}}
QLabel#EmptyStateIcon {{
    font-size: 30px;
    qproperty-alignment: AlignCenter;
}}
QLabel#EmptyStateTitle {{
    font-size: 15px;
    font-weight: 700;
    color: {COLORS['text_primary']};
    qproperty-alignment: AlignCenter;
}}
QLabel#EmptyStateDesc {{
    font-size: 12.5px;
    color: {COLORS['text_secondary']};
    qproperty-alignment: AlignCenter;
}}

/* ---------- 업무 화면: 날짜 필터 탭(pill) ---------- */
QFrame#FilterTab {{
    background-color: #FFFFFF;
    border: 1px solid {COLORS['border']};
    border-radius: 13px;
}}
QFrame#FilterTab:hover {{
    border-color: {COLORS['accent']};
}}
QFrame#FilterTab[active="true"] {{
    background-color: {COLORS['accent']};
    border-color: {COLORS['accent']};
}}
QLabel#FilterTabLabel {{
    color: {COLORS['text_primary']};
    font-weight: 700;
    font-size: 13px;
}}
QLabel#FilterTabLabel[active="true"] {{
    color: white;
}}
QLabel#FilterTabBadge {{
    color: white;
    font-weight: 700;
    font-size: 11px;
    border-radius: 9px;
    padding: 1px 7px;
    min-width: 12px;
    qproperty-alignment: AlignCenter;
}}
QLabel#FilterTabBadge[colorKey="all"] {{ background-color: {COLORS['accent']}; }}
QLabel#FilterTabBadge[colorKey="overdue"] {{ background-color: {COLORS['today']}; }}
QLabel#FilterTabBadge[colorKey="today"] {{ background-color: {COLORS['tomorrow']}; }}
QLabel#FilterTabBadge[colorKey="within7"] {{ background-color: {COLORS['amber']}; }}
QLabel#FilterTabBadge[colorKey="later"] {{ background-color: {COLORS['this_week']}; }}
QLabel#FilterTabBadge[colorKey="nodeadline"] {{ background-color: {COLORS['later']}; }}
QLabel#FilterTabBadge[colorKey="completed"] {{ background-color: {COLORS['success']}; }}

/* ---------- 메시지 화면: 기간 탭 / AI 상태 배지 ---------- */
QPushButton#PeriodTab {{
    background-color: #FFFFFF;
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 999px;
    padding: 9px 15px;
    font-weight: 700;
    font-size: 12.5px;
}}
QPushButton#PeriodTab:hover {{
    border-color: {COLORS['accent']};
}}
QPushButton#PeriodTab[active="true"] {{
    background-color: {COLORS['accent']};
    color: white;
    border-color: {COLORS['accent']};
}}
QLabel#MsgBadgeAction {{
    background-color: #FFF0EA;
    color: #C75B40;
    border-radius: 999px;
    padding: 4px 10px;
    font-weight: 800;
    font-size: 10.5px;
}}
QLabel#MsgBadgeReference {{
    background-color: #EDF3FF;
    color: #3B62B5;
    border-radius: 999px;
    padding: 4px 10px;
    font-weight: 800;
    font-size: 10.5px;
}}
QLabel#MsgBadgeIgnore {{
    background-color: #F2F4F7;
    color: #798294;
    border-radius: 999px;
    padding: 4px 10px;
    font-weight: 800;
    font-size: 10.5px;
}}
QLabel#MsgBadgePending {{
    background-color: transparent;
    color: {COLORS['text_secondary']};
    border: 1px solid {COLORS['border']};
    border-radius: 999px;
    padding: 3px 9px;
    font-weight: 700;
    font-size: 10.5px;
}}

/* ---------- 일정 화면: 달력 재스타일링 ---------- */
QCalendarWidget {{
    background-color: {COLORS['card_bg']};
    border: 1px solid {COLORS['border']};
    border-radius: 16px;
}}
QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background-color: {COLORS['card_bg']};
    border-top-left-radius: 16px;
    border-top-right-radius: 16px;
}}
QCalendarWidget QToolButton {{
    color: {COLORS['text_primary']};
    background-color: transparent;
    border: none;
    border-radius: 8px;
    font-weight: 700;
    font-size: 14px;
    padding: 6px 8px;
    icon-size: 16px;
}}
QCalendarWidget QToolButton:hover {{
    background-color: #F0F3FA;
}}
QCalendarWidget QToolButton::menu-indicator {{
    image: none;
}}
QCalendarWidget QMenu {{
    background-color: white;
    border: 1px solid {COLORS['border']};
}}
QCalendarWidget QSpinBox {{
    background-color: white;
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 2px 6px;
}}
QCalendarWidget QAbstractItemView:enabled {{
    background-color: {COLORS['card_bg']};
    color: {COLORS['text_primary']};
    selection-background-color: {COLORS['accent']};
    selection-color: white;
    outline: none;
}}
QCalendarWidget QAbstractItemView:disabled {{
    color: {COLORS['border']};
}}

/* ---------- 지난 알림장: 날짜 목록 행 ---------- */
QFrame#HistoryDateRow {{
    background-color: {COLORS['card_bg']};
    border: 1px solid {COLORS['border']};
    border-radius: 16px;
}}
QFrame#HistoryDateRow:hover {{
    border: 1.5px solid {COLORS['accent']};
}}
QFrame#HistoryDateRow[active="true"] {{
    background-color: {COLORS['accent']};
    border: 1.5px solid {COLORS['accent']};
}}
QFrame#HistoryDateRow[active="true"] QLabel {{
    color: white;
}}

/* ---------- 안내 콜아웃 박스 ("API 키가 없으신가요?" 등) ---------- */
QFrame#InfoBox {{
    background-color: #F4F7FF;
    border: 1px solid {COLORS['stat_blue_border']};
    border-radius: 12px;
}}
QLabel#InfoBoxTitle {{
    color: {COLORS['text_primary']};
    font-size: 13px;
    font-weight: 700;
}}
QLabel#InfoBoxStep {{
    color: {COLORS['text_primary']};
    font-size: 12.5px;
}}
QLabel#InfoBoxWarning {{
    color: {COLORS['today']};
    font-size: 12.5px;
    font-weight: 600;
}}
"""
