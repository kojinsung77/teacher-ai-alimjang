# -*- coding: utf-8 -*-
"""설정 화면 — SettingsPageView가 카드 4개(일반/Gemini AI/메신저 설정/
개인정보 마스킹 명단 설정)를 2x2로 보여주고, 각 카드는 자기 내용만
다루는 모달을 하나씩 연다. 카드 사이에 내용이 겹치지 않는 게 원칙이다:
- GeneralSettingsDialog: 자동 시작·시스템 트레이·창 닫기 동작, 버전 표시,
  업데이트 확인.
- AISettingsDialog: 분석 기간 / AI 서비스(Gemini 고정) / API 키(표시·숨김
  토글 포함) / 모델 선택 / 연결 테스트 / 키 발급 가이드. main.py의 최초
  실행 흐름에서도 그대로 재사용한다.
- 메신저 설정·개인정보 마스킹은 이 파일이 아니라 messenger_setup_dialog.py/
  privacy_masking_dialog.py의 기존 다이얼로그를 카드에서 곧바로 연다.

GeneralSettingsDialog와 AISettingsDialog는 폼 구성 로직을 _SettingsFormMixin
에서 공유해서 코드 중복을 피한다."""

import webbrowser

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QSpinBox, QFrame, QApplication,
    QCheckBox, QRadioButton, QButtonGroup, QWidget, QMessageBox
)

from .. import config, db
from ..ai import gemini_client
from ..core import autostart, holidays_sync, update_check
from .common_widgets import HoverLiftCard
from .messenger_setup_dialog import MessengerSetupDialog
from .privacy_masking_dialog import PrivacyMaskingDialog

_LABEL_WIDTH = 110

# (db 저장값, 표시 라벨). "0"은 "끄기" — main_window.py의
# MainWindow._apply_auto_sync_interval()이 그대로 해석한다.
_AUTO_CHECK_INTERVALS = [
    ("5", "5분 (기본)"),
    ("10", "10분"),
    ("30", "30분"),
    ("0", "끄기"),
]


def _relative_time_kr(iso_str: str) -> str:
    """ISO datetime 문자열을 "3분 전" 같은 상대 시각 문구로. 파싱 실패
    시(값이 없거나 형식이 이상하면) 빈 문자열을 돌려준다."""
    from datetime import datetime
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
    except ValueError:
        return ""
    seconds = int((datetime.now() - dt).total_seconds())
    if seconds < 60:
        return "방금 전"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}분 전"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}시간 전"
    days = hours // 24
    return f"{days}일 전"


def _last_auto_check_text() -> str:
    relative = _relative_time_kr(db.get_setting("last_auto_check_at", ""))
    if not relative:
        return "마지막 자동 확인: 아직 없음"
    return f"마지막 자동 확인: {relative}"


class _SettingsFormMixin:
    """AISettingsDialog와 SettingsPageView가 함께 쓰는 폼 내용/동작.
    QObject를 상속하지 않는 순수 Python 믹스인이라 QDialog/QWidget 중
    무엇과 다중 상속해도 안전하다(Qt는 QObject 계열 다중 상속을 허용하지
    않지만, 이런 '평범한 클래스' 믹스인은 문제없다)."""

    @staticmethod
    def _fixed_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("FormLabel")
        lbl.setFixedWidth(_LABEL_WIDTH)
        return lbl

    def _build_general_section(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        general_title = QLabel("일반")
        general_title.setObjectName("SectionTitle")
        v.addWidget(general_title)

        self.autostart_check = QCheckBox("Windows 시작 시 자동으로 실행")
        self.autostart_check.setChecked(autostart.is_enabled())
        self.autostart_check.toggled.connect(self._on_autostart_toggled)
        v.addWidget(self.autostart_check)

        self.autostart_hide_check = QCheckBox("Windows 시작 시 시스템 트레이에서 실행")
        self.autostart_hide_check.setChecked(
            db.get_setting("autostart_hide_window", "1") == "1"
        )
        self.autostart_hide_check.setEnabled(self.autostart_check.isChecked())
        v.addWidget(self.autostart_hide_check)

        close_label = QLabel("창 닫기 동작")
        close_label.setObjectName("FormLabel")
        v.addWidget(close_label)

        self.close_action_group = QButtonGroup(box)
        self.close_tray_radio = QRadioButton("X 버튼을 누르면 시스템 트레이로 최소화")
        self.close_quit_radio = QRadioButton("X 버튼을 누르면 프로그램 완전 종료")
        self.close_action_group.addButton(self.close_tray_radio)
        self.close_action_group.addButton(self.close_quit_radio)
        if db.get_setting("close_action", "tray") == "quit":
            self.close_quit_radio.setChecked(True)
        else:
            self.close_tray_radio.setChecked(True)
        v.addWidget(self.close_tray_radio)
        v.addWidget(self.close_quit_radio)

        v.addSpacing(4)
        self.auto_note_check = QCheckBox("평일 자동 알림장 생성")
        self.auto_note_check.setChecked(db.get_setting("auto_note_enabled", "1") == "1")
        self.auto_note_check.setToolTip(
            "평일(주말·휴일 제외) 아침 앱을 켜면 자동으로 오늘 알림장을 만듭니다.\n"
            "꺼두면 예전처럼 [업무] 화면의 [오늘 알림장 만들기] 버튼으로만 만들 수 있습니다."
        )
        v.addWidget(self.auto_note_check)

        v.addSpacing(4)
        neis_section_label = QLabel("학사일정 자동 채움 (선택)")
        neis_section_label.setObjectName("FormLabel")
        v.addWidget(neis_section_label)

        neis_key_row = QHBoxLayout()
        self.neis_key_input = QLineEdit()
        self.neis_key_input.setEchoMode(QLineEdit.Password)
        self.neis_key_input.setPlaceholderText("NEIS Open API 인증키")
        existing_neis_key = holidays_sync.load_api_key()
        if existing_neis_key:
            self.neis_key_input.setText(existing_neis_key)
        self.neis_key_input.deselect()
        neis_key_row.addWidget(self.neis_key_input, 1)

        self.neis_key_toggle_btn = QPushButton("보기")
        self.neis_key_toggle_btn.setObjectName("ToggleButton")
        self.neis_key_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.neis_key_toggle_btn.clicked.connect(self.on_toggle_neis_key_visibility)
        neis_key_row.addWidget(self.neis_key_toggle_btn)
        v.addLayout(neis_key_row)

        neis_code_row = QHBoxLayout()
        neis_code_row.setSpacing(8)

        atpt_col = QVBoxLayout()
        atpt_label = QLabel("시도교육청코드")
        atpt_label.setObjectName("Muted")
        atpt_col.addWidget(atpt_label)
        self.neis_atpt_input = QLineEdit()
        self.neis_atpt_input.setText(holidays_sync.get_atpt_code())
        self.neis_atpt_input.setPlaceholderText("예: P10")
        atpt_col.addWidget(self.neis_atpt_input)
        neis_code_row.addLayout(atpt_col, 1)

        school_col = QVBoxLayout()
        school_label = QLabel("학교코드")
        school_label.setObjectName("Muted")
        school_col.addWidget(school_label)
        self.neis_school_input = QLineEdit()
        self.neis_school_input.setText(holidays_sync.get_school_code())
        self.neis_school_input.setPlaceholderText("예: 8321103")
        school_col.addWidget(self.neis_school_input)
        neis_code_row.addLayout(school_col, 1)

        v.addLayout(neis_code_row)

        neis_desc = QLabel(
            "방학·재량휴업일·수요/금요대체일 같은 학교 자체 일정과 모의고사·\n"
            "행사 일정을 NEIS(나이스 교육정보 개방 포털)에서 자동으로 가져와\n"
            "[일정] 화면에 표시하고, 등교하지 않는 날에는 자동 알림장을 만들지\n"
            "않습니다. 기본값은 전주중앙여자고등학교이며, 다른 학교는 위\n"
            "코드를 해당 학교 것으로 바꾸면 됩니다(NEIS Open API 홈페이지의\n"
            "학교 검색에서 확인 가능). 인증키를 비워두면 이 자동 채움만\n"
            "꺼지고, [일정] 화면에서 직접 휴일을 지정할 수 있습니다."
        )
        neis_desc.setObjectName("Muted")
        neis_desc.setWordWrap(True)
        v.addWidget(neis_desc)

        return box

    def _on_autostart_toggled(self, checked: bool):
        self.autostart_hide_check.setEnabled(checked)

    def on_toggle_neis_key_visibility(self):
        if self.neis_key_input.echoMode() == QLineEdit.Password:
            self.neis_key_input.setEchoMode(QLineEdit.Normal)
            self.neis_key_toggle_btn.setText("숨기기")
        else:
            self.neis_key_input.setEchoMode(QLineEdit.Password)
            self.neis_key_toggle_btn.setText("보기")

    def _build_gemini_section(self, root: QVBoxLayout):
        """Gemini AI 설정 본문만 root 레이아웃에 채운다: 분석 기간/AI
        서비스/API 키/모델 선택/연결 테스트/발급 가이드 박스 여섯 가지뿐이다.
        일반 설정·메신저 설정·개인정보 마스킹은 각자 자기 카드/모달이
        따로 담당하므로 여기서는 다루지 않는다(설정 페이지가 카드 4개로
        나뉘기 전에는 이 모달 하나에 전부 들어있었지만, 지금은 카드별로
        내용이 겹치지 않아야 한다).
        다이얼로그의 제목/버튼 행 등 겉모습은 호출부의 _build_ui에서
        따로 만든다 — 그래서 여기서는 "Gemini AI" 제목을 또 넣지 않는다
        (호출부 AISettingsDialog._build_ui가 PageTitle로 이미 넣으므로,
        여기서도 넣으면 같은 제목이 두 번 겹쳐 보인다)."""
        desc = QLabel(
            "이 프로그램은 선생님 본인의 Gemini API 키를 사용합니다. 키는 이 PC의\n"
            "Windows 자격 증명 관리자에 암호화되어 저장되며, 앱 개발자나 다른 교사는\n"
            "이 키를 볼 수 없습니다."
        )
        desc.setObjectName("Muted")
        desc.setWordWrap(True)
        root.addWidget(desc)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.period_spin = QSpinBox()
        self.period_spin.setRange(1, 30)
        self.period_spin.setSuffix(" 일")
        self.period_spin.setValue(int(db.get_setting("analyze_days", "1")))
        form.addRow(self._fixed_label("분석 기간"), self.period_spin)

        ai_service_value = QLabel("Google Gemini")
        form.addRow(self._fixed_label("AI 서비스"), ai_service_value)

        key_row = QHBoxLayout()
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.Password)
        self.key_input.setPlaceholderText("Gemini API 키를 입력하세요")
        existing = gemini_client.load_api_key()
        if existing:
            self.key_input.setText(existing)
        self.key_input.deselect()
        key_row.addWidget(self.key_input, 1)

        self.toggle_key_btn = QPushButton("보기")
        self.toggle_key_btn.setObjectName("ToggleButton")
        self.toggle_key_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_key_btn.clicked.connect(self.on_toggle_key_visibility)
        key_row.addWidget(self.toggle_key_btn)
        form.addRow(self._fixed_label("API 키"), key_row)

        self.model_combo = QComboBox()
        for value, label in config.GEMINI_MODEL_OPTIONS:
            self.model_combo.addItem(label, userData=value)
        current = gemini_client.current_model()
        idx = self.model_combo.findData(current)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        form.addRow(self._fixed_label("모델 선택"), self.model_combo)

        self.auto_check_combo = QComboBox()
        for value, label in _AUTO_CHECK_INTERVALS:
            self.auto_check_combo.addItem(label, userData=value)
        current_interval = db.get_setting("auto_check_interval_min", "5")
        idx = self.auto_check_combo.findData(current_interval)
        if idx >= 0:
            self.auto_check_combo.setCurrentIndex(idx)
        form.addRow(self._fixed_label("자동 확인 주기"), self.auto_check_combo)

        root.addLayout(form)

        self.last_check_label = QLabel(_last_auto_check_text())
        self.last_check_label.setObjectName("Muted")
        root.addWidget(self.last_check_label)

        self.analyze_images_check = QCheckBox("캡처 이미지도 함께 분석")
        self.analyze_images_check.setChecked(db.get_setting("analyze_images", "1") == "1")
        self.analyze_images_check.setToolTip(
            "텍스트가 거의 없이 캡처 이미지만 온 공지도 업무로 인식합니다.\n"
            "이미지 속 이름·표 내용은 결과에 그대로 옮기지 않도록 안전장치가 있습니다."
        )
        root.addWidget(self.analyze_images_check)

        test_row = QHBoxLayout()
        test_btn = QPushButton("연결 테스트")
        test_btn.setObjectName("SecondaryButton")
        test_btn.setCursor(Qt.PointingHandCursor)
        test_btn.clicked.connect(self.on_test)
        test_row.addWidget(test_btn)
        test_row.addStretch(1)
        root.addLayout(test_row)

        self.status_label = QLabel("")
        self.status_label.setObjectName("Muted")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        root.addWidget(self._build_api_key_help_box())

    def _build_api_key_help_box(self) -> QFrame:
        box = QFrame()
        box.setObjectName("InfoBox")
        v = QVBoxLayout(box)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(6)

        title = QLabel("API 키가 없으신가요?")
        title.setObjectName("InfoBoxTitle")
        v.addWidget(title)

        steps = [
            "1. 아래 [Google AI Studio 열기] 버튼을 누르면 브라우저가 열립니다.",
            "2. 구글 계정으로 로그인합니다.",
        ]
        for s in steps:
            lbl = QLabel(s)
            lbl.setObjectName("InfoBoxStep")
            v.addWidget(lbl)

        warn = QLabel("   학교 계정이 막혀 있으면 개인 Gmail 계정을 쓰세요.")
        warn.setObjectName("InfoBoxWarning")
        v.addWidget(warn)

        more_steps = [
            "3. [API 키 만들기 / Create API key]를 누릅니다.",
            "4. 프로젝트를 고르라고 하면 아무거나 선택하거나 새로 만듭니다.",
            "5. 만들어진 키(AIza...로 시작)를 복사합니다.",
            "6. 위 API 키 칸에 붙여넣고 [연결 테스트]를 누릅니다.",
        ]
        for s in more_steps:
            lbl = QLabel(s)
            lbl.setObjectName("InfoBoxStep")
            v.addWidget(lbl)

        open_btn = QPushButton("Google AI Studio 열기")
        open_btn.setObjectName("SecondaryButton")
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.clicked.connect(lambda: webbrowser.open(config.GOOGLE_AI_STUDIO_KEY_URL))
        v.addWidget(open_btn)

        return box

    def on_toggle_key_visibility(self):
        if self.key_input.echoMode() == QLineEdit.Password:
            self.key_input.setEchoMode(QLineEdit.Normal)
            self.toggle_key_btn.setText("숨기기")
        else:
            self.key_input.setEchoMode(QLineEdit.Password)
            self.toggle_key_btn.setText("보기")

    def _set_status(self, ok: bool, text: str):
        self.status_label.setObjectName("StatusOk" if ok else "StatusError")
        self.status_label.setText(("✓ " if ok else "✗ ") + text)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def on_test(self):
        key = self.key_input.text().strip()
        model = self.model_combo.currentData()
        self.status_label.setObjectName("Muted")
        self.status_label.setText("연결 확인 중...")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        QApplication.processEvents()
        ok, message = gemini_client.test_connection(key, model)
        db.set_setting("gemini_last_test_ok", "1" if ok else "0")
        self._set_status(ok, message)

    def _persist_general_settings(self):
        autostart.set_enabled(self.autostart_check.isChecked())
        db.set_setting(
            "autostart_hide_window",
            "1" if self.autostart_hide_check.isChecked() else "0",
        )
        db.set_setting(
            "close_action",
            "quit" if self.close_quit_radio.isChecked() else "tray",
        )
        db.set_setting(
            "auto_note_enabled",
            "1" if self.auto_note_check.isChecked() else "0",
        )
        neis_key = self.neis_key_input.text().strip()
        if neis_key:
            holidays_sync.save_api_key(neis_key)

        atpt_code = self.neis_atpt_input.text().strip()
        school_code = self.neis_school_input.text().strip()
        if atpt_code and school_code and (atpt_code, school_code) != (
            holidays_sync.get_atpt_code(), holidays_sync.get_school_code()
        ):
            holidays_sync.set_school(atpt_code, school_code)

    def _persist_gemini_settings(self):
        key = self.key_input.text().strip()
        if key:
            gemini_client.save_api_key(key)
        gemini_client.set_current_model(self.model_combo.currentData())
        db.set_setting("analyze_days", str(self.period_spin.value()))
        db.set_setting("auto_check_interval_min", self.auto_check_combo.currentData())
        db.set_setting("analyze_images", "1" if self.analyze_images_check.isChecked() else "0")


class AISettingsDialog(QDialog, _SettingsFormMixin):
    """Gemini AI 설정 전용 모달 (분석 기간/API 키/모델/연결 테스트/발급
    가이드). 두 곳에서 쓰인다:
    - main.py의 최초 실행 흐름(MainWindow가 아직 없는 시점의 블로킹 모달)
    - 설정 페이지의 'Gemini AI' 카드를 눌렀을 때
    일반 설정·메신저·개인정보 마스킹은 각자 별도 모달이 맡는다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gemini AI 설정")
        self.setMinimumWidth(480)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)

        title = QLabel("Gemini AI")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        self._build_gemini_section(root)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryButton")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("PrimaryButton")
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.clicked.connect(self.on_ok)
        btn_row.addWidget(ok_btn)
        root.addLayout(btn_row)

    def on_ok(self):
        self._persist_gemini_settings()
        self.accept()


class GeneralSettingsDialog(QDialog, _SettingsFormMixin):
    """설정 페이지의 '일반' 카드에서 여는 모달 — 앱 시작 방식·시스템
    트레이·창 닫기 동작만 다룬다 (Gemini AI 관련 항목은 별도로
    AISettingsDialog가 맡는다)."""

    # 수동 확인으로 새 버전을 찾았을 때 — SettingsPageView를 거쳐
    # MainWindow까지 올려보내서, 자동 확인 때와 똑같이 대시보드에 실제
    # 배너를 띄우고 백그라운드 다운로드까지 시작하게 한다(단순히 여기서
    # 안내 문구만 보여주고 끝나면 [지금 설치]로 이어지는 실제 흐름을
    # 탈 수 없다).
    updateFound = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("일반 설정")
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)

        title = QLabel("일반")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        root.addWidget(self._build_general_section())

        update_row = QHBoxLayout()
        update_row.setSpacing(10)
        version_label = QLabel(f"버전 {config.APP_VERSION}")
        version_label.setObjectName("Muted")
        update_row.addWidget(version_label)
        update_row.addStretch(1)
        update_btn = QPushButton("지금 업데이트 확인")
        update_btn.setObjectName("SecondaryButton")
        update_btn.setCursor(Qt.PointingHandCursor)
        update_btn.clicked.connect(self.on_check_update)
        update_row.addWidget(update_btn)
        root.addLayout(update_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryButton")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("PrimaryButton")
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.clicked.connect(self.on_ok)
        btn_row.addWidget(ok_btn)
        root.addLayout(btn_row)

    def on_check_update(self):
        """수동 업데이트 확인 — 자동 확인과 달리 사용자가 직접 누른
        행동이라 결과를 항상 알려준다(자동 확인은 실패해도 조용히
        무시하지만, 이건 눌렀는데 아무 반응이 없으면 안 되므로 다르다).
        다만 기술적인 에러 메시지 대신 교사가 이해할 수 있는 문구로만
        안내한다."""
        info = update_check.fetch_latest_version_info()
        if not info:
            QMessageBox.information(
                self, "업데이트 확인",
                "지금은 업데이트 정보를 확인할 수 없습니다. 잠시 후 다시 시도해 주세요."
            )
            return
        if update_check.is_newer(info["version"], config.APP_VERSION):
            notes = info.get("notes", "")
            text = f"새 버전 v{info['version']}이 있습니다.\n'오늘' 화면에 안내 배너가 뜹니다."
            if notes:
                text += f"\n{notes}"
            QMessageBox.information(self, "업데이트 확인", text)
            self.updateFound.emit(info)
        else:
            QMessageBox.information(self, "업데이트 확인", "이미 최신 버전을 사용하고 있습니다.")

    def on_ok(self):
        self._persist_general_settings()
        self.accept()


class _SettingsCard(HoverLiftCard):
    """설정 페이지의 카드 하나(아이콘 + 제목 + 설명 + 화살표, 상태 배지는
    선택). 카드 전체가 클릭 가능하고 hover 시 그림자가 진해지며 살짝
    떠오른다(HoverLiftCard)."""

    def __init__(self, icon: str, title: str, desc: str, badge: tuple[str, bool] | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsCard")
        self.setMinimumHeight(108)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(16)

        icon_lbl = QLabel(icon)
        icon_lbl.setObjectName("SettingsCardIcon")
        outer.addWidget(icon_lbl, 0, Qt.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("SettingsCardTitle")
        title_row.addWidget(title_lbl)
        if badge is not None:
            badge_text, badge_ok = badge
            badge_lbl = QLabel(badge_text)
            badge_lbl.setObjectName("StatusBadgeOk" if badge_ok else "StatusBadgeWarn")
            title_row.addWidget(badge_lbl)
        title_row.addStretch(1)
        text_col.addLayout(title_row)

        desc_lbl = QLabel(desc)
        desc_lbl.setObjectName("SettingsCardDesc")
        desc_lbl.setWordWrap(True)
        text_col.addWidget(desc_lbl)

        outer.addLayout(text_col, 1)

        arrow_lbl = QLabel("›")
        arrow_lbl.setObjectName("SettingsCardArrow")
        outer.addWidget(arrow_lbl, 0, Qt.AlignVCenter)


class SettingsPageView(QWidget, _SettingsFormMixin):
    """MainWindow의 '설정' 메뉴 — 다른 메뉴(오늘/메시지/업무/일정/지난
    알림장)와 완전히 동일하게 switch_page()로 콘텐츠 영역이 그대로
    전환되는 일반 페이지다. 모달도 아니고 슬라이드 패널도 아니다.

    폼을 직접 풀어놓는 대신 카드 4개(일반/Gemini AI/메신저 설정/개인정보
    마스킹 명단 설정)를 2x2로 보여주고, 각 카드를 누르면 해당 모달이
    뜬다 — 실제 설정 폼은 그 모달들(GeneralSettingsDialog/AISettingsDialog/
    MessengerSetupDialog/PrivacyMaskingDialog)이 담당하고 이 페이지는
    진입점 역할만 한다.

    화면에 들어올 때마다(MainWindow.switch_page가 refresh() 호출) 카드를
    새로 그려서 Gemini AI 카드의 연결 상태 배지 등 최신 값을 반영한다 —
    다른 페이지들이 매번 refresh()로 최신 데이터를 다시 그리는 것과
    동일한 패턴."""

    settingsChanged = Signal()  # demo_mode 등 다른 화면이 참고하는 값이 바뀌었을 수 있음
    updateFound = Signal(dict)  # GeneralSettingsDialog의 수동 확인 결과를 MainWindow까지 전달

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    # ---------- UI ----------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(44, 36, 44, 36)
        root.setSpacing(16)

        title = QLabel("설정")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        self.grid = QGridLayout()
        self.grid.setSpacing(16)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        root.addLayout(self.grid)
        root.addStretch(1)

    def refresh(self):
        """화면에 들어올 때마다 카드를 다시 그려 Gemini AI 연결 상태
        배지 등 최신 값을 반영한다 (다른 페이지들과 동일한 refresh() 패턴)."""
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        has_key = bool(gemini_client.load_api_key())
        last_test_ok = db.get_setting("gemini_last_test_ok", "0") == "1"
        gemini_badge = ("✓ 연결됨", True) if (has_key and last_test_ok) else ("⚠ 설정 필요", False)
        gemini_desc = "API 키, 모델, 분석 기간, 자동 확인 주기 설정\n" + _last_auto_check_text()

        general_card = _SettingsCard("⚙️", "일반", "앱 시작 방식, 시스템 트레이 설정")
        general_card.clicked.connect(self.on_open_general)
        self.grid.addWidget(general_card, 0, 0)

        gemini_card = _SettingsCard("✨", "Gemini AI", gemini_desc, badge=gemini_badge)
        gemini_card.clicked.connect(self.on_open_gemini)
        self.grid.addWidget(gemini_card, 0, 1)

        messenger_card = _SettingsCard("💬", "메신저 설정", "쿨메신저 연동 정보를 다시 설정합니다")
        messenger_card.clicked.connect(self.on_open_messenger_setup)
        self.grid.addWidget(messenger_card, 1, 0)

        privacy_card = _SettingsCard("🔒", "개인정보 마스킹 명단 설정", "이름을 가릴 학생/교직원 명단을 관리합니다")
        privacy_card.clicked.connect(self.on_open_privacy_masking)
        self.grid.addWidget(privacy_card, 1, 1)

    # ---------- 액션 ----------

    def on_open_general(self):
        dlg = GeneralSettingsDialog(self)
        dlg.updateFound.connect(self.updateFound)
        dlg.exec()
        self.refresh()

    def on_open_gemini(self):
        AISettingsDialog(self).exec()
        # API 키/연결 테스트 상태가 바뀌었을 수 있으니 배지를 새로 그린다.
        self.settingsChanged.emit()
        self.refresh()

    def on_open_messenger_setup(self):
        MessengerSetupDialog(self).exec()
        # 메신저 재설정으로 demo_mode/로그인명이 바뀌었을 수 있다.
        self.settingsChanged.emit()
        self.refresh()

    def on_open_privacy_masking(self):
        PrivacyMaskingDialog(self).exec()
