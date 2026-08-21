# -*- coding: utf-8 -*-
"""메인 윈도우 — 왼쪽 사이드바 네비게이션 + 오른쪽 콘텐츠 영역."""

import subprocess
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
from ..core import autostart, stats, task_manager, update_check
from .common_widgets import Toast
from .dashboard_view import DashboardView
from .task_list_view import TaskListView
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
    to = "jinkso@jungang.hs.kr"
    subject = urllib.parse.quote("[교사업무 AI 알림장] 건의사항")
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


_NAV_ITEMS = [
    ("today", "⌂", "오늘"),
    ("messages", "✉", "메시지"),
    ("tasks", "✓", "업무"),
    ("calendar", "▦", "일정"),
    ("history", "▣", "지난 알림장"),
    ("settings", "⚙", "설정"),
]

# (하루 중 시각 "HH:MM", 알림 문구 — {n}은 미완료 업무 건수로 채워짐)
_DAILY_REMINDER_TIMES = [
    ("13:20", "점심시간 끝나기 전에 확인해보세요 — 오늘 처리할 업무 {n}건"),
    ("14:10", "퇴근 전에 마지막으로 확인해보세요 — 오늘 처리할 업무 {n}건"),
]


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
        brand_icon = QLabel("✓")
        brand_icon.setObjectName("SidebarBrandIcon")
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

        # 지금은 테스트 배포 단계 — 눈에 거슬리지 않는 작은 배지로만
        # 표시하고, 누르면 바로 건의사항 메일 작성창이 열리게 해서
        # 테스트 참여 선생님이 문제를 발견하면 바로 보낼 수 있게 한다.
        test_badge = QPushButton("🧪 테스트 버전")
        test_badge.setObjectName("TestBadge")
        test_badge.setCursor(Qt.PointingHandCursor)
        test_badge.setToolTip("테스트 배포 버전입니다. 눌러서 건의사항을 보내주세요.")
        test_badge.clicked.connect(lambda: webbrowser.open(_build_feedback_url()))
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

        credit_label = QLabel("Made by Gosussam")
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

        self.dashboard_view = DashboardView(demo_mode=self.demo_mode)
        self.dashboard_view.navigateRequested.connect(self.switch_page)
        self.dashboard_view.installUpdateRequested.connect(self._on_install_requested)
        self._add_page("today", self.dashboard_view)

        self.task_list_view = TaskListView(demo_mode=self.demo_mode)
        self._add_page("tasks", self.task_list_view)

        self.message_list_view = MessageListView()
        self._add_page("messages", self.message_list_view)

        self.calendar_view = CalendarView()
        self._add_page("calendar", self.calendar_view)

        self.history_view = HistoryView()
        self._add_page("history", self.history_view)

        self.settings_view = SettingsPageView()
        self.settings_view.settingsChanged.connect(self._refresh_demo_mode)
        self._add_page("settings", self.settings_view)

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

        # ---- 하루 두 번(13:20/14:10) 정기 알림 ----
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

        self._setup_tray_icon()
        self._start_update_check()

        # ---- 자동 메시지 확인 타이머 ----
        self._auto_sync_thread = None
        self._auto_sync_timer = QTimer(self)
        self._auto_sync_timer.timeout.connect(self._run_auto_sync)
        self._apply_auto_sync_interval()

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

    def _on_auto_sync_ok(self, new_message_count: int, new_task_count: int):
        db.set_setting("last_auto_check_at", datetime.now().isoformat())

        if new_message_count > 0 or new_task_count > 0:
            if self.current_page_key == "today":
                self.dashboard_view.refresh()
            elif self.current_page_key == "tasks":
                self.task_list_view.refresh()

        if new_task_count > 0:
            self.toast.show_message(f"새 업무 {new_task_count}건이 추가되었습니다")

    def _on_auto_sync_error(self, message: str):
        # 사용자에게는 조용히 넘어간다 — 팝업 없음, 다음 주기(타이머가
        # 계속 돌고 있으므로 자동)에 다시 시도된다. 콘솔 로그만 남긴다.
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

        self._update_check_thread = _UpdateCheckThread(self)
        self._update_check_thread.resultReady.connect(self._on_update_check_result)
        self._update_check_thread.start()

    def _on_update_check_result(self, info):
        if not info:
            return
        version = info.get("version", "")
        if update_check.is_version_ignored(version):
            return
        self._pending_update_info = info
        self.dashboard_view.show_update_banner(info)
        # 배너가 뜨는 시점에 사용자가 아무것도 안 눌러도 미리 조용히
        # 받아 둔다 — [지금 설치]를 눌렀을 때 대부분 곧바로 설치가
        # 시작되도록.
        self._start_update_download(info)

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
        self.dashboard_view.set_update_waiting(False)
        if path is not None:
            self._run_silent_install(path)
        # path가 None이면(해시 불일치·네트워크 오류 등) 조용히 원래 배너
        # 상태로 돌아간다 — 에러 팝업 없음, [나중에]로 넘어간 것과
        # 동일하게 취급(사용자는 대체 링크로 수동 설치 가능).

    def _on_install_requested(self):
        """대시보드 배너의 [지금 설치] 클릭. 이미 검증까지 끝난 파일이
        준비돼 있으면 곧바로 설치하고, 아직이면(다운로드 중이거나 이전
        시도가 실패해서 대기 중인 파일이 없으면) 대기 상태를 보여주고
        완료되는 대로 자동으로 이어서 설치한다."""
        if self._verified_installer_path is not None and self._verified_installer_path.exists():
            self._run_silent_install(self._verified_installer_path)
            return

        self._install_after_download = True
        self.dashboard_view.set_update_waiting(True)
        if self._update_download_thread is None or not self._update_download_thread.isRunning():
            if self._pending_update_info is not None:
                self._start_update_download(self._pending_update_info)

    def _run_silent_install(self, installer_path):
        """미리 받아 SHA256까지 검증해 둔 설치 파일을 조용한 옵션으로
        실행하고, 우리 앱은 곧바로 완전히 종료한다 — 설치 프로그램이
        exe 파일을 덮어써야 하므로 그 전에 파일 잠금을 풀어야 한다.
        DB는 요청마다 새로 연결하고 바로 닫는 구조라(app/db.py의
        get_conn()) 별도로 닫아야 할 지속 연결이 없다 — 자동 확인
        타이머만 멈추면 정리는 끝이다."""
        self._auto_sync_timer.stop()

        from ..core import single_instance
        single_instance.release_install_mutex()

        try:
            subprocess.Popen(
                [str(installer_path), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                close_fds=True,
            )
        except OSError:
            # 설치 파일이 그새 지워졌다거나 하는 경우 — 조용히 포기.
            # 팝업 없음, 배너는 [지금 설치]를 다시 누를 수 있는 상태로 남는다.
            return

        # setup.iss [Run]에서 skipifsilent를 빼 뒀으므로, 조용한 설치가
        # 끝나면 새 exe가 자동으로 다시 실행된다 — 여기서는 우리 자신만
        # 완전히 종료하면 된다(installer/setup.iss의 AppMutex가 우리
        # exe를 "실행 중"으로 오인하지 않도록 뮤텍스는 위에서 이미 풀었다).
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
            self.switch_page(self.current_page_key)

    def _check_daily_reminders(self):
        """1분마다 불려서 지금 시각이 13:20/14:10인지 확인한다. 데모
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

    def _show_reminder_notification(self, message: str):
        if not getattr(self, "tray_icon", None):
            return
        self._last_tray_message_was_reminder = True
        self.tray_icon.showMessage(
            config.APP_NAME, message, QSystemTrayIcon.Information, 8000
        )

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
        설정 메뉴 등 '창을 다시 보여달라'는 모든 경로가 이 메서드 하나로
        모인다. 최소화·숨김·다른 창 뒤에 가려짐 등 어떤 상태였든 정상
        복원한다."""
        if self.isMinimized():
            self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.show()
        self.raise_()
        self.activateWindow()

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
        if getattr(self, "tray_icon", None):
            self.tray_icon.hide()
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
