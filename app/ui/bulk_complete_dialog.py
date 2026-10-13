# -*- coding: utf-8 -*-
"""'업무' 화면 [✓ 완료 처리 ▾] → [기간을 정해서 완료…] 창.

기준(마감일/받은 날짜)과 기간을 고르면 해당 업무를 미리 보기 목록에 바로
보여 주고, 체크를 풀어 일부를 뺄 수 있다. [N건 완료 처리]를 누르면
selected_ids()로 고른 업무 id를 돌려준다 — 실제 완료 처리와 [되돌리기]는
TaskListView가 한다. 계산은 전부 app/core/bulk_complete.py에 있다."""

from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDateEdit, QDialog, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QAbstractItemView
)

from ..core import bulk_complete as bc
from .flow_layout import FlowContainer


def _to_qdate(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


def _to_date(qd: QDate) -> date:
    return date(qd.year(), qd.month(), qd.day())


class BulkRangeDialog(QDialog):
    def __init__(self, tab_key: str, tab_label: str, tasks, today: date = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("기간을 정해서 완료")
        self.setMinimumWidth(560)
        self.setMaximumHeight(780)

        self._tab_key = tab_key
        self._tab_label = tab_label
        self._tasks = list(tasks)
        self._today = today or date.today()
        self._bases = bc.bases_for(tab_key)
        self._basis = self._bases[0]
        self._preset_key = None
        self._start = None   # None = 처음부터
        self._end = None
        self._candidates = []
        self._excluded = set()
        self._updating = False

        self._build_ui()
        self._apply_preset(self._presets()[0])
        self._rebuild()

    # ---------- 화면 구성 ----------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(10)

        title = QLabel("기간을 정해서 완료")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        if self._tab_key == "no_deadline":
            sub_text = f"'{self._tab_label}' 탭에서 고른 기간에 받은 업무만 완료해요."
        else:
            sub_text = f"'{self._tab_label}' 탭에서 고른 기간에 해당하는 업무만 완료해요."
        sub = QLabel(sub_text)
        sub.setObjectName("Muted")
        root.addWidget(sub)
        root.addSpacing(4)

        # 기준
        root.addWidget(self._field_label("무엇을 기준으로 고를까요?"))
        self.seg_buttons = {}
        self.basis_hint = QLabel("")
        self.basis_hint.setObjectName("Muted")
        self.basis_hint.setWordWrap(True)
        if len(self._bases) == 1:
            fixed = QLabel("📨 받은 날짜 기준 — 기한이 없는 업무라 메시지를 받은 날로 골라요.")
            fixed.setObjectName("BulkBasisFixed")
            fixed.setWordWrap(True)
            root.addWidget(fixed)
        else:
            seg_row = QHBoxLayout()
            seg_row.setSpacing(6)
            group = QButtonGroup(self)
            group.setExclusive(True)
            for basis, text in ((bc.BASIS_DEADLINE, "📅 마감일 기준"), (bc.BASIS_RECEIVED, "📨 받은 날짜 기준")):
                b = QPushButton(text)
                b.setObjectName("SegButton")
                b.setCheckable(True)
                b.setAutoDefault(False)
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _=False, v=basis: self._on_basis(v))
                group.addButton(b)
                seg_row.addWidget(b)
                self.seg_buttons[basis] = b
            seg_row.addStretch(1)
            root.addLayout(seg_row)
            root.addWidget(self.basis_hint)

        # 기간
        root.addSpacing(2)
        root.addWidget(self._field_label("기간"))
        self.preset_box = FlowContainer(h_spacing=6, v_spacing=6)
        root.addWidget(self.preset_box)

        dates = QHBoxLayout()
        dates.setSpacing(8)
        self.start_edit = self._date_edit()
        self.start_text = QLabel("처음부터")
        self.start_text.setObjectName("BulkStartText")
        self.end_edit = self._date_edit()
        self.from_start_chk = QCheckBox("처음부터")
        self.start_edit.dateChanged.connect(self._on_dates_changed)
        self.end_edit.dateChanged.connect(self._on_dates_changed)
        self.from_start_chk.toggled.connect(self._on_from_start_toggled)
        dates.addWidget(self.start_edit)
        dates.addWidget(self.start_text)
        dates.addWidget(QLabel("~"))
        dates.addWidget(self.end_edit)
        dates.addSpacing(6)
        dates.addWidget(self.from_start_chk)
        dates.addStretch(1)
        root.addLayout(dates)

        # 요약·경고
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("BulkSummary")
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextFormat(Qt.RichText)
        root.addWidget(self.summary_label)

        self.warn_label = QLabel("")
        self.warn_label.setObjectName("BulkWarn")
        self.warn_label.setWordWrap(True)
        root.addWidget(self.warn_label)

        # 미리 보기 목록
        head = QHBoxLayout()
        self.preview_label = QLabel("")
        self.preview_label.setObjectName("Muted")
        head.addWidget(self.preview_label)
        head.addStretch(1)
        self.toggle_all_btn = QPushButton("모두 해제")
        self.toggle_all_btn.setObjectName("LinkButton")
        self.toggle_all_btn.setAutoDefault(False)
        self.toggle_all_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_all_btn.clicked.connect(self._on_toggle_all)
        head.addWidget(self.toggle_all_btn)
        root.addLayout(head)

        self.pick_list = QListWidget()
        self.pick_list.setObjectName("BulkPickList")
        self.pick_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.pick_list.setMinimumHeight(170)
        self.pick_list.itemChanged.connect(self._on_item_changed)
        root.addWidget(self.pick_list, 1)

        # 아래 버튼 — Enter를 잘못 눌러도 아무 일 없게 기본 버튼을 두지 않는다
        foot = QHBoxLayout()
        foot.setSpacing(8)
        hint = QLabel("빼고 싶은 업무는 체크를 풀면 돼요.")
        hint.setObjectName("Muted")
        foot.addWidget(hint)
        foot.addStretch(1)
        cancel_btn = QPushButton("취소")
        cancel_btn.setObjectName("SecondaryButton")
        cancel_btn.setAutoDefault(False)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        foot.addWidget(cancel_btn)
        self.ok_btn = QPushButton("완료 처리")
        self.ok_btn.setObjectName("PrimaryButton")
        self.ok_btn.setAutoDefault(False)
        self.ok_btn.setCursor(Qt.PointingHandCursor)
        self.ok_btn.clicked.connect(self.accept)
        foot.addWidget(self.ok_btn)
        root.addLayout(foot)

    def _field_label(self, text):
        label = QLabel(text)
        label.setObjectName("BulkFieldLabel")
        return label

    def _date_edit(self):
        edit = QDateEdit()
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("yyyy-MM-dd")
        edit.setDate(_to_qdate(self._today))
        return edit

    # ---------- 상태 ----------

    def _presets(self):
        return bc.presets_for(self._tab_key, self._basis, self._today)

    def _apply_preset(self, preset):
        self._preset_key = preset.key
        self._start = preset.start
        self._end = preset.end

    def _rebuild(self):
        """기준·기간이 바뀌었을 때 — 화면 전체를 다시 맞춘다."""
        self._updating = True
        try:
            for basis, b in self.seg_buttons.items():
                b.setChecked(basis == self._basis)
            if self.seg_buttons:
                if self._basis == bc.BASIS_DEADLINE:
                    hint = "마감일이 고른 기간 안에 있는 업무를 골라요."
                    if self._tab_key == "all":
                        hint += " 기한 없는 업무는 들어가지 않아요."
                else:
                    hint = "메시지를 받은 날이 고른 기간 안에 있는 업무를 골라요."
                    if self._tab_key == "all":
                        hint += " 기한 없는 업무도 들어가요."
                self.basis_hint.setText(hint)
            self._rebuild_presets()

            from_start = self._start is None
            self.from_start_chk.setChecked(from_start)
            self.start_edit.setVisible(not from_start)
            self.start_text.setVisible(from_start)
            if self._start is not None:
                self.start_edit.setDate(_to_qdate(self._start))
            if self._end is not None:
                self.end_edit.setDate(_to_qdate(self._end))
        finally:
            self._updating = False

        self._candidates = bc.sort_for_preview(
            bc.filter_by_range(self._tasks, self._basis, self._start, self._end), self._today
        )
        self._fill_list()
        self._update_summary()

    def _rebuild_presets(self):
        flow = self.preset_box.flow
        while flow.count():
            item = flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for p in self._presets():
            chip = QPushButton(p.label)
            chip.setObjectName("ChipButton")
            chip.setCheckable(True)
            chip.setChecked(p.key == self._preset_key)
            chip.setAutoDefault(False)
            chip.setCursor(Qt.PointingHandCursor)
            chip.clicked.connect(lambda _=False, preset=p: self._on_preset(preset))
            self.preset_box.addWidget(chip)
        self.preset_box.updateGeometry()

    def _fill_list(self):
        self._updating = True
        try:
            self.pick_list.clear()
            if not self._candidates:
                empty = QListWidgetItem("이 기간에 해당하는 업무가 없어요.")
                empty.setFlags(Qt.NoItemFlags)
                self.pick_list.addItem(empty)
                return
            for t in self._candidates:
                item = QListWidgetItem(self._item_text(t))
                item.setData(Qt.UserRole, t["task_id"])
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked if t["task_id"] in self._excluded else Qt.Checked)
                self.pick_list.addItem(item)
        finally:
            self._updating = False

    def _item_text(self, t) -> str:
        deadline = bc.basis_date(t, bc.BASIS_DEADLINE)
        bits = [f"마감 {bc.short_date(deadline)}" if deadline else "기한 없음"]
        received = bc.received_date(t)
        if received:
            bits.append(f"받은 날 {bc.short_date(received)}")
        try:
            dept = t["department"]
        except (KeyError, IndexError):
            dept = None
        if dept:
            bits.append(dept)
        return f"{t['title']}\n{' · '.join(bits)}"

    def _picked(self):
        return [t for t in self._candidates if t["task_id"] not in self._excluded]

    def _update_summary(self):
        picked = self._picked()
        text = f"<b>{bc.range_text(self._basis, self._start, self._end)} · {len(picked)}건 선택</b>"
        bd = bc.breakdown_text(picked, self._today)
        if bd:
            text += f"<br>{bd}"
        self.summary_label.setText(text)

        warns = bc.warnings_for(picked, self._today)
        self.warn_label.setText("\n".join(warns))
        self.warn_label.setVisible(bool(warns))

        self.preview_label.setText(f"미리 보기 {len(self._candidates)}건")
        all_picked = len(picked) == len(self._candidates)
        self.toggle_all_btn.setText("모두 해제" if all_picked else "모두 선택")
        self.toggle_all_btn.setVisible(bool(self._candidates))

        self.ok_btn.setText(f"{len(picked)}건 완료 처리")
        self.ok_btn.setEnabled(bool(picked))

    # ---------- 이벤트 ----------

    def _on_basis(self, basis):
        if basis == self._basis:
            self._rebuild()  # 같은 버튼을 다시 눌러 체크가 풀리지 않게
            return
        self._basis = basis
        self._excluded.clear()
        self._apply_preset(self._presets()[0])
        self._rebuild()

    def _on_preset(self, preset):
        self._apply_preset(preset)
        self._excluded.clear()
        self._rebuild()

    def _on_dates_changed(self, *_):
        if self._updating:
            return
        end = _to_date(self.end_edit.date())
        start = None
        if not self.from_start_chk.isChecked():
            start = min(_to_date(self.start_edit.date()), end)
        # Qt 날짜 칸은 날짜가 그대로여도 Enter를 누르면 dateChanged를 보낸다.
        # 기간이 실제로 안 바뀌었으면 풀어 둔 체크·고른 빠른 선택을 지우지 않는다.
        if start == self._start and end == self._end:
            return
        self._preset_key = None
        self._start = start
        self._end = end
        self._excluded.clear()
        self._rebuild()

    def _on_from_start_toggled(self, checked):
        if self._updating:
            return
        self._preset_key = None
        if checked:
            self._start = None
        else:
            end = self._end or self._today
            self._start = end - timedelta(days=6)
        self._excluded.clear()
        self._rebuild()

    def _on_item_changed(self, item):
        if self._updating:
            return
        task_id = item.data(Qt.UserRole)
        if task_id is None:
            return
        if item.checkState() == Qt.Checked:
            self._excluded.discard(task_id)
        else:
            self._excluded.add(task_id)
        self._update_summary()

    def _on_toggle_all(self):
        if len(self._picked()) == len(self._candidates):
            self._excluded = {t["task_id"] for t in self._candidates}
        else:
            self._excluded.clear()
        self._fill_list()
        self._update_summary()

    # ---------- 결과 ----------

    def selected_ids(self):
        return [t["task_id"] for t in self._picked()]
