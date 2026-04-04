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

        missing_invoices = self._fetch_unlinked_invoices(opening_doc, closing_doc)
        if missing_invoices:
            self._merge_missing_invoices(opening_doc, closing_doc, overview, missing_invoices)

        self.finished.emit(
            True,
            {
                "opening_doc": opening_doc,
                "closing_shift": closing_doc,
                "overview": overview,
            },
        )

    def _fetch_unlinked_invoices(self, opening_doc: dict, closing_doc: dict) -> list[dict]:
        period_start = opening_doc.get("period_start_date")
        owner = opening_doc.get("user")
        pos_profile = opening_doc.get("pos_profile")
        company = opening_doc.get("company")
        if not period_start or not owner:
            return []

        linked_names = {
            row.get("sales_invoice")
            for row in (closing_doc.get("pos_transactions") or [])
            if row.get("sales_invoice")
        }

        success, rows = self.api.call_method(
            "frappe.client.get_list",
            {
                "doctype": "Sales Invoice",
                "fields": [
                    "name",
                    "creation",
                    "posting_date",
                    "customer",
                    "grand_total",
                    "net_total",
                    "total_qty",
                    "currency",
                    "conversion_rate",
                    "change_amount",
                    "base_change_amount",
                    "owner",
                    "company",
                    "pos_profile",
                    "is_return",
                    "outstanding_amount",
                    "posa_pos_opening_shift",
                ],
                "filters": [
                    ["Sales Invoice", "creation", ">=", period_start],
                    ["Sales Invoice", "owner", "=", owner],
                    ["Sales Invoice", "docstatus", "=", 1],
                ],
                "limit_page_length": 100,
                "order_by": "creation desc",
            },
        )
        if not success or not isinstance(rows, list):
            return []

        docs = []
        for row in rows:
            name = row.get("name")
            if not name or name in linked_names:
                continue
            if row.get("posa_pos_opening_shift"):
                continue
            if company and row.get("company") not in (company, None, ""):
                continue
            if pos_profile and row.get("pos_profile") not in (pos_profile, None, ""):
                continue

            ok, doc = self.api.call_method(
                "frappe.client.get",
                {"doctype": "Sales Invoice", "name": name},
            )
            if ok and isinstance(doc, dict):
                docs.append(doc)
        return docs

    def _base_value(self, doc: dict, fieldname: str, base_fieldname: str | None = None, conversion_rate=None) -> float:
        base_fieldname = base_fieldname or f"base_{fieldname}"
        base_value = doc.get(base_fieldname)
        if base_value not in (None, ""):
            try:
                return float(base_value)
            except (TypeError, ValueError):
                return 0.0

        value = doc.get(fieldname)
        if value in (None, ""):
            return 0.0
        try:
            rate = float(
                conversion_rate
                or doc.get("conversion_rate")
                or doc.get("exchange_rate")
                or doc.get("target_exchange_rate")
                or doc.get("plc_conversion_rate")
                or 1
            )
        except (TypeError, ValueError):
            rate = 1.0
        try:
            return float(value) * rate
        except (TypeError, ValueError):
            return 0.0

    def _merge_missing_invoices(self, opening_doc: dict, closing_doc: dict, overview: dict, invoices: list[dict]):
        company_currency = overview.get("company_currency") or opening_doc.get("currency") or "UZS"
        cash_mode = (
            overview.get("cash_expected", {}) or {}
        ).get("mode_of_payment") or "Cash"

        pos_transactions = closing_doc.setdefault("pos_transactions", [])
        payment_rows = closing_doc.setdefault("payment_reconciliation", [])
        payment_map = {row.get("mode_of_payment"): row for row in payment_rows if row.get("mode_of_payment")}
        taxes = closing_doc.setdefault("taxes", [])

        multi_currency_map = {
            row.get("currency"): row for row in overview.setdefault("multi_currency_totals", []) if row.get("currency")
        }
        payments_map = {
            (row.get("mode_of_payment"), row.get("currency")): row
            for row in overview.setdefault("payments_by_mode", [])
            if row.get("mode_of_payment")
        }
        cash_rows = {
            row.get("currency"): row for row in (overview.setdefault("cash_expected", {}).setdefault("by_currency", [])) if row.get("currency")
        }

        sales_summary = overview.setdefault("sales_summary", {})
        credit_summary = overview.setdefault("credit_invoices", {"count": 0, "company_currency_total": 0.0, "by_currency": []})
        returns_summary = overview.setdefault("returns", {"count": 0, "company_currency_total": 0.0, "by_currency": []})
        change_summary = overview.setdefault(
            "change_returned",
            {
                "company_currency_total": 0.0,
                "by_currency": [],
                "invoice_change": {"company_currency_total": 0.0, "by_currency": []},
                "overpayment_change": {"company_currency_total": 0.0, "by_currency": []},
            },
        )

        for invoice in invoices:
            conversion_rate = invoice.get("conversion_rate")
            currency = invoice.get("currency") or company_currency
            grand_total = float(invoice.get("grand_total") or 0)
            net_total = float(invoice.get("net_total") or 0)
            total_qty = float(invoice.get("total_qty") or 0)
            base_grand_total = self._base_value(invoice, "grand_total", "base_grand_total", conversion_rate)
            base_net_total = self._base_value(invoice, "net_total", "base_net_total", conversion_rate)

            pos_transactions.append(
                {
                    "sales_invoice": invoice.get("name"),
                    "posting_date": invoice.get("posting_date"),
                    "grand_total": base_grand_total,
                    "transaction_currency": currency,
                    "transaction_amount": grand_total,
                    "customer": invoice.get("customer"),
                }
            )

            closing_doc["grand_total"] = float(closing_doc.get("grand_total") or 0) + base_grand_total
            closing_doc["net_total"] = float(closing_doc.get("net_total") or 0) + base_net_total
            closing_doc["total_quantity"] = float(closing_doc.get("total_quantity") or 0) + total_qty

            existing_currency_row = multi_currency_map.get(currency)
            if not existing_currency_row:
                existing_currency_row = {
                    "currency": currency,
                    "total": 0.0,
                    "company_currency_total": 0.0,
                    "invoice_count": 0,
                    "exchange_rates": [],
                }
                overview["multi_currency_totals"].append(existing_currency_row)
                multi_currency_map[currency] = existing_currency_row
            existing_currency_row["total"] += grand_total
            existing_currency_row["company_currency_total"] += base_grand_total
            existing_currency_row["invoice_count"] += 1

            overview["total_invoices"] = int(overview.get("total_invoices") or 0) + 1
            overview["company_currency_total"] = float(overview.get("company_currency_total") or 0) + base_grand_total
            sales_summary["gross_company_currency_total"] = float(sales_summary.get("gross_company_currency_total") or 0) + base_grand_total
            sales_summary["net_company_currency_total"] = float(sales_summary.get("net_company_currency_total") or 0) + base_net_total
            sales_summary["sale_invoices_count"] = int(sales_summary.get("sale_invoices_count") or 0) + 1
            total_sales = float(sales_summary.get("gross_company_currency_total") or 0)
            total_count = int(sales_summary.get("sale_invoices_count") or 0)
            sales_summary["average_invoice_value"] = (total_sales / total_count) if total_count else 0

            if float(invoice.get("outstanding_amount") or 0) > 0:
                credit_summary["count"] = int(credit_summary.get("count") or 0) + 1
                credit_summary["company_currency_total"] = float(credit_summary.get("company_currency_total") or 0) + self._base_value(
                    invoice, "outstanding_amount", "base_outstanding_amount", conversion_rate
                )

            if invoice.get("is_return"):
                returns_summary["count"] = int(returns_summary.get("count") or 0) + 1
                returns_summary["company_currency_total"] = float(returns_summary.get("company_currency_total") or 0) + abs(base_grand_total)

            change_amount = float(invoice.get("change_amount") or 0)
            if change_amount:
                base_change = self._base_value(invoice, "change_amount", "base_change_amount", conversion_rate)
                change_summary["company_currency_total"] = float(change_summary.get("company_currency_total") or 0) + base_change
                invoice_change = change_summary.setdefault("invoice_change", {"company_currency_total": 0.0, "by_currency": []})
                invoice_change["company_currency_total"] = float(invoice_change.get("company_currency_total") or 0) + base_change

            for tax in invoice.get("taxes", []) or []:
                account_head = tax.get("account_head")
                rate = tax.get("rate")
                amount = self._base_value(tax, "tax_amount", "base_tax_amount", conversion_rate)
                existing_tax = next((row for row in taxes if row.get("account_head") == account_head and row.get("rate") == rate), None)
                if existing_tax:
                    existing_tax["amount"] = float(existing_tax.get("amount") or 0) + amount
                else:
                    taxes.append({"account_head": account_head, "rate": rate, "amount": amount})

            for payment in invoice.get("payments", []) or []:
                mode = payment.get("mode_of_payment")
                if not mode:
                    continue
                expected_delta = self._base_value(payment, "amount", "base_amount", conversion_rate)
                if mode == cash_mode and change_amount:
                    expected_delta -= self._base_value(invoice, "change_amount", "base_change_amount", conversion_rate)

                row = payment_map.get(mode)
                if not row:
                    row = {"mode_of_payment": mode, "opening_amount": 0, "expected_amount": 0, "closing_amount": 0}
                    payment_rows.append(row)
                    payment_map[mode] = row
                row["expected_amount"] = float(row.get("expected_amount") or 0) + expected_delta
                if row.get("closing_amount") in (None, "", 0):
                    row["closing_amount"] = row["expected_amount"]

                pay_key = (mode, currency)
                pay_row = payments_map.get(pay_key)
                if not pay_row:
                    pay_row = {
                        "mode_of_payment": mode,
                        "currency": currency,
                        "total": 0.0,
                        "company_currency_total": 0.0,
                        "exchange_rates": [],
                    }
                    overview["payments_by_mode"].append(pay_row)
                    payments_map[pay_key] = pay_row
                pay_row["total"] += float(payment.get("amount") or 0)
                pay_row["company_currency_total"] += self._base_value(payment, "amount", "base_amount", conversion_rate)

                if mode == cash_mode:
                    cash_row = cash_rows.get(currency)
                    if not cash_row:
                        cash_row = {
                            "currency": currency,
                            "total": 0.0,
                            "company_currency_total": 0.0,
                            "exchange_rates": [],
                            "mode_of_payment": cash_mode,
                        }
                        overview["cash_expected"]["by_currency"].append(cash_row)
                        cash_rows[currency] = cash_row
                    cash_row["total"] += float(payment.get("amount") or 0) - change_amount
                    cash_row["company_currency_total"] += expected_delta
                    overview["cash_expected"]["company_currency_total"] = float(
                        overview["cash_expected"].get("company_currency_total") or 0
                    ) + expected_delta


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
