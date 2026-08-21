# -*- coding: utf-8 -*-
"""'오늘' 메뉴 — 요약 대시보드. 인사말/날짜, 통계 카드 4개, 우선 처리 업무
목록을 보여주는 읽기 전용 요약 화면이다. 실제 업무 카드 목록 전체·AI
재분석은 '업무' 메뉴(task_list_view.py)가 담당한다.

teacher_ai_dashboard_preview.html 레퍼런스 기준: 짙은 사이드바 + 파스텔
통계 카드 + 카드형 우선순위 목록. 날씨 관련 기능은 포함하지 않는다."""

import webbrowser
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QMessageBox, QScrollArea
)

from .. import config, db
from ..core import stats, update_check
from .common_widgets import apply_card_shadow, build_empty_state
from .task_card import TaskCard

_WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]

# (nav_key, filter_key, label, desc, icon, variant)
_STAT_DEFS = [
    ("overdue", "tasks", "overdue", "기한 지남", "확인이 필요한 업무", "!", "red"),
    ("today", "tasks", "today", "오늘까지", "오늘 마감 업무", "●", "coral"),
    ("within_7_days", "tasks", "within_7_days", "7일 이내", "곧 처리할 업무", "↗", "orange"),
    ("new_messages", "messages", "", "새 메시지", "최근 받은 메시지", "✉", "blue"),
]


class DashboardView(QWidget):
    # (page_key, filter_key) -- filter_key는 "업무" 페이지로 갈 때만 의미 있고, 그 외엔 ""
    navigateRequested = Signal(str, str)
    # [지금 설치] 클릭 — 실제 다운로드/설치 실행은 MainWindow가 담당한다
    # (백그라운드 스레드·subprocess·앱 종료를 이 위젯이 몰라도 되게 분리).
    installUpdateRequested = Signal()

    def __init__(self, demo_mode: bool = True, parent=None):
        super().__init__(parent)
        self.demo_mode = demo_mode
        self.stat_value_labels = {}
        self._pending_update_version = ""
        self._build_ui()
        self.refresh()

    # ---------- UI 구성 ----------

    def _build_ui(self):
        # 창 높이가 콘텐츠보다 작을 때 QVBoxLayout이 자식을 찌부러뜨리는 것을
        # 막기 위해 QScrollArea로 감싼다 (다른 화면들과 동일한 패턴).
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(44, 36, 44, 36)
        root.setSpacing(26)

        # 데모 모드가 켜져 있으면 상단에 항상 작게 표시한다 — 데모 모드일
        # 땐 정기 알림(13:20/16:10)이 조용히 안 울리는데(main_window.py의
        # _check_daily_reminders), 이 표시가 없으면 선생님이 데모 모드가
        # 켜진 줄 모른 채 "왜 알림이 안 뜨지"라고 헷갈릴 수 있다.
        self.demo_mode_badge = QLabel("🧪 데모 모드 사용 중 — 설정에서 끌 수 있습니다")
        self.demo_mode_badge.setObjectName("DemoModeBadge")
        self.demo_mode_badge.hide()
        root.addWidget(self.demo_mode_badge)

        self.update_banner = self._build_update_banner()
        self.update_banner.hide()
        root.addWidget(self.update_banner)

        root.addLayout(self._build_hero())

        section_title = QLabel("오늘 한눈에 보기")
        section_title.setObjectName("SectionTitle")
        root.addWidget(section_title)

        root.addWidget(self._build_stat_row())

        self.priority_panel = self._build_priority_section()
        root.addWidget(self.priority_panel)

        root.addStretch(1)

    def _build_hero(self) -> QHBoxLayout:
        hero = QHBoxLayout()
        hero.setSpacing(16)

        text_col = QVBoxLayout()
        text_col.setSpacing(7)

        eyebrow = QLabel("TODAY DASHBOARD")
        eyebrow.setObjectName("Eyebrow")
        text_col.addWidget(eyebrow)

        self.greeting_label = QLabel("")
        self.greeting_label.setObjectName("GreetingTitle")
        self.greeting_label.setTextFormat(Qt.RichText)
        text_col.addWidget(self.greeting_label)

        subtitle = QLabel("AI가 정리한 오늘의 업무를 확인해보세요.")
        subtitle.setObjectName("Muted")
        text_col.addWidget(subtitle)

        hero.addLayout(text_col, 1)
        hero.addStretch(0)

        date_badge = QFrame()
        date_badge.setObjectName("DateBadge")
        date_layout = QVBoxLayout(date_badge)
        date_layout.setContentsMargins(15, 11, 15, 11)
        today = date.today()
        self.date_label = QLabel(
            f"{today.year}. {today.month:02d}. {today.day:02d} ({_WEEKDAY_KR[today.weekday()]})"
        )
        self.date_label.setObjectName("DashboardDate")
        date_layout.addWidget(self.date_label)
        apply_card_shadow(date_badge, blur=20, y_offset=6, alpha=14)
        hero.addWidget(date_badge, 0, Qt.AlignTop)

        return hero

    def _build_update_banner(self) -> QFrame:
        """새 버전 안내 배너. 평소엔 숨겨져 있다가 MainWindow가 백그라운드
        업데이트 확인을 마치고 show_update_banner()를 호출할 때만 보인다.
        배너가 뜨는 시점에 MainWindow가 이미 설치 파일을 백그라운드로
        조용히 받아두기 시작하므로, [지금 설치]를 누르면 대개 곧바로
        (또는 다운로드가 아직 안 끝났으면 끝나는 대로 자동으로) 설치가
        진행된다. 자동 설치가 안 될 경우를 대비해 사람이 직접 받는
        페이지(DOWNLOAD_PAGE_URL) 링크도 작게 남겨 둔다."""
        banner = QFrame()
        banner.setObjectName("UpdateBanner")
        outer = QVBoxLayout(banner)
        outer.setContentsMargins(18, 12, 14, 10)
        outer.setSpacing(2)

        row = QHBoxLayout()
        row.setSpacing(10)

        self.update_banner_label = QLabel("")
        self.update_banner_label.setObjectName("UpdateBannerText")
        self.update_banner_label.setWordWrap(True)
        row.addWidget(self.update_banner_label, 1)

        self.update_install_btn = QPushButton("지금 설치")
        self.update_install_btn.setObjectName("SecondaryButton")
        self.update_install_btn.setCursor(Qt.PointingHandCursor)
        self.update_install_btn.clicked.connect(self.installUpdateRequested.emit)
        row.addWidget(self.update_install_btn)

        later_btn = QPushButton("나중에")
        later_btn.setObjectName("GhostButton")
        later_btn.setCursor(Qt.PointingHandCursor)
        later_btn.clicked.connect(self._on_update_dismiss_clicked)
        row.addWidget(later_btn)

        close_btn = QPushButton("✕")
        close_btn.setObjectName("ToggleButton")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedWidth(30)
        close_btn.clicked.connect(self._on_update_dismiss_clicked)
        row.addWidget(close_btn)

        outer.addLayout(row)

        self.update_fallback_label = QLabel(
            '<a href="#" style="color:inherit;">문제가 있다면 여기서 수동으로 받으세요</a>'
        )
        self.update_fallback_label.setObjectName("UpdateBannerFallback")
        self.update_fallback_label.setTextFormat(Qt.RichText)
        self.update_fallback_label.setCursor(Qt.PointingHandCursor)
        self.update_fallback_label.linkActivated.connect(
            lambda _: webbrowser.open(config.DOWNLOAD_PAGE_URL)
        )
        outer.addWidget(self.update_fallback_label)

        return banner

    def show_update_banner(self, info: dict):
        self._pending_update_version = info.get("version", "")
        text = f"새 버전 v{self._pending_update_version}이 있습니다."
        notes = info.get("notes", "")
        if notes:
            text += f" {notes}"
        self.update_banner_label.setText(text)
        self.update_install_btn.setText("지금 설치")
        self.update_install_btn.setEnabled(True)
        self.update_banner.show()

    def set_update_waiting(self, waiting: bool):
        """다운로드가 아직 안 끝난 상태에서 [지금 설치]를 눌렀을 때(또는
        눌러서 새로 다운로드를 시작했을 때) MainWindow가 호출한다.
        완료되면 자동으로 설치가 진행되므로, 여기서는 그 사이 상태만
        보여준다."""
        if waiting:
            self.update_banner_label.setText("설치 파일을 받는 중입니다...")
            self.update_install_btn.setEnabled(False)
            self.update_install_btn.setText("받는 중...")
        else:
            self.update_install_btn.setEnabled(True)
            self.update_install_btn.setText("지금 설치")
            if self._pending_update_version:
                text = f"새 버전 v{self._pending_update_version}이 있습니다."
                self.update_banner_label.setText(text)

    def _on_update_dismiss_clicked(self):
        if self._pending_update_version:
            update_check.set_ignored_version(self._pending_update_version)
        self.update_banner.hide()

    def _build_stat_row(self) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(16)

        for key, nav_key, filter_key, label, desc, icon, variant in _STAT_DEFS:
            card = self._make_stat_card(nav_key, filter_key, label, desc, icon, variant)
            h.addWidget(card, 1)
            self.stat_value_labels[key] = card.findChild(QLabel, "StatCardNumber")
            if key == "new_messages":
                self.new_messages_desc_label = card.findChild(QLabel, "StatCardDesc")

        return row

    def _make_stat_card(self, nav_key: str, filter_key: str, label: str,
                         desc: str, icon: str, variant: str) -> QFrame:
        from .common_widgets import ClickableCard

        card = ClickableCard()
        card.setObjectName("StatCard")
        card.setProperty("variant", variant)
        card.setMinimumHeight(138)
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(4)

        top_row = QHBoxLayout()
        label_lbl = QLabel(label)
        label_lbl.setObjectName("StatCardLabel")
        top_row.addWidget(label_lbl)
        top_row.addStretch(1)
        icon_badge = QLabel(icon)
        icon_badge.setObjectName("StatIconBadge")
        icon_badge.setFixedSize(34, 34)
        top_row.addWidget(icon_badge)
        v.addLayout(top_row)

        v.addSpacing(10)

        number = QLabel("0")
        number.setObjectName("StatCardNumber")
        v.addWidget(number)

        desc_lbl = QLabel(desc)
        desc_lbl.setObjectName("StatCardDesc")
        v.addWidget(desc_lbl)

        card.clicked.connect(lambda: self.navigateRequested.emit(nav_key, filter_key))
        return card

    def _build_priority_section(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        v = QVBoxLayout(panel)
        v.setContentsMargins(24, 22, 24, 22)
        v.setSpacing(4)
        apply_card_shadow(panel)

        heading = QLabel("우선 확인할 업무")
        heading.setObjectName("SectionTitle")
        v.addWidget(heading)

        sub = QLabel("마감이 가까운 순서로 정리했습니다.")
        sub.setObjectName("Muted")
        v.addWidget(sub)

        v.addSpacing(10)

        self.priority_list_layout = QVBoxLayout()
        self.priority_list_layout.setSpacing(10)
        v.addLayout(self.priority_list_layout)

        return panel

    # ---------- 데이터 로딩/표시 ----------

    def refresh(self):
        # "messenger_login_name" 설정으로 이름을 넣어 인사하던 예전 버전이
        # 있었는데, 그 값을 입력받던 UI 필드가 리팩터링 중 사라지면서 이
        # 설정은 항상 빈 값이라 개인화 인사말이 죽은 코드였다 — 정리함.
        greeting = "안녕하세요, <span style=\"color:#4F76F5\">선생님!</span> 👋"
        self.greeting_label.setText(greeting)

        self.demo_mode_badge.setVisible(self.demo_mode)

        values = stats.dashboard_stats()
        self.stat_value_labels["overdue"].setText(str(values["overdue"]))
        self.stat_value_labels["today"].setText(str(values["today"]))
        self.stat_value_labels["within_7_days"].setText(str(values["within_7_days"]))
        self.stat_value_labels["new_messages"].setText(str(values["new_messages"]))

        # '새 메시지' 카드는 '업무' 화면의 AI 재분석과 같은 analyze_days
        # 기준으로 세므로, 설명 문구도 그 기간을 그대로 보여준다.
        days = stats.analyze_days_setting()
        desc_text = "오늘 받은 메시지" if days <= 1 else f"최근 {days}일 받은 메시지"
        self.new_messages_desc_label.setText(desc_text)

        self._refresh_priority_list()

    def _clear_priority_list(self):
        while self.priority_list_layout.count():
            item = self.priority_list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _refresh_priority_list(self):
        self._clear_priority_list()
        items = stats.priority_tasks(limit=7)

        if not items:
            empty = build_empty_state(
                "🎉", "오늘 마감 업무가 없습니다.",
                "조금 여유롭게 하루를 시작해보세요."
            )
            self.priority_list_layout.addWidget(empty)
        else:
            for t in items:
                card = TaskCard(t)
                card.completedToggled.connect(self.on_task_completed_toggled)
                card.viewOriginalRequested.connect(self.on_view_original)
                self.priority_list_layout.addWidget(card)

        # 새로 만든 위젯이 화면이 이미 떠 있는 상태(예: switch_page로 재진입)에서
        # 바로 반영되도록 강제로 다시 그린다.
        self.priority_list_layout.activate()
        for child in self.priority_panel.findChildren(QWidget):
            child.style().unpolish(child)
            child.style().polish(child)
            child.update()
        self.priority_panel.updateGeometry()
        self.priority_panel.update()

    # ---------- 액션 ----------

    def on_task_completed_toggled(self, task_id: int, completed: bool):
        db.set_task_completed(task_id, completed)
        self.refresh()

    def on_view_original(self, task_id: int):
        rows = db.messages_for_task(task_id)
        if not rows:
            QMessageBox.information(self, "원문", "연결된 원문 메시지를 찾을 수 없습니다.")
            return
        text = "\n\n".join(
            f"[{r['sender']} · {r['department']}]\n{r['title']}\n{r['body']}" for r in rows
        )
        QMessageBox.information(self, f"원문 메시지 ({len(rows)}건)", text)
