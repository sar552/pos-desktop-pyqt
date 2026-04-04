"""Kassa yopish dialogi — POS Closing Shift yaratish."""
import json
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
    QWidget,
    QGridLayout,
)
from PyQt6.QtCore import pyqtSignal, Qt, QThread, QTimer
from PyQt6.QtGui import QDoubleValidator
from core.api import FrappeAPI
from core.logger import get_logger
from database.models import PosShift, db
from ui.components.numpad import TouchNumpad
from ui.components.dialogs import ClickableLineEdit, InfoDialog

logger = get_logger(__name__)


class ClosingDataWorker(QThread):
    """Serverdan closing shift draft va overview ma'lumotlarini olish."""

    finished = pyqtSignal(bool, object)  # success, payload/error

    def __init__(self, api: FrappeAPI, opening_entry: str):
        super().__init__()
        self.api = api
        self.opening_entry = opening_entry

    def run(self):
        success, opening_doc = self.api.call_method(
            "frappe.client.get",
            {"doctype": "POS Opening Shift", "name": self.opening_entry},
        )
        if not success or not isinstance(opening_doc, dict):
            self.finished.emit(False, f"POS Opening Shift olinmadi: {opening_doc}")
            return

        success, closing_doc = self.api.call_method(
            "posawesome.posawesome.doctype.pos_closing_shift.pos_closing_shift.make_closing_shift_from_opening",
            {"opening_shift": json.dumps(opening_doc)},
        )
        if not success or not isinstance(closing_doc, dict):
            self.finished.emit(False, f"Closing draft yaratilmadi: {closing_doc}")
            return

        overview_success, overview = self.api.call_method(
            "posawesome.posawesome.doctype.pos_closing_shift.pos_closing_shift.get_closing_shift_overview",
            {"pos_opening_shift": self.opening_entry},
        )
        if not overview_success or not isinstance(overview, dict):
            overview = {}

        self.finished.emit(
            True,
            {
                "opening_doc": opening_doc,
                "closing_shift": closing_doc,
                "overview": overview,
            },
        )


class ClosingWorker(QThread):
    """Kassani yopish — POS Closing Shift submit."""

    finished = pyqtSignal(bool, str)

    def __init__(self, api: FrappeAPI, closing_shift_doc: dict):
        super().__init__()
        self.api = api
        self.closing_shift_doc = closing_shift_doc

    def run(self):
        success, response = self.api.call_method(
            "posawesome.posawesome.doctype.pos_closing_shift.pos_closing_shift.submit_closing_shift",
            {"closing_shift": json.dumps(self.closing_shift_doc)},
        )
        if success:
            self._close_local_shift()
            if isinstance(response, str):
                self.finished.emit(True, f"Kassa yopildi: {response}")
            else:
                self.finished.emit(True, "Kassa muvaffaqiyatli yopildi.")
            return

        self.finished.emit(False, f"Kassa yopishda xatolik: {response}")

    def _close_local_shift(self):
        try:
            import datetime

            db.connect(reuse_if_open=True)
            PosShift.update(
                status="Closed",
                closed_at=datetime.datetime.now(),
            ).where(PosShift.status == "Open").execute()
        except Exception as e:
            logger.error("Lokal shift yopishda xatolik: %s", e)
        finally:
            if not db.is_closed():
                db.close()


class PosClosingDialog(QDialog):
    closing_completed = pyqtSignal()

    def __init__(self, parent, api: FrappeAPI, opening_entry: str):
        super().__init__(parent)
        self.api = api
        self.opening_entry = opening_entry
        self.opening_doc = {}
        self.closing_shift_doc = {}
        self.overview = {}
        self.closing_inputs = {}
        self.active_input = None
        self.input_style_active = (
            "padding: 8px 12px; font-size: 16px; font-weight: 700; "
            "border: 2px solid #3b82f6; border-radius: 10px; background: #eff6ff; color: #1e293b;"
        )
        self.input_style_idle = (
            "padding: 8px 12px; font-size: 16px; font-weight: 700; "
            "border: 1.5px solid #e2e8f0; border-radius: 10px; background: white; color: #1e293b;"
        )
        self.init_ui()
        QTimer.singleShot(50, self._center_on_parent)
        self._load_closing_data()

    def _center_on_parent(self):
        if self.parent():
            p_geo = self.parent().frameGeometry()
            c_geo = self.frameGeometry()
            c_geo.moveCenter(p_geo.center())
            self.move(c_geo.topLeft())

    def init_ui(self):
        self.setWindowTitle("Kassa yopish")
        self.setMinimumSize(860, 640)
        self.resize(1040, 760)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet("background: white;")

        main_h = QHBoxLayout(self)
        main_h.setContentsMargins(20, 20, 20, 20)
        main_h.setSpacing(20)

        left = QWidget()
        self.left_layout = QVBoxLayout(left)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(12)

        header = QFrame()
        header.setStyleSheet("background: #7c2d12; border-radius: 12px; padding: 16px;")
        header_layout = QVBoxLayout(header)

        title = QLabel("KASSA YOPISH")
        title.setStyleSheet("color: #fed7aa; font-size: 11px; font-weight: 700; letter-spacing: 2px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title)

        self.info_label = QLabel("Closing shift ma'lumotlari yuklanmoqda...")
        self.info_label.setStyleSheet("color: white; font-size: 14px; font-weight: 600;")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.info_label)

        self.meta_label = QLabel("")
        self.meta_label.setStyleSheet("color: #fde68a; font-size: 12px;")
        self.meta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.meta_label)

        self.left_layout.addWidget(header)

        self.loading_label = QLabel("Serverdan shift overview olinmoqda...")
        self.loading_label.setStyleSheet("font-size: 14px; color: #64748b; padding: 20px;")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.left_layout.addWidget(self.loading_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("border: none; background: transparent;")
        self.scroll.setVisible(False)
        self.left_layout.addWidget(self.scroll)

        self.diff_label = QLabel()
        self.diff_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.diff_label.setVisible(False)
        self.left_layout.addWidget(self.diff_label)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        btn_cancel = QPushButton("Bekor")
        btn_cancel.setMinimumHeight(44)
        btn_cancel.setStyleSheet("""
            QPushButton { background: #f1f5f9; color: #64748b;
                font-weight: 700; font-size: 14px; border-radius: 12px; border: none; }
            QPushButton:hover { background: #e2e8f0; }
        """)
        btn_cancel.clicked.connect(self.reject)

        self.btn_close = QPushButton("KASSANI YOPISH")
        self.btn_close.setMinimumHeight(44)
        self.btn_close.setEnabled(False)
        self.btn_close.setStyleSheet("""
            QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #dc2626, stop:1 #b91c1c);
                color: white; font-weight: 800; font-size: 15px;
                border-radius: 12px; border: none; }
            QPushButton:hover { background: #991b1b; }
            QPushButton:disabled { background: #fca5a5; color: #fecaca; }
        """)
        self.btn_close.clicked.connect(self._process_closing)

        btn_layout.addWidget(btn_cancel, 1)
        btn_layout.addWidget(self.btn_close, 1)
        self.left_layout.addLayout(btn_layout)

        main_h.addWidget(left, 3)

        right = QWidget()
        right.setStyleSheet("background: #f8fafc; border-radius: 14px;")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(10)

        numpad_lbl = QLabel("YOPISH SUMMASI")
        numpad_lbl.setStyleSheet(
            "font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 1px;"
        )
        right_layout.addWidget(numpad_lbl)

        self.numpad = TouchNumpad()
        self.numpad.digit_clicked.connect(self._on_numpad_clicked)
        right_layout.addWidget(self.numpad)
        right_layout.addStretch()

        main_h.addWidget(right, 1)

    def _load_closing_data(self):
        if not self.opening_entry:
            self.loading_label.setText("Ochiq kassa topilmadi.")
            return

        self.data_worker = ClosingDataWorker(self.api, self.opening_entry)
        self.data_worker.finished.connect(self._on_data_loaded)
        self.data_worker.start()

    def _fmt(self, val, currency="UZS"):
        try:
            number = float(val or 0)
        except (TypeError, ValueError):
            number = 0.0
        return f"{number:,.2f} {currency}".replace(",", " ")

    def _set_active_input(self, inp):
        if self.active_input:
            self.active_input.setStyleSheet(self.input_style_idle)
        self.active_input = inp
        inp.setStyleSheet(self.input_style_active)
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

    def _build_stat_card(self, title: str, value: str, subtitle: str = "") -> QWidget:
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b;")
        value_lbl = QLabel(value)
        value_lbl.setStyleSheet("font-size: 18px; font-weight: 800; color: #0f172a;")
        layout.addWidget(title_lbl)
        layout.addWidget(value_lbl)
        if subtitle:
            sub_lbl = QLabel(subtitle)
            sub_lbl.setWordWrap(True)
            sub_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
            layout.addWidget(sub_lbl)
        return card

    def _build_overview_section(self, content_layout: QVBoxLayout):
        company_currency = self.overview.get("company_currency") or self.opening_doc.get("currency") or "UZS"
        summary_grid = QGridLayout()
        summary_grid.setHorizontalSpacing(12)
        summary_grid.setVerticalSpacing(12)

        cards = [
            ("Cheklar soni", str(self.overview.get("total_invoices", 0)), f"Shift: {self.opening_entry}"),
            ("Jami savdo", self._fmt(self.closing_shift_doc.get("grand_total", 0), company_currency), "Grand Total"),
            ("Sof savdo", self._fmt(self.closing_shift_doc.get("net_total", 0), company_currency), "Net Total"),
            ("Jami qty", f"{float(self.closing_shift_doc.get('total_quantity', 0) or 0):,.2f}".replace(",", " "), "Umumiy miqdor"),
            (
                "Kredit sotuv",
                self._fmt(self.overview.get("credit_invoices", {}).get("company_currency_total", 0), company_currency),
                f"Cheklar: {self.overview.get('credit_invoices', {}).get('count', 0)}",
            ),
            (
                "Returnlar",
                self._fmt(self.overview.get("returns", {}).get("company_currency_total", 0), company_currency),
                f"Cheklar: {self.overview.get('returns', {}).get('count', 0)}",
            ),
            (
                "Qaytim",
                self._fmt(self.overview.get("change_returned", {}).get("company_currency_total", 0), company_currency),
                "Mijozlarga qaytarilgan summa",
            ),
            (
                "Kassa kutilgan qoldiq",
                self._fmt(self.overview.get("cash_expected", {}).get("company_currency_total", 0), company_currency),
                self.overview.get("cash_expected", {}).get("mode_of_payment", ""),
            ),
        ]

        for idx, (title, value, subtitle) in enumerate(cards):
            row = idx // 2
            col = idx % 2
            summary_grid.addWidget(self._build_stat_card(title, value, subtitle), row, col)

        content_layout.addLayout(summary_grid)

        payment_rows = self.overview.get("payments_by_mode") or []
        if payment_rows:
            section = QFrame()
            section.setStyleSheet("QFrame { background: white; border: 1px solid #e2e8f0; border-radius: 12px; }")
            layout = QVBoxLayout(section)
            layout.setContentsMargins(16, 14, 16, 14)
            layout.setSpacing(8)

            title = QLabel("To'lovlar kesimi")
            title.setStyleSheet("font-size: 13px; font-weight: 700; color: #334155;")
            layout.addWidget(title)

            for row in payment_rows:
                item_row = QHBoxLayout()
                mop = row.get("mode_of_payment", "")
                currency = row.get("currency", company_currency)
                amount = self._fmt(row.get("total", 0), currency)
                base_amount = self._fmt(row.get("company_currency_total", 0), company_currency)

                left = QLabel(f"{mop} [{currency}]")
                left.setStyleSheet("font-size: 12px; font-weight: 600; color: #0f172a;")
                right = QLabel(f"{amount} ({base_amount})")
                right.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                right.setStyleSheet("font-size: 12px; color: #475569;")
                item_row.addWidget(left)
                item_row.addStretch()
                item_row.addWidget(right)
                layout.addLayout(item_row)

            content_layout.addWidget(section)

    def _build_reconciliation_section(self, content_layout: QVBoxLayout):
        section = QFrame()
        section.setStyleSheet("QFrame { background: white; border: 1px solid #e2e8f0; border-radius: 12px; }")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title = QLabel("Payment Reconciliation")
        title.setStyleSheet("font-size: 14px; font-weight: 800; color: #0f172a;")
        layout.addWidget(title)

        header_row = QHBoxLayout()
        for text, width in [("To'lov turi", 160), ("Opening", 120), ("Expected", 120), ("Closing", 140)]:
            lbl = QLabel(text)
            lbl.setMinimumWidth(width)
            lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 1px;")
            header_row.addWidget(lbl)
        header_row.addStretch()
        layout.addLayout(header_row)

        self.closing_inputs = {}
        payment_rows = self.closing_shift_doc.get("payment_reconciliation") or []
        company_currency = self.overview.get("company_currency") or self.opening_doc.get("currency") or "UZS"

        for idx, rec in enumerate(payment_rows):
            mode = rec.get("mode_of_payment", "")
            opening_amount = float(rec.get("opening_amount") or 0)
            expected_amount = float(rec.get("expected_amount") or 0)
            closing_amount = rec.get("closing_amount")
            if closing_amount in (None, ""):
                closing_amount = expected_amount

            row = QHBoxLayout()
            row.setSpacing(8)

            mode_lbl = QLabel(mode)
            mode_lbl.setMinimumWidth(160)
            mode_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #334155;")
            row.addWidget(mode_lbl)

            open_lbl = QLabel(self._fmt(opening_amount, company_currency))
            open_lbl.setMinimumWidth(120)
            open_lbl.setStyleSheet("font-size: 13px; color: #475569;")
            row.addWidget(open_lbl)

            exp_lbl = QLabel(self._fmt(expected_amount, company_currency))
            exp_lbl.setMinimumWidth(120)
            exp_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #1e40af;")
            row.addWidget(exp_lbl)

            inp = ClickableLineEdit()
            inp.setValidator(QDoubleValidator(-999999999.0, 999999999.0, 2))
            inp.setText(f"{float(closing_amount):.2f}".rstrip("0").rstrip("."))
            inp.setMinimumWidth(140)
            inp.setMaximumWidth(180)
            inp.setMinimumHeight(40)
            inp.setAlignment(Qt.AlignmentFlag.AlignRight)
            inp.clicked.connect(self._set_active_input)
            inp.textChanged.connect(self._update_difference)
            inp.setStyleSheet(self.input_style_active if idx == 0 else self.input_style_idle)
            row.addWidget(inp)
            row.addStretch()

            if idx == 0:
                self.active_input = inp

            self.closing_inputs[mode] = {
                "input": inp,
                "row": rec,
                "expected": expected_amount,
            }
            layout.addLayout(row)

        content_layout.addWidget(section)

    def _on_data_loaded(self, success: bool, payload):
        if not success:
            self.loading_label.setText(str(payload))
            self.btn_close.setEnabled(False)
            return

        self.opening_doc = payload.get("opening_doc", {})
        self.closing_shift_doc = payload.get("closing_shift", {})
        self.overview = payload.get("overview", {})

        self.loading_label.setVisible(False)
        self.scroll.setVisible(True)
        self.diff_label.setVisible(True)
        self.btn_close.setEnabled(True)

        total_invoices = self.overview.get("total_invoices", 0)
        period_start = self.opening_doc.get("period_start_date") or self.closing_shift_doc.get("period_start_date") or ""
        self.info_label.setText(f"Jami cheklar: {total_invoices}")
        self.meta_label.setText(f"{self.opening_entry} | {period_start}")

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        self._build_overview_section(content_layout)
        self._build_reconciliation_section(content_layout)
        content_layout.addStretch()

        self.scroll.setWidget(content)
        self._update_difference()

    def _update_difference(self):
        total_diff = 0.0
        company_currency = self.overview.get("company_currency") or self.opening_doc.get("currency") or "UZS"

        for data in self.closing_inputs.values():
            try:
                closing_amt = float(data["input"].text() or 0)
            except ValueError:
                closing_amt = 0.0
            diff = closing_amt - float(data["expected"] or 0)
            total_diff += abs(diff)

        if total_diff == 0:
            self.diff_label.setText("Farq yo'q — reconciliation to'g'ri")
            self.diff_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: #16a34a; padding: 6px;"
            )
        else:
            self.diff_label.setText(f"Umumiy farq: {self._fmt(total_diff, company_currency)}")
            self.diff_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: #dc2626; padding: 6px;"
            )

    def _process_closing(self):
        if not self.closing_shift_doc:
            return

        payment_rows = self.closing_shift_doc.get("payment_reconciliation") or []
        for rec in payment_rows:
            mode = rec.get("mode_of_payment", "")
            data = self.closing_inputs.get(mode, {})
            try:
                rec["closing_amount"] = float(data["input"].text() or 0)
            except (ValueError, KeyError):
                rec["closing_amount"] = 0

        self.btn_close.setEnabled(False)
        self.btn_close.setText("Kassa yopilmoqda...")

        self.closing_worker = ClosingWorker(self.api, self.closing_shift_doc)
        self.closing_worker.finished.connect(self._on_closing_finished)
        self.closing_worker.start()

    def _on_closing_finished(self, success: bool, message: str):
        self.btn_close.setEnabled(True)
        self.btn_close.setText("KASSANI YOPISH")

        if success:
            self.accept()
            self.closing_completed.emit()
            return

        logger.error("Kassa yopish xatosi: %s", message)
        InfoDialog(self, "Xatolik", message, kind="error").exec()
