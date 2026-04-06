from PyQt6.QtWidgets import (
    QApplication, QLineEdit, QComboBox, QDialog,
    QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QWidget,
    QPushButton, QSplitter, QTabWidget,
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from database.sync import SyncWorker
from database.offline_sync import OfflineSyncWorker
from database.migrations import initialize_db
from database.models import PendingInvoice, PosShift, db
from core.api import FrappeAPI
from core.company_logo import get_cached_company_logo_path
from core.logger import get_logger
from core.constants import MONITOR_INTERVAL_MS
from core.config import load_config
from ui.components.item_browser import ItemBrowser
from ui.components.cart_widget import CartWidget
from ui.components.checkout_window import CheckoutWindow
from ui.components.history_window import HistoryWindow
from ui.components.payments_window import PaymentsWindow
from ui.components.offline_queue_window import OfflineQueueWindow
from ui.components.pos_opening import PosOpeningDialog
from ui.components.pos_closing import PosClosingDialog
from ui.components.dialogs import InfoDialog, ConfirmDialog
from ui.components.keyboard import TouchKeyboard
from ui.theme_manager import ThemeManager

logger = get_logger(__name__)


class ConnectivityCheckWorker(QThread):
    """Server bilan aloqani tekshirish — background thread'da."""
    finished = pyqtSignal(bool)

    def __init__(self, api: FrappeAPI):
        super().__init__()
        self.api = api

    def run(self):
        try:
            success, _ = self.api.call_method("frappe.auth.get_logged_user")
            self.finished.emit(success)
        except Exception:
            self.finished.emit(False)


class PosOpeningCheckWorker(QThread):
    finished = pyqtSignal(bool, str, dict)  # has_opening, opening_entry_name, dialog_data

    def __init__(self, api: FrappeAPI):
        super().__init__()
        self.api = api

    def run(self):
        user = self.api.user
        if not user:
            user = load_config().get("user", "")

        success, response = self.api.call_method(
            "posawesome.posawesome.api.shifts.check_opening_shift",
            {"user": user}
        )

        if success:
            if isinstance(response, dict) and response.get("pos_opening_shift"):
                opening_entry = response["pos_opening_shift"].get("name", "")
                self._sync_local_shift(opening_entry)
                self.finished.emit(True, opening_entry, {})
            else:
                self._close_local_shifts()
                
                # Agar ochilmagan bo'lsa, posawesome dialog data olinadi
                succ2, diag_data = self.api.call_method("posawesome.posawesome.api.shifts.get_opening_dialog_data")
                if succ2 and isinstance(diag_data, dict):
                    self.finished.emit(False, "", diag_data)
                else:
                    self.finished.emit(False, "", {})
        else:
            # Oflayn rejim - local bazadan tekshirish
            try:
                db.connect(reuse_if_open=True)
                shift = PosShift.select().where(PosShift.status == "Open").first()
                if shift:
                    self.finished.emit(True, shift.opening_entry or "", {})
                else:
                    self.finished.emit(False, "", {})
            except Exception as e:
                logger.debug("Local shift tekshirishda xato: %s", e)
                self.finished.emit(False, "", {})
            finally:
                if not db.is_closed():
                    db.close()

    def _sync_local_shift(self, opening_entry: str):
        """Server ochiq desa — lokal bazada ham ochiq shift bo'lishini ta'minlash."""
        try:
            db.connect(reuse_if_open=True)
            existing = PosShift.select().where(
                (PosShift.status == "Open") & (PosShift.opening_entry == opening_entry)
            ).first()
            if not existing:
                # Eski ochiq shiftlarni yopish + yangi yaratish
                PosShift.update(status="Closed").where(PosShift.status == "Open").execute()
                PosShift.create(
                    opening_entry=opening_entry,
                    pos_profile="",
                    company="",
                    user=self.api.user or "",
                    status="Open",
                )
        except Exception as e:
            logger.debug("Lokal shift sinxronlash: %s", e)
        finally:
            if not db.is_closed():
                db.close()

    def _close_local_shifts(self):
        """Server yopiq desa — lokal bazadagi barcha ochiq shiftlarni yopish."""
        try:
            import datetime
            db.connect(reuse_if_open=True)
            PosShift.update(
                status="Closed", closed_at=datetime.datetime.now()
            ).where(PosShift.status == "Open").execute()
        except Exception as e:
            logger.debug("Lokal shiftlarni yopish: %s", e)
        finally:
            if not db.is_closed():
                db.close()


class MainWindow(QMainWindow):
    logout_requested = pyqtSignal()

    def __init__(self, api: FrappeAPI):
        super().__init__()
        self.api = api
        self.opening_entry = None  # Ochiq kassa nomi
        self.setWindowTitle("POSAwesome Desktop")
        self.showMaximized()

        initialize_db()
        
        # Store UI elements for theme updates
        self.themed_elements = {}

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self._apply_central_widget_theme(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- Top Bar ---
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(10, 4, 10, 4)
        top_bar.setSpacing(12)

        # ── POSAwesome Brand Logo ──────────────────
        colors = ThemeManager.get_theme_colors()
        
        logo_widget = QWidget()
        logo_widget.setMinimumWidth(150)
        logo_widget.setMaximumWidth(220)
        logo_widget.setStyleSheet("""
            QWidget {
                background: transparent;
                border-left: none;
                padding-left: 10px;
            }
        """)
        logo_layout = QVBoxLayout(logo_widget)
        logo_layout.setContentsMargins(10, 2, 0, 2)
        logo_layout.setSpacing(0)

        self.brand_name = QLabel(f"POS<font color=\"{colors['accent']}\">Awesome</font>")
        self.brand_name.setStyleSheet(f"""
            font-size: 24px;
            font-weight: 900;
            color: {colors['accent']};
            background: transparent;
        """)

        self.brand_sub = QLabel("DESKTOP")
        self.brand_sub.setStyleSheet(f"""
            font-size: 9px;
            font-weight: 700;
            color: {colors['accent_hover']};
            background: transparent;
            letter-spacing: 2px;
        """)

        logo_layout.addWidget(self.brand_name)
        logo_layout.addWidget(self.brand_sub)
        top_bar.addWidget(logo_widget)

        self.company_logo_label = QLabel()
        self.company_logo_label.setFixedSize(72, 72)
        self.company_logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_bar.addWidget(self.company_logo_label)

        # ── Filial / Company badge ──────────────
        config = load_config()
        company_name = config.get("company", "")
        pos_profile = config.get("pos_profile", "")

        self.company_badge = QLabel()
        self._update_company_badge(company_name, pos_profile)
        self._update_company_logo(config)
        top_bar.addWidget(self.company_badge)

        # Connection Status
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(12, 12)
        self.status_dot.setStyleSheet(f"background-color: {colors['text_tertiary']}; border-radius: 6px;")

        self.status_text = QLabel("Checking...")
        self.status_text.setStyleSheet(f"font-weight: bold; color: {colors['text_secondary']}; font-size: 13px;")

        top_bar.addWidget(self.status_dot)
        top_bar.addWidget(self.status_text)
        top_bar.addStretch()

        # ── helper for consistent top-bar button style ──────────
        def _tb_btn(label: str, bg: str, color: str = "white",
                    hover: str = "", border: str = "none") -> QPushButton:
            b = QPushButton(label)
            b.setMinimumHeight(36)
            b.setMaximumHeight(52)
            h = hover or bg
            disabled_bg = colors['bg_tertiary']
            disabled_text = colors['text_tertiary']
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {bg}; color: {color};
                    font-weight: 700; font-size: 13px;
                    border-radius: 10px; border: {border};
                    padding: 0 14px;
                }}
                QPushButton:hover {{ background: {h}; }}
                QPushButton:pressed {{ opacity: 0.85; }}
                QPushButton:disabled {{ background: {disabled_bg}; color: {disabled_text}; }}
            """)
            return b

        # Offline Queue Button — themed
        self.offline_btn = _tb_btn(
            "Offline: 0", colors['bg_secondary'], colors['text_primary'],
            hover=colors['bg_tertiary'], border=f"1px solid {colors['border']}"
        )
        self.offline_btn.clicked.connect(self.show_offline_queue)
        top_bar.addWidget(self.offline_btn)

        # New Sale Button — success color
        self.add_sale_btn = _tb_btn(
            "+ Yangi sotuv", colors['success'], "white", 
            hover="#059669"
        )
        self.add_sale_btn.clicked.connect(self.add_new_sale_tab)
        top_bar.addWidget(self.add_sale_btn)

        # History Button — accent color
        self.history_btn = _tb_btn(
            "Tarix", "#8b5cf6", "white", hover="#7c3aed"
        )
        self.history_btn.clicked.connect(self.show_history)
        top_bar.addWidget(self.history_btn)

        self.payments_btn = _tb_btn(
            "Payments", colors['accent'], "white", hover=colors['accent_hover']
        )
        self.payments_btn.clicked.connect(self.show_payments_window)
        top_bar.addWidget(self.payments_btn)

        # Sync Button — accent color
        self.sync_btn = _tb_btn(
            "Sinxronlash", colors['accent'], "white", hover=colors['accent_hover']
        )
        self.sync_btn.clicked.connect(self.start_sync)
        top_bar.addWidget(self.sync_btn)

        # Printer Settings Button — muted
        self.printer_btn = _tb_btn(
            "Printer", colors['text_secondary'], "white", hover=colors['text_primary']
        )
        self.printer_btn.clicked.connect(self.show_printer_settings)
        top_bar.addWidget(self.printer_btn)

        # Theme Toggle Button — muted
        current_theme = ThemeManager.get_current_theme()
        theme_icon = "🌙" if current_theme == "light" else "☀️"
        self.theme_btn = _tb_btn(
            theme_icon, colors['text_secondary'], "white", hover=colors['text_primary']
        )
        self.theme_btn.setToolTip("Mavzu o'zgartirish (Light/Dark)")
        self.theme_btn.clicked.connect(self.toggle_theme)
        top_bar.addWidget(self.theme_btn)

        # Kassa ochish Button — success
        self.open_shift_btn = _tb_btn(
            "Kassa ochish", colors['success'], "white", hover="#059669"
        )
        self.open_shift_btn.clicked.connect(lambda: self._show_pos_opening_dialog({}))
        top_bar.addWidget(self.open_shift_btn)
        self.open_shift_btn.hide()  # hidden initially

        # Kassa yopish Button — error/destructive
        self.close_shift_btn = _tb_btn(
            "Kassa yopish", colors['error'], "white", hover="#dc2626"
        )
        self.close_shift_btn.clicked.connect(self.show_pos_closing)
        top_bar.addWidget(self.close_shift_btn)

        main_layout.addLayout(top_bar)

        # --- Main Content Splitter ---
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.item_browser = ItemBrowser(self.api)
        self.item_browser.item_selected.connect(self.add_item_to_active_cart)
        # splitter.addWidget(self.item_browser)

        # ── Sales Tabs ──────────────────
        self.sales_tabs = QTabWidget()
        self.sales_tabs.setTabsClosable(True)
        self.sales_tabs.setMovable(True)
        self.sales_tabs.tabCloseRequested.connect(self.close_sale_tab)
        self.sales_tabs.currentChanged.connect(self._on_tab_changed)
        self.sales_tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: {colors['bg_primary']};
            }}
            QTabBar::tab {{
                background: {colors['bg_secondary']};
                color: {colors['text_tertiary']};
                padding: 10px 20px;
                font-weight: 600;
                font-size: 13px;
                border-radius: 8px 8px 0 0;
                margin-right: 4px;
                border: 1px solid {colors['border']};
                border-bottom: none;
                min-width: 90px;
            }}
            QTabBar::tab:selected {{
                background: {colors['bg_tertiary']};
                color: {colors['accent']};
                font-weight: 900;
                border: 1px solid {colors['accent']};
            }}
            QTabBar::tab:hover:!selected {{
                background: {colors['bg_tertiary']};
                color: {colors['text_primary']};
            }}
        """)


        splitter.addWidget(self.item_browser)
        splitter.addWidget(self.sales_tabs)
        
        # Foizli o'lcham - 45% item_browser, 55% sales_tabs
        splitter.setStretchFactor(0, 45)
        splitter.setStretchFactor(1, 55)

        main_layout.addWidget(splitter, stretch=1)

        # ── Inline History Panel (hidden by default) ──
        self.history_panel = HistoryWindow(self.api, self)
        self.history_panel.setVisible(False)
        self.history_panel.setMinimumHeight(360)
        self.history_panel.setMaximumHeight(500)
        self.history_panel.setStyleSheet(f"""
            background: {colors['bg_primary']};
            border-top: 2px solid {colors['border']};
        """)
        main_layout.addWidget(self.history_panel)

        # Footer
        self.status_label = QLabel("Tayyor.")
        self.statusBar().addWidget(self.status_label)

        
        # Global Keyboard instance
        self.global_keyboard = None
        self._current_focused_input = None
        QApplication.instance().focusChanged.connect(self._on_focus_changed)

        from PyQt6.QtGui import QShortcut, QKeySequence
        self.kb_shortcut = QShortcut(QKeySequence("F11"), self)
        self.kb_shortcut.activated.connect(self._toggle_global_keyboard)


        # Bottom Keyboard Button
        self.keyboard_btn = QPushButton("⌨️ Elektron Klaviatura (F11)")
        self.keyboard_btn.setMinimumHeight(26)
        self.keyboard_btn.setMaximumHeight(36)
        self.keyboard_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.keyboard_btn.setStyleSheet(f"""
            QPushButton {{
                background: {colors['bg_tertiary']}; color: {colors['text_primary']};
                font-weight: bold; font-size: 13px;
                border-radius: 6px; padding: 0 16px; margin: 2px;
            }}
            QPushButton:hover {{ background: {colors['border']}; }}
            QPushButton:pressed {{ background: {colors['text_tertiary']}; }}
        """)
        self.keyboard_btn.clicked.connect(self._toggle_global_keyboard)
        self.statusBar().addPermanentWidget(self.keyboard_btn)


        # Initial Sale Tab
        self.add_new_sale_tab()


        # Workers - Shared API beriladi
        self.sync_worker = None
        self._auto_sync = True  # birinchi sinxronizatsiya dialog ko'rsatmasin
        self._start_sync_worker()  # Login dan keyin avtomatik sinxronizatsiya

        self.offline_sync_worker = OfflineSyncWorker(self.api)
        self.offline_sync_worker.sync_status.connect(self.update_status)
        self.offline_sync_worker.start()

        # Monitor timer
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self.monitor_system)
        self.monitor_timer.start(MONITOR_INTERVAL_MS)
        self.monitor_system()

        # POS Opening check — kassa ochiqligini tekshirish
        self._check_pos_opening()

    def request_exit(self):
        dlg = ConfirmDialog(
            self, "Chiqish", "Dasturdan chiqishni xohlaysizmi?",
            icon="🚪", yes_text="Chiqish", yes_color="#ef4444",
        )
        dlg.exec()
        if dlg.result_accepted:
            self.close()

    def request_logout(self):
        dlg = ConfirmDialog(
            self, "Tizimdan chiqish",
            "Tizimdan chiqishni xohlaysizmi?\nBarcha hisob ma'lumotlari tozalanadi.",
            icon="🔓", yes_text="Chiqish", yes_color="#f59e0b",
        )
        dlg.exec()
        if dlg.result_accepted:
            self.logout_requested.emit()

    def _update_company_badge(self, company: str = "", pos_profile: str = ""):
        colors = ThemeManager.get_theme_colors()
        display = company or pos_profile or "—"
        self.company_badge.setText(f"🏢  {display}")
        self.company_badge.setStyleSheet(f"""
            font-size: 12px;
            font-weight: 700;
            color: {colors['text_primary']};
            background: {colors['bg_secondary']};
            border: 1.5px solid {colors['border']};
            border-radius: 8px;
            padding: 4px 12px;
        """)

    def _update_company_logo(self, config: dict | None = None):
        if not hasattr(self, "company_logo_label"):
            return

        colors = ThemeManager.get_theme_colors()
        self.company_logo_label.setStyleSheet(f"""
            QLabel {{
                background: {colors['bg_secondary']};
                border: 1.5px solid {colors['border']};
                border-radius: 14px;
                color: {colors['text_tertiary']};
                font-size: 28px;
                font-weight: 700;
                padding: 4px;
            }}
        """)

        cfg = config if isinstance(config, dict) else load_config()
        logo_path = get_cached_company_logo_path(cfg)
        if logo_path:
            pixmap = QPixmap(logo_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.company_logo_label.width() - 8,
                    self.company_logo_label.height() - 8,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.company_logo_label.setPixmap(scaled)
                self.company_logo_label.setText("")
                return

        self.company_logo_label.setPixmap(QPixmap())
        self.company_logo_label.setText("🏢")

    def monitor_system(self):
        self._check_server_status()
        self._update_offline_queue_count()

    def _check_server_status(self):
        # Background thread'da tekshirish — GUI muzlamasligi uchun
        if hasattr(self, '_connectivity_worker') and self._connectivity_worker.isRunning():
            return  # oldingi tekshiruv hali tugamagan
        self._connectivity_worker = ConnectivityCheckWorker(self.api)
        self._connectivity_worker.finished.connect(self._update_connectivity_ui)
        self._connectivity_worker.start()

    def _update_connectivity_ui(self, is_online: bool):
        if is_online:
            self.status_dot.setStyleSheet("background-color: #10b981; border-radius: 6px;")
            self.status_text.setText("ONLINE")
            self.status_text.setStyleSheet("font-weight: bold; color: #10b981; font-size: 13px;")
        else:
            self.status_dot.setStyleSheet("background-color: #ef4444; border-radius: 6px;")
            self.status_text.setText("OFFLINE")
            self.status_text.setStyleSheet("font-weight: bold; color: #ef4444; font-size: 13px;")

    def _update_offline_queue_count(self):
        try:
            db.connect(reuse_if_open=True)
            count = PendingInvoice.select().where(PendingInvoice.status == "Pending").count()
            self.offline_btn.setText(f"Offline: {count}")

            if count > 0:
                self.offline_btn.setStyleSheet("""
                    QPushButton { padding: 12px 20px; background-color: #fff7ed; color: #ea580c;
                    font-weight: bold; font-size: 14px; border-radius: 8px; border: 2px solid #f97316; }
                """)
            else:
                self.offline_btn.setStyleSheet("""
                    QPushButton { padding: 12px 20px; background-color: #f3f4f6; color: #374151;
                    font-weight: bold; font-size: 14px; border-radius: 8px; border: 1px solid #d1d5db; }
                """)
        except Exception as e:
            logger.debug("Offline queue count xatosi: %s", e)
        finally:
            if not db.is_closed():
                db.close()

    def show_offline_queue(self):
        dialog = OfflineQueueWindow(self)
        dialog.exec()
        self._update_offline_queue_count()

    def add_new_sale_tab(self):
        tab_count = self.sales_tabs.count()
        new_cart = CartWidget(self.api)
        new_cart.checkout_requested.connect(self.on_checkout)
        new_cart.price_list_changed.connect(self.item_browser.set_price_list)
        new_cart.cart_updated.connect(self._sync_item_browser_cart_view)
        tab_index = self.sales_tabs.addTab(new_cart, f"Sotuv {tab_count + 1}")
        self.sales_tabs.setCurrentIndex(tab_index)
        self._sync_item_browser_cart_view()

    def _on_tab_changed(self, index: int):
        cart = self.sales_tabs.widget(index)
        if cart:
            self.item_browser.set_price_list(cart.price_list_combo.currentText())
        self._sync_item_browser_cart_view()

    def _get_active_cart_reservations(self) -> dict:
        active_cart = self.sales_tabs.currentWidget()
        if not active_cart or not hasattr(active_cart, "items"):
            return {}

        reservations = {}
        for code, item in active_cart.items.items():
            try:
                qty = int(float(item.get("qty", 0)))
            except (TypeError, ValueError):
                qty = 0
            if qty > 0:
                reservations[code] = qty
        return reservations

    def _sync_item_browser_cart_view(self, *_args):
        if hasattr(self, "item_browser"):
            self.item_browser.set_reserved_quantities(self._get_active_cart_reservations())

    def close_sale_tab(self, index: int):
        if self.sales_tabs.count() > 1:
            cart = self.sales_tabs.widget(index)
            if cart and cart.items:
                dlg = ConfirmDialog(
                    self, "Vkladkani yopish",
                    "Savatda tovarlar bor. Baribir yopmoqchimisiz?",
                    icon="⚠️", yes_text="Ha, yopish", yes_color="#ef4444",
                )
                dlg.exec()
                if not dlg.result_accepted:
                    return
            self.sales_tabs.removeTab(index)
            self._sync_item_browser_cart_view()
        else:
            InfoDialog(self, "Diqqat", "Kamida bitta sotuv oynasi ochiq bo'lishi kerak.", kind="warning").exec()

    def add_item_to_active_cart(self, item_code: str, item_name: str, price: float, currency: str):
        active_cart = self.sales_tabs.currentWidget()
        if active_cart:
            active_cart.add_item(item_code, item_name, price, currency)
            self._sync_item_browser_cart_view()

    def on_checkout(self, order_data: dict):
        if self.opening_entry:
            order_data = dict(order_data)
            order_data["opening_entry"] = self.opening_entry
        # CheckoutWindow ham shared API ishlatadi
        dialog = CheckoutWindow(self, order_data, self.api)
        dialog.checkout_completed.connect(self.on_checkout_completed)
        dialog.exec()

    def on_checkout_completed(self):
        active_cart = self.sales_tabs.currentWidget()
        if active_cart:
            active_cart.clear_cart()
        self._sync_item_browser_cart_view()
        self._update_offline_queue_count()

    def _get_active_cart_customer(self) -> str:
        active_cart = self.sales_tabs.currentWidget()
        if not active_cart or not hasattr(active_cart, "get_selected_customer_name"):
            return ""
        customer = (active_cart.get_selected_customer_name() or "").strip()
        if customer.lower() in {"guest", "guest customer"}:
            return ""
        return customer

    def show_printer_settings(self):
        from ui.components.printer_settings import PrinterSettingsDialog
        dlg = PrinterSettingsDialog(self, self.api)
        dlg.exec()

    def toggle_theme(self):
        """Toggle between light and dark theme"""
        new_theme = ThemeManager.toggle_theme()
        # Update button icon
        theme_icon = "🌙" if new_theme == "light" else "☀️"
        self.theme_btn.setText(theme_icon)
        # Apply theme to all UI elements
        self._apply_theme_to_ui()
        logger.info(f"Theme changed to: {new_theme}")

    def show_payments_window(self):
        dlg = PaymentsWindow(
            self,
            self.api,
            opening_entry=self.opening_entry or "",
            initial_customer=self._get_active_cart_customer(),
        )
        dlg.payment_processed.connect(self._after_payment_processed)
        dlg.exec()

    def _after_payment_processed(self):
        if self.history_panel.isVisible():
            self.history_panel.load_history()

    def show_history(self):
        colors = ThemeManager.get_theme_colors()
        visible = self.history_panel.isVisible()
        if visible:
            self.history_panel.setVisible(False)
            self.history_btn.setStyleSheet(
                f"padding: 12px 20px; background-color: {colors['accent']}; color: white; "
                "font-weight: bold; border-radius: 8px; margin-left: 10px;"
            )
        else:
            self.history_panel.opening_entry = self.opening_entry or ""
            self.history_panel.setVisible(True)
            self.history_panel.load_history()
            self.history_btn.setStyleSheet(
                f"padding: 12px 20px; background-color: {colors['accent_hover']}; color: white; "
                "font-weight: bold; border-radius: 8px; margin-left: 10px;"
                f"border: 2px solid {colors['accent']};"
            )

    def start_sync(self):
        self.sync_btn.setEnabled(False)
        self._auto_sync = False  # qo'lda bosdi — dialog ko'rsatilsin
        self.status_label.setText("Sinxronizatsiya boshlandi...")
        self._start_sync_worker()

    def _start_sync_worker(self):
        if self.sync_worker and self.sync_worker.isRunning():
            return
        self.sync_worker = SyncWorker(self.api)
        self.sync_worker.progress_update.connect(self.update_status)
        self.sync_worker.sync_finished.connect(self.on_sync_finished)
        self.sync_worker.start()

    def update_status(self, message: str):
        self.status_label.setText(message)

    def on_sync_finished(self, success: bool, message: str):
        self.sync_btn.setEnabled(True)
        # Filial nomini yangilash
        cfg = load_config()
        self._update_company_badge(cfg.get("company", ""), cfg.get("pos_profile", ""))
        self._update_company_logo(cfg)
        if success:
            self.item_browser.load_items()
            # Also refresh Cart's price list combo
            for i in range(self.sales_tabs.count()):
                cart = self.sales_tabs.widget(i)
                if hasattr(cart, 'load_price_lists'):
                    cart.load_price_lists()
                if hasattr(cart, 'invalidate_item_meta_cache'):
                    cart.invalidate_item_meta_cache()
                if hasattr(cart, 'load_customers'):
                    cart.load_customers()
                if hasattr(cart, 'refresh_customer_groups'):
                    cart.refresh_customer_groups()
        # Avtomatik sinxronizatsiyada dialog ko'rsatmaymiz
        if self._auto_sync:
            self._auto_sync = False
            if not success:
                self.status_label.setText(f"Sinxronizatsiya xatosi: {message}")
            else:
                self.status_label.setText("Sinxronizatsiya muvaffaqiyatli!")
        else:
            if success:
                InfoDialog(self, "Muvaffaqiyatli", message, kind="success").exec()
            else:
                InfoDialog(self, "Xatolik", message, kind="error").exec()

    # ── POS Opening / Closing ──────────────────────────────
    def _check_pos_opening(self):
        """Login dan keyin kassa ochiqligini tekshirish."""
        self._set_pos_enabled(False)
        self.opening_check_worker = PosOpeningCheckWorker(self.api)
        self.opening_check_worker.finished.connect(self._on_opening_check_done)
        self.opening_check_worker.start()

    def _on_opening_check_done(self, has_opening: bool, opening_entry: str, dialog_data: dict = None):
        if has_opening:
            self.opening_entry = opening_entry
            self._set_pos_enabled(True)
            self.status_label.setText("Kassa ochiq.")
        else:
            self._show_pos_opening_dialog(dialog_data or {})

    def _show_pos_opening_dialog(self, dialog_data: dict):
        if not dialog_data:
            success, response = self.api.call_method("posawesome.posawesome.api.shifts.get_opening_dialog_data")
            if success and isinstance(response, dict):
                dialog_data = response
        dlg = PosOpeningDialog(self, self.api, dialog_data)
        dlg.opening_completed.connect(self._on_pos_opened)
        dlg.exit_requested.connect(self._on_opening_exit)
        dlg.logout_requested.connect(self._on_opening_logout)
        dlg.exec()

    def _on_opening_exit(self):
        """Kassa ochish dialogidan chiqish — dasturni yopish."""
        self.close()

    def _on_opening_logout(self):
        """Kassa ochish dialogidan logout — boshqa kassir kirishi uchun."""
        self.logout_requested.emit()

    def _on_pos_opened(self, opening_entry: str):
        self.opening_entry = opening_entry
        self._set_pos_enabled(True)
        self.status_label.setText("Kassa ochildi!")

    def show_pos_closing(self):
        if not self.opening_entry:
            InfoDialog(
                self, "Kassa topilmadi",
                "Ochiq kassa topilmadi.",
                kind="warning",
            ).exec()
            return

        dlg = ConfirmDialog(
            self, "Kassani yopish",
            "Kassani yopmoqchimisiz?\nBarcha to'lovlar hisoblanadi.",
            icon="🔒", yes_text="Ha, yopish", yes_color="#dc2626",
        )
        dlg.exec()
        if not dlg.result_accepted:
            return

        closing_dlg = PosClosingDialog(self, self.api, self.opening_entry)
        closing_dlg.closing_completed.connect(self._on_pos_closed)
        closing_dlg.exec()

    def _on_pos_closed(self):
        self.opening_entry = None
        self._set_pos_enabled(False)
        self.status_label.setText("Kassa yopildi.")

        # Muvaffaqiyat xabari
        InfoDialog(
            self, "Kassa yopildi",
            "Kassa muvaffaqiyatli yopildi.\nDavom etish uchun yangi kassa oching.",
            kind="success",
        ).exec()

        # Yangi kassa ochish dialogini ko'rsatish
        self._show_pos_opening_dialog({})

    def _set_pos_enabled(self, enabled: bool):
        """Kassa ochiq/yopiq holatiga qarab UI elementlarini boshqarish."""
        self.add_sale_btn.setEnabled(enabled)
        self.close_shift_btn.setEnabled(enabled)
        self.open_shift_btn.setVisible(not enabled)
        self.payments_btn.setEnabled(enabled)
        if hasattr(self, 'item_browser'):
            self.item_browser.setEnabled(enabled)
        if hasattr(self, 'sales_tabs'):
            self.sales_tabs.setEnabled(enabled)

    
    def _on_focus_changed(self, old_widget, new_widget):
        if hasattr(self, 'global_keyboard') and new_widget:
            # Check safely to prevent circular reference or crash
            if isinstance(new_widget, QLineEdit):
                if new_widget.property("disable_virtual_keyboard"):
                    self._current_focused_input = None
                    return
                if getattr(self.global_keyboard, 'input_field', None) != new_widget:
                    self._current_focused_input = new_widget
                    try:
                        new_widget.destroyed.connect(self._clear_destroyed_focused_input)
                    except Exception:
                        pass

    def _clear_destroyed_focused_input(self, *_args):
        self._current_focused_input = None

    def _get_live_focused_input(self):
        widget = getattr(self, "_current_focused_input", None)
        if widget is None or not isinstance(widget, QLineEdit):
            self._current_focused_input = None
            return None
        try:
            widget.objectName()
            return widget
        except RuntimeError:
            self._current_focused_input = None
            return None

    def _toggle_global_keyboard(self):
        if getattr(self, 'global_keyboard', None) is None or not self.global_keyboard.isVisible():
            focused_input = self._get_live_focused_input()
            if focused_input is None:
                return
            current_text = ""
            try:
                current_text = focused_input.text()
            except RuntimeError:
                self._current_focused_input = None
                return
            
            self.global_keyboard = TouchKeyboard(self, initial_text=current_text, title="Elektron Klaviatura")
            self.global_keyboard.text_changed.connect(self._on_global_keyboard_text_changed)
            # Show below the main window or floating
            self.global_keyboard.show()
        else:
            self.global_keyboard.close()
            self.global_keyboard = None
            
    def _on_global_keyboard_text_changed(self, text):
        focused_input = self._get_live_focused_input()
        if focused_input is None:
            return
        try:
            focused_input.setText(text)
        except RuntimeError:
            self._current_focused_input = None
    
    def _apply_central_widget_theme(self, widget):
        """Apply theme to central widget"""
        colors = ThemeManager.get_theme_colors()
        widget.setStyleSheet(f'background: {colors["bg_primary"]};')
    
    def _apply_theme_to_ui(self):
        """Apply current theme to all UI elements"""
        colors = ThemeManager.get_theme_colors()
        
        # Update central widget
        central = self.centralWidget()
        if central:
            central.setStyleSheet(f'background: {colors["bg_primary"]};')
        
        # Update brand logo colors
        if hasattr(self, 'brand_name'):
            self.brand_name.setText(f"POS<font color=\"{colors['accent']}\">Awesome</font>")
            self.brand_name.setStyleSheet(f"""
                font-size: 24px;
                font-weight: 900;
                color: {colors['accent']};
                background: transparent;
            """)
        
        if hasattr(self, 'brand_sub'):
            self.brand_sub.setStyleSheet(f"""
                font-size: 9px;
                font-weight: 700;
                color: {colors['accent_hover']};
                background: transparent;
                letter-spacing: 2px;
            """)

        if hasattr(self, "company_badge"):
            cfg = load_config()
            self._update_company_badge(cfg.get("company", ""), cfg.get("pos_profile", ""))
            self._update_company_logo(cfg)
        
        # Update status indicators
        if hasattr(self, 'status_dot'):
            self.status_dot.setStyleSheet(f"background-color: {colors['text_tertiary']}; border-radius: 6px;")
        
        if hasattr(self, 'status_text'):
            self.status_text.setStyleSheet(f"font-weight: bold; color: {colors['text_secondary']}; font-size: 13px;")
        
        # Update tabs styling
        if hasattr(self, 'sales_tabs'):
            self.sales_tabs.setStyleSheet(f"""
                QTabWidget::pane {{
                    border: none;
                    background: {colors['bg_primary']};
                }}
                QTabBar::tab {{
                    background: {colors['bg_secondary']};
                    color: {colors['text_tertiary']};
                    padding: 10px 20px;
                    font-weight: 600;
                    font-size: 13px;
                    border-radius: 8px 8px 0 0;
                    margin-right: 4px;
                    border: 1px solid {colors['border']};
                    border-bottom: none;
                    min-width: 90px;
                }}
                QTabBar::tab:selected {{
                    background: {colors['bg_tertiary']};
                    color: {colors['accent']};
                    font-weight: 900;
                    border: 1px solid {colors['accent']};
                }}
                QTabBar::tab:hover:!selected {{
                    background: {colors['bg_tertiary']};
                    color: {colors['text_primary']};
                }}
            """)
        
        # Update history panel if exists
        if hasattr(self, 'history_panel'):
            self.history_panel.setStyleSheet(f"""
                background: {colors['bg_primary']};
                border-top: 2px solid {colors['border']};
            """)
            if hasattr(self.history_panel, "apply_theme"):
                self.history_panel.apply_theme()

        if hasattr(self, "item_browser") and hasattr(self.item_browser, "apply_theme"):
            self.item_browser.apply_theme()

        if hasattr(self, "sales_tabs"):
            for i in range(self.sales_tabs.count()):
                cart = self.sales_tabs.widget(i)
                if hasattr(cart, "apply_theme"):
                    cart.apply_theme()

        if hasattr(self, "history_btn") and hasattr(self, "history_panel"):
            if self.history_panel.isVisible():
                self.history_btn.setStyleSheet(
                    f"padding: 12px 20px; background-color: {colors['accent_hover']}; color: white; "
                    "font-weight: bold; border-radius: 8px; margin-left: 10px;"
                    f"border: 2px solid {colors['accent']};"
                )
            else:
                self.history_btn.setStyleSheet(
                    f"padding: 12px 20px; background-color: {colors['accent']}; color: white; "
                    "font-weight: bold; border-radius: 8px; margin-left: 10px;"
                )

    def closeEvent(self, event):
        self.monitor_timer.stop()
        self.offline_sync_worker.stop()
        if not self.offline_sync_worker.wait(2000):
            logger.warning("Offline sync worker 2 sekund ichida to'xtamadi")
        super().closeEvent(event)
