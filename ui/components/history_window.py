import json
from PyQt6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QFrame, QLineEdit,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from core.api import FrappeAPI
from core.logger import get_logger
from core.constants import HISTORY_FETCH_LIMIT
from ui.component_styles import get_component_styles
from ui.theme_manager import ThemeManager

logger = get_logger(__name__)


# ─────────────────────────────────────
#  Worker threads
# ─────────────────────────────────────
class FetchHistoryWorker(QThread):
    finished = pyqtSignal(bool, list)

    def __init__(self, api: FrappeAPI, opening_entry: str = ""):
        super().__init__()
        self.api = api
        self.opening_entry = opening_entry

    def run(self):
        if not self.opening_entry:
            self.finished.emit(True, [])
            return

        success, opening_doc = self.api.call_method(
            "frappe.client.get",
            {"doctype": "POS Opening Shift", "name": self.opening_entry},
        )
        if not success or not isinstance(opening_doc, dict):
            self.finished.emit(False, [])
            return

        fields = json.dumps([
            "name",
            "customer",
            "grand_total",
            "outstanding_amount",
            "posting_date",
            "posting_time",
            "status",
            "docstatus",
            "creation",
            "posa_pos_opening_shift",
        ])
        filters = json.dumps([["Sales Invoice", "posa_pos_opening_shift", "=", self.opening_entry]])

        data = self.api.fetch_data(
            "Sales Invoice", fields=fields, filters=filters, limit=HISTORY_FETCH_LIMIT,
        )
        if data is not None:
            linked_names = {row.get("name") for row in data}
            missing = self._fetch_unlinked_invoices(opening_doc, linked_names)
            if missing:
                data.extend(missing)
            data.sort(key=lambda x: x.get("creation", ""), reverse=True)
            self.finished.emit(True, data)
        else:
            self.finished.emit(False, [])

    def _fetch_unlinked_invoices(self, opening_doc: dict, linked_names: set[str]):
        period_start = opening_doc.get("period_start_date")
        owner = opening_doc.get("user")
        pos_profile = opening_doc.get("pos_profile")
        company = opening_doc.get("company")
        if not period_start or not owner:
            return []

        success, rows = self.api.call_method(
            "frappe.client.get_list",
            {
                "doctype": "Sales Invoice",
                "fields": [
                    "name",
                    "customer",
                    "grand_total",
                    "outstanding_amount",
                    "posting_date",
                    "posting_time",
                    "status",
                    "docstatus",
                    "creation",
                    "owner",
                    "company",
                    "pos_profile",
                    "posa_pos_opening_shift",
                ],
                "filters": [
                    ["Sales Invoice", "creation", ">=", period_start],
                    ["Sales Invoice", "owner", "=", owner],
                    ["Sales Invoice", "docstatus", "=", 1],
                ],
                "limit_page_length": HISTORY_FETCH_LIMIT,
                "order_by": "creation desc",
            },
        )
        if not success or not isinstance(rows, list):
            return []

        missing = []
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
            missing.append(row)
        return missing


class FetchDetailsWorker(QThread):
    finished = pyqtSignal(bool, dict)

    def __init__(self, api: FrappeAPI, invoice_id: str):
        super().__init__()
        self.invoice_id = invoice_id
        self.api = api

    def run(self):
        success, doc = self.api.call_method(
            "frappe.client.get", {"doctype": "Sales Invoice", "name": self.invoice_id}
        )
        self.finished.emit(success and isinstance(doc, dict), doc if isinstance(doc, dict) else {})


class CancelOrderWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, api: FrappeAPI, invoice_id: str, reason: str):
        super().__init__()
        self.invoice_id = invoice_id
        self.reason = reason
        self.api = api

    def run(self):
        success, doc = self.api.call_method(
            "frappe.client.get",
            {"doctype": "Sales Invoice", "name": self.invoice_id},
        )
        if not success or not isinstance(doc, dict):
            self.finished.emit(False, f"Xatolik: {doc}")
            return

        docstatus = int(doc.get("docstatus") or 0)
        status = str(doc.get("status") or "").strip().lower()

        if docstatus == 2 or status == "cancelled":
            self.finished.emit(True, "Chek allaqachon bekor qilingan.")
            return

        if docstatus == 0 or status == "draft":
            success, response = self.api.call_method(
                "frappe.client.delete",
                {"doctype": "Sales Invoice", "name": self.invoice_id},
            )
            if success:
                self.finished.emit(True, "Draft chek muvaffaqiyatli o'chirildi!")
            else:
                self.finished.emit(False, f"Xatolik: {response}")
            return

        success, response = self.api.call_method(
            "frappe.client.cancel",
            {"doctype": "Sales Invoice", "name": self.invoice_id},
        )
        if success:
            self.finished.emit(True, "Chek muvaffaqiyatli bekor qilindi!")
        else:
            self.finished.emit(False, f"Xatolik: {response}")


# ─────────────────────────────────────
#  Inline detail panel (replaces dialog)
# ─────────────────────────────────────
class TransactionDetailDialog(QDialog):
    """Still kept as QDialog so double-click flow works unchanged."""

    def __init__(self, parent, api: FrappeAPI, invoice_id: str):
        super().__init__(parent)
        self.api = api
        self.invoice_id = invoice_id
        self.setWindowTitle(f"Chek: {invoice_id}")
        self.setMinimumSize(420, 450)
        self.resize(520, 560)
        
        # Apply theme
        styles = get_component_styles()
        self.setStyleSheet(styles["list_container"])
        
        self._init_ui()
        self._load()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        styles = get_component_styles()
        colors = ThemeManager.get_theme_colors()

        # Header
        hdr = QLabel(f"Chek  #{self.invoice_id}")
        hdr.setStyleSheet(styles["dialog_title"])
        layout.addWidget(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {colors['border']};")
        layout.addWidget(sep)

        # Items table
        lbl = QLabel("MAHSULOTLAR")
        lbl.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {colors['text_tertiary']}; letter-spacing: 1px;"
        )
        layout.addWidget(lbl)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Mahsulot", "Soni", "Summa"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet(f"""
            QTableWidget {{ border: none; font-size: 13px; background: {colors['bg_secondary']}; color: {colors['text_primary']}; }}
            QTableWidget::item {{ padding: 6px; }}
            QTableWidget::item:selected {{ background: {colors['selection_bg']}; color: {colors['selection_text']}; }}
            QHeaderView::section {{
                background: {colors['bg_tertiary']}; color: {colors['text_secondary']};
                font-size: 11px; font-weight: 700;
                padding: 6px; border: none;
                border-bottom: 1px solid {colors['border']};
            }}
        """)
        layout.addWidget(self.table)

        # Payments
        pay_lbl = QLabel("TO'LOV TURLARI")
        pay_lbl.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {colors['text_tertiary']}; letter-spacing: 1px;"
        )
        layout.addWidget(pay_lbl)

        self.payments_frame = QFrame()
        self.payments_frame.setStyleSheet(
            f"background: {colors['bg_secondary']}; border-radius: 10px; padding: 2px; border: 1px solid {colors['border']};"
        )
        self.payments_layout = QVBoxLayout(self.payments_frame)
        self.payments_layout.setContentsMargins(12, 8, 12, 8)
        layout.addWidget(self.payments_frame)

        layout.addStretch()

        close_btn = QPushButton("Yopish")
        close_btn.setMinimumHeight(40)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: {colors['bg_tertiary']}; color: {colors['text_secondary']};
                font-weight: 700; border-radius: 10px; border: none; }}
            QPushButton:hover {{ background: {colors['border']}; }}
        """)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

    def _load(self):
        self.worker = FetchDetailsWorker(self.api, self.invoice_id)
        self.worker.finished.connect(self._on_loaded)
        self.worker.start()

    def _on_loaded(self, success: bool, doc: dict):
        if not success:
            QMessageBox.warning(self, "Xato", "Tafsilotlarni yuklab bo'lmadi.")
            return

        items = doc.get("items", [])
        self.table.setRowCount(0)
        for i, item in enumerate(items):
            self.table.insertRow(i)
            self.table.setItem(i, 0, QTableWidgetItem(item.get("item_name", "")))
            self.table.setItem(i, 1, QTableWidgetItem(str(item.get("qty", 0))))
            self.table.setItem(i, 2, QTableWidgetItem(
                f"{item.get('amount', 0):,.0f}".replace(",", " ")
            ))

        # clear payments
        for i in reversed(range(self.payments_layout.count())):
            w = self.payments_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        payments = [p for p in doc.get("payments", []) if float(p.get("amount", 0)) > 0]
        if payments:
            colors = ThemeManager.get_theme_colors()
            for p in payments:
                row_w = QWidget()
                row_l = QHBoxLayout(row_w)
                row_l.setContentsMargins(0, 2, 0, 2)
                mode = QLabel(p.get("mode_of_payment", ""))
                mode.setStyleSheet(f"font-weight: 600; color: {colors['text_secondary']}; font-size: 13px;")
                amt = QLabel(f"{float(p.get('amount', 0)):,.0f} UZS".replace(",", " "))
                amt.setStyleSheet(f"color: {colors['success']}; font-weight: 700; font-size: 13px;")
                row_l.addWidget(mode)
                row_l.addStretch()
                row_l.addWidget(amt)
                self.payments_layout.addWidget(row_w)
        else:
            no = QLabel("To'lov ma'lumotlari mavjud emas.")
            colors = ThemeManager.get_theme_colors()
            no.setStyleSheet(f"color: {colors['text_tertiary']}; font-size: 12px;")
            self.payments_layout.addWidget(no)


# ─────────────────────────────────────
#  Cancel reason dialog with keyboard
# ─────────────────────────────────────
class CancelReasonDialog(QDialog):
    def __init__(self, parent, invoice_id: str):
        super().__init__(parent)
        self.invoice_id = invoice_id
        self.setWindowTitle("Bekor qilish sababi")
        self.setMinimumSize(460, 220)
        self.resize(520, 240)
        styles = get_component_styles()
        self.setStyleSheet(styles["dialog_bg"])
        self._init_ui()

    def _init_ui(self):
        colors = ThemeManager.get_theme_colors()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # Title
        title = QLabel(f"#{self.invoice_id}  —  Bekor qilish sababi")
        title.setStyleSheet(f"font-size: 16px; font-weight: 800; color: {colors['text_primary']};")
        layout.addWidget(title)

        # Input display
        self.input = QLineEdit()
        self.input.setPlaceholderText("Sabab yozing...")
        self.input.setMinimumHeight(40)
        self.input.setStyleSheet(f"""
            QLineEdit {{
                font-size: 15px; color: {colors['text_primary']};
                background: {colors['input_bg']};
                border: 2px solid {colors['accent']};
                border-radius: 10px; padding: 8px 14px;
            }}
        """)
        layout.addWidget(self.input)
        self.input.setFocus()

        # Buttons
        btn_row = QHBoxLayout()

        cancel_btn = QPushButton("Bekor")
        cancel_btn.setMinimumHeight(40)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{ background: {colors['bg_tertiary']}; color: {colors['text_secondary']};
                font-weight: 700; border-radius: 10px; border: none; }}
            QPushButton:hover {{ background: {colors['border']}; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        confirm_btn = QPushButton("✓  Tasdiqlash")
        confirm_btn.setMinimumHeight(40)
        confirm_btn.setStyleSheet(f"""
            QPushButton {{ background: {colors['error']}; color: white;
                font-weight: 700; font-size: 14px;
                border-radius: 10px; border: none; }}
            QPushButton:hover {{ background: {colors['accent_hover']}; }}
        """)
        confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(confirm_btn)

        layout.addLayout(btn_row)

    def _on_confirm(self):
        if self.input.text().strip():
            self.accept()
        else:
            colors = ThemeManager.get_theme_colors()
            self.input.setStyleSheet(f"""
                QLineEdit {{
                    font-size: 15px; color: {colors['text_primary']};
                    background: {colors['bg_tertiary']};
                    border: 2px solid {colors['error']};
                    border-radius: 10px; padding: 8px 14px;
                }}
            """)

    def get_reason(self) -> str:
        return self.input.text().strip()


# ─────────────────────────────────────
#  Main History Panel (inline widget)
# ─────────────────────────────────────
class HistoryWindow(QWidget):
    """Inline panel — embed in main_window, show/hide via toggle."""

    def __init__(self, api: FrappeAPI, parent=None):
        super().__init__(parent)
        self.api = api
        self.opening_entry = ""
        self._init_ui()

    @staticmethod
    def _table_style(colors: dict) -> str:
        return f"""
            QTableWidget {{
                border: none; background: {colors['bg_secondary']}; color: {colors['text_primary']}; font-size: 13px;
            }}
            QTableWidget::item {{ padding: 5px 8px; border-bottom: 1px solid {colors['border_light']}; }}
            QTableWidget::item:selected {{ background: {colors['selection_bg']}; color: {colors['selection_text']}; }}
            QHeaderView::section {{
                background: {colors['bg_tertiary']}; color: {colors['text_secondary']};
                font-size: 11px; font-weight: 700; letter-spacing: 0.5px;
                padding: 8px 8px; border: none;
                border-bottom: 1px solid {colors['border']};
            }}
        """

    def _init_ui(self):
        styles = get_component_styles()
        colors = ThemeManager.get_theme_colors()
        self.setStyleSheet(styles["list_container"])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # ── Header row ──────────────────────
        hdr_row = QHBoxLayout()

        self.title_label = QLabel("Shift bo'yicha Sales Invoice lar")
        self.title_label.setStyleSheet(f"font-size: 18px; font-weight: 800; color: {colors['text_primary']};")
        hdr_row.addWidget(self.title_label)

        self.hint_label = QLabel("(2× bosing — tafsilot)")
        self.hint_label.setStyleSheet(f"font-size: 11px; color: {colors['text_tertiary']}; font-style: italic;")
        hdr_row.addWidget(self.hint_label)
        hdr_row.addStretch()

        self.refresh_btn = QPushButton("⟳  Yangilash")
        self.refresh_btn.setMinimumHeight(38)
        self.refresh_btn.setMaximumHeight(48)
        self.refresh_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 0 16px; background: {colors['bg_tertiary']}; color: {colors['text_secondary']};
                font-weight: 600; font-size: 13px;
                border-radius: 8px; border: none;
            }}
            QPushButton:hover {{ background: {colors['border']}; }}
        """)
        self.refresh_btn.clicked.connect(self.load_history)
        hdr_row.addWidget(self.refresh_btn)

        self.close_btn = QPushButton("✕")
        self.close_btn.setMinimumSize(38, 38)
        self.close_btn.setMaximumSize(48, 48)
        self.close_btn.setStyleSheet(f"""
            QPushButton {{ background: {colors['bg_tertiary']}; color: {colors['error']};
                font-weight: 700; font-size: 14px; border-radius: 8px; border: none; }}
            QPushButton:hover {{ background: {colors['border']}; }}
        """)
        self.close_btn.clicked.connect(self.hide)
        hdr_row.addWidget(self.close_btn)

        layout.addLayout(hdr_row)

        self.sep_line = QFrame()
        self.sep_line.setFrameShape(QFrame.Shape.HLine)
        self.sep_line.setStyleSheet(f"background: {colors['border']}; max-height: 1px;")
        layout.addWidget(self.sep_line)

        # ── Table ────────────────────────────
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["ID", "Sana", "Vaqt", "Mijoz", "Holat", "Summa", "Amal"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setStyleSheet(self._table_style(colors))
        self.table.itemDoubleClicked.connect(self._show_details)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 150)
        self.table.setColumnWidth(5, 150)
        self.table.setColumnWidth(6, 130)
        layout.addWidget(self.table)

    def apply_theme(self):
        styles = get_component_styles()
        colors = ThemeManager.get_theme_colors()
        self.setStyleSheet(styles["list_container"])
        if hasattr(self, "title_label"):
            self.title_label.setStyleSheet(f"font-size: 18px; font-weight: 800; color: {colors['text_primary']};")
        if hasattr(self, "hint_label"):
            self.hint_label.setStyleSheet(f"font-size: 11px; color: {colors['text_tertiary']}; font-style: italic;")
        if hasattr(self, "refresh_btn"):
            self.refresh_btn.setStyleSheet(f"""
                QPushButton {{
                    padding: 0 16px; background: {colors['bg_tertiary']}; color: {colors['text_secondary']};
                    font-weight: 600; font-size: 13px;
                    border-radius: 8px; border: none;
                }}
                QPushButton:hover {{ background: {colors['border']}; }}
            """)
        if hasattr(self, "close_btn"):
            self.close_btn.setStyleSheet(f"""
                QPushButton {{ background: {colors['bg_tertiary']}; color: {colors['error']};
                    font-weight: 700; font-size: 14px; border-radius: 8px; border: none; }}
                QPushButton:hover {{ background: {colors['border']}; }}
            """)
        if hasattr(self, "sep_line"):
            self.sep_line.setStyleSheet(f"background: {colors['border']}; max-height: 1px;")
        if hasattr(self, "table"):
            self.table.setStyleSheet(self._table_style(colors))
        if self.isVisible() and self.opening_entry:
            self.load_history()

    def load_history(self):
        self.table.setRowCount(0)
        if not self.opening_entry:
            return
        self.worker = FetchHistoryWorker(self.api, self.opening_entry)
        self.worker.finished.connect(self._on_loaded)
        self.worker.start()

    def _on_loaded(self, success: bool, data: list):
        if not success:
            return
        colors = ThemeManager.get_theme_colors()
        self.table.setRowCount(0)
        for i, item in enumerate(data):
            self.table.insertRow(i)
            self.table.setRowHeight(i, 46)
            inv_name = item.get("name", "")
            status_text, status_tone = self._derive_payment_status(item)

            self.table.setItem(i, 0, QTableWidgetItem(inv_name))
            self.table.setItem(i, 1, QTableWidgetItem(item.get("posting_date", "")))
            self.table.setItem(i, 2, QTableWidgetItem(item.get("posting_time", "")[:5]))
            self.table.setItem(i, 3, QTableWidgetItem(item.get("customer", "")))
            self.table.setCellWidget(i, 4, self._build_status_badge(item))
            amt = QTableWidgetItem(f"{item.get('grand_total', 0):,.0f} UZS".replace(",", " "))
            amt.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
            self.table.setItem(i, 5, amt)

            if status_tone == "cancelled":
                lbl = QLabel("Bekor qilingan")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setStyleSheet(f"color: {colors['error']}; font-weight: 600; font-size: 11px;")
                self.table.setCellWidget(i, 6, lbl)
            else:
                action_text = "O'chirish" if status_tone == "draft" else "Bekor qilish"
                btn = QPushButton(action_text)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {colors['bg_tertiary']}; color: {colors['accent_action']};
                        font-weight: 600; font-size: 12px;
                        border-radius: 6px; border: 1px solid {colors['border']};
                        padding: 4px 10px;
                    }}
                    QPushButton:hover {{ background: {colors['border_light']}; }}
                """)
                btn.clicked.connect(
                    lambda _, inv=inv_name, tone=status_tone: self._confirm_cancel(inv, tone)
                )
                self.table.setCellWidget(i, 6, btn)

    def _derive_payment_status(self, item: dict) -> tuple[str, str]:
        status = str(item.get("status") or "").strip()
        status_key = status.lower()
        docstatus = int(item.get("docstatus") or 0)
        outstanding = float(item.get("outstanding_amount") or 0.0)
        grand_total = float(item.get("grand_total") or 0.0)
        paid_amount = max(grand_total - outstanding, 0.0)

        if docstatus == 0 or status_key == "draft":
            return "Draft", "draft"
        if docstatus == 2 or status.lower() == "cancelled":
            return "Bekor qilingan", "cancelled"
        if status_key == "paid":
            return "Paid", "paid"
        if status_key in {"partly paid", "partially paid"}:
            return "Qisman to'langan", "partial"
        if status_key in {"unpaid", "overdue"}:
            return "To'lanmagan", "unpaid"
        if outstanding <= 0:
            return "Paid", "paid"
        if paid_amount > 0:
            return "Qisman to'langan", "partial"
        return "To'lanmagan", "unpaid"

    def _build_status_badge(self, item: dict) -> QLabel:
        text, tone = self._derive_payment_status(item)
        colors = ThemeManager.get_theme_colors()
        styles = {
            "paid": (colors["bg_tertiary"], colors["success"], colors["border"]),
            "partial": (colors["bg_tertiary"], colors["warning"], colors["border"]),
            "unpaid": (colors["bg_tertiary"], colors["error"], colors["border"]),
            "draft": (colors["bg_tertiary"], colors["accent"], colors["border"]),
            "cancelled": (colors["bg_tertiary"], colors["text_tertiary"], colors["border"]),
        }
        bg, fg, border = styles.get(tone, styles["unpaid"])
        badge = QLabel(text)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setMinimumWidth(118)
        badge.setStyleSheet(
            f"""
            QLabel {{
                background: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: 10px;
                font-size: 11px;
                font-weight: 700;
                padding: 6px 12px;
            }}
            """
        )
        badge.setToolTip(f"Asl status: {item.get('status', '')}")
        return badge

    def _show_details(self, item):
        invoice_id = self.table.item(item.row(), 0).text()
        TransactionDetailDialog(self, self.api, invoice_id).exec()

    def _confirm_cancel(self, invoice_id: str, status_tone: str):
        if status_tone == "draft":
            answer = QMessageBox.question(
                self,
                "Draft chekni o'chirish",
                f"{invoice_id} draft chekni o'chirmoqchimisiz?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            reason = ""
        else:
            dlg = CancelReasonDialog(self, invoice_id)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            reason = dlg.get_reason()

        self.cancel_worker = CancelOrderWorker(self.api, invoice_id, reason)
        self.cancel_worker.finished.connect(self._on_cancel_finished)
        self.cancel_worker.start()

    def _on_cancel_finished(self, success: bool, message: str):
        QMessageBox.information(self, "Natija", message)
        self.load_history()
