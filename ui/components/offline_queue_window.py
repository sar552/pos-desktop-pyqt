import json
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt6.QtCore import Qt
from database.models import PendingInvoice, db
from core.logger import get_logger
from core.i18n import tr
from ui.theme_manager import ThemeManager

logger = get_logger(__name__)


class OfflineQueueWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Yuborilmagan (Offline) Cheklar"))
        self.setMinimumSize(640, 400)
        self.resize(780, 520)
        self.colors = ThemeManager.get_theme_colors()
        self.init_ui()
        self._load_pending_invoices()

    def init_ui(self):
        colors = self.colors
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header = QLabel(tr("Internet yo'qligida yaratilgan cheklar ro'yxati:"))
        header.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {colors['text_primary']};")
        layout.addWidget(header)

        info_text = QLabel(tr("Ushbu cheklar internet tiklanishi bilan avtomatik ravishda serverga yuboriladi."))
        info_text.setStyleSheet(f"color: {colors['text_secondary']}; font-style: italic;")
        layout.addWidget(info_text)

        self.failed_hint = QLabel(tr("⚠ Xatolik bilan qaytgan cheklar avtomatik qayta yuborilmaydi — sababi Holat ustunida."))
        self.failed_hint.setStyleSheet(f"color: {colors['warning']}; font-weight: 600;")
        self.failed_hint.setVisible(False)
        layout.addWidget(self.failed_hint)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([tr("Vaqt"), tr("Mijoz"), tr("Summa"), tr("Holat")])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        close_btn = QPushButton(tr("YOPISH"))
        close_btn.setMinimumHeight(44)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors['bg_tertiary']}; color: {colors['text_primary']};
                font-weight: bold; border-radius: 8px; border: 1px solid {colors['border']};
            }}
            QPushButton:hover {{ background-color: {colors['bg_hover']}; }}
        """)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

    def _load_pending_invoices(self):
        self.table.setRowCount(0)
        colors = self.colors
        has_failed = False
        try:
            db.connect(reuse_if_open=True)
            # Failed cheklar ham ko'rsatiladi — ular avtomatik qayta
            # yuborilmaydi, kassir yo'qolgan sotuvni shu yerda ko'radi.
            pending = (
                PendingInvoice.select()
                .where(PendingInvoice.status.in_(["Pending", "Failed"]))
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

                if inv.status == "Failed":
                    has_failed = True
                    status_text = f"⚠ {tr('Xato')}: {(inv.error_message or '')[:60]}"
                else:
                    status_text = tr("Kutilmoqda")

                status_item = QTableWidgetItem(status_text)
                if inv.status == "Failed":
                    status_item.setForeground(Qt.GlobalColor.red)
                    status_item.setToolTip(inv.error_message or "")

                self.table.setItem(row_idx, 0, QTableWidgetItem(inv.created_at.strftime("%d-%m %H:%M")))
                self.table.setItem(row_idx, 1, QTableWidgetItem(str(customer)))
                self.table.setItem(row_idx, 2, QTableWidgetItem(
                    f"{total:,.0f} UZS".replace(",", " ")
                ))
                self.table.setItem(row_idx, 3, status_item)

        except Exception as e:
            logger.error("Oflayn cheklar yuklashda xatolik: %s", e)
        finally:
            if not db.is_closed():
                db.close()
        self.failed_hint.setVisible(has_failed)

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
