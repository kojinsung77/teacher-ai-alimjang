# -*- coding: utf-8 -*-
"""'지난 알림장' 화면 — 날짜별 업무 요약 기록(daily_summary)을 다시 확인한다.
메시지 원문 기록이 아니라, '업무' 화면에서 [오늘 알림장 만들기]를 누른
시점의 업무 그룹 스냅샷이다 (app/db.py의 save_daily_summary가 저장,
task_list_view.py의 on_make_note()가 저장 시점)."""

from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
    QGraphicsOpacityEffect
)

from .. import db
from .common_widgets import ClickableCard, build_empty_state

_ENTRANCE_DURATION_MS = 320
_ENTRANCE_STAGGER_MS = 60
_ENTRANCE_RISE_PX = 14


class _AnimatedDateCard(ClickableCard):
    """날짜 카드 하나. 화면 진입 시 아래에서 살짝 올라오며 페이드인한다.

    hover 시 그림자를 QGraphicsDropShadowEffect로 애니메이션하는 방식도
    시도해봤지만, 이 카드는 클릭할 때마다 "선택됨" 상태를 dynamic
    property + unpolish/polish로 다시 그리는데(HistoryView._select_date),
    QGraphicsEffect가 붙어 있는 상태에서 그 restyle이 일어나면 실측으로
    확인된 실제 렌더링 버그가 있었다 — 카드 배경은 정상 표시되는데
    자식 QLabel 텍스트가 사라짐(위젯 자체의 geometry·text는 내부적으로
    멀쩡한데 화면에만 안 그려짐). 그래서 hover 강조는 QGraphicsEffect
    없이 순수 QSS(:hover 시 테두리 색 변경, styles.py의
    QFrame#HistoryDateRow:hover)로 처리하고, 여기서는 등장 애니메이션이
    끝나면 이펙트를 아예 떼어낸다."""

    def clear_entrance_effect(self):
        try:
            self.setGraphicsEffect(None)
        except RuntimeError:
            pass  # 위젯이 이미 삭제된 뒤라면 조용히 무시


class HistoryView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_date = None
        self._date_rows = {}
        self._build_ui()
        self.refresh()

    # ---------- UI 구성 ----------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(44, 36, 44, 36)
        root.setSpacing(16)

        header = QVBoxLayout()
        header.setSpacing(2)
        title = QLabel("지난 알림장")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        subtitle = QLabel("날짜별로 만들었던 업무 알림장을 다시 확인합니다.")
        subtitle.setObjectName("Muted")
        header.addWidget(subtitle)
        root.addLayout(header)

        content_row = QHBoxLayout()
        content_row.setSpacing(16)

        # 왼쪽: 날짜 목록
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setFixedWidth(230)
        self.date_list_container = QWidget()
        self.date_list_layout = QVBoxLayout(self.date_list_container)
        self.date_list_layout.setSpacing(8)
        self.date_list_layout.setContentsMargins(0, 0, 0, 0)
        left_scroll.setWidget(self.date_list_container)
        content_row.addWidget(left_scroll)

        # 오른쪽: 선택한 날짜 상세
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)
        self.detail_container = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_container)
        self.detail_layout.setSpacing(14)
        self.detail_layout.setContentsMargins(0, 0, 0, 0)
        right_scroll.setWidget(self.detail_container)
        content_row.addWidget(right_scroll, 1)

        root.addLayout(content_row, 1)

    def _clear_date_list(self):
        while self.date_list_layout.count():
            item = self.date_list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._date_rows = {}

    def _clear_detail(self):
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    # ---------- 데이터 로딩/표시 ----------

    def refresh(self):
        self._clear_date_list()
        entries = db.list_daily_summary_dates()

        if not entries:
            self._clear_detail()
            empty = build_empty_state(
                "🗂", "아직 저장된 알림장이 없습니다.",
                "'업무' 화면에서 [📋 오늘 알림장 만들기]를 누르면\n"
                "AI가 정리한 하루 기록이 여기에 날짜별로 자동 저장됩니다."
            )
            self.detail_layout.addWidget(empty)
            self.selected_date = None
            return

        for i, entry in enumerate(entries):
            row = self._build_date_row(entry)
            self.date_list_layout.addWidget(row)
            self._date_rows[entry["date"]] = row
            self._animate_card_in(row, i * _ENTRANCE_STAGGER_MS)
        self.date_list_layout.addStretch(1)

        # 선택된 날짜가 사라졌으면(?) 가장 최근 날짜로, 아니면 유지
        if self.selected_date not in self._date_rows:
            self.selected_date = entries[0]["date"]
        self._select_date(self.selected_date)

    def _animate_card_in(self, widget: _AnimatedDateCard, delay_ms: int):
        """등장: 아래에서 살짝 올라오며 페이드인. 카드마다 delay_ms만큼
        늦게 시작해서 순차적으로 나타나 보이게 한다. 애니메이션이 끝나면
        상시 hover 그림자 효과로 전환한다."""
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.0)
        widget.setGraphicsEffect(effect)

        def start():
            try:
                if not widget.isVisible():
                    widget.clear_entrance_effect()
                    return
                final_pos = widget.pos()
                widget.move(final_pos.x(), final_pos.y() + _ENTRANCE_RISE_PX)

                pos_anim = QPropertyAnimation(widget, b"pos", widget)
                pos_anim.setDuration(_ENTRANCE_DURATION_MS)
                pos_anim.setStartValue(widget.pos())
                pos_anim.setEndValue(final_pos)
                pos_anim.setEasingCurve(QEasingCurve.OutCubic)

                opacity_anim = QPropertyAnimation(effect, b"opacity", widget)
                opacity_anim.setDuration(_ENTRANCE_DURATION_MS)
                opacity_anim.setStartValue(0.0)
                opacity_anim.setEndValue(1.0)
                opacity_anim.setEasingCurve(QEasingCurve.OutCubic)
                # 다음 이벤트 루프 틱으로 한 박자 미뤄서 애니메이션
                # 시스템의 내부 갱신 흐름과 분리한다 (QGraphicsEffect를
                # finished 핸들러에서 곧바로 건드리면 카드 하나가 가끔
                # 페인트 글리치를 일으키는 게 실측 확인됐다).
                opacity_anim.finished.connect(
                    lambda w=widget: QTimer.singleShot(0, w.clear_entrance_effect)
                )

                # 재생 중 GC로 사라지지 않도록 위젯에 붙잡아 둔다.
                widget._entrance_anims = (pos_anim, opacity_anim)
                pos_anim.start()
                opacity_anim.start()
            except RuntimeError:
                pass  # 애니메이션 시작 전에 화면을 벗어나 위젯이 삭제된 경우

        QTimer.singleShot(delay_ms, start)

    def _build_date_row(self, entry: dict) -> _AnimatedDateCard:
        row = _AnimatedDateCard()
        row.setObjectName("HistoryDateRow")
        v = QVBoxLayout(row)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(4)

        y, m, d = entry["date"].split("-")
        date_label = QLabel(f"{int(m)}/{int(d)}")
        date_label.setObjectName("TaskTitle")
        v.addWidget(date_label)

        count_label = QLabel(f"업무 {entry['total_open']}건 · 완료 {entry['total_completed']}건")
        count_label.setObjectName("Muted")
        v.addWidget(count_label)

        row.clicked.connect(lambda d=entry["date"]: self._select_date(d))
        return row

    def _select_date(self, date_str: str):
        self.selected_date = date_str
        for d, row in self._date_rows.items():
            row.setProperty("active", d == date_str)
            row.style().unpolish(row)
            row.style().polish(row)
            # 자식 QLabel 색은 QFrame#HistoryDateRow[active="true"] QLabel
            # 처럼 부모(row)의 active 속성에 걸린 자손 선택자로 정해진다.
            # row만 unpolish/polish하면 Qt가 각 QLabel에 캐싱해 둔 스타일
            # 매치 결과까지 자동으로 무효화해주지 않아서, 선택 상태를 여러
            # 번 오가면 자식 글씨가 안 보이거나(흰 배경에 흰 글씨로 남는 등)
            # 겹쳐 보이는 게 실측 확인됐다 — 자식도 직접 unpolish/polish로
            # 스타일을 다시 계산시켜야 한다.
            for child in row.findChildren(QLabel):
                child.style().unpolish(child)
                child.style().polish(child)
                child.update()
            row.update()

        self._clear_detail()
        data = db.get_daily_summary(date_str)
        if not data:
            return

        y, m, d = date_str.split("-")
        heading = QLabel(f"{y}년 {int(m)}월 {int(d)}일 알림장")
        heading.setObjectName("PageSubtitle")
        self.detail_layout.addWidget(heading)

        total_open = data.get("total_open", 0)
        total_completed = data.get("total_completed", 0)
        totals = QLabel(f"전체 업무 {total_open}건 · 완료 {total_completed}건")
        totals.setObjectName("SectionTitle")
        self.detail_layout.addWidget(totals)

        for group in data.get("groups", []):
            self.detail_layout.addWidget(self._build_group_section(group))

        if not data.get("groups"):
            empty = QLabel("이 날짜엔 기록된 업무가 없습니다.")
            empty.setObjectName("Muted")
            self.detail_layout.addWidget(empty)

        self.detail_layout.addStretch(1)

    def _build_group_section(self, group: dict) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)

        heading = QLabel(f"{group['label']} ({len(group['items'])})")
        heading.setObjectName("SectionTitle")
        v.addWidget(heading)

        for item in group["items"]:
            suffix = f" - {item['deadline']}" if item.get("deadline") else ""
            line = QLabel(f"• {item['title']}{suffix}")
            line.setObjectName("TaskMeta")
            line.setWordWrap(True)
            v.addWidget(line)

        return card
