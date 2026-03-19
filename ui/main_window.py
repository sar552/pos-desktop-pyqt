import json
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QMessageBox,
    QLineEdit,
    QButtonGroup,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt, pyqtSignal
from ui.styles import GLOBAL_STYLE
from ui.components.cart_widget import CartWidget
from ui.components.item_browser import ItemBrowser
from ui.components.checkout_window import CheckoutWindow
from ui.components.customer_dialog import CustomerDialog
from ui.components.pos_opening import PosOpeningDialog
from database.migrations import initialize_db
from database.models import Item, ItemPrice, SalesInvoice, Customer, PosShift, db
from peewee import JOIN
from database.sync import SyncWorker
from database.invoice_processor import process_pending_invoice
from core.api import FrappeAPI
from core.logger import get_logger
from core.config import load_config, clear_credentials

logger = get_logger(__name__)


class MainWindow(QMainWindow):
    logout_requested = pyqtSignal()

    def __init__(self, api: FrappeAPI):
        super().__init__()
        self.api = api
        self.current_opening_shift = None
        self.setWindowTitle("PosAwesome Desktop")
        self.setMinimumSize(1280, 800)

        initialize_db()
        self.init_ui()
        self.setStyleSheet(GLOBAL_STYLE)

        self.load_items_to_browser()
        self.load_orders_table()
        self.refresh_customers_page()
        self.refresh_shift_status()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QHBoxLayout(central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self._build_sidebar()
        self._build_right_container()

    def _build_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 20, 0, 20)
        sidebar_layout.setSpacing(10)
        sidebar_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.btn_group = QButtonGroup(self)
        self.nav_buttons = {}

        nav_items = [
            ("POS", "🏠"),
            ("Orders", "📋"),
            ("Customers", "👥"),
            ("Shift", "🕒"),
            ("Settings", "⚙️"),
        ]

        for name, icon in nav_items:
            btn = QPushButton(icon)
            btn.setToolTip(name)
            btn.setCheckable(True)
            btn.setFixedSize(80, 70)
            btn.setProperty("class", "SidebarBtn")
            btn.clicked.connect(lambda checked, n=name: self.on_nav_clicked(n))
            sidebar_layout.addWidget(btn)
            self.btn_group.addButton(btn)
            self.nav_buttons[name] = btn
            if name == "POS":
                btn.setChecked(True)

        sidebar_layout.addStretch()

        self.btn_logout = QPushButton("🚪")
        self.btn_logout.setToolTip("Logout")
        self.btn_logout.setFixedSize(80, 70)
        self.btn_logout.setProperty("class", "SidebarBtn")
        self.btn_logout.clicked.connect(self.handle_logout)
        sidebar_layout.addWidget(self.btn_logout)

        self.main_layout.addWidget(self.sidebar)

    def _build_right_container(self):
        self.right_container = QVBoxLayout()
        self.right_container.setSpacing(0)
        self.right_container.setContentsMargins(0, 0, 0, 0)

        self.top_bar = QFrame()
        self.top_bar.setObjectName("TopBar")
        top_bar_layout = QHBoxLayout(self.top_bar)
        top_bar_layout.setContentsMargins(24, 0, 24, 0)
        top_bar_layout.setSpacing(16)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Qidirish: Mahsulot nomi, kodi yoki shtrix-kodi...")
        self.search_bar.setFixedWidth(450)
        self.search_bar.setFixedHeight(42)
        self.search_bar.textChanged.connect(self.on_global_search)
        top_bar_layout.addWidget(self.search_bar)

        top_bar_layout.addStretch()

        self.lbl_sync_status = QLabel("Ready")
        self.lbl_sync_status.setStyleSheet("color: #4e5969;")
        top_bar_layout.addWidget(self.lbl_sync_status)

        self.btn_customer_top = QPushButton("Walk-in Customer")
        self.btn_customer_top.setObjectName("CustomerBtn")
        self.btn_customer_top.setFixedHeight(42)
        self.btn_customer_top.clicked.connect(self.open_customer_dialog)
        top_bar_layout.addWidget(self.btn_customer_top)

        self.btn_sync = QPushButton("Sinxronizatsiya")
        self.btn_sync.setObjectName("SyncBtn")
        self.btn_sync.setFixedHeight(42)
        self.btn_sync.clicked.connect(self.start_sync)
        top_bar_layout.addWidget(self.btn_sync)

        self.right_container.addWidget(self.top_bar)

        self.stack = QStackedWidget()
        self.page_pos = self._build_pos_page()
        self.page_orders = self._build_orders_page()
        self.page_customers = self._build_customers_page()
        self.page_shift = self._build_shift_page()
        self.page_settings = self._build_settings_page()

        self.stack.addWidget(self.page_pos)
        self.stack.addWidget(self.page_orders)
        self.stack.addWidget(self.page_customers)
        self.stack.addWidget(self.page_shift)
        self.stack.addWidget(self.page_settings)
        self.right_container.addWidget(self.stack)

        self.main_layout.addLayout(self.right_container)

    def _build_pos_page(self):
        page = QWidget()
        content_hbox = QHBoxLayout(page)
        content_hbox.setSpacing(0)
        content_hbox.setContentsMargins(0, 0, 0, 0)

        browser_container = QWidget()
        browser_layout = QVBoxLayout(browser_container)
        browser_layout.setContentsMargins(24, 24, 24, 24)

        self.browser = ItemBrowser()
        self.browser.search_input.setVisible(False)
        self.browser.item_selected.connect(self.on_item_selected)
        browser_layout.addWidget(self.browser)

        content_hbox.addWidget(browser_container, stretch=7)

        self.cart_panel = QFrame()
        self.cart_panel.setObjectName("CartPanel")
        cart_layout = QVBoxLayout(self.cart_panel)
        cart_layout.setContentsMargins(0, 0, 0, 0)

        self.cart = CartWidget()
        self.cart.checkout_requested.connect(self.on_checkout)
        self.cart.btn_customer.clicked.connect(self.open_customer_dialog)
        self.cart.btn_add_customer.clicked.connect(self.open_customer_dialog)
        cart_layout.addWidget(self.cart)

        content_hbox.addWidget(self.cart_panel, stretch=3)

        config = load_config()
        default_customer = config.get("default_customer") or "Walk-in Customer"
        self.set_active_customer(default_customer)

        return page

    def _build_orders_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Orders")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        header.addWidget(title)
        header.addStretch()

        refresh_btn = QPushButton("Yangilash")
        refresh_btn.clicked.connect(self.load_orders_table)
        header.addWidget(refresh_btn)

        retry_btn = QPushButton("Tanlangan chekni yuborish")
        retry_btn.clicked.connect(self.retry_selected_order)
        header.addWidget(retry_btn)

        layout.addLayout(header)

        self.orders_table = QTableWidget()
        self.orders_table.setColumnCount(6)
        self.orders_table.setHorizontalHeaderLabels(
            ["Offline ID", "Server ID", "Customer", "Grand Total", "Status", "Xabar"]
        )
        self.orders_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.orders_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.orders_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.orders_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.orders_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.orders_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.orders_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.orders_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.orders_table.verticalHeader().setVisible(False)
        layout.addWidget(self.orders_table)

        return page

    def _build_customers_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Customers")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(title)

        self.lbl_customer_stats = QLabel("Mijozlar soni: 0")
        layout.addWidget(self.lbl_customer_stats)

        self.btn_select_customer_page = QPushButton("Mijoz tanlash")
        self.btn_select_customer_page.clicked.connect(self.open_customer_dialog)
        layout.addWidget(self.btn_select_customer_page)

        layout.addStretch()
        return page

    def _build_shift_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Shift")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(title)

        self.lbl_shift_status = QLabel("Holat: noma'lum")
        layout.addWidget(self.lbl_shift_status)

        actions = QHBoxLayout()
        self.btn_shift_refresh = QPushButton("Holatni tekshirish")
        self.btn_shift_refresh.clicked.connect(self.refresh_shift_status)
        actions.addWidget(self.btn_shift_refresh)

        self.btn_shift_open = QPushButton("Shift ochish")
        self.btn_shift_open.clicked.connect(self.open_shift_dialog)
        actions.addWidget(self.btn_shift_open)

        self.btn_shift_close = QPushButton("Shift yopish")
        self.btn_shift_close.clicked.connect(self.close_current_shift)
        actions.addWidget(self.btn_shift_close)

        actions.addStretch()
        layout.addLayout(actions)
        layout.addStretch()
        return page

    def _build_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Settings")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(title)

        config = load_config()
        server = config.get("serverUrl") or "-"
        site = config.get("site") or "-"
        user = config.get("user") or "-"
        self.lbl_settings_info = QLabel(
            f"Server: {server}\nSite: {site}\nUser: {user}\n\nNote: Parol faylda saqlanmaydi."
        )
        layout.addWidget(self.lbl_settings_info)

        btn_clear = QPushButton("Credentiallarni tozalash")
        btn_clear.clicked.connect(self._clear_auth)
        layout.addWidget(btn_clear)

        layout.addStretch()
        return page

    def on_nav_clicked(self, page_name):
        pages = {
            "POS": 0,
            "Orders": 1,
            "Customers": 2,
            "Shift": 3,
            "Settings": 4,
        }
        idx = pages.get(page_name, 0)
        self.stack.setCurrentIndex(idx)

        if page_name != "POS":
            self.search_bar.clear()

        if page_name == "Orders":
            self.load_orders_table()
        elif page_name == "Customers":
            self.refresh_customers_page()
        elif page_name == "Shift":
            self.refresh_shift_status()

    def on_global_search(self, text):
        if self.stack.currentIndex() == 0:
            self.browser.search_input.setText(text)

    def load_items_to_browser(self):
        try:
            db.connect(reuse_if_open=True)
            query = (
                Item.select(Item, ItemPrice.price_list_rate)
                .join(ItemPrice, on=(Item.item_code == ItemPrice.item_code), join_type=JOIN.LEFT_OUTER)
                .dicts()
            )

            items = []
            for row in query:
                tax_rate = 0.0
                raw_taxes = row.get("taxes")
                if raw_taxes:
                    try:
                        taxes = json.loads(raw_taxes)
                        if isinstance(taxes, list) and taxes:
                            first = taxes[0]
                            if isinstance(first, dict):
                                tax_rate = float(first.get("rate") or first.get("tax_rate") or 0)
                    except Exception:
                        tax_rate = 0.0

                items.append(
                    {
                        "item_code": row["item_code"],
                        "item_name": row["item_name"],
                        "item_group": row["item_group"],
                        "price": row["price_list_rate"] or 0.0,
                        "barcode": row["barcode"],
                        "uom": row["uom"],
                        "tax_rate": tax_rate,
                    }
                )

            logger.info("Yuklangan mahsulotlar soni: %d", len(items))
            self.browser.load_items(items)
        except Exception as e:
            logger.error("Mahsulotlarni yuklashda xatolik: %s", e)
        finally:
            if not db.is_closed():
                db.close()

    def on_item_selected(self, item_data):
        self.cart.add_item(item_data, 1)

    def open_customer_dialog(self):
        current = self.cart.btn_customer.text()
        dialog = CustomerDialog(selected_customer=current)
        if dialog.exec():
            self.set_active_customer(dialog.selected_customer)

    def set_active_customer(self, customer_name: str):
        self.cart.set_customer(customer_name)
        self.btn_customer_top.setText(customer_name)

    def on_checkout(self, cart_data):
        checkout_win = CheckoutWindow(cart_data)
        checkout_win.payment_submitted.connect(self.on_payment_completed)
        checkout_win.exec()

    def on_payment_completed(self, invoice_obj):
        QMessageBox.information(self, "Muvaffaqiyatli", f"Sotuv saqlandi!\nID: {invoice_obj.offline_id}")
        self.cart.table.setRowCount(0)
        self.cart.update_totals()
        self.load_orders_table()

    def start_sync(self):
        self.btn_sync.setEnabled(False)
        self.btn_sync.setText("Sinxronizatsiya...")
        self.lbl_sync_status.setText("Sync boshlandi...")
        self.sync_worker = SyncWorker(self.api)
        self.sync_worker.progress_update.connect(self.on_sync_progress)
        self.sync_worker.sync_finished.connect(self.on_sync_finished)
        self.sync_worker.start()

    def on_sync_progress(self, message):
        self.lbl_sync_status.setText(message)

    def on_sync_finished(self, success, message):
        self.btn_sync.setEnabled(True)
        self.btn_sync.setText("Sinxronizatsiya")
        self.lbl_sync_status.setText(message)
        if success:
            QMessageBox.information(self, "Sinxronizatsiya", message)
            self.load_items_to_browser()
            self.browser.load_categories()
            self.refresh_customers_page()
        else:
            QMessageBox.critical(self, "Xatolik", f"Sinxronizatsiya xatosi: {message}")

    def load_orders_table(self):
        try:
            db.connect(reuse_if_open=True)
            invoices = (
                SalesInvoice.select()
                .order_by(SalesInvoice.created_at.desc())
                .limit(300)
            )
            rows = list(invoices)
        finally:
            if not db.is_closed():
                db.close()

        self.orders_table.setRowCount(len(rows))
        for row_idx, inv in enumerate(rows):
            self.orders_table.setItem(row_idx, 0, QTableWidgetItem(inv.offline_id))
            self.orders_table.setItem(row_idx, 1, QTableWidgetItem(inv.name or ""))
            self.orders_table.setItem(row_idx, 2, QTableWidgetItem(inv.customer or ""))
            self.orders_table.setItem(row_idx, 3, QTableWidgetItem(f"{float(inv.grand_total or 0):,.2f}"))
            self.orders_table.setItem(row_idx, 4, QTableWidgetItem(inv.status or ""))
            self.orders_table.setItem(row_idx, 5, QTableWidgetItem(inv.sync_message or ""))

    def retry_selected_order(self):
        row = self.orders_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Orders", "Avval chek tanlang.")
            return

        offline_id_item = self.orders_table.item(row, 0)
        if not offline_id_item:
            return

        offline_id = offline_id_item.text()
        try:
            db.connect(reuse_if_open=True)
            inv = SalesInvoice.get(SalesInvoice.offline_id == offline_id)
            status, message = process_pending_invoice(self.api, inv)
            inv.status = status
            inv.sync_message = message
            inv.save()
        except Exception as e:
            QMessageBox.critical(self, "Orders", f"Chek yuborilmadi: {e}")
        finally:
            if not db.is_closed():
                db.close()

        self.load_orders_table()

    def refresh_customers_page(self):
        count = 0
        try:
            db.connect(reuse_if_open=True)
            count = Customer.select().count()
        finally:
            if not db.is_closed():
                db.close()
        self.lbl_customer_stats.setText(f"Mijozlar soni: {count}")

    def refresh_shift_status(self):
        config = load_config()
        user = config.get("user") or self.api.user
        if not user:
            self.lbl_shift_status.setText("Holat: foydalanuvchi aniqlanmadi")
            self.current_opening_shift = None
            return

        success, response = self.api.call_method(
            "posawesome.posawesome.api.shifts.check_opening_shift", {"user": user}
        )
        if not success:
            self.lbl_shift_status.setText("Holat: server bilan tekshirib bo'lmadi")
            self.current_opening_shift = None
            return

        opening = None
        if isinstance(response, dict):
            opening = response.get("pos_opening_shift")

        if opening:
            name = opening.get("name", "")
            self.current_opening_shift = opening
            self.lbl_shift_status.setText(f"Holat: Open ({name})")
            self._store_local_shift(name, "Open")
        else:
            self.current_opening_shift = None
            self.lbl_shift_status.setText("Holat: Closed")

    def open_shift_dialog(self):
        config = load_config()
        pos_profile = config.get("pos_profile")
        if not pos_profile:
            QMessageBox.warning(self, "Shift", "POS Profile topilmadi. Avval Sync qiling.")
            return

        dialog = PosOpeningDialog(self.api, pos_profile)
        dialog.opening_completed.connect(self.on_opening_completed)
        dialog.exec()

    def on_opening_completed(self, payload: dict):
        opening = payload.get("pos_opening_shift") if isinstance(payload, dict) else None
        if opening:
            self.current_opening_shift = opening
            self._store_local_shift(opening.get("name"), "Open")
        self.refresh_shift_status()

    def close_current_shift(self):
        if not self.current_opening_shift:
            QMessageBox.information(self, "Shift", "Yopish uchun ochiq shift topilmadi.")
            return

        opening_json = json.dumps(self.current_opening_shift)
        success_make, closing_doc = self.api.call_method(
            "posawesome.posawesome.api.shifts.make_closing_shift_from_opening",
            {"opening_shift": opening_json},
        )
        if not success_make:
            QMessageBox.critical(self, "Shift", f"Closing draft yaratilmadi: {closing_doc}")
            return

        closing_payload = closing_doc if isinstance(closing_doc, dict) else {}
        success_submit, submit_resp = self.api.call_method(
            "posawesome.posawesome.api.shifts.submit_closing_shift",
            {"closing_shift": json.dumps(closing_payload)},
        )
        if not success_submit:
            QMessageBox.critical(self, "Shift", f"Closing shift yuborilmadi: {submit_resp}")
            return

        self._store_local_shift(self.current_opening_shift.get("name"), "Closed")
        self.current_opening_shift = None
        QMessageBox.information(self, "Shift", f"Shift yopildi: {submit_resp}")
        self.refresh_shift_status()

    def _store_local_shift(self, opening_entry: str, status: str):
        if not opening_entry:
            return
        config = load_config()
        try:
            db.connect(reuse_if_open=True)
            shift, created = PosShift.get_or_create(
                opening_entry=opening_entry,
                defaults={
                    "pos_profile": config.get("pos_profile") or "",
                    "company": config.get("company") or "",
                    "user": config.get("user") or "",
                    "opening_amounts": "{}",
                    "status": status,
                },
            )
            if not created:
                shift.status = status
                shift.save()
        finally:
            if not db.is_closed():
                db.close()

    def _clear_auth(self):
        clear_credentials()
        self.api.reload_config()
        QMessageBox.information(self, "Settings", "Credentiallar tozalandi.")

    def handle_logout(self):
        reply = QMessageBox.question(
            self,
            "Chiqish",
            "Tizimdan chiqmoqchimisiz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.logout_requested.emit()
