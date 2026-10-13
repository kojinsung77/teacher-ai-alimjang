# -*- coding: utf-8 -*-
"""'업무' 화면 — 마감일 기준 탭 필터(전체/기한 지남/오늘까지/7일 이내/
그 이후/기한 없음/완료) + 업무 카드 목록 + AI 재분석/알림장 만들기.

탭은 FlowLayout에 담겨 창이 좁으면 다음 줄로 넘어간다(상자가 찌그러지지
않게). '전체'·'기한 지남'·'기한 없음' 탭에서는 오른쪽 위 [✓ 완료 처리 ▾]
메뉴로 [전체 완료] / [기간을 정해서 완료…]를 할 수 있고, 처리 직후 목록
위에 [되돌리기] 안내를 잠깐 띄운다. 계산은 app/core/bulk_complete.py.

날짜 분류는 전부 app/core/deadline_classifier.py + app/core/stats.py에
위임한다 — 이 파일은 그 결과를 화면에 그리는 역할만 한다."""

from PySide6.QtCore import Qt, QPoint, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QFrame, QDialog, QMessageBox, QApplication, QMenu
)

from .. import db
from ..core import task_manager, stats, daily_note
from ..core import bulk_complete
from ..core.deadline_classifier import DeadlineGroup, GROUP_LABELS
from ..adapters.mock_adapter import MockMessengerAdapter
from ..adapters.coolmessenger_adapter import CoolMessengerAdapter
from ..ai.gemini_client import GeminiKeyError
from .common_widgets import ClickableCard, build_empty_state
from .task_card import TaskCard
from .flow_layout import FlowContainer
from .bulk_complete_dialog import BulkRangeDialog

# (탭 key, 라벨, DeadlineGroup 또는 None(전체/완료), 배지 색상 키)
_FILTER_TABS = [
    ("all", "전체", None, "all"),
    ("overdue", GROUP_LABELS[DeadlineGroup.OVERDUE], DeadlineGroup.OVERDUE, "overdue"),
    ("today", GROUP_LABELS[DeadlineGroup.TODAY], DeadlineGroup.TODAY, "today"),
    ("within_7_days", GROUP_LABELS[DeadlineGroup.WITHIN_7_DAYS], DeadlineGroup.WITHIN_7_DAYS, "within7"),
    ("later", GROUP_LABELS[DeadlineGroup.LATER], DeadlineGroup.LATER, "later"),
    ("no_deadline", GROUP_LABELS[DeadlineGroup.NO_DEADLINE], DeadlineGroup.NO_DEADLINE, "nodeadline"),
    ("completed", "완료", None, "completed"),
]

# [✓ 완료 처리 ▾] 메뉴를 보여 주는 탭('전체'·'기한 지남'·'기한 없음').
# '오늘까지'·'7일 이내'·'그 이후' 탭에는 두지 않는다 — 아직 실제로 해야 할
# 일이라 그 탭만 따로 한꺼번에 완료할 일은 드물고 실수 위험만 크다.
_BULK_COMPLETE_TABS = bulk_complete.MENU_TABS

# 일괄 완료 직후 [되돌리기] 안내를 띄워 두는 시간
_UNDO_VISIBLE_MS = 15000


def _tab_label(key: str) -> str:
    return next(label for k, label, _, _ in _FILTER_TABS if k == key)


class _FilterTab(ClickableCard):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setObjectName("FilterTab")
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 8, 14, 8)
        h.setSpacing(6)

        self.label_widget = QLabel(label)
        self.label_widget.setObjectName("FilterTabLabel")
        h.addWidget(self.label_widget)

        self.badge = QLabel("0")
        self.badge.setObjectName("FilterTabBadge")
        h.addWidget(self.badge)

    def set_badge_color(self, color_key: str):
        self.badge.setProperty("colorKey", color_key)

    def set_count(self, count: int):
        self.badge.setText(str(count))

    def set_active(self, active: bool):
        self.setProperty("active", active)
        self.label_widget.setProperty("active", active)
        for w in (self, self.label_widget):
            w.style().unpolish(w)
            w.style().polish(w)


class _DailyNoteResultDialog(QDialog):
    """[오늘 알림장 만들기] 결과를 보여주는 창. QMessageBox.information()
    대신 직접 만든 이유: QMessageBox는 본문에 스크롤 영역이 없어서,
    업무가 많아 본문이 길어지면 창이 화면 높이보다 커져도 그냥 계속
    늘어나기만 하고 OK 버튼이 화면 밖으로 밀려나 눌리지 않는 경우가
    있었다. 여기서는 본문만 QScrollArea에 넣고 OK 버튼은 항상 스크롤
    영역 밖 하단에 고정해서, 창 자체 높이를 화면 안에 묶어 둬도(최대
    높이 제한) 본문을 끝까지 스크롤해서 읽고 OK를 누를 수 있다."""

    def __init__(self, note_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("알림장 생성 완료")
        self.setMinimumWidth(480)
        self.setMaximumHeight(640)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)

        title = QLabel("알림장 생성 완료")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        copied_label = QLabel("(클립보드에 복사되었습니다)")
        copied_label.setObjectName("Muted")
        root.addWidget(copied_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        note_label = QLabel(note_text)
        note_label.setWordWrap(True)
        note_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        scroll.setWidget(note_label)
        root.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("PrimaryButton")
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        root.addLayout(btn_row)


class TaskListView(QWidget):
    # 업무의 완료 상태가 바뀌었을 때(개별·일괄·되돌리기) — MainWindow가
    # 걸어 다니는 파랑새의 건수를 1분 기다리지 않고 바로 맞추는 데 쓴다.
    tasksChanged = Signal()

    def __init__(self, demo_mode: bool = True, parent=None):
        super().__init__(parent)
        self.demo_mode = demo_mode
        self.active_filter = "all"
        self._tabs = {}
        self._filter_counts = {}
        self._undo_ids = []
        self._undo_stamp = None
        self._build_ui()
        self.refresh()

    # ---------- UI 구성 ----------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("업무")
        title.setObjectName("PageTitle")
        title_col.addWidget(title)
        subtitle = QLabel("AI가 메시지에서 추출한 해야 할 일을 관리합니다.")
        subtitle.setObjectName("Muted")
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch(1)

        self.reanalyze_btn = QPushButton("✨ AI 다시 분석")
        self.reanalyze_btn.setObjectName("SecondaryButton")
        self.reanalyze_btn.setCursor(Qt.PointingHandCursor)
        self.reanalyze_btn.clicked.connect(self.on_reanalyze)
        header.addWidget(self.reanalyze_btn)

        self.make_note_btn = QPushButton("📋 오늘 알림장 만들기")
        self.make_note_btn.setObjectName("PrimaryButton")
        self.make_note_btn.setCursor(Qt.PointingHandCursor)
        self.make_note_btn.clicked.connect(self.on_make_note)
        header.addWidget(self.make_note_btn)

        root.addLayout(header)

        tabs_row = QHBoxLayout()
        tabs_row.setSpacing(10)
        # 탭은 왼쪽 영역에서 줄 바꿈한다 — 창을 줄여도 상자가 찌그러지지 않고
        # 두 줄, 세 줄로 넘어간다.
        # 탭 사이 6px — 1200px 창에서 '완료' 탭까지 한 줄에 들어가게(8px이면 약 8px 모자람)
        self.tabs_flow = FlowContainer(h_spacing=6, v_spacing=8)
        for key, label, _group, color_key in _FILTER_TABS:
            tab = _FilterTab(label)
            tab.set_badge_color(color_key)
            tab.clicked.connect(lambda k=key: self.select_filter(k))
            self.tabs_flow.addWidget(tab)
            self._tabs[key] = tab
        tabs_row.addWidget(self.tabs_flow, 1)

        # 오른쪽 위에 고정 — 창 너비가 바뀌어도 자리가 움직이지 않는다.
        # 눈에 덜 띄는 회색 보조 버튼이라 잘못 누르는 일을 줄인다.
        self.complete_menu_btn = QPushButton("✓ 완료 처리 ▾")
        self.complete_menu_btn.setObjectName("GhostButton")
        self.complete_menu_btn.setCursor(Qt.PointingHandCursor)
        self.complete_menu_btn.setToolTip("이 탭의 업무를 한꺼번에 완료합니다")
        self.complete_menu_btn.clicked.connect(self._show_complete_menu)
        self.complete_menu_btn.hide()
        tabs_row.addWidget(self.complete_menu_btn, 0, Qt.AlignTop)
        root.addLayout(tabs_row)

        self.complete_menu = QMenu(self)
        self.complete_menu.setObjectName("CompleteMenu")
        self.menu_all_action = self.complete_menu.addAction("✓  전체 완료")
        self.menu_all_action.triggered.connect(self.on_bulk_complete)
        self.complete_menu.addSeparator()
        self.menu_range_action = self.complete_menu.addAction("📅  기간을 정해서 완료…")
        self.menu_range_action.triggered.connect(self.on_range_complete)

        # 일괄 완료 직후의 [되돌리기] 안내 줄
        self.undo_bar = QFrame()
        self.undo_bar.setObjectName("UndoBar")
        undo_layout = QHBoxLayout(self.undo_bar)
        undo_layout.setContentsMargins(18, 8, 10, 8)
        undo_layout.setSpacing(10)
        self.undo_label = QLabel("")
        self.undo_label.setObjectName("UndoBarLabel")
        undo_layout.addWidget(self.undo_label)
        undo_layout.addStretch(1)
        self.undo_btn = QPushButton("되돌리기")
        self.undo_btn.setObjectName("UndoBarButton")
        self.undo_btn.setCursor(Qt.PointingHandCursor)
        self.undo_btn.clicked.connect(self.on_undo_bulk_complete)
        undo_layout.addWidget(self.undo_btn)
        undo_close = QPushButton("✕")
        undo_close.setObjectName("UndoBarClose")
        undo_close.setCursor(Qt.PointingHandCursor)
        undo_close.setToolTip("안내 닫기")
        undo_close.clicked.connect(self._hide_undo_bar)
        undo_layout.addWidget(undo_close)
        self.undo_bar.hide()
        root.addWidget(self.undo_bar)

        self._undo_timer = QTimer(self)
        self._undo_timer.setSingleShot(True)
        self._undo_timer.timeout.connect(self._hide_undo_bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setSpacing(10)
        self.list_layout.setContentsMargins(0, 4, 0, 0)
        self.scroll.setWidget(self.list_container)
        root.addWidget(self.scroll, 1)

        self.stat_bar = QFrame()
        self.stat_bar.setObjectName("StatBar")
        stat_layout = QHBoxLayout(self.stat_bar)
        stat_layout.setContentsMargins(20, 14, 20, 14)
        self.stat_label = QLabel("")
        self.stat_label.setObjectName("Muted")
        stat_layout.addWidget(self.stat_label)
        stat_layout.addStretch(1)
        root.addWidget(self.stat_bar)

        self.select_filter("all")

    def _clear_list(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    # ---------- 필터 ----------

    def select_filter(self, key: str):
        """대시보드 카드 클릭 등 외부에서도 호출한다 (필터 자동 선택용)."""
        if key not in self._tabs:
            key = "all"
        self.active_filter = key
        for k, tab in self._tabs.items():
            tab.set_active(k == key)
        self._render_list()
        self._update_bulk_button()

    # ---------- 데이터 로딩/표시 ----------

    def refresh(self):
        counts = stats.task_filter_counts()
        self._filter_counts = counts
        for key, _, _, _ in _FILTER_TABS:
            self._tabs[key].set_count(counts.get(key, 0))
        self._render_list()
        self._refresh_stats(counts["all"])
        self._update_bulk_button()

    def _update_bulk_button(self):
        """'전체'·'기한 지남'·'기한 없음' 탭에 업무가 있을 때만 [✓ 완료 처리 ▾]를 보인다."""
        n = self._filter_counts.get(self.active_filter, 0)
        self.complete_menu_btn.setVisible(self.active_filter in _BULK_COMPLETE_TABS and n > 0)

    def _current_tab_tasks(self):
        """지금 탭에 보이는 미완료 업무 — 화면에 그린 것과 같은 기준으로 다시
        계산한다(숨은 업무가 섞여 완료되는 일이 없게)."""
        if self.active_filter == "all":
            return list(stats.todo_tasks())
        group = next(g for k, _, g, _ in _FILTER_TABS if k == self.active_filter)
        return list(stats.group_todo_tasks()[group])

    def _show_complete_menu(self):
        n = self._filter_counts.get(self.active_filter, 0)
        self.menu_all_action.setText(f"✓  전체 완료 ({n}건)")
        btn = self.complete_menu_btn
        # 버튼 오른쪽 끝에 맞춰 바로 아래에 띄운다
        width = self.complete_menu.sizeHint().width()
        self.complete_menu.exec(btn.mapToGlobal(QPoint(btn.width() - width, btn.height() + 4)))

    def _render_list(self):
        self._clear_list()

        if self.active_filter == "all":
            tasks = stats.sort_deadline_group(stats.todo_tasks())
        elif self.active_filter == "completed":
            tasks = stats.sort_completed(stats.completed_tasks())
        else:
            group = next(g for k, _, g, _ in _FILTER_TABS if k == self.active_filter)
            tasks = stats.sort_for_group(group, stats.group_todo_tasks()[group])

        if not tasks:
            if self.active_filter == "all":
                empty = build_empty_state(
                    "✨", "아직 분석된 업무가 없습니다.",
                    "오른쪽 위 [✨ AI 다시 분석]으로 메시지를 분석하면\nAI가 해야 할 일을 정리해드립니다."
                )
            elif self.active_filter == "completed":
                empty = build_empty_state(
                    "✅", "완료한 업무가 아직 없습니다.",
                    "업무를 완료 처리하면 여기에 모아서 보여드립니다."
                )
            else:
                empty = build_empty_state(
                    "🎉", "표시할 업무가 없습니다.",
                    "이 구간에는 해당하는 업무가 없어요."
                )
            self.list_layout.addWidget(empty)
        else:
            for row in tasks:
                card = TaskCard(row)
                card.completedToggled.connect(self.on_task_completed_toggled)
                card.viewOriginalRequested.connect(self.on_view_original)
                self.list_layout.addWidget(card)

        self.list_layout.addStretch(1)

    def _refresh_stats(self, todo_count: int):
        counts = stats.message_classification_counts()
        self.stat_label.setText(
            f"전체 메시지 {counts['total']}   ·   미완료 업무 {todo_count}   ·   "
            f"참고 {counts['reference']}   ·   중복/제외 {counts['ignore']}"
        )

    # ---------- 액션 ----------

    def on_task_completed_toggled(self, task_id: int, completed: bool):
        db.set_task_completed(task_id, completed)
        self.refresh()
        self.tasksChanged.emit()

    def on_bulk_complete(self):
        """[✓ 완료 처리 ▾] → [전체 완료]"""
        if self.active_filter not in _BULK_COMPLETE_TABS:
            return
        tasks = self._current_tab_tasks()
        if not tasks:
            self.refresh()
            return

        box = QMessageBox(self)
        box.setWindowTitle("전체 완료")
        box.setIcon(QMessageBox.Question)
        box.setText(bulk_complete.all_confirm_text(_tab_label(self.active_filter), tasks))
        ok_btn = box.addButton(f"{len(tasks)}건 완료 처리", QMessageBox.AcceptRole)
        cancel_btn = box.addButton("취소", QMessageBox.RejectRole)
        box.setDefaultButton(cancel_btn)  # Enter를 잘못 눌러도 아무 일 없게
        box.setEscapeButton(cancel_btn)
        box.exec()
        if box.clickedButton() is not ok_btn:
            return
        self._complete_with_undo([t["task_id"] for t in tasks])

    def on_range_complete(self):
        """[✓ 완료 처리 ▾] → [기간을 정해서 완료…] — 고른 업무만 완료한다.
        창 안의 미리 보기 목록이 확인 단계라 확인창을 따로 띄우지 않는다."""
        if self.active_filter not in _BULK_COMPLETE_TABS:
            return
        tasks = self._current_tab_tasks()
        if not tasks:
            self.refresh()
            return
        dialog = BulkRangeDialog(self.active_filter, _tab_label(self.active_filter), tasks, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        ids = dialog.selected_ids()
        if ids:
            self._complete_with_undo(ids)

    def _complete_with_undo(self, ids):
        stamp = db.complete_tasks_bulk(ids)
        self._undo_ids = list(ids)
        self._undo_stamp = stamp
        self.refresh()
        self.tasksChanged.emit()
        self.undo_label.setText(f"✓ {len(ids)}건을 완료했어요")
        self.undo_btn.setEnabled(True)
        self.undo_bar.show()
        self._undo_timer.start(_UNDO_VISIBLE_MS)

    def on_undo_bulk_complete(self):
        if not self._undo_ids or not self._undo_stamp:
            self._hide_undo_bar()
            return
        db.undo_bulk_complete(self._undo_ids, self._undo_stamp)
        self._hide_undo_bar()
        self.refresh()
        self.tasksChanged.emit()

    def _hide_undo_bar(self):
        self._undo_timer.stop()
        self.undo_bar.hide()
        self._undo_ids = []
        self._undo_stamp = None

    def on_view_original(self, task_id: int):
        rows = db.messages_for_task(task_id)
        if not rows:
            QMessageBox.information(self, "원문", "연결된 원문 메시지를 찾을 수 없습니다.")
            return
        text = "\n\n".join(
            f"[{r['sender']} · {r['department']}]\n{r['title']}\n{r['body']}" for r in rows
        )
        QMessageBox.information(self, f"원문 메시지 ({len(rows)}건)", text)

    def on_reanalyze(self):
        self.reanalyze_btn.setEnabled(False)
        self.reanalyze_btn.setText("분석 중...")
        QApplication.processEvents()
        try:
            adapter = MockMessengerAdapter() if self.demo_mode else CoolMessengerAdapter()
            days = int(db.get_setting("analyze_days", "1"))
            new_count, image_map = task_manager.sync_messages(adapter, days=days)
            counts = task_manager.analyze_unanalyzed(image_map=image_map)
            self.refresh()
            QMessageBox.information(
                self, "분석 완료",
                f"새 메시지 {new_count}건 수집\n"
                f"ACTION {counts.get('ACTION', 0)} · "
                f"REFERENCE {counts.get('REFERENCE', 0)} · "
                f"IGNORE {counts.get('IGNORE', 0)}"
                + (f"\n민감정보로 분류 제외 {counts['SKIPPED_SENSITIVE']}건"
                   if counts.get("SKIPPED_SENSITIVE") else "")
            )
        except GeminiKeyError as e:
            QMessageBox.warning(self, "API Key 필요", str(e))
        except Exception as e:
            QMessageBox.critical(self, "분석 실패", str(e))
        finally:
            self.reanalyze_btn.setEnabled(True)
            self.reanalyze_btn.setText("✨ AI 다시 분석")

    def on_make_note(self):
        """오늘 알림장 텍스트를 만들어 클립보드에 복사하고, 그 스냅샷을
        daily_summary에 저장한다 (지난 알림장 화면이 이걸 읽어서 보여준다).
        텍스트/스냅샷 생성 로직 자체는 app/core/daily_note.py에 있다 —
        main_window.py의 평일 자동 생성도 같은 로직을 쓴다."""
        result = daily_note.generate_and_save_daily_note()
        QApplication.clipboard().setText(result["note_text"])
        _DailyNoteResultDialog(result["note_text"], self).exec()
