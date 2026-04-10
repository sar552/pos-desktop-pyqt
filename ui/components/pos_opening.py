"""Kassa ochish dialogi — POS Opening Entry yaratish."""
import json
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QWidget, QComboBox
)
from PyQt6.QtCore import pyqtSignal, Qt, QThread, QTimer
from PyQt6.QtGui import QDoubleValidator
from core.api import FrappeAPI
from core.config import load_config
from core.logger import get_logger
from database.models import PosShift, db
from ui.components.numpad import TouchNumpad
from ui.components.dialogs import ClickableLineEdit
from ui.component_styles import get_component_styles
from ui.theme_manager import ThemeManager

logger = get_logger(__name__)


class OpeningWorker(QThread):
    finished = pyqtSignal(bool, str, str)  # success, message, opening_entry_name

    def __init__(self, api: FrappeAPI, pos_profile: str, company: str, balance_details: list):
        super().__init__()
        self.api = api
        self.pos_profile = pos_profile
        self.company = company
        self.balance_details = balance_details

    def run(self):
        success, response = self.api.call_method(
            "posawesome.posawesome.api.shifts.create_opening_voucher",
            {
                "pos_profile": self.pos_profile,
                "company": self.company,
                "balance_details": json.dumps(self.balance_details),
            },
        )

        if success and isinstance(response, dict):
            shift_data = response.get("pos_opening_shift", {})
            name = shift_data.get("name", "")
            self._save_local_shift(name)
            self.finished.emit(True, "Kassa muvaffaqiyatli ochildi!", name)
        else:
            response_text = str(response or "")
            if "Server bilan aloqa" in response_text or "timeout" in response_text.lower():
                # Faqat real network xatoda oflayn ochishga ruxsat beramiz.
                self._save_local_shift(None)
                self.finished.emit(False, "Server bilan aloqa yo'q. Kassa lokal ochildi.", "")
                return

            # Server javob qaytardi, demak lokal ochish mumkin emas.
            self.finished.emit(False, f"Server xatosi: {response_text}", "")

    def _save_local_shift(self, opening_entry):
        try:
            db.connect(reuse_if_open=True)
            # Avvalgi ochiq shiftlarni yopish
            PosShift.update(status="Closed").where(PosShift.status == "Open").execute()
            PosShift.create(
                opening_entry=opening_entry,
                pos_profile=self.pos_profile,
                company=self.company,
                user=self.api.user or "offline",
                opening_amounts=json.dumps(self.balance_details),
                status="Open",
            )
        except Exception as e:
            logger.error("Lokal shift saqlashda xatolik: %s", e)
        finally:
            if not db.is_closed():
                db.close()


class PosOpeningDialog(QDialog):
    opening_completed = pyqtSignal(str)  # opening_entry name
    exit_requested = pyqtSignal()  # dasturdan chiqish
    logout_requested = pyqtSignal()  # boshqa kassir uchun logout

    def __init__(self, parent, api: FrappeAPI, dialog_data: dict = None):
        super().__init__(parent)
        self.api = api
        self.dialog_data = dialog_data or {}
        self.config = load_config()
        self.payment_inputs = {}
        self.active_input = None

        styles = get_component_styles()
        self.colors = ThemeManager.get_theme_colors()
        self.profile_style_active = styles["opening_input_active"]
        self.profile_style_idle = styles["opening_input_idle"]

        if not self.dialog_data:
            success, response = self.api.call_method("posawesome.posawesome.api.shifts.get_opening_dialog_data")
            if success and isinstance(response, dict):
                self.dialog_data = response

        self.profiles = self.dialog_data.get("pos_profiles_data", [])
        self.companies = self.dialog_data.get("companies", [])
        self.payment_methods = self.dialog_data.get("payments_method", [])

        self.init_ui()
        self._populate_company_and_profile()
        QTimer.singleShot(50, self._center_on_parent)

    def _center_on_parent(self):
        if self.parent():
            p_geo = self.parent().frameGeometry()
            c_geo = self.frameGeometry()
            c_geo.moveCenter(p_geo.center())
            self.move(c_geo.topLeft())

    def init_ui(self):
        self.setWindowTitle("Kassa ochish")
        self.setMinimumSize(640, 480)
        self.resize(780, 560)
        self.setModal(True)
        self.setWindowFlags(
            self.windowFlags()
            & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        styles = get_component_styles()
        colors = self.colors
        self.setStyleSheet(styles["opening_container"])

        main_h = QHBoxLayout(self)
        main_h.setContentsMargins(20, 20, 20, 20)
        main_h.setSpacing(20)

        # ── LEFT PANEL ───────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        # Header
        header = QFrame()
        header.setStyleSheet(styles["opening_header"])
        h_layout = QVBoxLayout(header)

        title = QLabel("KASSA OCHISH")
        title.setStyleSheet(f"color: rgba(255,255,255,0.7); font-size: 11px; font-weight: 700; letter-spacing: 2px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_layout.addWidget(title)

        self.company_combo = QComboBox()
        self.company_combo.setStyleSheet(styles["opening_combo"])
        self.company_combo.currentIndexChanged.connect(self._on_company_changed)
        h_layout.addWidget(self.company_combo)

        self.profile_combo = QComboBox()
        self.profile_combo.setStyleSheet(styles["opening_combo"])
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        h_layout.addWidget(self.profile_combo)

        left_layout.addWidget(header)

        # Payment mode inputs
        pay_label = QLabel("BOSHLANG'ICH SUMMALAR")
        pay_label.setStyleSheet(styles["opening_section_label"])
        left_layout.addWidget(pay_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background: transparent;")
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setSpacing(8)
        scroll.setWidget(self.scroll_content)
        left_layout.addWidget(scroll)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        btn_exit = QPushButton("Chiqish")
        btn_exit.setMinimumHeight(44)
        btn_exit.setStyleSheet(styles["opening_btn_secondary"])
        btn_exit.clicked.connect(self._on_exit)

        btn_logout = QPushButton("Logout")
        btn_logout.setMinimumHeight(44)
        btn_logout.setStyleSheet(styles["opening_btn_warning"])
        btn_logout.clicked.connect(self._on_logout)

        self.btn_open = QPushButton("KASSANI OCHISH")
        self.btn_open.setMinimumHeight(44)
        self.btn_open.setStyleSheet(styles["opening_btn_primary"])
        self.btn_open.clicked.connect(self._process_opening)

        btn_layout.addWidget(btn_exit, 1)
        btn_layout.addWidget(btn_logout, 1)
        btn_layout.addWidget(self.btn_open, 2)
        left_layout.addLayout(btn_layout)

        main_h.addWidget(left, 1)

        # ── RIGHT PANEL — Numpad ─────────────
        right = QWidget()
        right.setStyleSheet(f"background: {colors['bg_tertiary']}; border-radius: 12px;")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(10)

        numpad_lbl = QLabel("MIQDOR KIRITING")
        numpad_lbl.setStyleSheet(styles["opening_section_label"])
        right_layout.addWidget(numpad_lbl)

        self.numpad = TouchNumpad()
        self.numpad.digit_clicked.connect(self._on_numpad_clicked)
        right_layout.addWidget(self.numpad)
        right_layout.addStretch()

        main_h.addWidget(right, 1)

    def _populate_company_and_profile(self):
        self.company_combo.blockSignals(True)
        self.company_combo.clear()

        seen_companies = set()
        company_names = []
        for company in self.companies:
            if isinstance(company, dict):
                name = (company.get("name") or "").strip()
            else:
                name = str(company or "").strip()
            if name and name not in seen_companies:
                seen_companies.add(name)
                company_names.append(name)

        if not company_names:
            config_company = (self.config.get("company") or "").strip()
            if config_company:
                company_names.append(config_company)

        for name in company_names:
            self.company_combo.addItem(name, name)

        preferred_company = (self.config.get("company") or "").strip()
        idx = self.company_combo.findData(preferred_company)
        if idx < 0 and self.company_combo.count():
            idx = 0
        if idx >= 0:
            self.company_combo.setCurrentIndex(idx)
        self.company_combo.blockSignals(False)

        self._on_company_changed(self.company_combo.currentIndex())

    def _on_company_changed(self, _index: int):
        company = self.company_combo.currentData() or self.company_combo.currentText().strip()
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()

        available_profiles = [p for p in self.profiles if (p.get("company") or "").strip() == company] if company else list(self.profiles)
        if not available_profiles and self.config.get("pos_profile"):
            available_profiles = [{"name": self.config.get("pos_profile"), "company": company or self.config.get("company", "")}]

        for profile in available_profiles:
            self.profile_combo.addItem(profile.get("name", ""), profile)

        preferred_profile = (self.config.get("pos_profile") or "").strip()
        idx = self.profile_combo.findText(preferred_profile)
        if idx < 0 and self.profile_combo.count():
            idx = 0
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)
        self.profile_combo.blockSignals(False)

        self._on_profile_changed(self.profile_combo.currentIndex())

    def _clear_payment_rows(self):
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                while child_layout.count():
                    child_item = child_layout.takeAt(0)
                    child_widget = child_item.widget()
                    if child_widget is not None:
                        child_widget.deleteLater()
        self.payment_inputs = {}
        self.active_input = None

    def _on_profile_changed(self, _index: int):
        self._rebuild_payment_inputs()

    def _rebuild_payment_inputs(self):
        self._clear_payment_rows()
        selected_profile = self.profile_combo.currentData() or {}
        selected_profile_name = (selected_profile.get("name") or self.profile_combo.currentText() or "").strip()

        methods = []
        if selected_profile_name:
            methods = [
                row for row in self.payment_methods
                if (row.get("parent") or "").strip() == selected_profile_name and row.get("mode_of_payment")
            ]

        if not methods:
            methods = [
                {"mode_of_payment": mop}
                for mop in (self.config.get("payment_methods") or ["Cash"])
            ]

        for idx, method in enumerate(methods):
            mode = (method.get("mode_of_payment") or "").strip()
            if not mode:
                continue

            row = QHBoxLayout()
            lbl = QLabel(mode)
            lbl.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {self.colors['text_primary']};")

            inp = ClickableLineEdit()
            inp.setValidator(QDoubleValidator(0.0, 999999999.0, 2))
            inp.setPlaceholderText("0")
            inp.setText("0")
            inp.setMinimumWidth(140)
            inp.setMaximumWidth(220)
            inp.setMinimumHeight(44)
            inp.setAlignment(Qt.AlignmentFlag.AlignRight)
            inp.clicked.connect(self._set_active_input)
            inp.setStyleSheet(self.profile_style_active if idx == 0 else self.profile_style_idle)

            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(inp)
            self.payment_inputs[mode] = inp
            self.scroll_layout.addLayout(row)

            if idx == 0:
                self.active_input = inp
                inp.setFocus()

        self.scroll_layout.addStretch()

    def _on_exit(self):
        self.exit_requested.emit()
        self.reject()

    def _on_logout(self):
        self.logout_requested.emit()
        self.reject()

    def _set_active_input(self, inp):
        # Reset previous
        if self.active_input:
            self.active_input.setStyleSheet(self.profile_style_idle)
        self.active_input = inp
        inp.setStyleSheet(self.profile_style_active)
        inp.setFocus()

    def _on_numpad_clicked(self, action: str):
        if not self.active_input:
            return
        current = self.active_input.text()
        if action == "CLEAR":
            self.active_input.setText("0")
        elif action == "BACKSPACE":
            new_val = current[:-1] if len(current) > 1 else "0"
            self.active_input.setText(new_val)
        elif action == ".":
            if "." not in current:
                self.active_input.setText(current + ".")
        else:
            if current == "0":
                self.active_input.setText(action)
            else:
                self.active_input.setText(current + action)

    def _process_opening(self):
        self.btn_open.setEnabled(False)
        self.btn_open.setText("Kassa ochilmoqda...")

        balance_details = []
        for mode, inp in self.payment_inputs.items():
            try:
                amount = float(inp.text() or 0)
            except ValueError:
                amount = 0
            balance_details.append({
                "mode_of_payment": mode,
                "opening_amount": amount,
            })

        # Kassa ochish processiga profilni jo'natish
        provider = self.profile_combo.currentData() or {}
        selected_profile = provider.get("name") or self.profile_combo.currentText().strip() or self.config.get("pos_profile", "")
        company = provider.get("company") or self.company_combo.currentData() or self.company_combo.currentText().strip() or self.config.get("company", "")

        self.worker = OpeningWorker(self.api, selected_profile, company, balance_details)
        self.worker.finished.connect(self._on_opening_finished)
        self.worker.start()

    def _on_opening_finished(self, success: bool, message: str, opening_entry: str):
        self.btn_open.setEnabled(True)
        self.btn_open.setText("KASSANI OCHISH")

        if success:
            self.opening_completed.emit(opening_entry)
            self.accept()
        elif "Server xatosi" in message:
            from ui.components.dialogs import InfoDialog
            InfoDialog(self, "Xatolik", message, kind="error").exec()
        else:
            # Oflayn — lokal ochildi, POS ga ruxsat beramiz
            logger.warning("Kassa oflayn ochildi: %s", message)
            self.opening_completed.emit("")
            self.accept()
