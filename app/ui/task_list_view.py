# -*- coding: utf-8 -*-
"""'업무' 화면 — 마감일 기준 탭 필터(전체/기한 지남/오늘까지/7일 이내/
그 이후/기한 없음/완료) + 업무 카드 목록 + AI 재분석/알림장 만들기.

날짜 분류는 전부 app/core/deadline_classifier.py + app/core/stats.py에
위임한다 — 이 파일은 그 결과를 화면에 그리는 역할만 한다."""

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QFrame, QDialog, QMessageBox, QApplication
)

from .. import db
from ..core import task_manager, stats
from ..core.deadline_classifier import DeadlineGroup, GROUP_ORDER, GROUP_LABELS
from ..adapters.mock_adapter import MockMessengerAdapter
from ..adapters.coolmessenger_adapter import CoolMessengerAdapter
from ..ai.gemini_client import GeminiKeyError
from .common_widgets import ClickableCard, build_empty_state
from .task_card import TaskCard

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
    def __init__(self, demo_mode: bool = True, parent=None):
        super().__init__(parent)
        self.demo_mode = demo_mode
        self.active_filter = "all"
        self._tabs = {}
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
        tabs_row.setSpacing(8)
        for key, label, _group, color_key in _FILTER_TABS:
            tab = _FilterTab(label)
            tab.set_badge_color(color_key)
            tab.clicked.connect(lambda k=key: self.select_filter(k))
            tabs_row.addWidget(tab)
            self._tabs[key] = tab
        tabs_row.addStretch(1)
        root.addLayout(tabs_row)

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

    # ---------- 데이터 로딩/표시 ----------

    def refresh(self):
        counts = stats.task_filter_counts()
        for key, _, _, _ in _FILTER_TABS:
            self._tabs[key].set_count(counts.get(key, 0))
        self._render_list()
        self._refresh_stats(counts["all"])

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
        daily_summary에 저장한다 (지난 알림장 화면이 이걸 읽어서 보여준다)."""
        grouped = stats.group_todo_tasks()
        completed = stats.completed_tasks()

        today = date.today()
        lines = [f"📋 {today.month}월 {today.day}일 업무 알림장", ""]
        summary_groups = []
        total_open = 0

        for g in GROUP_ORDER:
            rows = stats.sort_for_group(g, grouped[g])
            total_open += len(rows)
            if not rows:
                continue
            label = GROUP_LABELS[g]
            lines.append(label)
            items = []
            for t in rows:
                suffix = f" - {t['deadline']}" if t["deadline"] else ""
                lines.append(f"• {t['title']}{suffix}")
                items.append({"title": t["title"], "deadline": t["deadline"]})
            lines.append("")
            summary_groups.append({"key": g.value, "label": label, "items": items})

        if completed:
            label = "✅ 완료"
            lines.append(label)
            items = []
            for t in stats.sort_completed(completed):
                lines.append(f"• {t['title']}")
                items.append({"title": t["title"]})
            lines.append("")
            summary_groups.append({"key": "completed", "label": label, "items": items})

        lines.append(f"📌 현재 미처리 업무: {total_open}건")
        note = "\n".join(lines)

        QApplication.clipboard().setText(note)

        db.save_daily_summary(today.isoformat(), {
            "groups": summary_groups,
            "total_open": total_open,
            "total_completed": len(completed),
            "note_text": note,
        })

        _DailyNoteResultDialog(note, self).exec()
