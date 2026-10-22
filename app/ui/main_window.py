# -*- coding: utf-8 -*-
"""메인 윈도우 — 왼쪽 사이드바 네비게이션 + 오른쪽 콘텐츠 영역."""

import os
import subprocess
import sys
import time
import traceback
import urllib.parse
import webbrowser
from datetime import date, datetime

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QStackedWidget, QSystemTrayIcon, QMenu, QApplication
)

from .. import config, db
from ..core import (
    autostart, daily_note, holidays_sync, mascot_settings, session_lock, stats,
    task_manager, update_check,
)
from .common_widgets import Toast
from . import mascot_walker
from .update_modal import UpdateModal
from .update_popup import UpdatePopup
from .dashboard_view import DashboardView
from .task_list_view import TaskListView
from .manual_view import ManualView
from .message_list_view import MessageListView
from .calendar_view import CalendarView
from .history_view import HistoryView
from .ai_settings_dialog import SettingsPageView

def _build_feedback_url() -> str:
    """건의사항 보내기 — mailto: 대신 Gmail 웹 작성 화면을 직접 연다.
    mailto:는 PC에 등록된 기본 메일 앱에 의존하는 구조라 웹메일만 쓰는
    교사 PC에서 불안정했고, 제목에 공백/대괄호/한글을 URL 인코딩 없이
    그대로 넣었던 것도 RFC 6068 위반이라 Chrome이 Gmail 계정 선택
    화면 이후로 못 넘어가는 원인이었다 — su(제목)를 quote()로 정확히
    인코딩해서 넘긴다."""
    to = "jinsko@jungang.hs.kr"
    subject = urllib.parse.quote("[쿨브리핑] 건의사항")
    body = urllib.parse.quote("여기에 건의사항을 적어주세요.\n\n")
    return f"https://mail.google.com/mail/?view=cm&fs=1&to={to}&su={subject}&body={body}"

class _UpdateCheckThread(QThread):
    """version.json 조회는 네트워크 호출이라 메인 스레드(UI)를 막지
    않도록 백그라운드 스레드에서 실행한다. 결과는 시그널로만 돌려주고,
    실제 UI 반영(배너 표시)은 받는 쪽(MainWindow)이 메인 스레드에서
    처리한다 — Qt 위젯은 자신을 만든 스레드가 아닌 곳에서 건드리면
    안 되기 때문이다."""
    resultReady = Signal(object)  # dict(새 버전 있음) 또는 None

    def run(self):
        self.resultReady.emit(update_check.check_for_update())


class _UpdateDownloadThread(QThread):
    """새 버전 안내 배너가 뜨는 시점에 곧바로 시작해서, 사용자가 아직
    아무것도 누르지 않았어도 설치 파일을 미리 받아 둔다. 다운로드와
    SHA256 검증까지 전부 update_check.download_and_verify_update()가
    조용히 흡수한다(실패 원인 불문 None) — 여기서는 그 결과를 시그널로
    메인 스레드에 전달하기만 한다."""
    finishedWithPath = Signal(object)  # pathlib.Path(검증 통과) 또는 None

    def __init__(self, info: dict, parent=None):
        super().__init__(parent)
        self._info = info

    def run(self):
        self.finishedWithPath.emit(update_check.download_and_verify_update(self._info))


class _AutoSyncThread(QThread):
    """'✨ AI 다시 분석' 버튼과 똑같은 작업(sync_messages + analyze_unanalyzed)을
    백그라운드에서 조용히 실행한다. 새 메시지가 없으면 analyze_unanalyzed()의
    분석 대상 목록이 비어서 Gemini API 호출 자체가 안 일어난다(기존 로직
    그대로) — 토큰 절약의 핵심이라 여기서는 손대지 않는다.
    실제 쿨메신저 어댑터는 여기서 직접 골라야 한다 — task_list_view.py의
    on_reanalyze()처럼 데모/실제 모드에 따라 어댑터가 갈리는데, 이 타이머는
    데모 모드에서는 아예 안 돌기 때문에(MainWindow._apply_auto_sync_interval)
    실제 어댑터 하나만 알면 된다."""
    finishedOk = Signal(int, int)   # new_message_count, new_task_count
    finishedError = Signal(str)

    def run(self):
        try:
            from ..adapters.coolmessenger_adapter import CoolMessengerAdapter
            adapter = CoolMessengerAdapter()
            days = int(db.get_setting("analyze_days", "1"))
            new_message_count, image_map = task_manager.sync_messages(adapter, days=days)
            counts = task_manager.analyze_unanalyzed(image_map=image_map)
            self.finishedOk.emit(new_message_count, counts.get("ACTION", 0))
        except Exception as e:
            traceback.print_exc()
            self.finishedError.emit(str(e))


class _HolidaySyncThread(QThread):
    """국가 공휴일 자동 채움(연 1회, data.go.kr)을 백그라운드에서 조용히
    시도한다. holidays_sync.sync_if_needed()가 실패를 전부 내부에서
    흡수하므로 여기서는 결과를 기다리거나 신경 쓸 필요가 없다 — 그래서
    시그널도 없다. 새해 첫 실행 당일에 한해, 이 스레드가 끝나기 전에
    MainWindow._maybe_auto_generate_note()가 먼저 오늘이 휴일인지 판단할
    수 있어 아주 드물게(그날이 실제로는 공휴일인데 아직 못 받아온 경우)
    자동 알림장이 만들어질 수 있다 — 수동 버튼/캘린더 수동 지정으로
    언제든 바로잡을 수 있는 수준이라 감내한다."""

    def run(self):
        holidays_sync.sync_if_needed()


_NAV_ITEMS = [
    ("today", "⌂", "오늘"),
    ("messages", "✉", "메시지"),
    ("tasks", "✓", "업무"),
    ("calendar", "▦", "일정"),
    ("history", "▣", "지난 알림장"),
    ("settings", "⚙", "설정"),
    ("manual", "📖", "사용설명서"),
]

# (하루 중 시각 "HH:MM", 알림 문구 — {n}은 미완료 업무 건수로 채워짐)
_DAILY_REMINDER_TIMES = [
    ("13:20", "점심시간 끝나기 전에 확인해보세요 — 오늘 처리할 업무 {n}건"),
    ("16:10", "퇴근 전에 마지막으로 확인해보세요 — 오늘 처리할 업무 {n}건"),
]

# 화면 잠금을 풀면 파랑새를 '바로' 내보낸다. 다만 잠금 해제 신호 직후엔
# Windows가 아직 "자리 비움(잠금)" 상태로 답하는 순간이 있어, 아주 잠깐
# 뒤에 첫 시도를 하고 아직이면 1초 간격으로 몇 번 더 본다.
_UNLOCK_MASCOT_FIRST_TRY_MS = 400
_UNLOCK_MASCOT_RETRY_MS = 1000
_UNLOCK_MASCOT_MAX_TRIES = 8
# 잠금 해제 뒤 가운데 업데이트 카드를 띄우기까지 기다리는 시간(ms) —
# 파랑새가 먼저 나오고, 카드는 바탕화면이 다 그려진 뒤에 뜨게.
_UNLOCK_UPDATE_POPUP_DELAY_MS = 3000
# 앱이 하루 종일 트레이에 켜져 있어도 낮에 나온 새 버전을 알 수 있도록
# 이 간격마다 version.json을 다시 확인한다.
_UPDATE_RECHECK_INTERVAL_MS = 2 * 60 * 60 * 1000
# 아침에 앱이 처음 켜졌을 때 파랑새를 내보내기까지 기다리는 시간(ms) —
# 로그인 직후 바탕화면·작업표시줄이 다 그려진 뒤에 나오게.
_STARTUP_MASCOT_DELAY_MS = 8000
# "오늘 앱이 처음 켜질 때 파랑새를 이미 내보냈다"는 날짜(YYYY-MM-DD).
# 업데이트 설치 뒤 자동 재시작 등으로 같은 날 다시 켜질 때는 또 나오지
# 않게 한다(그날 잠금 해제·정기 알림 때는 그대로 나온다).
_SETTING_MASCOT_STARTUP_DATE = "mascot_startup_date"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(config.APP_NAME)
        icon_path = config.icon_path()
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setMinimumSize(900, 600)
        self._resize_to_screen()
        self.demo_mode = db.get_setting("demo_mode", "1") == "1"
        # 트레이 메뉴 '프로그램 종료'로만 True가 된다 — X 버튼과 완전
        # 종료를 구분하는 스위치. closeEvent가 이 값으로 판단한다.
        self._force_quit = False
        self.single_instance_guard = None  # main.py에서 채워 넣는다

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 사이드바 ----
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(18, 24, 18, 18)
        side_layout.setSpacing(7)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(12)
        brand_icon = QLabel()
        brand_icon.setObjectName("SidebarBrandIcon")
        icon_path = config.icon_path()
        if icon_path.exists():
            brand_icon.setPixmap(QIcon(str(icon_path)).pixmap(40, 40))
        brand_icon.setAlignment(Qt.AlignCenter)
        brand_icon.setFixedSize(44, 44)
        brand_row.addWidget(brand_icon)

        brand_text = QVBoxLayout()
        brand_text.setSpacing(3)
        title = QLabel(config.APP_NAME)
        title.setObjectName("SidebarTitle")
        title.setWordWrap(True)
        brand_text.addWidget(title)
        subtitle = QLabel("AI가 정리해주는 당신의 하루")
        subtitle.setObjectName("SidebarSubtitle")
        subtitle.setWordWrap(True)
        brand_text.addWidget(subtitle)
        brand_row.addLayout(brand_text, 1)
        side_layout.addLayout(brand_row)

        # 현재 실행 중인 버전과 배포일을 눈에 거슬리지 않는 작은 배지로
        # 보여준다. 클릭 동작은 없다 — 건의사항은 사이드바 하단의
        # 별도 [건의사항 보내기] 버튼(feedback_btn)이 이미 맡고 있다.
        # config.APP_VERSION/APP_RELEASE_DATE를 그대로 읽으므로 다음
        # 버전이 올라가도 여기는 따로 안 고쳐도 된다.
        test_badge = QLabel(f"v{config.APP_VERSION} · {config.APP_RELEASE_DATE}")
        test_badge.setObjectName("TestBadge")
        side_layout.addWidget(test_badge, 0, Qt.AlignLeft)

        side_layout.addSpacing(20)

        self.nav_buttons = {}
        for key, icon, label in _NAV_ITEMS:
            btn = QPushButton(f"{icon}   {label}")
            btn.setObjectName("NavButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("active", False)
            btn.clicked.connect(lambda checked=False, k=key: self.switch_page(k))
            side_layout.addWidget(btn)
            self.nav_buttons[key] = btn

        side_layout.addStretch(1)

        feedback_btn = QPushButton("💌  건의사항 보내기")
        feedback_btn.setObjectName("SidebarFeedbackButton")
        feedback_btn.setCursor(Qt.PointingHandCursor)
        feedback_btn.clicked.connect(lambda: webbrowser.open(_build_feedback_url()))
        side_layout.addWidget(feedback_btn)

        credit_label = QLabel("Made by sseamedu.com")
        credit_label.setObjectName("SidebarCredit")
        credit_label.setAlignment(Qt.AlignCenter)
        credit_label.setWordWrap(True)
        side_layout.addWidget(credit_label)

        root.addWidget(sidebar)

        # ---- 콘텐츠 영역 ----
        content = QWidget()
        content.setObjectName("ContentArea")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        self.pages = {}

        # 새 버전 안내 카드 — "오늘" 탭 안에 파묻혀 있던 인라인 배너 대신
        # 창 어디에 있든(메시지/업무/설정 등 어느 탭이든) 우측 상단에
        # 떠 있는 오버레이로 띄운다. central의 자식으로만 두고 레이아웃엔
        # 넣지 않는다 — 위치는 resizeEvent에서 절대좌표로 직접 잡는다.
        self.update_modal = UpdateModal(central)
        self.update_modal.download_requested.connect(self._on_install_requested)
        self.update_modal.dismiss_requested.connect(self._on_update_dismiss_clicked)
        self.update_modal.closed.connect(self.update_modal.hide)

        # 새 버전을 모니터 가운데에 알리는 카드 — 앱 창이 트레이에 숨어
        # 있어도 보이도록 부모 없는 독립 창으로 만든다(위 update_modal은
        # 앱 창을 열어야만 보인다). 자세한 동작은 update_popup.py 참고.
        self.update_popup = UpdatePopup()
        self.update_popup.install_requested.connect(self._on_install_requested)
        self.update_popup.later_requested.connect(self._on_update_popup_later)
        self._update_popup_waiting = False

        self.dashboard_view = DashboardView(demo_mode=self.demo_mode)
        self.dashboard_view.navigateRequested.connect(self.switch_page)
        self._add_page("today", self.dashboard_view)

        self.task_list_view = TaskListView(demo_mode=self.demo_mode)
        # 업무 완료·일괄 완료·되돌리기 직후 파랑새 말풍선 건수를 바로 맞춘다
        self.task_list_view.tasksChanged.connect(self._refresh_mascot_count)
        self._add_page("tasks", self.task_list_view)

        self.message_list_view = MessageListView()
        self._add_page("messages", self.message_list_view)

        self.calendar_view = CalendarView()
        self._add_page("calendar", self.calendar_view)

        self.history_view = HistoryView()
        self._add_page("history", self.history_view)

        self.settings_view = SettingsPageView()
        self.settings_view.settingsChanged.connect(self._refresh_demo_mode)
        self.settings_view.updateFound.connect(self._on_update_check_result)
        self._add_page("settings", self.settings_view)

        self.manual_view = ManualView()
        self._add_page("manual", self.manual_view)

        content_layout.addWidget(self.stack)
        root.addWidget(content, 1)

        # 자동 확인 결과를 팝업 없이 알리는 토스트. content 위에 겹쳐 뜨는
        # 오버레이라 레이아웃에 넣지 않고 절대 좌표로만 움직인다.
        self.toast = Toast(content)

        self.current_page_key = "today"
        self._last_known_date = date.today()
        self.switch_page("today")

        # 프로그램을 밤새 켜둔 경우: 날짜가 바뀌면 현재 화면을 다시 계산해서 그린다.
        # (분류 자체는 항상 date.today() 기준으로 매번 새로 계산되므로 저장된 값을
        # 고치는 게 아니라 그냥 다시 그리기만 하면 된다.)
        self._date_watch_timer = QTimer(self)
        self._date_watch_timer.timeout.connect(self._check_date_rollover)
        self._date_watch_timer.start(5 * 60 * 1000)  # 5분마다 확인

        # ---- 하루 두 번(13:20/16:10) 정기 알림 ----
        # "오늘 이미 보낸 시각"을 담아 두는 집합 — 자정에 _check_date_rollover가
        # 비워 준다(날짜가 바뀔 때만 리셋해야 다음날 다시 뜬다).
        self._reminder_sent_today = set()
        # 트레이 풍선(showMessage)은 어떤 메시지든 클릭되면 같은
        # messageClicked 시그널 하나로만 알려주므로, 방금 띄운 게
        # 정기 알림이었는지 여기에 표시해 둔다 — 클릭 시 "업무" 화면
        # 이동은 정기 알림에만 해당하고, 트레이 안내 풍선 클릭 때는
        # 그냥 창만 보여주면 된다.
        self._last_tray_message_was_reminder = False
        self._reminder_timer = QTimer(self)
        self._reminder_timer.timeout.connect(self._check_daily_reminders)
        self._reminder_timer.start(60 * 1000)  # 1분마다 확인

        # ---- 놓친 파랑새를 "대기"로 기억했다가 돌아오면 내보내기 ----
        # 13:20/16:10에 화면이 잠겨 있거나(점심시간에 자리 비움) 발표·
        # 전체화면 중이라 파랑새를 못 띄웠으면, 그날 날짜를 대기로 적어
        # 둔다. 화면 잠금이 풀리면(바로) 또는 발표가 끝나 Windows가
        # "알림 받아도 됨"으로 바뀌면(위 1분 타이머) 그때 한 번 걸어간다.
        # 앱 창은 절대 저절로 띄우지 않는다 — 작업 중인 화면을 가로채지
        # 않는다는 원칙. 그날 안에서만 유효하고(자정에 지움), 앱을 껐다
        # 켜면 사라져도 되므로 DB에 저장하지 않는다.
        self._mascot_pending_date = None
        # 잠금 해제마다 1씩 올린다 — 해제 직후 재시도 중에 다시 잠갔다
        # 풀어도 파랑새가 두 번 나오지 않게(_show_mascot_after_unlock).
        self._unlock_mascot_seq = 0
        self._reminder_timer.timeout.connect(self._check_pending_mascot)
        # 잠금·발표 때문에 못 띄운 가운데 업데이트 카드도 같은 1분
        # 타이머로 다시 시도한다(_maybe_show_update_popup 참고).
        self._reminder_timer.timeout.connect(self._maybe_show_update_popup)
        # 세션 알림으로 추적하는 현재 잠금 상태. 앱이 뜨는 시점은 보통
        # 로그인 직후(잠금 아님)라 False로 시작한다. LOCK 이벤트를 놓쳐도
        # 잠금 중에는 SHQueryUserNotificationState가 NOT_PRESENT(1)를
        # 돌려주므로 파랑새가 잠금 화면 뒤로 나가지는 않는다.
        self._screen_locked = False
        self._session_monitor = session_lock.WindowsSessionMonitor(
            int(self.winId()),
            on_lock=self._on_screen_locked,
            on_unlock=self._on_screen_unlocked,
        )
        self._session_monitor.install(QApplication.instance())

        self._setup_tray_icon()
        self._start_update_check()

        # 아침에 컴퓨터를 켜서 앱이 처음 뜨면 파랑새가 한 번 걸어 나온다.
        QTimer.singleShot(_STARTUP_MASCOT_DELAY_MS, self._maybe_startup_mascot)
        # 걸어 다니는 파랑새의 말풍선 건수를 1분마다 최신으로 맞춘다
        # (다 처리해서 0건이 되면 파랑새가 스스로 사라진다).
        self._reminder_timer.timeout.connect(self._refresh_mascot_count)

        # ---- 자동 메시지 확인 타이머 ----
        self._auto_sync_thread = None
        self._auto_sync_timer = QTimer(self)
        self._auto_sync_timer.timeout.connect(self._run_auto_sync)
        self._apply_auto_sync_interval()

        self._pending_auto_note = False
        self._start_holiday_sync()
        self._maybe_auto_generate_note()

    def _apply_auto_sync_interval(self):
        """db의 auto_check_interval_min("0"=끄기)과 demo_mode를 기준으로
        타이머를 다시 맞춘다. 설정 페이지에서 주기를 바꾸거나 데모 모드가
        토글될 때(settingsChanged) 이 메서드가 다시 불려서 바로 반영된다.
        데모 모드에서는 절대 돌리지 않는다 — 실제 쿨메신저가 아니라 매번
        똑같은 예시 메시지만 만드는 MockMessengerAdapter를 백그라운드에서
        계속 돌릴 이유가 없다."""
        self._auto_sync_timer.stop()
        if self.demo_mode:
            return
        interval_min = int(db.get_setting("auto_check_interval_min", "5"))
        if interval_min <= 0:
            return
        self._auto_sync_timer.start(interval_min * 60 * 1000)

    def _run_auto_sync(self):
        if self._auto_sync_thread is not None and self._auto_sync_thread.isRunning():
            return  # 이전 주기가 아직 안 끝났으면 겹쳐 돌리지 않는다
        self._auto_sync_thread = _AutoSyncThread(self)
        self._auto_sync_thread.finishedOk.connect(self._on_auto_sync_ok)
        self._auto_sync_thread.finishedError.connect(self._on_auto_sync_error)
        self._auto_sync_thread.start()

    def _maybe_auto_generate_note(self):
        """평일 자동 알림장 생성. 데모 모드/설정 꺼짐/주말/휴일이거나
        오늘 것이 이미 있으면 조용히 건너뛴다 — [업무] 화면의 수동
        [오늘 알림장 만들기] 버튼은 이 조건과 무관하게 항상 그대로 쓸 수
        있다(db.save_daily_summary()가 upsert라 나중에 수동으로 다시
        만들어도 안전하게 덮어써진다).

        기존 자동 확인 타이머(_apply_auto_sync_interval)는 기본 5분 뒤에야
        처음 돈다 — 그대로 기다리면 자동 알림장이 너무 늦게 만들어지거나,
        그 전에 선생님이 앱을 꺼버리면 아예 안 만들어질 수 있어서 여기서
        _run_auto_sync()를 앱을 켠 즉시 한 번 더 호출한다."""
        if db.get_setting("auto_note_enabled", "1") != "1":
            return
        if self.demo_mode:
            return
        today = date.today()
        if today.weekday() >= 5:
            return
        if db.is_holiday(today.isoformat()):
            return
        if db.get_daily_summary(today.isoformat()) is not None:
            return

        self._pending_auto_note = True
        self._run_auto_sync()

    def _start_holiday_sync(self):
        self._holiday_sync_thread = _HolidaySyncThread(self)
        self._holiday_sync_thread.start()

    def _on_auto_sync_ok(self, new_message_count: int, new_task_count: int):
        db.set_setting("last_auto_check_at", datetime.now().isoformat())

        if new_message_count > 0 or new_task_count > 0:
            if self.current_page_key == "today":
                self.dashboard_view.refresh()
            elif self.current_page_key == "tasks":
                self.task_list_view.refresh()

        toast_parts = []
        if new_task_count > 0:
            toast_parts.append(f"새 업무 {new_task_count}건이 추가되었습니다")

        if self._pending_auto_note:
            self._pending_auto_note = False
            daily_note.generate_and_save_daily_note()
            toast_parts.append("오늘 알림장이 자동으로 만들어졌습니다")

        if toast_parts:
            self.toast.show_message(" · ".join(toast_parts))

    def _on_auto_sync_error(self, message: str):
        # 사용자에게는 조용히 넘어간다 — 팝업 없음, 다음 주기(타이머가
        # 계속 돌고 있으므로 자동)에 다시 시도된다. 콘솔 로그만 남긴다.
        # 이번 시도가 자동 알림장 생성을 위한 최초 동기화였다면(pending
        # 플래그) 그 시도도 실패한 것이므로 플래그만 내리고 넘어간다 —
        # 수동 버튼은 여전히 그대로 쓸 수 있다.
        self._pending_auto_note = False
        print(f"[자동 확인 오류] {message}")

    def _start_update_check(self):
        """앱 시작 시 딱 한 번, 백그라운드에서 새 버전이 있는지 조용히
        확인한다. UPDATE_CHECK_URL이 비어 있거나 네트워크에 문제가
        있으면 update_check.check_for_update()가 그냥 None을 돌려주므로
        여기서는 실패를 신경 쓸 필요가 없다 — 앱 실행에 전혀 영향이
        없어야 한다는 원칙 그대로다."""
        self._pending_update_info = None
        self._verified_installer_path = None
        self._install_after_download = False
        self._update_download_thread = None

        self._update_check_thread = None
        self._recheck_update()

        # 앱이 하루 종일 켜져 있어도(Windows 시작 시 트레이 실행) 낮에 나온
        # 새 버전을 알 수 있게 주기적으로 다시 확인한다.
        self._update_recheck_timer = QTimer(self)
        self._update_recheck_timer.timeout.connect(self._recheck_update)
        self._update_recheck_timer.start(_UPDATE_RECHECK_INTERVAL_MS)

    def _recheck_update(self):
        """version.json을 백그라운드에서 한 번 확인한다. 이전 확인이 아직
        진행 중이면 겹치지 않게 건너뛴다."""
        if self._update_check_thread is not None and self._update_check_thread.isRunning():
            return
        self._update_check_thread = _UpdateCheckThread(self)
        self._update_check_thread.resultReady.connect(self._on_update_check_result)
        self._update_check_thread.start()

    def _on_update_check_result(self, info):
        if not info:
            return
        version = info.get("version", "")
        # 예전 버전의 [다시 안보기]로 DB에 남은 무시 기록은 더 이상 보지
        # 않는다 — 업데이트를 안 하면 컴퓨터를 다시 켤 때마다 알려야 한다.
        same_as_pending = (
            self._pending_update_info is not None
            and self._pending_update_info.get("version") == version
        )
        self._pending_update_info = info
        if not same_as_pending:
            # 카드가 뜨는 시점에 사용자가 아무것도 안 눌러도 미리 조용히
            # 받아 둔다 — [지금 업데이트]를 눌렀을 때 대부분 곧바로
            # 설치가 시작되도록. 같은 버전을 다시 확인한 경우(2시간마다)엔
            # 이미 받아 뒀거나 받는 중이므로 다시 받지 않는다.
            self._start_update_download(info)

        if self._update_popup_snoozed(version):
            # 이번 실행 중에 [나중에]를 눌렀다 — 가운데 카드는 컴퓨터를
            # 다시 켜서 앱이 새로 뜰 때 다시 띄우고, 지금은 앱 창 안의
            # 카드만 보여 둔다(앱을 열면 거기서 업데이트 가능).
            self._show_in_app_update_modal(info)
            return
        if self.update_popup.isVisible():
            return
        self._update_popup_waiting = True
        self._maybe_show_update_popup()

    def _show_in_app_update_modal(self, info: dict):
        # 1분 타이머·2시간 재확인에서 여러 번 불릴 수 있다 — 이미 떠
        # 있으면 다시 그리지 않는다. 다시 그리면 [업데이트 다운로드]를
        # 눌러 '받는 중…'으로 바뀐 버튼이 원래대로 돌아가 버린다.
        if not self.update_modal.isVisible():
            self.update_modal.show_update(info)
            self._position_update_modal()
        if self._install_after_download:
            self.update_modal.set_waiting(True)

    def _update_popup_snoozed(self, version: str) -> bool:
        """[나중에]는 이번 실행 동안만 유효하다(메모리에만 기억). DB에
        남기지 않으므로 업데이트를 안 한 채 컴퓨터를 끄고 켜면 앱이 새로
        뜨면서 가운데 카드가 다시 나온다."""
        return getattr(self, "_update_snoozed_version", None) == version

    def _maybe_show_update_popup(self):
        """가운데 업데이트 카드를 띄울 차례면 띄운다. 화면이 잠겨 있거나
        발표·전체화면 중이면 지금은 건너뛰고(대기 유지), 1분 타이머·잠금
        해제 때 다시 불려서 그때 띄운다 — 학생들 앞 화면에 갑자기 뜨거나
        잠금 화면 뒤에서 아무도 못 보고 지나가지 않게. 대기 중엔 앱 창 안의
        카드는 미리 보여 둔다(앱을 열면 거기서도 업데이트할 수 있게)."""
        if not self._update_popup_waiting or self._pending_update_info is None:
            return
        info = self._pending_update_info
        if self._update_popup_snoozed(info.get("version", "")):
            self._update_popup_waiting = False
            return
        if self._screen_locked or not mascot_walker.can_show_now():
            self._show_in_app_update_modal(info)
            return
        self._update_popup_waiting = False
        try:
            self.update_modal.hide()  # 같은 안내가 두 군데 뜨지 않게
            self.update_popup.show_update(info)
            if self._install_after_download:
                # 앱 창 안 카드에서 이미 [업데이트 다운로드]를 눌러 받는
                # 중이면 가운데 카드도 '받는 중…'으로 맞춘다.
                self.update_popup.set_waiting(True)
            update_check.log_update_event(
                f"[가운데 카드] 표시 — 버전={info.get('version')}"
            )
        except Exception:
            traceback.print_exc()
            self._show_in_app_update_modal(info)

    def _on_update_popup_later(self):
        """가운데 카드의 [나중에]/✕ — 이번 실행 동안은 다시 안 띄우고, 앱
        창 안의 카드로만 남겨 둔다. 업데이트를 안 한 채 컴퓨터를 껐다
        켜면(앱이 새로 뜨면) 가운데 카드가 다시 나온다. 버그 수정이 담긴
        업데이트를 영영 놓치지 않도록 '다시 안 보기'(영구 무시)는 없다."""
        self.update_popup.hide()
        self._update_popup_waiting = False
        if self._pending_update_info is not None:
            version = self._pending_update_info.get("version", "")
            self._update_snoozed_version = version
            update_check.log_update_event(
                f"[가운데 카드] 나중에 — 버전={version}, 앱을 다시 켤 때까지 안 띄움"
            )
            self._show_in_app_update_modal(self._pending_update_info)

    def _start_update_download(self, info: dict):
        if self._update_download_thread is not None and self._update_download_thread.isRunning():
            return
        self._verified_installer_path = None
        self._update_download_thread = _UpdateDownloadThread(info, self)
        self._update_download_thread.finishedWithPath.connect(self._on_update_download_result)
        self._update_download_thread.start()

    def _on_update_download_result(self, path):
        self._verified_installer_path = path
        if not self._install_after_download:
            return
        self._install_after_download = False
        self.update_modal.set_waiting(False)
        self.update_popup.set_waiting(False)
        if path is not None:
            self._run_silent_install(path)
        else:
            # 해시 불일치·네트워크 오류 등 — 조용히 원래 카드 상태로
            # 돌아간다(에러 팝업 없음, [다시 안보기]로 넘어간 것과 동일하게
            # 취급하지는 않고 그냥 버튼만 원상복구, 사용자는 대체 링크로
            # 수동 설치 가능). 왜 실패했는지는 download_and_verify_update()
            # 내부에서 이미 파일을 지우고 조용히 None만 돌려주므로 여기서
            # 원인까지는 알 수 없지만, 적어도 "이 시점에 다운로드가
            # 실패했다"는 사실 자체는 남긴다.
            update_check.log_update_event(
                "[업데이트 다운로드] 대기 중 다운로드 실패 — 카드를 원래 상태로 되돌림"
            )

    def _on_install_requested(self):
        """새 버전 안내 카드의 [업데이트 다운로드] 클릭. 이미 검증까지
        끝난 파일이 준비돼 있으면 곧바로 설치하고, 아직이면(다운로드
        중이거나 이전 시도가 실패해서 대기 중인 파일이 없으면) 대기
        상태를 보여주고 완료되는 대로 자동으로 이어서 설치한다.

        클릭했는데 아무 설치도 안 되고 카드/앱만 조용히 사라지는 문제가
        실제로 보고된 적이 있다 — 재현은 못 했지만(직접 subprocess.Popen
        호출은 정상 동작 확인됨), 가장 유력한 원인은 클릭 시점에
        _pending_update_info가 가리키는 버전이 그 사이 서버에서
        삭제/교체돼(예: 릴리스를 다시 올리는 도중이었다거나) 다운로드가
        조용히 실패하는 경우로 추정된다. 그래서 각 분기가 실제로 어느
        길로 갔는지 로그로 남겨서, 다음에 재발하면 update_debug.log만
        봐도 바로 원인을 알 수 있게 한다."""
        if self._verified_installer_path is not None and self._verified_installer_path.exists():
            update_check.log_update_event("[업데이트 다운로드] 클릭 — 이미 검증된 파일로 즉시 설치")
            self._run_silent_install(self._verified_installer_path)
            return

        self._install_after_download = True
        self.update_modal.set_waiting(True)
        self.update_popup.set_waiting(True)
        if self._update_download_thread is None or not self._update_download_thread.isRunning():
            if self._pending_update_info is not None:
                update_check.log_update_event(
                    f"[업데이트 다운로드] 클릭 — 다운로드 대기 상태로 전환, 버전={self._pending_update_info.get('version')}"
                )
                self._start_update_download(self._pending_update_info)
            else:
                update_check.log_update_event(
                    "[업데이트 다운로드] 클릭 — _pending_update_info가 없어 다운로드를 시작할 수 없음"
                )
        else:
            update_check.log_update_event("[업데이트 다운로드] 클릭 — 이미 진행 중인 다운로드를 기다림")

    def _on_update_dismiss_clicked(self):
        """앱 창 안 새 버전 카드의 [나중에] — 예전엔 '다시 안보기'(영구
        무시)였지만, 업데이트를 안 하면 컴퓨터를 다시 켤 때 또 알려야 해서
        가운데 카드의 [나중에]와 똑같이 이번 실행 동안만 숨긴다."""
        if self._pending_update_info is not None:
            self._update_snoozed_version = self._pending_update_info.get("version", "")
        self.update_modal.hide()
        self.update_popup.hide()
        self._update_popup_waiting = False

    def _run_silent_install(self, installer_path):
        """미리 받아 SHA256까지 검증해 둔 설치 파일을 실행하고, 우리 앱은
        곧바로 완전히 종료한다 — 설치 프로그램이 exe 파일을 덮어써야
        하므로 그 전에 파일 잠금을 풀어야 한다. DB는 요청마다 새로
        연결하고 바로 닫는 구조라(app/db.py의 get_conn()) 별도로 닫아야
        할 지속 연결이 없다 — 자동 확인 타이머만 멈추면 정리는 끝이다.

        /VERYSILENT가 아니라 /SILENT를 쓴다 — 마법사 화면(사용자가 눌러야
        하는 단계)은 여전히 안 뜨지만, 진행률 표시줄은 보여준다. 완전히
        조용하면(/VERYSILENT) 클릭 후 몇 초간 화면에 아무 반응이 없어
        "정말 설치되고 있는 게 맞나" 확인할 방법이 없었다.

        [지금 설치]를 눌러도 아무 일 없이 배너/앱만 사라지고 실제로는
        설치가 안 되는 문제가 실제로 보고됐고, 이번에 원인을 실측으로
        확인했다: PyInstaller onefile 부트로더가 Windows Job Object로
        프로세스를 관리하는데, 여기서 그냥 subprocess.Popen()으로 띄운
        Setup.exe는 그 Job Object에 자식으로 딸려 들어간다 — 그 상태에서
        우리 앱(부모)이 self.close()로 종료하면 Setup.exe까지 함께
        강제 종료돼버린다. 순수 python.exe 스크립트로 직접 띄운
        subprocess.Popen()은 이 문제가 재현되지 않고(Job Object가 없으니
        당연함), 실제 배포된 exe(PowerShell로 띄우든 explorer.exe로
        더블클릭하듯 띄우든 둘 다 동일하게 재현됨)에서만 나타나는 걸
        확인해서 특정했다. CREATE_BREAKAWAY_FROM_JOB 플래그로 Setup.exe를
        그 Job Object에서 명시적으로 떼어내야 우리가 종료된 뒤에도
        살아남는다.

        이 함수는 Qt 시그널 슬롯이라 여기서 예외가 나면(방화벽/백신이
        설치 파일 실행을 막는 경우 등) windowed 빌드는 콘솔이 없어
        예외가 그냥 조용히 사라지고 아무 단서도 안 남는다 — 그래서
        전체를 try/except로 감싸 update_debug.log에 남긴다(사용자에게는
        여전히 팝업을 띄우지 않는다는 원칙은 그대로 유지).

        Popen 호출 자체가 성공해도 Setup.exe가 그 직후에 조용히 죽는
        경우가 실제로 있다는 걸 이번에 확인했다. 재현 실험으로 두 가지
        경로를 확인했다: (1) AppMutex(TeacherAlimjangRunningMutex)를 다른
        프로세스가 아직 쥐고 있으면 Setup은 "이미 실행 중" 확인창을
        띄우려다 /SUPPRESSMSGBOXES 때문에 자동으로 취소 처리되고 EAbort로
        종료한다. (2) 더 미묘하게는, 우리 앱이 self.close()를 부르는
        시점과 PyInstaller onefile 부모 런처 프로세스가 실제로 완전히
        죽어 TeacherAlimjang.exe 이미지 핸들을 놓는 시점 사이에 시차가
        있어서, Setup이 그 사이에 파일을 덮어쓰려 하면 RestartManager가
        "아직 쓰는 중"으로 보고 마찬가지로 조용히 취소될 수 있다(실제
        재현: 방금 배포된 실제 v1.3.2 설치본에서 [지금 설치]를 눌렀을 때
        이 경로로 실패, 반면 같은 파일을 우리 앱이 안 떠 있는 상태에서
        수동으로 실행하면 항상 성공). 두 경우 다 종료 코드를 우리 쪽에서
        확인 안 하면 예외도 안 나고, 사용자 화면엔 배너/앱이 사라지는
        것만 보인다("지금 설치" 눌러도 아무 일 없다는 보고와 정확히
        일치). installer/setup.iss의 InitializeSetup()에 짧은 대기를
        추가해 (2)를 완화했지만, 그래도 실패할 수 있는 경로들이라 Setup
        자체의 /LOG 출력을 우리 진단 폴더에 남겨서 다음에 재발하면 굳이
        재현하지 않아도 Inno Setup이 정확히 어느 단계에서 멈췄는지 바로
        보이게 한다. Popen은 논블로킹이라 기본적으로 이 실패를 알 도리가
        없으므로, 아주 짧게(0.8초) 기다렸다가 그새 죽었는지만 확인해서
        로그를 남긴다 — 정상 설치는 이 시점에 이미 파일 압축 해제
        중이라 절대 이만큼 빨리 안 끝나므로, 체감 속도에는 영향이
        없다."""
        try:
            self._auto_sync_timer.stop()

            # [진단 전용] 설치를 시작하려는 시점에 백그라운드 스레드가
            # 아직 돌고 있는지 확인해 둔다 — self.close()는 새 스레드
            # 시작만 막을 뿐, 이미 돌고 있는 스레드(AI 분석 등)를 기다리지
            # 않으므로, 이 스레드들이 실제로 설치 지연의 원인인지 실측으로
            # 알아보기 위함이다. 동작은 바꾸지 않는다.
            auto_sync_running = self._auto_sync_thread is not None and self._auto_sync_thread.isRunning()
            update_download_running = self._update_download_thread is not None and self._update_download_thread.isRunning()
            holiday_sync_running = getattr(self, "_holiday_sync_thread", None) is not None and self._holiday_sync_thread.isRunning()
            update_check.log_update_event(
                f"[설치 전 점검] _auto_sync_thread 실행 중={auto_sync_running}, "
                f"_update_download_thread 실행 중={update_download_running}, "
                f"_holiday_sync_thread 실행 중={holiday_sync_running}"
            )

            from ..core import single_instance
            single_instance.release_install_mutex()

            installer_log_path = config.app_data_dir() / "installer_last_run.log"
            update_check.log_update_event(
                f"[설치] 실행 시도 경로={installer_path} 로그={installer_log_path}"
            )
            # 우리 자신이 PyInstaller onefile의 "자식" 단계로 떠 있는
            # 프로세스라, _PYI_로 시작하는 내부 환경변수(부모-자식
            # 재실행 단계·임시 압축해제 경로 등)가 이미 우리 환경에
            # 설정돼 있다. subprocess.Popen()은 기본적으로 부모(우리)의
            # 환경을 통째로 물려주므로, 그대로 두면 Setup.exe와 그
            # Setup.exe가 다시 실행하는 새 TeacherAlimjang.exe까지 이
            # 변수를 그대로 물려받는다 — 새로 실행된 앱이 "나는 이미
            # 재실행된 자식 단계"라고 착각해 자기 자신의 정상 1단계
            # 부트스트랩을 건너뛰고 곧장 부모-프로세스 검증에 들어가는데,
            # 그 시점의 실제 부모는 Setup.exe라 검증에 실패해 "Security
            # validation failure: parent process has different
            # executable!" 오류창이 뜬다. Setup.iss 쪽에서 재실행
            # 시점을 늦춰봐도(InitializeSetup/CurStepChanged의 Sleep)
            # 이 문제는 타이밍과 무관하게 100%에 가깝게 재현돼서 원인이
            # 아니었다 — 실제로는 환경변수 오염이었다. Setup.exe를 띄울
            # 때 _PYI_ 변수를 지운 깨끗한 환경을 넘겨서, Setup.exe와
            # 그 자식 모두 우리 프로세스의 내부 상태를 물려받지 않게
            # 한다.
            clean_env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI")}
            proc = subprocess.Popen(
                [
                    str(installer_path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                    f"/LOG={installer_log_path}",
                ],
                close_fds=True,
                creationflags=subprocess.CREATE_BREAKAWAY_FROM_JOB,
                env=clean_env,
            )
            time.sleep(0.8)
            returncode = proc.poll()
            if returncode is not None:
                update_check.log_update_event(
                    f"[설치] 실행 직후 이미 종료됨 returncode={returncode} — "
                    "설치가 시작도 못했을 가능성 높음(다른 인스턴스가 AppMutex를 "
                    "쥐고 있거나, 손상된 설치 파일 등)"
                )
            else:
                update_check.log_update_event(f"[설치] 실행 확인됨 PID={proc.pid}, 앱 종료 진행")
        except Exception as e:
            update_check.log_update_event(
                f"[설치] 실행 실패: {type(e).__name__}: {e} (경로: {installer_path})"
            )
            # 설치 파일이 그새 지워졌다거나, 실행 자체가 막힌 경우 —
            # 조용히 포기. 팝업 없음, 배너는 [지금 설치]를 다시 누를 수
            # 있는 상태로 남는다(앱을 안 닫았으므로).
            return

        # setup.iss [Run]에서 skipifsilent를 빼 뒀으므로, 설치가 끝나면
        # 새 exe가 자동으로 다시 실행된다 — 여기서는 우리 자신만 완전히
        # 종료하면 된다(installer/setup.iss의 AppMutex가 우리 exe를
        # "실행 중"으로 오인하지 않도록 뮤텍스는 위에서 이미 풀었다).
        # WizardSilent()는 /SILENT·/VERYSILENT 둘 다에서 True이므로 이
        # 자동 재실행 로직 자체는 그대로 동작한다.

        # [진단 전용] self.close() 직전 상태를 한 번 더 남긴다 — 위쪽
        # 점검 이후 Popen/Sleep(0.8초) 사이에 스레드가 끝났는지, 아니면
        # 여전히 돌고 있는 채로 종료를 요청하는 건지 구분하기 위함이다.
        # 이 로그 줄의 타임스탬프(log_update_event가 자동으로 남김)가 곧
        # "몇 시 몇 분 몇 초에 설치를 시작하려 했는지"이며, 이후
        # installer_last_run.log의 WaitForProcessToExit 로그와 시간을
        # 맞춰볼 수 있다.
        auto_sync_running_at_close = self._auto_sync_thread is not None and self._auto_sync_thread.isRunning()
        update_download_running_at_close = self._update_download_thread is not None and self._update_download_thread.isRunning()
        holiday_sync_running_at_close = getattr(self, "_holiday_sync_thread", None) is not None and self._holiday_sync_thread.isRunning()
        update_check.log_update_event(
            f"[설치 전 점검] self.close() 호출 직전 — _auto_sync_thread 실행 중={auto_sync_running_at_close}, "
            f"_update_download_thread 실행 중={update_download_running_at_close}, "
            f"_holiday_sync_thread 실행 중={holiday_sync_running_at_close}"
        )

        self._force_quit = True
        self.close()

    def _resize_to_screen(self):
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(1080, 720)
            return
        available = screen.availableGeometry()
        width = min(int(available.width() * 0.75), 1200)
        height = min(int(available.height() * 0.80), 800)
        width = max(width, 900)
        height = max(height, 600)
        self.resize(width, height)

        frame_geo = self.frameGeometry()
        frame_geo.moveCenter(available.center())
        self.move(frame_geo.topLeft())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # __init__ 초반의 _resize_to_screen() 호출 시점엔 update_modal이
        # 아직 안 만들어져 있으므로(centralWidget 구성 전) 방어적으로
        # getattr로 확인한다.
        if getattr(self, "update_modal", None) is not None:
            self._position_update_modal()

    def _position_update_modal(self):
        """새 버전 안내 카드를 창 우측 상단(여백 24px)에 절대좌표로 둔다
        — 레이아웃에 들어있지 않으므로 창 크기가 바뀔 때마다(resizeEvent)
        또는 카드가 새로 뜰 때(show_update 직후) 직접 다시 계산해야 한다."""
        central = self.centralWidget()
        if central is None:
            return
        self.update_modal.adjustSize()
        margin = 24
        x = central.width() - self.update_modal.width() - margin
        self.update_modal.move(max(x, 0), margin)
        self.update_modal.raise_()

    def _add_page(self, key: str, widget: QWidget):
        self.pages[key] = widget
        self.stack.addWidget(widget)

    def switch_page(self, key: str, filter_key: str = ""):
        """filter_key: '업무' 화면으로 이동할 때만 의미 있음 — 대시보드 카드
        클릭처럼 특정 필터 탭을 자동으로 선택시켜야 할 때 넘긴다."""
        for k, btn in self.nav_buttons.items():
            btn.setProperty("active", k == key)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        widget = self.pages[key]
        self.stack.setCurrentWidget(widget)
        # QStackedWidget에 숨겨진 채로 생성됐다가 처음 표시되는 위젯은
        # 자식(특히 버튼) 텍스트가 첫 페인트에서 비어 보이는 경우가 있어
        # 표시될 때마다 강제로 다시 그리게 한다.
        for child in widget.findChildren(QWidget):
            child.style().unpolish(child)
            child.style().polish(child)
            child.update()
        widget.update()
        self.current_page_key = key
        if key == "today":
            self.dashboard_view.refresh()
        elif key == "tasks":
            self.task_list_view.refresh()
            if filter_key:
                self.task_list_view.select_filter(filter_key)
        elif key == "messages":
            self.message_list_view.refresh()
        elif key == "calendar":
            self.calendar_view.refresh()
        elif key == "history":
            self.history_view.refresh()
        elif key == "settings":
            self.settings_view.refresh()

    def _check_date_rollover(self):
        today = date.today()
        if today != self._last_known_date:
            self._last_known_date = today
            self._reminder_sent_today = set()
            self._mascot_pending_date = None
            self.switch_page(self.current_page_key)

    def _check_daily_reminders(self):
        """1분마다 불려서 지금 시각이 13:20/16:10인지 확인한다. 데모
        모드에서는 실제 업무가 아니라 가짜 예시라 알림을 안 울린다.
        미완료 업무가 0건이면 그 시각엔 아예 안 띄운다 — 그래도 "오늘
        이 시각은 처리했다"는 표시는 남겨서, 잠깐 뒤에 새 업무가
        생기더라도 같은 시각에 두 번 뜨는 일은 없게 한다."""
        if self.demo_mode:
            return
        now_str = datetime.now().strftime("%H:%M")
        for time_str, template in _DAILY_REMINDER_TIMES:
            if now_str != time_str or time_str in self._reminder_sent_today:
                continue
            self._reminder_sent_today.add(time_str)
            count = len(stats.todo_tasks())
            if count >= 1:
                self._show_reminder_notification(template.format(n=count))
                # 파랑새는 설정 → 일반에서 이 시각을 켜 둔 경우에만(트레이 알림은 항상)
                if mascot_settings.is_on(time_str):
                    self._start_mascot(count)

    def _show_reminder_notification(self, message: str):
        """정기 알림(13:20/16:10)을 여러 채널로 동시에 알린다. 트레이
        풍선 하나만 믿으면 8초 뒤 사라지거나, Windows 알림 설정(방해
        금지 모드 등)에 따라 아예 안 뜨는 경우까지 있어 놓치기 쉬웠다.

        - 작업표시줄 아이콘 깜빡임(QApplication.alert): 창을 다시
          클릭하기 전까지 계속 유지되므로, "아까 뭔가 왔었다"는 걸
          나중에 봐도 알 수 있다 — Windows 알림 설정과 무관하게 항상
          동작한다.
        - 알림음(QApplication.beep): 청각으로도 알 수 있게.
        - 창이 트레이로 숨겨지지 않고 열려 있으면(self.isVisible()) 인앱
          토스트도 같이 띄운다 — 트레이 풍선은 화면 구석에 작게만
          나타나 놓치기 쉬운데, 토스트는 창 안에서 더 눈에 띈다.
        - 트레이 풍선(창이 숨겨져 있을 때를 대비한 채널)은 그대로 유지하되
          표시 시간을 8초 -> 12초로 늘린다."""
        QApplication.beep()
        QApplication.alert(self)

        if self.isVisible():
            self.toast.show_message(message, duration_ms=6000)

        if not getattr(self, "tray_icon", None):
            return
        self._last_tray_message_was_reminder = True
        self.tray_icon.showMessage(
            config.APP_NAME, message, QSystemTrayIcon.Information, 12000
        )

    def _start_mascot(self, count: int):
        """정기 알림과 함께 마스코트(파랑새)를 작업표시줄 위로 걸어가게
        한다. 설정에서 꺼져 있거나 데모 모드면 아무것도 안 한다. 화면
        잠금·화면보호기·발표·전체화면 중이라 지금 못 띄우면 "대기"로
        적어 두고, 나중에 _release_pending_mascot이 내보낸다(트레이 풍선
        알림은 호출부에서 이미 나갔으므로 알림 자체는 남는다). 이미지가
        없는 등 어떤 이유로든 실패해도 앱은 계속 동작해야 하므로 예외는
        로그만 남기고 삼킨다."""
        if not mascot_settings.master_on() or self.demo_mode:
            return
        if self._screen_locked or not mascot_walker.can_show_now():
            # 13:20과 16:10을 둘 다 놓쳐도 대기는 날짜 하나뿐이라 파랑새는
            # 한 번만 나온다.
            self._mascot_pending_date = date.today()
            return
        self._mascot_pending_date = None
        old = getattr(self, "_mascot", None)
        if old is not None and old.is_active():
            # 이미 화면을 왔다 갔다 하고 있다(클릭할 때까지 안 사라지므로
            # 흔한 일) — 새로 만들어 왼쪽 끝으로 순간이동시키지 말고 건수만
            # 맞춘다. 발표·잠금 때문에 잠깐 숨어 있었다면 스스로 다시 나온다.
            try:
                old.set_count(stats.today_todo_count())
                return
            except RuntimeError:
                self._mascot = None  # 이미 정리된 위젯 — 새로 띄운다
        try:
            # 말풍선 숫자는 '업무' 화면 '오늘까지' 탭과 같은 건수다. 파랑새를
            # 내보낼지는 호출부가 전체 미완료 업무(count)로 이미 판단했다.
            walker = mascot_walker.MascotWalker(stats.today_todo_count())
            walker.clicked.connect(self._on_mascot_clicked)
            # 닫힌 게 '지금 걷고 있는 그 마스코트'일 때만 참조를 지운다 —
            # 이전 마스코트가 늦게 정리되면서 새 마스코트 참조를 지우지 않게.
            walker.destroyed.connect(
                lambda *_, w=walker: setattr(self, "_mascot", None)
                if getattr(self, "_mascot", None) is w else None
            )
            self._mascot = walker
            walker.start()
        except Exception:
            traceback.print_exc()

    def _on_mascot_clicked(self):
        """마스코트를 누르면 앱 창을 띄우고 '오늘' 화면을 보여준다 —
        트레이에 숨어 있었든 다른 창 뒤에 있었든 맨 앞으로 나온다.
        show_and_activate가 Windows에서 _win_bring_to_front까지 불러
        포그라운드 제한을 넘어 확실히 맨 앞으로 올린다(실패하면 조용히
        일반 activateWindow 동작으로 남는다)."""
        self.show_and_activate()
        self.switch_page("today")

    # ---------- 놓친 파랑새 대기 ----------

    def _has_pending_mascot(self) -> bool:
        """오늘 날짜로 대기 중인 파랑새가 있는지. 자정 직후
        _check_date_rollover가 아직 안 돌았어도 어제 대기는 무효다."""
        return self._mascot_pending_date == date.today()

    def _check_pending_mascot(self):
        """1분마다 불린다(정기 알림 타이머와 같은 타이머). 대기 중인데
        발표·전체화면이 끝나 지금 띄워도 되는 상태가 됐으면 내보낸다."""
        if self._has_pending_mascot():
            self._release_pending_mascot()

    def _release_pending_mascot(self):
        """대기 중인 파랑새를 내보낸다. 아직 잠겨 있거나 발표 중이면
        대기를 그대로 두고 다음 기회(잠금 해제·1분 타이머)를 기다린다.
        업무 개수는 출발 직전에 다시 센다 — 그사이 다 처리해서 0건이면
        띄우지 않고 대기만 지운다. 말풍선 숫자도 이때 센 값이다."""
        if not self._has_pending_mascot():
            self._mascot_pending_date = None
            return
        if not mascot_settings.master_on() or self.demo_mode:
            self._mascot_pending_date = None
            return
        if self._screen_locked or not mascot_walker.can_show_now():
            return
        count = len(stats.todo_tasks())
        if count < 1:
            self._mascot_pending_date = None
            return
        self._start_mascot(count)  # 출발하면 여기서 대기가 지워진다

    def _maybe_startup_mascot(self):
        """아침에 컴퓨터를 켜서 앱이 그날 처음 뜨면 파랑새를 한 번 내보낸다.
        같은 날 다시 켜질 때(업데이트 뒤 자동 재시작 등)는 안 나온다.
        로그인 직후엔 Windows가 잠깐 '자리 비움'으로 답할 수 있어 잠금
        해제 때와 같은 재시도 경로를 쓴다."""
        if not mascot_settings.is_on(mascot_settings.STARTUP):
            return
        today = date.today().isoformat()
        if db.get_setting(_SETTING_MASCOT_STARTUP_DATE, "") == today:
            return
        db.set_setting(_SETTING_MASCOT_STARTUP_DATE, today)
        self._unlock_mascot_seq = getattr(self, "_unlock_mascot_seq", 0) + 1
        self._show_mascot_after_unlock(self._unlock_mascot_seq, 1)

    def _refresh_mascot_count(self):
        """1분마다 — 걸어 다니는 파랑새가 있으면 말풍선의 '오늘까지' 건수를
        최신으로 맞춘다. 미완료 업무가 하나도 안 남으면 파랑새를 닫는다."""
        walker = getattr(self, "_mascot", None)
        if walker is None:
            return
        try:
            if not walker.is_active():
                self._mascot = None
                return
            if len(stats.todo_tasks()) < 1:
                walker.close()
                return
            walker.set_count(stats.today_todo_count())
        except RuntimeError:
            self._mascot = None
        except Exception:
            traceback.print_exc()

    def _on_screen_locked(self):
        self._screen_locked = True

    def _on_screen_unlocked(self):
        """잠금 해제 = 선생님이 자리에 돌아왔다는 뜻. 할 일이 1건 이상이면
        (정기 알림 시각과 상관없이) 잠금을 풀 때마다 파랑새가 바로 주
        모니터 왼쪽에 나타나 걸어간다. 앱 창은 띄우지 않는다 — 파랑새를
        눌러야 열린다."""
        self._screen_locked = False
        self._unlock_mascot_seq = getattr(self, "_unlock_mascot_seq", 0) + 1
        seq = self._unlock_mascot_seq
        # '화면 잠금을 풀 때'를 꺼 두었어도, 잠금 때문에 못 나온 13:20·16:10
        # 파랑새(대기)는 이때 내보낸다.
        if mascot_settings.is_on(mascot_settings.UNLOCK) or self._has_pending_mascot():
            QTimer.singleShot(
                _UNLOCK_MASCOT_FIRST_TRY_MS,
                lambda: self._show_mascot_after_unlock(seq, 1),
            )
        if self._update_popup_waiting:
            QTimer.singleShot(_UNLOCK_UPDATE_POPUP_DELAY_MS, self._maybe_show_update_popup)

    def _show_mascot_after_unlock(self, seq: int, attempt: int):
        """잠금 해제 직후 파랑새를 내보낸다. 놓친 정기 알림(대기)도 이걸로
        함께 처리된다 — 한 번만 나온다. 해제 직후 Windows가 아직 '자리
        비움'으로 답하면 1초 간격으로 몇 번 더 보고, 그래도 발표·전체화면
        중이면 이번 해제 때는 띄우지 않는다(대기가 있으면 1분 타이머가
        나중에 내보낸다)."""
        if seq != getattr(self, "_unlock_mascot_seq", 0) or self._screen_locked:
            return  # 그사이 다시 잠갔거나 더 새로운 해제가 있었다
        if not mascot_settings.master_on() or self.demo_mode:
            self._mascot_pending_date = None
            return
        if not mascot_walker.can_show_now():
            if attempt < _UNLOCK_MASCOT_MAX_TRIES:
                QTimer.singleShot(
                    _UNLOCK_MASCOT_RETRY_MS,
                    lambda: self._show_mascot_after_unlock(seq, attempt + 1),
                )
            return
        try:
            count = len(stats.todo_tasks())
        except Exception:
            traceback.print_exc()
            return
        if count < 1:
            self._mascot_pending_date = None
            return
        self._start_mascot(count)  # 대기가 있었으면 여기서 함께 지워진다

    def _on_tray_message_clicked(self):
        """트레이 풍선 알림을 클릭했을 때. 정기 알림이었으면 창을
        복원하면서 곧바로 '업무' 화면으로 이동하고, 그 외(트레이 숨김
        안내 등)는 창만 복원한다."""
        self.show_and_activate()
        if self._last_tray_message_was_reminder:
            self._last_tray_message_was_reminder = False
            self.switch_page("tasks")

    def _open_settings_from_tray(self):
        """트레이 메뉴 '설정' — 창이 트레이에 숨겨진 상태(자동 시작 등)
        일 수 있으니 먼저 창을 보여준 뒤 설정 페이지로 전환한다."""
        self.show_and_activate()
        self.switch_page("settings")

    def _refresh_demo_mode(self):
        """SettingsPageView.settingsChanged가 울릴 때마다 불린다 — 데모
        모드뿐 아니라 자동 확인 주기도 그 자리에서 같이 바뀌었을 수
        있으니(둘 다 Gemini AI/메신저 설정 모달에서 바뀜) 타이머도
        여기서 같이 다시 맞춘다."""
        self.demo_mode = db.get_setting("demo_mode", "1") == "1"
        self.dashboard_view.demo_mode = self.demo_mode
        self.task_list_view.demo_mode = self.demo_mode
        self._apply_auto_sync_interval()

    # ---------- 시스템 트레이 ----------

    def _setup_tray_icon(self):
        self._tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        if not self._tray_available:
            # 트레이를 쓸 수 없는 드문 환경(트레이가 꺼진 Windows 설정 등) —
            # 이때는 X 버튼이 곧 완전 종료로 폴백한다(closeEvent 참고).
            # 그렇지 않으면 창을 숨겨도 다시 열 방법이 없어진다.
            return

        icon_path = config.icon_path()
        icon = QIcon(str(icon_path)) if icon_path.exists() else self.windowIcon()

        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip(config.APP_NAME)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.messageClicked.connect(self._on_tray_message_clicked)

        menu = QMenu()

        open_action = menu.addAction(f"{config.APP_NAME} 열기")
        open_action.triggered.connect(self.show_and_activate)

        menu.addSeparator()

        self.autostart_action = menu.addAction("Windows 시작 시 자동 실행")
        self.autostart_action.setCheckable(True)
        self.autostart_action.toggled.connect(self._on_toggle_autostart)
        menu.aboutToShow.connect(self._sync_autostart_action)

        settings_action = menu.addAction("설정")
        settings_action.triggered.connect(self._open_settings_from_tray)

        menu.addSeparator()

        quit_action = menu.addAction("프로그램 종료")
        quit_action.triggered.connect(self.quit_application)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def _sync_autostart_action(self):
        """트레이 메뉴를 열 때마다 실제 레지스트리 상태로 체크 표시를
        다시 맞춘다 — 설정 화면에서 바꿨을 수도 있으니 메뉴 자체가
        별도 상태를 들고 있지 않고 항상 레지스트리를 다시 물어본다."""
        self.autostart_action.blockSignals(True)
        self.autostart_action.setChecked(autostart.is_enabled())
        self.autostart_action.blockSignals(False)

    def _on_toggle_autostart(self, checked: bool):
        autostart.set_enabled(checked)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_and_activate()

    def show_and_activate(self):
        """트레이 더블클릭·바탕화면 아이콘 재실행(Single Instance IPC)·
        설정 메뉴·파랑새 클릭 등 '창을 다시 보여달라'는 모든
        경로가 이 메서드 하나로 모인다. 최소화·숨김·다른 창 뒤에 가려짐
        등 어떤 상태였든 정상 복원한다.

        Windows는 포그라운드가 아닌 프로세스가 자기 창을 맨 앞으로
        끌어올리는 걸 막는다 — self.activateWindow()(내부적으로
        SetForegroundWindow)가 조용히 무시되고 작업표시줄 버튼만
        깜빡인다. 다른 앱(브라우저 등)이 포그라운드를 쥔 상태에서 이
        창을 띄우려 하면 바로 이 상황이라, 창이 뒤에 가린 채 안
        보였다(실측 확인). 파랑새는 포커스를 안 받는 창이라 그걸 눌러도
        같은 일이 생길 수 있다. 그래서
        Windows에서는 _win_bring_to_front()로 한 번 더 확실하게
        끌어올린다."""
        if self.isMinimized():
            self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.show()
        self.raise_()
        self.activateWindow()
        if sys.platform.startswith("win"):
            self._win_bring_to_front()

    def _win_bring_to_front(self):
        """Windows 전용: SetForegroundWindow 제한과 무관하게 창을 실제로
        화면 맨 앞에 올린다.

        1) 포그라운드 스레드에 우리 스레드의 입력 큐를 잠깐 붙였다(Attach
           ThreadInput) SetForegroundWindow를 부르면 제한이 풀린다 —
           끝나면 바로 뗀다.
        2) 그것마저 막혀도, '항상 위(topmost)'로 잠깐 올렸다가 곧바로
           해제하면 포커스와 무관하게 z-순서 맨 위로 온다.
        전부 best-effort — 실패해도 예외를 삼키고 넘어간다(적어도
        activateWindow()까지는 이미 했다)."""
        try:
            import ctypes

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            hwnd = int(self.winId())

            HWND_TOPMOST = -1
            HWND_NOTOPMOST = -2
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            no_move_size = SWP_NOMOVE | SWP_NOSIZE

            fg = user32.GetForegroundWindow()
            fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
            our_tid = kernel32.GetCurrentThreadId()
            attached = False
            try:
                if fg_tid and fg_tid != our_tid:
                    attached = bool(user32.AttachThreadInput(fg_tid, our_tid, True))
                user32.SetForegroundWindow(hwnd)
            finally:
                if attached:
                    user32.AttachThreadInput(fg_tid, our_tid, False)

            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, no_move_size | SWP_NOACTIVATE)
            user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, no_move_size | SWP_NOACTIVATE)
        except Exception:
            pass

    def start_hidden_in_tray(self):
        """Windows 자동 시작으로 실행된 경우 main.py가 호출한다. 트레이
        아이콘은 __init__에서 이미 준비돼 있으니 여기서는 창을 그냥
        띄우지 않고 둔다 — 의도를 코드로 분명히 남기기 위한 메서드."""
        pass

    def _maybe_show_tray_notice(self):
        """트레이로 숨을 때 최초 1회만 풍선 안내를 띄운다. 체크박스로
        '다시 보지 않기'를 물어보는 대신, 애초에 딱 한 번만 뜨고
        영구히 다시 안 뜨게 만드는 쪽이 Windows 트레이 앱들의 표준
        관례(Dropbox/Slack 등)라 더 자연스럽다고 판단했다."""
        if not getattr(self, "tray_icon", None):
            return
        if db.get_setting("tray_notice_dismissed", "0") == "1":
            return
        self._last_tray_message_was_reminder = False
        self.tray_icon.showMessage(
            config.APP_NAME,
            "이 프로그램은 시스템 트레이에서 계속 실행됩니다.\n"
            "오른쪽 아래 알림 영역의 아이콘을 클릭하면 다시 열 수 있습니다.",
            QSystemTrayIcon.Information,
            4000,
        )
        db.set_setting("tray_notice_dismissed", "1")

    def _cleanup_before_quit(self):
        if getattr(self, "_session_monitor", None):
            self._session_monitor.remove()
        if getattr(self, "tray_icon", None):
            self.tray_icon.hide()
        # 부모 없는 독립 창이라 앱 창과 같이 닫히지 않는다 — 직접 숨긴다.
        if getattr(self, "update_popup", None) is not None:
            self.update_popup.hide()
        QApplication.instance().quit()

    def quit_application(self):
        """트레이 메뉴 '프로그램 종료' 전용 — X 버튼과 달리 트레이
        아이콘까지 완전히 내리고 프로세스를 끝낸다."""
        self._force_quit = True
        self.close()

    def closeEvent(self, event):
        if self._force_quit:
            event.accept()
            self._cleanup_before_quit()
            return

        if not getattr(self, "_tray_available", False):
            # 트레이가 없는 환경에선 숨겨봐야 다시 열 방법이 없으므로
            # X 버튼이 곧 완전 종료다.
            self._force_quit = True
            event.accept()
            self._cleanup_before_quit()
            return

        if db.get_setting("close_action", "tray") == "quit":
            self._force_quit = True
            event.accept()
            self._cleanup_before_quit()
            return

        event.ignore()
        self.hide()
        self._maybe_show_tray_notice()
