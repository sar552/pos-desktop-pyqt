import json
from datetime import datetime

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.api import FrappeAPI
from core.config import load_config
from core.logger import get_logger
from database.models import Customer, PosProfile, db
from ui.components.dialogs import ClickableLineEdit

logger = get_logger(__name__)


class PaymentsDataWorker(QThread):
    finished = pyqtSignal(bool, dict, str)

    def __init__(
        self,
        api: FrappeAPI,
        customer: str,
        company: str,
        currency: str,
        pos_profile_name: str,
        allow_reconcile_payments: bool,
    ):
        super().__init__()
        self.api = api
        self.customer = customer
        self.company = company
        self.currency = currency
        self.pos_profile_name = pos_profile_name
        self.allow_reconcile_payments = allow_reconcile_payments

    def _call_list(self, doctype: str, fields: list[str], filters: list[list], order_by: str, limit: int = 200):
        success, response = self.api.call_method(
            "frappe.client.get_list",
            {
                "doctype": doctype,
                "fields": fields,
                "filters": filters,
                "limit_page_length": limit,
                "order_by": order_by,
            },
        )
        if success and isinstance(response, list):
            return response
        raise RuntimeError(str(response))

    def _call_get(self, doctype: str, name: str):
        success, response = self.api.call_method(
            "frappe.client.get",
            {
                "doctype": doctype,
                "name": name,
            },
        )
        if success and isinstance(response, dict):
            return response
        raise RuntimeError(str(response))

    def run(self):
        try:
            sales_invoices = self._call_list(
                "Sales Invoice",
                [
                    "name",
                    "posting_date",
                    "customer",
                    "grand_total",
                    "outstanding_amount",
                    "currency",
                    "status",
                    "docstatus",
                    "is_return",
                    "due_date",
                ],
                [
                    ["Sales Invoice", "customer", "=", self.customer],
                    ["Sales Invoice", "company", "=", self.company],
                    ["Sales Invoice", "docstatus", "in", [1, 2]],
                ],
                "posting_date desc, creation desc",
                300,
            )

            payment_entries = self._call_list(
                "Payment Entry",
                [
                    "name",
                    "posting_date",
                    "paid_amount",
                    "received_amount",
                    "unallocated_amount",
                    "mode_of_payment",
                    "payment_type",
                    "remarks",
                    "docstatus",
                ],
                [
                    ["Payment Entry", "party_type", "=", "Customer"],
                    ["Payment Entry", "party", "=", self.customer],
                    ["Payment Entry", "company", "=", self.company],
                    ["Payment Entry", "docstatus", "in", [1, 2]],
                ],
                "posting_date desc, creation desc",
                300,
            )
            payment_entry_docs = {}
            for payment in payment_entries:
                name = str(payment.get("name") or "").strip()
                if not name:
                    continue
                try:
                    payment_entry_docs[name] = self._call_get("Payment Entry", name)
                except Exception as fetch_error:
                    logger.debug("Payment Entry detail olinmadi %s: %s", name, fetch_error)

            success, outstanding_invoices = self.api.call_method(
                "posawesome.posawesome.api.payment_entry.get_outstanding_invoices",
                {
                    "customer": self.customer,
                    "company": self.company,
                    "currency": self.currency,
                    "pos_profile": self.pos_profile_name or None,
                    "include_all_currencies": True,
                },
            )
            if not success or not isinstance(outstanding_invoices, list):
                raise RuntimeError(str(outstanding_invoices))

            unallocated_payments = []
            if self.allow_reconcile_payments:
                success, unallocated_payments = self.api.call_method(
                    "posawesome.posawesome.api.payment_entry.get_unallocated_payments",
                    {
                        "customer": self.customer,
                        "company": self.company,
                        "currency": self.currency,
                    },
                )
                if not success or not isinstance(unallocated_payments, list):
                    raise RuntimeError(str(unallocated_payments))

            self.finished.emit(
                True,
                {
                    "sales_invoices": sales_invoices,
                    "payment_entries": payment_entries,
                    "payment_entry_docs": payment_entry_docs,
                    "outstanding_invoices": outstanding_invoices,
                    "unallocated_payments": unallocated_payments,
                },
                "",
            )
        except Exception as e:
            logger.error("Payments data worker xatosi: %s", e)
            self.finished.emit(False, {}, str(e))


class ProcessPaymentWorker(QThread):
    finished = pyqtSignal(bool, dict, str)

    def __init__(self, api: FrappeAPI, payload: dict):
        super().__init__()
        self.api = api
        self.payload = payload

    def run(self):
        try:
            success, response = self.api.call_method(
                "posawesome.posawesome.api.payment_entry.process_pos_payment",
                {"payload": json.dumps(self.payload)},
            )
            if success and isinstance(response, dict):
                self.finished.emit(True, response, "")
                return
            self.finished.emit(False, {}, str(response))
        except Exception as e:
            logger.error("Process payment xatosi: %s", e)
            self.finished.emit(False, {}, str(e))


class AutoReconcileWorker(QThread):
    finished = pyqtSignal(bool, dict, str)

    def __init__(self, api: FrappeAPI, customer: str, company: str, currency: str, pos_profile_name: str):
        super().__init__()
        self.api = api
        self.customer = customer
        self.company = company
        self.currency = currency
        self.pos_profile_name = pos_profile_name

    def run(self):
        try:
            success, response = self.api.call_method(
                "posawesome.posawesome.api.payment_entry.auto_reconcile_customer_invoices",
                {
                    "customer": self.customer,
                    "company": self.company,
                    "currency": self.currency,
                    "pos_profile": self.pos_profile_name or None,
                },
            )
            if success and isinstance(response, dict):
                self.finished.emit(True, response, "")
                return
            self.finished.emit(False, {}, str(response))
        except Exception as e:
            logger.error("Auto reconcile xatosi: %s", e)
            self.finished.emit(False, {}, str(e))


class PaymentsWindow(QDialog):
    payment_processed = pyqtSignal()

    def __init__(self, parent, api: FrappeAPI, opening_entry: str = "", initial_customer: str = ""):
        super().__init__(parent)
        self.api = api
        self.opening_entry = opening_entry
        self.initial_customer = initial_customer
        self.config = load_config()
        self.company = self.config.get("company", "")
        self.currency = self.config.get("currency", "UZS")
        self.pos_profile_name = self.config.get("pos_profile", "")
        self.profile_data = self._load_profile_data()
        self.allow_make_new_payments = bool(self._flt_profile_flag("posa_allow_make_new_payments", 0))
        self.allow_reconcile_payments = bool(self._flt_profile_flag("posa_allow_reconcile_payments", 0))
        self._all_customers = []
        self._filtered_customers = []
        self._customer_ui_updating = False
        self._selected_customer = ""
        self._updating_tables = False
        self.sales_invoices = []
        self.payment_entries = []
        self.payment_entry_docs = {}
        self.outstanding_rows = []
        self.unallocated_rows = []
        self.sverka_final_balance = 0.0
        self.payment_method_inputs = {}
        self.payment_method_currencies = {}
        self._build_ui()
        self._load_customers()
        self._load_payment_method_currencies()
        if self.initial_customer:
            self._apply_customer_filters("", self.initial_customer, False)
            self._load_dashboard()

    def _build_ui(self):
        self.setWindowTitle("Klient Sverka va To'lovlar")
        self.resize(1520, 920)
        self.setModal(True)
        self.setStyleSheet("background: #0f172a; color: white;")

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        top_card = QFrame()
        top_card.setStyleSheet("background: #111827; border: 1px solid #1f2937; border-radius: 16px;")
        top_layout = QVBoxLayout(top_card)
        top_layout.setContentsMargins(16, 16, 16, 16)
        top_layout.setSpacing(12)

        header = QLabel("Klient Sverka va Payment")
        header.setStyleSheet("font-size: 22px; font-weight: 900; color: #f8fafc;")
        top_layout.addWidget(header)

        controls = QHBoxLayout()
        controls.setSpacing(10)

        customer_box = QVBoxLayout()
        customer_label = QLabel("Customer")
        customer_label.setStyleSheet("font-size: 12px; color: #94a3b8; font-weight: 700;")
        self.customer_input = ClickableLineEdit()
        self.customer_input.setPlaceholderText("Customer tanlang...")
        self.customer_input.setFixedHeight(40)
        self.customer_input.setStyleSheet("""
            QLineEdit {
                background: #0f172a; color: white; border: 1px solid #334155;
                border-radius: 10px; padding: 8px 10px; min-height: 40px;
            }
            QLineEdit:focus {
                border: 1px solid #3b82f6;
            }
        """)
        self.customer_input.textEdited.connect(self._on_customer_search_edited)
        self.customer_input.returnPressed.connect(self._commit_customer_search)
        customer_box.addWidget(customer_label)
        customer_box.addWidget(self.customer_input)

        self.customer_results = QListWidget()
        self.customer_results.setVisible(False)
        self.customer_results.setMaximumHeight(220)
        self.customer_results.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.customer_results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.customer_results.setStyleSheet("""
            QListWidget {
                background: #0f172a;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 10px;
                padding: 4px;
                font-size: 13px;
            }
            QListWidget::item {
                padding: 10px 12px;
                border-radius: 8px;
            }
            QListWidget::item:selected {
                background: #1d4ed8;
                color: white;
            }
            QListWidget::item:hover {
                background: #1e293b;
            }
        """)
        self.customer_results.itemClicked.connect(self._on_customer_item_clicked)
        customer_box.addWidget(self.customer_results)
        controls.addLayout(customer_box, 4)

        self.customer_clear_btn = QPushButton("X")
        self.customer_clear_btn.setFixedSize(40, 40)
        self.customer_clear_btn.setStyleSheet("""
            QPushButton {
                background: #1e293b; color: #e2e8f0; border: 1px solid #334155;
                border-radius: 10px; font-weight: 800;
            }
            QPushButton:hover { background: #334155; }
        """)
        self.customer_clear_btn.clicked.connect(self._clear_customer)
        controls.addWidget(self.customer_clear_btn, alignment=Qt.AlignmentFlag.AlignBottom)

        self.search_btn = QPushButton("Search")
        self.search_btn.setMinimumHeight(40)
        self.search_btn.setStyleSheet("""
            QPushButton {
                background: #f59e0b; color: white; border-radius: 10px; border: none;
                font-weight: 800; padding: 0 18px;
            }
            QPushButton:hover { background: #d97706; }
        """)
        self.search_btn.clicked.connect(self._load_dashboard)
        controls.addWidget(self.search_btn, alignment=Qt.AlignmentFlag.AlignBottom)

        self.auto_reconcile_btn = QPushButton("Auto Reconcile")
        self.auto_reconcile_btn.setMinimumHeight(40)
        self.auto_reconcile_btn.setVisible(self.allow_reconcile_payments)
        self.auto_reconcile_btn.setStyleSheet("""
            QPushButton {
                background: #2563eb; color: white; border-radius: 10px; border: none;
                font-weight: 800; padding: 0 18px;
            }
            QPushButton:hover { background: #1d4ed8; }
        """)
        self.auto_reconcile_btn.clicked.connect(self._auto_reconcile)
        controls.addWidget(self.auto_reconcile_btn, alignment=Qt.AlignmentFlag.AlignBottom)

        controls.addStretch()
        top_layout.addLayout(controls)

        summary = QGridLayout()
        summary.setHorizontalSpacing(12)
        self.final_balance_label = self._make_summary_box("Qoldiq", "#fee2e2", "#b91c1c")
        self.outstanding_total_label = self._make_summary_box("Qarzdor Invoice", "#fef3c7", "#92400e")
        self.selected_invoice_total_label = self._make_summary_box("FIFO Yopiladi", "#dbeafe", "#1d4ed8")
        self.selected_payment_total_label = self._make_summary_box("Qoladi", "#dcfce7", "#166534")
        self.new_payment_total_label = self._make_summary_box("Kiritilgan To'lov", "#ede9fe", "#6d28d9")
        summary.addWidget(self.final_balance_label, 0, 0)
        summary.addWidget(self.outstanding_total_label, 0, 1)
        summary.addWidget(self.selected_invoice_total_label, 0, 2)
        summary.addWidget(self.selected_payment_total_label, 0, 3)
        summary.addWidget(self.new_payment_total_label, 0, 4)
        top_layout.addLayout(summary)
        root.addWidget(top_card)

        content = QHBoxLayout()
        content.setSpacing(14)

        left_card = QFrame()
        left_card.setStyleSheet("background: #111827; border: 1px solid #1f2937; border-radius: 16px;")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(10)
        left_title = QLabel("Klient Sverka")
        left_title.setStyleSheet("font-size: 16px; font-weight: 800; color: #f8fafc;")
        left_layout.addWidget(left_title)

        self.sverka_table = self._build_table(
            ["Sana", "Turi", "Hujjat", "Debit", "Credit", "Balance", "Status"],
            stretch_columns={2},
        )
        left_layout.addWidget(self.sverka_table)
        content.addWidget(left_card, 5)

        right_card = QFrame()
        right_card.setStyleSheet("background: #111827; border: 1px solid #1f2937; border-radius: 16px;")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(14, 14, 14, 14)
        right_layout.setSpacing(10)

        outstanding_title = QLabel("Qarzdor Invoicelar")
        outstanding_title.setStyleSheet("font-size: 15px; font-weight: 800; color: #f8fafc;")
        right_layout.addWidget(outstanding_title)
        self.outstanding_table = self._build_table(
            ["Hujjat"],
            stretch_columns={0},
        )
        right_layout.addWidget(self.outstanding_table, 3)

        payment_methods_title = QLabel("Yangi Payment")
        payment_methods_title.setStyleSheet("font-size: 15px; font-weight: 800; color: #f8fafc;")
        right_layout.addWidget(payment_methods_title)

        payment_methods_card = QFrame()
        payment_methods_card.setStyleSheet("background: #0f172a; border: 1px solid #1e293b; border-radius: 12px;")
        self.payment_methods_layout = QGridLayout(payment_methods_card)
        self.payment_methods_layout.setContentsMargins(12, 12, 12, 12)
        self.payment_methods_layout.setHorizontalSpacing(10)
        self.payment_methods_layout.setVerticalSpacing(10)
        right_layout.addWidget(payment_methods_card)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        self.process_btn = QPushButton("Payment Qilish")
        self.process_btn.setMinimumHeight(46)
        self.process_btn.setStyleSheet("""
            QPushButton {
                background: #16a34a; color: white; border: none; border-radius: 12px;
                font-size: 16px; font-weight: 900; padding: 0 16px;
            }
            QPushButton:hover { background: #15803d; }
            QPushButton:disabled { background: #334155; color: #94a3b8; }
        """)
        self.process_btn.clicked.connect(self._process_payment)
        action_row.addWidget(self.process_btn)

        close_btn = QPushButton("Yopish")
        close_btn.setMinimumHeight(46)
        close_btn.setStyleSheet("""
            QPushButton {
                background: #1e293b; color: #e2e8f0; border: 1px solid #334155;
                border-radius: 12px; font-size: 14px; font-weight: 800; padding: 0 16px;
            }
            QPushButton:hover { background: #334155; }
        """)
        close_btn.clicked.connect(self.reject)
        action_row.addWidget(close_btn)
        right_layout.addLayout(action_row)

        content.addWidget(right_card, 3)
        content.setStretch(0, 7)
        content.setStretch(1, 3)
        root.addLayout(content, 1)

        self._build_payment_method_inputs()
        self._update_totals()

    def _make_summary_box(self, title: str, bg: str, fg: str) -> QLabel:
        label = QLabel(f"{title}\n0 UZS")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            f"""
            background: {bg};
            color: {fg};
            border-radius: 12px;
            padding: 12px;
            font-size: 14px;
            font-weight: 800;
            """
        )
        return label

    def _build_table(self, headers: list[str], stretch_columns=None) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.setStyleSheet("""
            QTableWidget {
                background: #0f172a;
                alternate-background-color: #14213d;
                color: #e2e8f0;
                border: 1px solid #1e293b;
                border-radius: 10px;
                font-size: 12px;
                selection-background-color: #1d4ed8;
                selection-color: #ffffff;
                outline: 0;
            }
            QHeaderView::section {
                background: #111827;
                color: #94a3b8;
                font-size: 11px;
                font-weight: 800;
                border: none;
                border-bottom: 1px solid #1e293b;
                padding: 8px;
            }
            QTableWidget::item {
                background: transparent;
                padding: 8px 10px;
                border-bottom: 1px solid #1e293b;
            }
            QTableWidget::item:selected {
                background: #1d4ed8;
                color: #ffffff;
            }
        """)
        table.horizontalHeader().setFixedHeight(34)
        table.verticalHeader().setDefaultSectionSize(42)
        header = table.horizontalHeader()
        stretch_columns = stretch_columns or set()
        for idx in range(len(headers)):
            mode = (
                QHeaderView.ResizeMode.Stretch
                if idx in stretch_columns
                else QHeaderView.ResizeMode.ResizeToContents
            )
            header.setSectionResizeMode(idx, mode)
        return table

    def _load_profile_data(self) -> dict:
        try:
            db.connect(reuse_if_open=True)
            query = PosProfile.select()
            if self.pos_profile_name:
                query = query.where(PosProfile.name == self.pos_profile_name)
            row = query.first()
            if not row or not row.profile_data:
                return {}
            return json.loads(row.profile_data)
        except Exception as e:
            logger.debug("Payments window POS Profile o'qilmadi: %s", e)
            return {}
        finally:
            if not db.is_closed():
                db.close()

    def _flt_profile_flag(self, key: str, default=0.0) -> float:
        try:
            return float(self.profile_data.get(key, default) or default)
        except (TypeError, ValueError, AttributeError):
            return float(default or 0.0)

    def _load_customers(self):
        try:
            db.connect(reuse_if_open=True)
            self._all_customers = list(
                Customer.select(Customer.name, Customer.customer_name, Customer.phone)
                .order_by(Customer.customer_name)
                .dicts()
            )
        except Exception as e:
            logger.debug("Payments window customerlar yuklanmadi: %s", e)
            self._all_customers = []
        finally:
            if not db.is_closed():
                db.close()
        self._filtered_customers = list(self._all_customers)
        if self.initial_customer:
            matched = self._find_customer_by_text(self.initial_customer, self._all_customers)
            if matched:
                self._select_customer_row(matched)
                return
        self._render_customer_results([])

    def _format_customer_label(self, row: dict) -> str:
        name = (row.get("name") or "").strip()
        customer_name = (row.get("customer_name") or name).strip()
        phone = (row.get("phone") or "").strip()
        label = customer_name
        if name and name != customer_name:
            label += f" ({name})"
        if phone:
            label += f" | {phone}"
        return label

    def _find_customer_by_text(self, text: str, rows=None):
        lookup = (text or "").strip().lower()
        if not lookup:
            return None
        rows = rows if rows is not None else self._all_customers
        for row in rows:
            name = str(row.get("name") or "").strip().lower()
            customer_name = str(row.get("customer_name") or "").strip().lower()
            phone = str(row.get("phone") or "").strip().lower()
            if lookup in {name, customer_name, phone}:
                return row
        for row in rows:
            values = [
                str(row.get("name") or "").lower(),
                str(row.get("customer_name") or "").lower(),
                str(row.get("phone") or "").lower(),
            ]
            if any(lookup in value for value in values):
                return row
        return None

    def _filter_customer_rows(self, text: str | None):
        search_text = (text or "").strip().lower()
        parts = [part for part in search_text.split() if part]
        if not parts:
            return list(self._all_customers)

        filtered = []
        for row in self._all_customers:
            values = [
                str(row.get("name") or "").lower(),
                str(row.get("customer_name") or "").lower(),
                str(row.get("phone") or "").lower(),
            ]
            if all(any(part in value for value in values) for part in parts):
                filtered.append(row)
        return filtered

    def _render_customer_results(self, rows: list[dict]):
        self.customer_results.clear()
        for row in rows:
            item = QListWidgetItem(self._format_customer_label(row))
            item.setData(Qt.ItemDataRole.UserRole, row.get("name"))
            self.customer_results.addItem(item)
        self.customer_results.setVisible(bool(rows))

    def _select_customer_row(self, row: dict):
        label = self._format_customer_label(row)
        self._customer_ui_updating = True
        self.customer_input.blockSignals(True)
        self.customer_input.setText(label)
        self.customer_input.setCursorPosition(len(label))
        self.customer_input.deselect()
        self.customer_input.blockSignals(False)
        self._selected_customer = str(row.get("name") or "").strip()
        self._filtered_customers = self._filter_customer_rows(label)
        self._render_customer_results([])
        self._customer_ui_updating = False

    def _apply_customer_filters(self, typed_text: str | None = None, selected_name: str = "", show_popup: bool = False):
        search_text = typed_text if typed_text is not None else self.customer_input.text()
        filtered = self._filter_customer_rows(search_text)
        self._filtered_customers = filtered

        if selected_name:
            selected = next(
                (row for row in (filtered or self._all_customers) if str(row.get("name") or "").strip() == selected_name),
                None,
            )
            if selected:
                self._select_customer_row(selected)
            return

        if typed_text is None:
            self._render_customer_results(filtered if show_popup else [])

    def _on_customer_search_edited(self, text: str):
        if self._customer_ui_updating:
            return
        self._selected_customer = ""
        self._filtered_customers = self._filter_customer_rows(text)
        self._render_customer_results(self._filtered_customers)

    def _on_customer_item_clicked(self, item: QListWidgetItem):
        if not item:
            return
        name = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
        if not name:
            return
        self._apply_customer_filters("", str(name), False)

    def _commit_customer_search(self):
        typed = self.customer_input.text().strip()
        matched = self._find_customer_by_text(typed, self._filtered_customers or self._all_customers)
        if matched:
            self._apply_customer_filters("", str(matched.get("name") or ""), False)
        elif self._filtered_customers:
            first = self._filtered_customers[0]
            self._apply_customer_filters("", str(first.get("name") or ""), False)

    def _clear_customer(self):
        self.customer_input.blockSignals(True)
        self.customer_input.clear()
        self.customer_input.blockSignals(False)
        self._selected_customer = ""
        self._filtered_customers = list(self._all_customers)
        self._render_customer_results([])
        self.sales_invoices = []
        self.payment_entries = []
        self.payment_entry_docs = {}
        self.outstanding_rows = []
        self.unallocated_rows = []
        self._populate_sverka_table()
        self._populate_outstanding_table()
        self._populate_unallocated_table()
        self._update_totals()

    def _selected_customer_name(self) -> str:
        if self._selected_customer:
            return self._selected_customer
        typed = self.customer_input.text().strip()
        matched = self._find_customer_by_text(typed, self._filtered_customers or self._all_customers)
        if matched:
            return str(matched.get("name") or "").strip()
        return typed

    def _load_payment_method_currencies(self):
        if not self.api:
            return
        payments = self.profile_data.get("payments") or []
        mode_names = [row.get("mode_of_payment") for row in payments if row.get("mode_of_payment")]
        if not mode_names:
            return
        success, response = self.api.call_method(
            "posawesome.posawesome.api.payment_entry.get_payment_methods_accounts",
            {"company": self.company, "mode_of_payments": mode_names},
        )
        if success and isinstance(response, dict):
            self.payment_method_currencies = response

    def _build_payment_method_inputs(self):
        while self.payment_methods_layout.count():
            item = self.payment_methods_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.payment_method_inputs = {}

        if not self.allow_make_new_payments:
            note = QLabel("POS Profile'da yangi payment yaratish ruxsati yo'q.")
            note.setStyleSheet("color: #94a3b8; font-size: 12px;")
            self.payment_methods_layout.addWidget(note, 0, 0, 1, 2)
            return

        payments = self.profile_data.get("payments") or []
        validator = QDoubleValidator(0.0, 999999999.0, 2)
        for row_idx, payment in enumerate(payments):
            mode = (payment.get("mode_of_payment") or "").strip()
            if not mode:
                continue
            lbl = QLabel(mode)
            lbl.setStyleSheet("color: #e2e8f0; font-weight: 700; font-size: 13px;")
            inp = ClickableLineEdit()
            inp.setPlaceholderText("0")
            inp.setValidator(validator)
            inp.setFixedHeight(36)
            inp.textChanged.connect(self._update_totals)
            inp.setStyleSheet("""
                QLineEdit {
                    background: #111827; color: white; border: 1px solid #334155;
                    border-radius: 10px; padding: 0 10px; font-size: 13px; font-weight: 700;
                }
            """)
            currency = self.payment_method_currencies.get(mode)
            if currency and currency != self.currency:
                lbl.setText(f"{mode} ({currency})")
            self.payment_methods_layout.addWidget(lbl, row_idx, 0)
            self.payment_methods_layout.addWidget(inp, row_idx, 1)
            self.payment_method_inputs[mode] = inp

    def _load_dashboard(self):
        if not self.api:
            QMessageBox.warning(self, "API", "Server API ulanmagan.")
            return
        customer = self._selected_customer_name()
        if not customer:
            QMessageBox.warning(self, "Customer", "Avval customer tanlang.")
            return
        self.search_btn.setEnabled(False)
        self.worker = PaymentsDataWorker(
            self.api,
            customer,
            self.company,
            self.currency,
            self.pos_profile_name,
            self.allow_reconcile_payments,
        )
        self.worker.finished.connect(self._on_dashboard_loaded)
        self.worker.start()

    def _on_dashboard_loaded(self, success: bool, payload: dict, error: str):
        self.search_btn.setEnabled(True)
        if not success:
            QMessageBox.warning(self, "Xatolik", error or "Ma'lumotlarni yuklab bo'lmadi.")
            return
        self.sales_invoices = payload.get("sales_invoices", [])
        self.payment_entries = payload.get("payment_entries", [])
        self.payment_entry_docs = payload.get("payment_entry_docs", {})
        self.outstanding_rows = payload.get("outstanding_invoices", [])
        self.unallocated_rows = payload.get("unallocated_payments", [])
        self._populate_sverka_table()
        self._populate_outstanding_table()
        self._populate_unallocated_table()
        self._update_totals()

    def _populate_sverka_table(self):
        rows = []
        outstanding_refs = {
            str(row.get("voucher_no") or row.get("name") or "").strip()
            for row in (self.outstanding_rows or [])
            if str(row.get("voucher_type") or "") == "Journal Entry"
        }
        for invoice in self.sales_invoices:
            grand_total = float(invoice.get("grand_total") or 0.0)
            is_return = int(invoice.get("is_return") or 0)
            rows.append(
                {
                    "date": invoice.get("posting_date") or "",
                    "type": "Credit Note" if is_return else "Sales Invoice",
                    "reference": invoice.get("name") or "",
                    "debit": 0.0 if is_return else grand_total,
                    "credit": abs(grand_total) if is_return else 0.0,
                    "status": self._invoice_payment_status(invoice),
                }
            )

        journal_rows = {}
        for payment_name, payment_doc in (self.payment_entry_docs or {}).items():
            payment_date = payment_doc.get("posting_date") or ""
            for ref in payment_doc.get("references") or []:
                if str(ref.get("reference_doctype") or "") != "Journal Entry":
                    continue
                reference_name = str(ref.get("reference_name") or "").strip()
                if not reference_name:
                    continue
                if reference_name not in outstanding_refs:
                    continue
                outstanding_amount = abs(float(ref.get("outstanding_amount") or 0.0))
                allocated_amount = abs(float(ref.get("allocated_amount") or 0.0))
                opening_outstanding = max(outstanding_amount, allocated_amount)
                existing = journal_rows.get(reference_name)
                if existing:
                    existing["debit"] = max(existing["debit"], opening_outstanding)
                    existing["status"] = self._reference_payment_status(opening_outstanding, outstanding_amount, allocated_amount)
                    continue
                journal_rows[reference_name] = {
                    "date": payment_date,
                    "type": "Journal Entry",
                    "reference": reference_name,
                    "debit": opening_outstanding,
                    "credit": 0.0,
                    "status": self._reference_payment_status(opening_outstanding, outstanding_amount, allocated_amount),
                }

        rows.extend(journal_rows.values())

        for payment in self.payment_entries:
            payment_type = (payment.get("payment_type") or "").strip()
            payment_mode = (payment.get("mode_of_payment") or "").strip()
            received = float(payment.get("received_amount") or payment.get("paid_amount") or 0.0)
            debit = received if payment_type == "Pay" else 0.0
            credit = received if payment_type != "Pay" else 0.0
            rows.append(
                {
                    "date": payment.get("posting_date") or "",
                    "type": f"Payment Entry ({payment_mode})" if payment_mode else "Payment Entry",
                    "reference": payment.get("name") or "",
                    "debit": debit,
                    "credit": credit,
                    "status": self._payment_entry_status(payment),
                }
            )

        def _sort_key(row):
            try:
                dt = datetime.strptime(row.get("date") or "", "%Y-%m-%d")
            except ValueError:
                dt = datetime.min
            return (dt, row.get("reference") or "")

        rows.sort(key=_sort_key)
        running_balance = 0.0

        self.sverka_table.setRowCount(0)
        for idx, row in enumerate(rows):
            running_balance += float(row.get("debit") or 0.0) - float(row.get("credit") or 0.0)
            self.sverka_table.insertRow(idx)
            self.sverka_table.setItem(idx, 0, QTableWidgetItem(row.get("date") or ""))
            self.sverka_table.setItem(idx, 1, QTableWidgetItem(row.get("type") or ""))
            self.sverka_table.setItem(idx, 2, QTableWidgetItem(row.get("reference") or ""))
            debit_item = QTableWidgetItem(self._money(row.get("debit")))
            credit_item = QTableWidgetItem(self._money(row.get("credit")))
            balance_item = QTableWidgetItem(self._format_running_balance(running_balance))
            for item in (debit_item, credit_item, balance_item):
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.sverka_table.setItem(idx, 3, debit_item)
            self.sverka_table.setItem(idx, 4, credit_item)
            self.sverka_table.setItem(idx, 5, balance_item)
            status_text = row.get("status") or "Paid"
            self.sverka_table.setItem(idx, 6, QTableWidgetItem(status_text))
        self.sverka_final_balance = running_balance

    def _populate_outstanding_table(self):
        self._updating_tables = True
        self.outstanding_table.setRowCount(0)
        for idx, row in enumerate(self.outstanding_rows):
            self.outstanding_table.insertRow(idx)
            self.outstanding_table.setItem(idx, 0, QTableWidgetItem(row.get("voucher_no") or row.get("name") or ""))
        self._updating_tables = False

    def _populate_unallocated_table(self):
        return

    def _fifo_outstanding_rows(self) -> list[dict]:
        rows = [dict(row) for row in self.outstanding_rows if float(row.get("outstanding_amount") or 0.0) > 0]

        def _sort_key(row: dict):
            raw_date = str(row.get("posting_date") or "")
            try:
                posting_date = datetime.strptime(raw_date, "%Y-%m-%d")
            except ValueError:
                posting_date = datetime.max
            return (
                posting_date,
                str(row.get("voucher_no") or row.get("name") or ""),
            )

        return sorted(rows, key=_sort_key)

    def _new_payment_methods(self) -> list[dict]:
        rows = []
        for mode, inp in self.payment_method_inputs.items():
            raw = (inp.text() or "").replace(" ", "").strip()
            if not raw:
                continue
            try:
                amount = float(raw)
            except ValueError:
                continue
            if amount <= 0:
                continue
            rows.append({"mode_of_payment": mode, "amount": amount})
        return rows

    def _update_totals(self):
        new_payment_total = sum(float(row.get("amount") or 0.0) for row in self._new_payment_methods())
        outstanding_total = sum(float(row.get("outstanding_amount") or 0.0) for row in self.outstanding_rows)
        max_payable = max(outstanding_total, 0.0)
        payment_applied = min(new_payment_total, max_payable)
        remaining_after_payment = max(max_payable - payment_applied, 0.0)
        balance_text = f"Qoldiq (Qarzdor)\n{self._money(max_payable)}" if max_payable > 0 else "Qoldiq\n0 UZS"

        self.final_balance_label.setText(balance_text)
        self.outstanding_total_label.setText(f"Qarzdor Invoice\n{self._money(outstanding_total)}")
        self.selected_invoice_total_label.setText(f"FIFO Yopiladi\n{self._money(payment_applied)}")
        self.selected_payment_total_label.setText(f"Qoladi\n{self._money(remaining_after_payment)}")
        self.new_payment_total_label.setText(f"Kiritilgan To'lov\n{self._money(new_payment_total)}")

        has_customer = bool(self._selected_customer_name())
        has_action = new_payment_total > 0
        not_overpaying = new_payment_total <= (max_payable + 0.0001)
        has_debt = max_payable > 0.0001
        self.process_btn.setVisible(has_customer)
        self.process_btn.setEnabled(has_customer and has_debt and has_action and not_overpaying)
        if has_customer and has_action and not not_overpaying and has_debt:
            self.process_btn.setText(f"Maksimum {self._money(max_payable)}")
        elif has_customer and not has_debt:
            self.process_btn.setText("Qarz yopilgan")
        else:
            self.process_btn.setText("Payment Qilish")

    def _money(self, amount, currency: str | None = None) -> str:
        currency = currency or self.currency
        try:
            value = float(amount or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        return f"{value:,.0f} {currency}".replace(",", " ")

    def _format_running_balance(self, amount: float) -> str:
        if amount > 0:
            return f"{self._money(amount)} Qarzdor"
        if amount < 0:
            return f"{self._money(abs(amount))} Avans"
        return self._money(0.0)

    def _invoice_payment_status(self, invoice: dict) -> str:
        docstatus = int(invoice.get("docstatus") or 0)
        raw_status = str(invoice.get("status") or "").strip().lower()
        if docstatus == 2 or raw_status == "cancelled":
            return "Cancelled"

        grand_total = abs(float(invoice.get("grand_total") or 0.0))
        outstanding = abs(float(invoice.get("outstanding_amount") or 0.0))
        if outstanding <= 0.0001:
            return "Paid"
        if grand_total > 0.0001 and outstanding < grand_total - 0.0001:
            return "Partial"
        return "Unpaid"

    def _payment_entry_status(self, payment: dict) -> str:
        docstatus = int(payment.get("docstatus") or 0)
        if docstatus == 2:
            return "Cancelled"
        return "Paid"

    def _reference_payment_status(self, opening_outstanding: float, outstanding_amount: float, allocated_amount: float) -> str:
        remaining_after_payment = max(float(outstanding_amount or 0.0) - float(allocated_amount or 0.0), 0.0)
        if remaining_after_payment <= 0.0001:
            return "Paid"
        if allocated_amount > 0.0001:
            return "Partial"
        return "Unpaid"

    def _get_effective_final_balance(self, outstanding_total: float | None = None) -> float:
        if outstanding_total is None:
            outstanding_total = sum(float(row.get("outstanding_amount") or 0.0) for row in self.outstanding_rows)
        return float(outstanding_total)
    def _auto_reconcile(self):
        if not self.api:
            QMessageBox.warning(self, "API", "Server API ulanmagan.")
            return
        customer = self._selected_customer_name()
        if not customer:
            QMessageBox.warning(self, "Customer", "Avval customer tanlang.")
            return
        if not self.allow_reconcile_payments:
            return
        self.auto_reconcile_btn.setEnabled(False)
        self.auto_worker = AutoReconcileWorker(
            self.api,
            customer,
            self.company,
            self.currency,
            self.pos_profile_name,
        )
        self.auto_worker.finished.connect(self._on_auto_reconcile_finished)
        self.auto_worker.start()

    def _on_auto_reconcile_finished(self, success: bool, payload: dict, error: str):
        self.auto_reconcile_btn.setEnabled(True)
        if not success:
            QMessageBox.warning(self, "Xatolik", error or "Auto reconcile bajarilmadi.")
            return
        QMessageBox.information(
            self,
            "Auto Reconcile",
            payload.get("summary") or "Auto reconcile yakunlandi.",
        )
        self._load_dashboard()

    def _process_payment(self):
        if not self.api:
            QMessageBox.warning(self, "API", "Server API ulanmagan.")
            return
        customer = self._selected_customer_name()
        if not customer:
            QMessageBox.warning(self, "Customer", "Avval customer tanlang.")
            return

        payment_methods = self._new_payment_methods()
        total_payment_methods = sum(float(row.get("amount") or 0.0) for row in payment_methods)
        remaining_debt = max(self._get_effective_final_balance(), 0.0)

        if remaining_debt <= 0:
            QMessageBox.information(self, "Qarz", "Bu customerda yopiladigan qarz yo'q.")
            return

        if total_payment_methods <= 0:
            QMessageBox.warning(self, "Payment", "To'lov summasini kiriting.")
            return

        if total_payment_methods > remaining_debt + 0.0001:
            QMessageBox.warning(
                self,
                "Payment",
                f"To'lov qarzdan oshib ketdi. Maksimum: {self._money(remaining_debt)}",
            )
            return

        selected_invoices = self._fifo_outstanding_rows()
        if not selected_invoices:
            QMessageBox.information(self, "Invoice", "Yopiladigan qarzdor invoice topilmadi.")
            return

        payload = {
            "customer": customer,
            "company": self.company,
            "currency": self.currency,
            "exchange_rate": None,
            "pos_opening_shift_name": self.opening_entry,
            "pos_profile_name": self.pos_profile_name,
            "pos_profile": self.profile_data,
            "payment_methods": payment_methods,
            "selected_invoices": selected_invoices,
            "selected_payments": [],
            "total_selected_invoices": sum(float(row.get("outstanding_amount") or 0.0) for row in selected_invoices),
            "selected_mpesa_payments": [],
            "total_selected_payments": 0.0,
            "total_payment_methods": total_payment_methods,
            "total_selected_mpesa_payments": 0.0,
        }

        self.process_btn.setEnabled(False)
        self.process_btn.setText("Kuting...")
        self.process_worker = ProcessPaymentWorker(self.api, payload)
        self.process_worker.finished.connect(self._on_payment_processed)
        self.process_worker.start()

    def _on_payment_processed(self, success: bool, payload: dict, error: str):
        self.process_btn.setEnabled(True)
        self.process_btn.setText("Payment Qilish")
        if not success:
            QMessageBox.warning(self, "Xatolik", error or "Payment bajarilmadi.")
            return

        errors = payload.get("errors") or []
        new_entries = payload.get("new_payments_entry") or []
        reconciled = payload.get("reconciled_payments") or []
        message_lines = []
        if new_entries:
            message_lines.append(f"Yangi payment: {len(new_entries)} ta")
        if reconciled:
            message_lines.append(f"Reconcile qilingan: {len(reconciled)} ta")
        if errors:
            message_lines.append("Xatolar:")
            message_lines.extend(str(err) for err in errors[:5])
        QMessageBox.information(
            self,
            "Payment",
            "\n".join(message_lines) or "Payment muvaffaqiyatli bajarildi.",
        )

        for inp in self.payment_method_inputs.values():
            inp.clear()
        self.payment_processed.emit()
        self._load_dashboard()
