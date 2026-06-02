import json
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt6.QtCore import Qt
from database.models import PendingInvoice, db
from core.logger import get_logger
from core.i18n import tr

logger = get_logger(__name__)


class OfflineQueueWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Yuborilmagan (Offline) Cheklar"))
        self.setMinimumSize(550, 400)
        self.resize(700, 500)
        self.init_ui()
        self._load_pending_invoices()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header = QLabel(tr("Internet yo'qligida yaratilgan cheklar ro'yxati:"))
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #374151;")
        layout.addWidget(header)

        info_text = QLabel(tr("Ushbu cheklar internet tiklanishi bilan avtomatik ravishda serverga yuboriladi."))
        info_text.setStyleSheet("color: #6b7280; font-style: italic;")
        layout.addWidget(info_text)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("Vaqt"), tr("Mijoz"), tr("Summa")])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        close_btn = QPushButton(tr("YOPISH"))
        close_btn.setMinimumHeight(44)
        close_btn.setStyleSheet("""
            QPushButton { background-color: #f3f4f6; color: #374151; font-weight: bold; border-radius: 8px; }
            QPushButton:hover { background-color: #e5e7eb; }
        """)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

    def _load_pending_invoices(self):
        self.table.setRowCount(0)
        try:
            db.connect(reuse_if_open=True)
            pending = (
                PendingInvoice.select()
                .where(PendingInvoice.status == "Pending")
                .order_by(PendingInvoice.created_at.desc())
            )

            for row_idx, inv in enumerate(pending):
                self.table.insertRow(row_idx)

                data = {}
                try:
                    data = json.loads(inv.invoice_data)
                except (json.JSONDecodeError, ValueError):
                    pass

                customer = data.get("customer") or "—"
                total = self._invoice_amount(data)

                self.table.setItem(row_idx, 0, QTableWidgetItem(inv.created_at.strftime("%d-%m %H:%M")))
                self.table.setItem(row_idx, 1, QTableWidgetItem(str(customer)))
                self.table.setItem(row_idx, 2, QTableWidgetItem(
                    f"{total:,.0f} UZS".replace(",", " ")
                ))

        except Exception as e:
            logger.error("Oflayn cheklar yuklashda xatolik: %s", e)
        finally:
            if not db.is_closed():
                db.close()

    @staticmethod
    def _invoice_amount(data: dict) -> float:
        """Saqlangan invoice'dan haqiqiy summani aniqlaydi.

        Sales Invoice payloadida `net_total` + `discount_amount` bor;
        to'lanadigan summa = net_total - discount. Topilmasa — to'lovlar
        yig'indisi yoki eski `total_amount` ga qaytamiz.
        """
        def _f(x):
            try:
                return float(x or 0)
            except (TypeError, ValueError):
                return 0.0

        net = _f(data.get("net_total")) or _f(data.get("total"))
        amount = net - _f(data.get("discount_amount"))
        if amount > 0:
            return amount
        # Zaxira: to'lovlar yig'indisi
        pays = data.get("_payments") or data.get("payments") or []
        if isinstance(pays, list):
            total_paid = sum(_f(p.get("amount")) for p in pays if isinstance(p, dict))
            if total_paid > 0:
                return total_paid
        # Eski format
        return _f(data.get("total_amount"))
