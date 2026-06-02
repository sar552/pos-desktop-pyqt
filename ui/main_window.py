import time

from PyQt6.QtWidgets import (
    QApplication, QLineEdit,
    QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QWidget,
    QPushButton, QSplitter, QTabWidget, QComboBox,
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
from core.i18n import tr, i18n, SUPPORTED_LANGUAGES
from core.updater import check_for_update, perform_update
from core.barcode_listener import BarcodeManager
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


class UpdateCheckWorker(QThread):
    """GitHub'dan yangi versiya bor-yo'qligini background'da tekshiradi."""
    update_available = pyqtSignal(dict)  # {version, url, notes}

    def run(self):
        info = check_for_update()
        if info:
            self.update_available.emit(info)


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
    relaunch_requested = pyqtSignal()  # til o'zgarganda oynani qayta qurish

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
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Top Bar ---
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(16, 8, 16, 8)
        top_bar.setSpacing(10)

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
            font-size: 22px;
            font-weight: 800;
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

        self.status_text = QLabel(tr("Checking..."))
        self.status_text.setStyleSheet(f"font-weight: bold; color: {colors['text_secondary']}; font-size: 12px;")

        top_bar.addWidget(self.status_dot)
        top_bar.addWidget(self.status_text)
        top_bar.addStretch()

        # ── helper for consistent top-bar button style ──────────
        def _tb_btn(label: str, bg: str, color: str = "white",
                    hover: str = "", border: str = "none") -> QPushButton:
            b = QPushButton(label)
            b.setMinimumHeight(36)
            b.setMaximumHeight(44)
            h = hover or bg
            disabled_bg = colors['bg_tertiary']
            disabled_text = colors['text_tertiary']
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {bg}; color: {color};
                    font-weight: 600; font-size: 12px;
                    border-radius: 8px; border: {border};
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
            tr("+ Yangi sotuv"), colors['success'], "white",
            hover="#059669"
        )
        self.add_sale_btn.clicked.connect(self.add_new_sale_tab)
        top_bar.addWidget(self.add_sale_btn)

        # History Button — accent variant
        self.history_btn = _tb_btn(
            tr("Tarix"), colors['accent'], "white", hover=colors['accent_hover']
        )
        self.history_btn.clicked.connect(self.show_history)
        top_bar.addWidget(self.history_btn)

        self.payments_btn = _tb_btn(
            tr("Payments"), colors['accent'], "white", hover=colors['accent_hover']
        )
        self.payments_btn.clicked.connect(self.show_payments_window)
        top_bar.addWidget(self.payments_btn)

        # Sync Button — accent color
        self.sync_btn = _tb_btn(
            tr("Sinxronlash"), colors['accent'], "white", hover=colors['accent_hover']
        )
        self.sync_btn.clicked.connect(self.start_sync)
        top_bar.addWidget(self.sync_btn)

        # Printer Settings Button — muted
        self.printer_btn = _tb_btn(
            tr("Printer"), colors['text_secondary'], "white", hover=colors['text_primary']
        )
        self.printer_btn.clicked.connect(self.show_printer_settings)
        top_bar.addWidget(self.printer_btn)

        # Theme Toggle Button — muted
        current_theme = ThemeManager.get_current_theme()
        theme_icon = "🌙" if current_theme == "light" else "☀️"
        self.theme_btn = _tb_btn(
            theme_icon, colors['text_secondary'], "white", hover=colors['text_primary']
        )
        self.theme_btn.setToolTip(tr("Mavzu o'zgartirish (Light/Dark)"))
        self.theme_btn.clicked.connect(self.toggle_theme)
        top_bar.addWidget(self.theme_btn)

        # Til tanlash — logout qilmasdan tilni o'zgartirish
        self.lang_combo = QComboBox()
        self.lang_combo.setMinimumHeight(36)
        self.lang_combo.setMaximumHeight(44)
        self.lang_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        for code, name in SUPPORTED_LANGUAGES.items():
            self.lang_combo.addItem(f"🌐 {name}", code)
        _ci = self.lang_combo.findData(i18n.language)
        if _ci >= 0:
            self.lang_combo.setCurrentIndex(_ci)
        self.lang_combo.setStyleSheet(f"""
            QComboBox {{
                background: {colors['bg_secondary']}; color: {colors['text_primary']};
                border: 1px solid {colors['border']}; border-radius: 8px;
                padding: 0 10px; font-size: 12px; font-weight: 600;
            }}
            QComboBox::drop-down {{ border: none; width: 18px; }}
            QComboBox QAbstractItemView {{
                background: {colors['bg_secondary']}; color: {colors['text_primary']};
                selection-background-color: {colors['accent']};
            }}
        """)
        self.lang_combo.setToolTip(tr("Til"))
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        top_bar.addWidget(self.lang_combo)

        # Kassa ochish Button — success
        self.open_shift_btn = _tb_btn(
            tr("Kassa ochish"), colors['success'], "white", hover="#059669"
        )
        self.open_shift_btn.clicked.connect(lambda: self._show_pos_opening_dialog({}))
        top_bar.addWidget(self.open_shift_btn)
        self.open_shift_btn.hide()  # hidden initially

        # Kassa yopish Button — error/destructive
        self.close_shift_btn = _tb_btn(
            tr("Kassa yopish"), colors['error'], "white", hover="#dc2626"
        )
        self.close_shift_btn.clicked.connect(self.show_pos_closing)
        top_bar.addWidget(self.close_shift_btn)

        # Logout (tizimdan chiqish) — tasdiqlash so'raydi, keyin login oynasiga qaytadi
        self.logout_btn = _tb_btn(
            tr("🔓 Chiqish"), colors['warning'], "white", hover="#d97706"
        )
        self.logout_btn.setToolTip(tr("Tizimdan chiqish (boshqa kassir kirishi uchun)"))
        self.logout_btn.clicked.connect(self.request_logout)
        top_bar.addWidget(self.logout_btn)

        main_layout.addLayout(top_bar)

        # --- Main Content Splitter ---
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.item_browser = ItemBrowser(self.api)
        self.item_browser.item_selected.connect(self.add_item_to_active_cart)
        self.item_browser.search_resolved.connect(self.add_item_payload_to_active_cart)
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
                font-size: 12px;
                border-radius: 8px 8px 0 0;
                margin-right: 3px;
                border: 1px solid {colors['border']};
                border-bottom: none;
                min-width: 90px;
            }}
            QTabBar::tab:selected {{
                background: {colors['bg_primary']};
                color: {colors['accent']};
                font-weight: 700;
                border: 1px solid {colors['border']};
                border-bottom: 2px solid {colors['accent']};
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
            border-top: 1px solid {colors['border']};
        """)
        main_layout.addWidget(self.history_panel)

        # Footer
        self.status_label = QLabel(tr("Tayyor."))
        self.statusBar().addWidget(self.status_label)

        
        # Global Keyboard instance
        self.global_keyboard = None
        self._current_focused_input = None
        QApplication.instance().focusChanged.connect(self._on_focus_changed)
        # Yoziladigan maydon allaqachon fokusda bo'lsa, qayta bosilganda
        # focusChanged ishlamaydi — shuning uchun bosishni alohida kuzatamiz
        # (klaviatura yopilgandan keyin ham qayta ochilishi uchun).
        QApplication.instance().installEventFilter(self)

        from PyQt6.QtGui import QShortcut, QKeySequence
        self.kb_shortcut = QShortcut(QKeySequence("F11"), self)
        self.kb_shortcut.activated.connect(self._toggle_global_keyboard)

        # Avto-yangilanish: startdan ~4 soniya keyin background'da tekshiramiz.
        self._update_worker = None
        self._update_in_progress = False
        QTimer.singleShot(4000, self._start_update_check)


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

        # --- Professional Barcode Management ---
        self.barcode_manager = BarcodeManager(self)
        self.barcode_manager.barcode_scanned.connect(self._handle_external_barcode)
        self.barcode_manager.scanner_error.connect(self._on_scanner_error)
        self.barcode_manager.input_polluted.connect(self._clean_polluted_input)

        # HID filter — faqat MainWindow hayoti davomida. Login oynasi kalit'larni ushlamaydi.
        self.barcode_manager.install_keyboard_filter(QApplication.instance())

        # COM Portlarni sozlash
        self._reload_barcode_ports()

    def _reload_barcode_ports(self):
        """Apply COM/Serial scanner config; auto-detect ports if none configured.

        For HID (USB-keyboard) skanerlar hech qanday sozlama kerak emas —
        global event filter avtomatik tutadi.  Serial skanerlar uchun
        config.json'dagi `barcode_ports` ishlatiladi; agar bo'sh bo'lsa,
        OS'dagi mavjud serial portlarni avtomatik aniqlab ko'ramiz.
        """
        cfg = load_config()
        ports = list(cfg.get("barcode_ports") or [])
        # Migration: eski yakka `barcode_port` kalitini ham qo'shib qo'yamiz.
        single_port = cfg.get("barcode_port")
        if single_port and single_port not in ports:
            ports.append(single_port)

        # Avtomatik aniqlash — faqat config'da port yo'q bo'lsa.
        if not ports:
            ports = self._auto_detect_serial_scanners()

        self.barcode_manager.setup_scanners(ports)
        self.barcode_manager.reload_config()

    @staticmethod
    def _auto_detect_serial_scanners() -> list:
        """Probe OS serial ports that look like USB-Serial scanners.

        We only include obviously safe candidates (USB/ACM bridges).  Native
        COM1/ttyS0 ports are skipped to avoid disturbing mice, modems, or
        industrial RS-232 devices.
        """
        try:
            from serial.tools import list_ports
        except ImportError:
            return []
        try:
            ports_info = list(list_ports.comports())
        except Exception as e:
            logger.debug("Serial port aniqlashda xato: %s", e)
            return []

        detected = []
        for p in ports_info:
            name = (getattr(p, "device", "") or "").upper()
            desc = (getattr(p, "description", "") or "").lower()
            # USB-Serial bridges (Linux: ttyUSB*/ttyACM*, Windows: USB description)
            if (
                "USB" in name
                or "ACM" in name
                or "usb" in desc
                or "scanner" in desc
                or "hid" in desc
            ):
                detected.append({"port": p.device, "baudrate": 9600})
        if detected:
            logger.info("Serial skanerlar avtomatik aniqlandi: %s", detected)
        return detected

    def _on_scanner_error(self, port: str, message: str):
        """Show a non-blocking status-bar warning when a Serial scanner fails."""
        text = f"⚠️ Skaner {port}: {message}"
        logger.warning(text)
        if hasattr(self, "status_label"):
            self.status_label.setText(text)

    def _clean_polluted_input(self, widget, barcode: str):
        """Remove a barcode prefix that leaked into any QLineEdit.

        The first-key-delay normally prevents leaks, but if focus is on a
        QLineEdit during the burst (or some chars sneak through), the tail of
        the widget's text will match a prefix of the emitted barcode.  We
        strip that tail, and as a safety net we also scan all visible
        QLineEdits.
        """
        from PyQt6.QtWidgets import QLineEdit
        if not barcode:
            return

        def trim_if_matches(le: QLineEdit) -> bool:
            try:
                current = le.text() or ""
            except RuntimeError:
                return False  # widget destroyed
            if not current:
                return False
            for length in range(min(len(current), len(barcode)), 0, -1):
                tail = current[-length:]
                if barcode.startswith(tail):
                    # Signallarni bloklaymiz — `textChanged` filterni qayta
                    # ishga tushirmasin.
                    blocker = le.blockSignals(True)
                    try:
                        le.setText(current[:-length])
                    finally:
                        le.blockSignals(blocker)
                    return True
            return False

        cleaned_any = False
        # 1. Listener bergan aniq nishon.
        if isinstance(widget, QLineEdit):
            cleaned_any |= trim_if_matches(widget)

        # 2. Safety net: barcha ko'rinadigan QLineEditlarni ham tekshiramiz.
        try:
            for w in QApplication.allWidgets():
                if not isinstance(w, QLineEdit) or w is widget:
                    continue
                if not w.isVisible():
                    continue
                cleaned_any |= trim_if_matches(w)
        except Exception as e:
            logger.debug("allWidgets() skanida xato: %s", e)

        if cleaned_any:
            logger.debug("Skaner prefix'i %r inputdan tozalandi.", barcode[:4])

    def _handle_external_barcode(self, barcode):
        """Tashqi skanerdan (Serial yoki Global Keyboard) kelgan barcodeni qayta ishlash."""
        barcode = (barcode or "").strip()
        if not barcode:
            return

        # --- Deduplication (Double-entry protection) ---
        current_time = time.time()
        last_time = getattr(self, "_last_barcode_time", 0)
        last_barcode = getattr(self, "_last_barcode", "")

        # 200ms — skanerlar ba'zan bir uzatishni 2 marta yuboradi, lekin
        # kassir atayin ikki marta o'tkazganini bloklamaymiz.
        if barcode == last_barcode and (current_time - last_time) < 0.2:
            logger.debug("Dublikat barcode inkor qilindi: %s", barcode)
            return

        self._last_barcode = barcode
        self._last_barcode_time = current_time

        logger.info("Tashqi barcode skanerlandi: %s", barcode)

        cart_count_before = self._active_cart_item_count()
        # MUHIM: barcode'ni LEFT search inputga YOZMAYMIZ — submit_search uni
        # argument sifatida oladi.  Aks holda cart_updated → reservations →
        # load_items(search_input.text()) zanjiri LEFT ro'yxatni shu barcode
        # bo'yicha filterlab qoldiradi.
        self.item_browser.submit_search(barcode, add_to_cart=True)

        if self._active_cart_item_count() > cart_count_before:
            self.status_label.setText(f"✅ Skanerlandi: {barcode}")
        else:
            self.status_label.setText(
                f"❌ '{barcode}' barcode bo'yicha tovar topilmadi"
            )

    def _active_cart_item_count(self) -> int:
        cart = self.sales_tabs.currentWidget() if hasattr(self, "sales_tabs") else None
        if cart is None or not hasattr(cart, "items"):
            return 0
        try:
            return sum(int(it.get("qty", 0)) for it in cart.items.values())
        except Exception:
            return len(getattr(cart, "items", {}) or {})

    def request_exit(self):
        dlg = ConfirmDialog(
            self, tr("Chiqish"), tr("Dasturdan chiqishni xohlaysizmi?"),
            icon="🚪", yes_text=tr("Chiqish"), yes_color="#ef4444",
        )
        dlg.exec()
        if dlg.result_accepted:
            self.close()

    def request_logout(self):
        dlg = ConfirmDialog(
            self, tr("Tizimdan chiqish"),
            tr("Tizimdan chiqishni xohlaysizmi?\nBarcha hisob ma'lumotlari tozalanadi."),
            icon="🔓", yes_text=tr("Chiqish"), yes_color="#f59e0b",
        )
        dlg.exec()
        if dlg.result_accepted:
            self.logout_requested.emit()

    def _on_language_changed(self, _index):
        code = self.lang_combo.currentData()
        if not code or code == i18n.language:
            return
        # Savatda tovar bo'lsa — qayta qurishda yo'qoladi, ogohlantiramiz.
        has_items = False
        for i in range(self.sales_tabs.count()):
            w = self.sales_tabs.widget(i)
            if getattr(w, "items", None):
                has_items = True
                break
        if has_items:
            dlg = ConfirmDialog(
                self, tr("Til"),
                tr("Til o'zgartirilsinmi? Oyna qayta yuklanadi va savatdagi tovarlar yo'qoladi."),
                icon="🌐", yes_text=tr("Ha"), yes_color="#f59e0b",
            )
            dlg.exec()
            if not dlg.result_accepted:
                # Bekor qilindi — combo'ni eski tilga qaytaramiz.
                _ci = self.lang_combo.findData(i18n.language)
                if _ci >= 0:
                    self.lang_combo.blockSignals(True)
                    self.lang_combo.setCurrentIndex(_ci)
                    self.lang_combo.blockSignals(False)
                return
        i18n.set_language(code)
        # Butun oyna yangi tilda qayta quriladi (hamma matn yangilanadi).
        self.relaunch_requested.emit()

    # ── Avto-yangilanish ─────────────────────────────────────────────
    def _start_update_check(self):
        try:
            self._update_worker = UpdateCheckWorker()
            self._update_worker.update_available.connect(self._on_update_available)
            self._update_worker.start()
        except Exception as e:
            logger.debug("Update check ishga tushmadi: %s", e)

    def _on_update_available(self, info: dict):
        if self._update_in_progress:
            return
        version = info.get("version", "")
        dlg = ConfirmDialog(
            self, tr("Yangi versiya"),
            f"{tr('Yangi versiya chiqdi')}: {version}\n{tr('Hozir yangilansinmi?')}",
            icon="⬆️", yes_text=tr("Yangilash"), yes_color="#2563eb",
        )
        dlg.exec()
        if not dlg.result_accepted:
            return
        self._update_in_progress = True
        try:
            started = perform_update(info.get("url", ""))
        except Exception as e:
            logger.error("Yangilash xatosi: %s", e)
            InfoDialog(self, tr("Xatolik"), tr("Yangilash amalga oshmadi."), "error").exec()
            self._update_in_progress = False
            return
        if started:
            # .bat fayllarni almashtirib, dasturni qayta ishga tushiradi.
            QApplication.quit()
        else:
            # Dev rejim yoki .exe emas — faqat xabar.
            InfoDialog(self, tr("Yangi versiya"), tr("Yangi versiyani GitHub'dan yuklab oling."), "warning").exec()
            self._update_in_progress = False

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
        """Spawn a connectivity check off the GUI thread; never overlap two."""
        existing = getattr(self, "_connectivity_worker", None)
        if existing is not None:
            try:
                still_running = existing.isRunning()
            except RuntimeError:
                # Underlying C++ object was already deleted — clear our handle.
                self._connectivity_worker = None
                still_running = False
            if still_running:
                return

        worker = ConnectivityCheckWorker(self.api)
        worker.finished.connect(self._update_connectivity_ui)
        # Bo'shatilganda Python reference'ni ham tozalaymiz — keyingi safar
        # `isRunning()`'ga o'lik C++ ob'ektga ulanmaslik uchun.
        worker.finished.connect(lambda *_: self._on_connectivity_worker_done(worker))
        self._connectivity_worker = worker
        worker.start()

    def _on_connectivity_worker_done(self, worker):
        if getattr(self, "_connectivity_worker", None) is worker:
            self._connectivity_worker = None
        try:
            worker.deleteLater()
        except RuntimeError:
            pass

    def _update_connectivity_ui(self, is_online: bool):
        colors = ThemeManager.get_theme_colors()
        if is_online:
            self.status_dot.setStyleSheet(f"background-color: {colors['success']}; border-radius: 6px;")
            self.status_text.setText(tr("ONLINE"))
            self.status_text.setStyleSheet(f"font-weight: bold; color: {colors['success']}; font-size: 12px;")
        else:
            self.status_dot.setStyleSheet(f"background-color: {colors['error']}; border-radius: 6px;")
            self.status_text.setText(tr("OFFLINE"))
            self.status_text.setStyleSheet(f"font-weight: bold; color: {colors['error']}; font-size: 12px;")

    def _update_offline_queue_count(self):
        try:
            db.connect(reuse_if_open=True)
            count = PendingInvoice.select().where(PendingInvoice.status == "Pending").count()
            self.offline_btn.setText(f"{tr('Offline')}: {count}")
            colors = ThemeManager.get_theme_colors()

            if count > 0:
                self.offline_btn.setStyleSheet(f"""
                    QPushButton {{ padding: 12px 20px; background-color: {colors.get('warning_bg', '#fff7ed')}; color: {colors['warning']};
                    font-weight: bold; font-size: 12px; border-radius: 8px; border: 1.5px solid {colors.get('warning_border', '#f97316')}; }}
                """)
            else:
                self.offline_btn.setStyleSheet(f"""
                    QPushButton {{ padding: 12px 20px; background-color: {colors['bg_secondary']}; color: {colors['text_primary']};
                    font-weight: bold; font-size: 12px; border-radius: 8px; border: 1.5px solid {colors['border']}; }}
                    QPushButton:hover {{ background-color: {colors['bg_tertiary']}; }}
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
        tab_index = self.sales_tabs.addTab(new_cart, f"{tr('Sotuv')} {tab_count + 1}")
        self.sales_tabs.setCurrentIndex(tab_index)
        self._sync_item_browser_cart_view()

    def _on_tab_changed(self, index: int):
        cart = self.sales_tabs.widget(index)
        if cart and hasattr(cart, "price_list_combo"):
            new_pl = cart.price_list_combo.currentText()
            # Faqat haqiqatan boshqa price list bo'lsa ro'yxatni qayta yuklaymiz.
            if getattr(self.item_browser, "current_price_list", "") != new_pl:
                self.item_browser.set_price_list(new_pl)
        self._sync_item_browser_cart_view()

    def _get_active_cart_reservations(self) -> dict:
        active_cart = self.sales_tabs.currentWidget()
        if not active_cart or not hasattr(active_cart, "items"):
            return {}

        reservations = {}
        for code, item in active_cart.items.items():
            try:
                qty = float(item.get("qty", 0))
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
                    self, tr("Vkladkani yopish"),
                    tr("Savatda tovarlar bor. Baribir yopmoqchimisiz?"),
                    icon="⚠️", yes_text="Ha, yopish", yes_color="#ef4444",
                )
                dlg.exec()
                if not dlg.result_accepted:
                    return
            self.sales_tabs.removeTab(index)
            self._sync_item_browser_cart_view()
        else:
            InfoDialog(self, tr("Diqqat"), tr("Kamida bitta sotuv oynasi ochiq bo'lishi kerak."), kind="warning").exec()

    def add_item_to_active_cart(self, item_code: str, item_name: str, price: float, currency: str):
        active_cart = self.sales_tabs.currentWidget()
        if active_cart:
            # MUHIM: matnni avval tozalaymiz — cart.add_item() cart_updated
            # signali orqali set_reserved_quantities -> load_items(text) zanjirini
            # ishga tushiradi.  Text bo'sh bo'lsagina butun ro'yxat ko'rinadi.
            self.item_browser.set_search_text("", trigger=False)
            if hasattr(active_cart, "clear_item_search"):
                active_cart.clear_item_search()
            active_cart.add_item(item_code, item_name, price, currency)
            self._sync_item_browser_cart_view()

    def add_item_payload_to_active_cart(self, payload: dict):
        active_cart = self.sales_tabs.currentWidget()
        if active_cart:
            # Yuqoridagi kabi: matnni emit'dan/apply'dan oldin tozalaymiz.
            self.item_browser.set_search_text("", trigger=False)
            if hasattr(active_cart, "clear_item_search"):
                active_cart.clear_item_search()
            active_cart.apply_item_payload(payload)
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
                "font-weight: 600; border-radius: 8px; margin-left: 10px; border: none;"
            )
        else:
            self.history_panel.opening_entry = self.opening_entry or ""
            self.history_panel.setVisible(True)
            self.history_panel.load_history()
            self.history_btn.setStyleSheet(
                f"padding: 12px 20px; background-color: {colors['accent_hover']}; color: white; "
                "font-weight: 600; border-radius: 8px; margin-left: 10px; "
                f"border: 2px solid {colors['accent']};"
            )

    def start_sync(self):
        self.sync_btn.setEnabled(False)
        self._auto_sync = False  # qo'lda bosdi — dialog ko'rsatilsin
        self.status_label.setText(tr("Sinxronizatsiya boshlandi..."))
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
                self.status_label.setText(f"{tr('Sinxronizatsiya xatosi')}: {message}")
            else:
                self.status_label.setText(tr("Sinxronizatsiya muvaffaqiyatli!"))
        else:
            if success:
                InfoDialog(self, tr("Muvaffaqiyatli"), message, kind="success").exec()
            else:
                InfoDialog(self, tr("Xatolik"), message, kind="error").exec()

    # ── POS Opening / Closing ──────────────────────────────
    def _check_pos_opening(self):
        """Login dan keyin kassa ochiqligini tekshirish."""
        self._set_pos_enabled(False)
        self.opening_check_worker = PosOpeningCheckWorker(self.api)
        self.opening_check_worker.finished.connect(self._on_opening_check_done)
        self.opening_check_worker.start()

    def _on_opening_check_done(self, has_opening: bool, opening_entry: str, dialog_data: dict = None):
        # Worker'dan kelgan dialog_data'ni cache qilamiz — keyin "Kassa ochish"
        # tugmasi bosilganda yana API'ga bormaslik uchun.
        if isinstance(dialog_data, dict) and dialog_data:
            self._cached_opening_dialog = dialog_data
        if has_opening:
            self.opening_entry = opening_entry
            self._set_pos_enabled(True)
            self.status_label.setText(tr("Kassa ochiq."))
        else:
            self._show_pos_opening_dialog(dialog_data or {})

    def _show_pos_opening_dialog(self, dialog_data: dict):
        if not dialog_data:
            dialog_data = getattr(self, "_cached_opening_dialog", None) or {}
        if not dialog_data:
            success, response = self.api.call_method("posawesome.posawesome.api.shifts.get_opening_dialog_data")
            if success and isinstance(response, dict):
                dialog_data = response
                self._cached_opening_dialog = dialog_data
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
        self.status_label.setText(tr("Kassa ochildi!"))

    def show_pos_closing(self):
        if not self.opening_entry:
            InfoDialog(
                self, tr("Kassa topilmadi"),
                tr("Ochiq kassa topilmadi."),
                kind="warning",
            ).exec()
            return

        dlg = ConfirmDialog(
            self, tr("Kassani yopish"),
            tr("Kassani yopmoqchimisiz?\nBarcha to'lovlar hisoblanadi."),
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
        self._cached_opening_dialog = None  # eski qoldiqlardan tozalaymiz
        self._set_pos_enabled(False)
        self.status_label.setText(tr("Kassa yopildi."))

        # Muvaffaqiyat xabari
        InfoDialog(
            self, tr("Kassa yopildi"),
            tr("Kassa muvaffaqiyatli yopildi.\nDavom etish uchun yangi kassa oching."),
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

    
    def eventFilter(self, obj, event):
        """Yoziladigan maydon bosilganini kuzatadi.

        focusChanged faqat fokus o'zgarganda ishlaydi; maydon allaqachon
        fokusda bo'lsa (masalan klaviatura yopilgandan keyin) qayta bosish
        klaviaturani ochmaydi. Shu sababli bosishni ham ushlaymiz.
        """
        try:
            from PyQt6.QtCore import QEvent
            if event.type() == QEvent.Type.MouseButtonPress:
                if isinstance(obj, QLineEdit):
                    self._maybe_reopen_keyboard(obj)
                else:
                    # Yoziladigan maydondan tashqariga bosildi — klaviaturani
                    # yopamiz (klaviaturaning o'z tugmalari bundan mustasno).
                    self._maybe_close_keyboard(obj)
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _maybe_close_keyboard(self, obj):
        kb = getattr(self, 'global_keyboard', None)
        if kb is None:
            return
        try:
            if not kb.isVisible():
                return
            # Klaviaturaning o'zini (yoki ichidagi widgetni) bossa — yopmaymiz.
            if obj is kb or kb.isAncestorOf(obj):
                return
        except RuntimeError:
            self.global_keyboard = None
            return
        kb.hide()
        self._current_focused_input = None

    def _maybe_reopen_keyboard(self, line_edit):
        # Klaviaturaning o'z ichidagi maydonni bosish — e'tibor bermaymiz.
        kb = getattr(self, 'global_keyboard', None)
        if kb is not None:
            try:
                if line_edit is kb or kb.isAncestorOf(line_edit):
                    return
            except RuntimeError:
                self.global_keyboard = None
        if line_edit.property("disable_virtual_keyboard"):
            return
        if not line_edit.isEnabled() or line_edit.isReadOnly():
            return
        self._current_focused_input = line_edit
        # Fokus o'rnashishi uchun keyingi event-loop siklida ochamiz.
        QTimer.singleShot(0, lambda le=line_edit: self._reopen_keyboard_for(le))

    def _reopen_keyboard_for(self, line_edit):
        try:
            line_edit.objectName()
        except RuntimeError:
            return
        self._show_keyboard_for(line_edit)

    def _on_focus_changed(self, old_widget, new_widget):
        """Yoziladigan maydonga fokus tushganda klaviatura avtomatik ochiladi
        (telefondagidek). Skaner/qidiruv maydonida esa yashiriladi."""
        if new_widget is None:
            return

        kb = getattr(self, 'global_keyboard', None)
        # Klaviaturaning o'z ichidagi widgetlarga fokus o'tsa — e'tibor bermaymiz.
        if kb is not None:
            try:
                if new_widget is kb or kb.isAncestorOf(new_widget):
                    return
            except RuntimeError:
                self.global_keyboard = None
                kb = None

        if not isinstance(new_widget, QLineEdit):
            # Fokus yoziladigan maydondan tashqariga (tugma, jadval, bo'sh joy)
            # o'tdi — klaviaturani avtomatik yopamiz (telefondagidek).
            self._current_focused_input = None
            if kb is not None and kb.isVisible():
                kb.hide()
            return

        if new_widget.property("disable_virtual_keyboard"):
            # Skaner/qidiruv maydoni — klaviatura yo'ldan olib turilsin.
            self._current_focused_input = None
            if kb is not None and kb.isVisible():
                kb.hide()
            return

        if not new_widget.isEnabled() or new_widget.isReadOnly():
            return

        # Yoziladigan maydon — klaviaturani ochamiz/moslaymiz.
        self._current_focused_input = new_widget
        try:
            new_widget.destroyed.connect(self._clear_destroyed_focused_input)
        except Exception:
            pass
        self._show_keyboard_for(new_widget)

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

    @staticmethod
    def _is_numeric_input(line_edit) -> bool:
        """Maydon faqat raqam qabul qiladimi — kichik numpad ko'rsatish uchun."""
        from PyQt6.QtGui import QIntValidator, QDoubleValidator
        # 1) Aniq belgilab qo'yilgan bo'lsa — ustuvor.
        prop = line_edit.property("numeric_keyboard")
        if prop is not None:
            return bool(prop)
        # 2) Raqamli validator bo'lsa — raqamli maydon.
        if isinstance(line_edit.validator(), (QIntValidator, QDoubleValidator)):
            return True
        # 3) Input method hints raqam deb belgilangan bo'lsa.
        try:
            from PyQt6.QtCore import Qt as _Qt
            hints = line_edit.inputMethodHints()
            if hints & (_Qt.InputMethodHint.ImhDigitsOnly | _Qt.InputMethodHint.ImhPreferNumbers):
                return True
        except Exception:
            pass
        return False

    def _show_keyboard_for(self, line_edit):
        """Berilgan maydon uchun klaviaturani ochadi yoki moslaydi.

        Faqat raqam yoziladigan maydonga kichik numpad, qolganlarga to'liq
        klaviatura chiqadi. Modal dialoglarda ham ishlashi uchun klaviatura
        fokuslangan maydonning oynasiga (window) bola qilib yaratiladi —
        aks holda modal dialog uni bloklab qo'yadi.
        """
        try:
            text = line_edit.text()
        except RuntimeError:
            return
        title = line_edit.placeholderText() or "Klaviatura"
        host = line_edit.window() or self
        want_numeric = self._is_numeric_input(line_edit)

        kb = getattr(self, 'global_keyboard', None)
        # Klaviatura boshqa oynaga tegishli yoki rejimi (raqamli/to'liq) mos
        # bo'lmasa — qayta yaratamiz (rejim qurilishda belgilanadi).
        if kb is not None:
            try:
                needs_rebuild = (kb.parent() is not host) or (kb.is_numeric != want_numeric)
            except RuntimeError:
                needs_rebuild = True
                kb = None
            if kb is not None and needs_rebuild:
                try:
                    kb.close()
                    kb.deleteLater()
                except Exception:
                    pass
                kb = None
                self.global_keyboard = None

        if kb is None:
            kb = TouchKeyboard(host, initial_text=text, title=title, is_numeric=want_numeric)
            kb.text_changed.connect(self._on_global_keyboard_text_changed)
            self.global_keyboard = kb
        else:
            kb.set_target(text, title)

        if not kb.isVisible():
            kb.show()

    def _toggle_global_keyboard(self):
        """F11 / status-bar tugmasi: klaviaturani qo'lda ochish-yopish."""
        kb = getattr(self, 'global_keyboard', None)
        if kb is not None and kb.isVisible():
            kb.hide()
            return
        focused_input = self._get_live_focused_input()
        if focused_input is None:
            return
        self._show_keyboard_for(focused_input)

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
        """Apply current theme to all UI elements."""
        colors = ThemeManager.get_theme_colors()
        
        # Update central widget
        central = self.centralWidget()
        if central:
            central.setStyleSheet(f'background: {colors["bg_primary"]};')
        
        # Update brand logo colors
        if hasattr(self, 'brand_name'):
            self.brand_name.setText(f"POS<font color=\"{colors['accent']}\">Awesome</font>")
            self.brand_name.setStyleSheet(f"""
                font-size: 22px;
                font-weight: 800;
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
            self.status_text.setStyleSheet(f"font-weight: bold; color: {colors['text_secondary']}; font-size: 12px;")
        
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
                    font-size: 12px;
                    border-radius: 8px 8px 0 0;
                    margin-right: 3px;
                    border: 1px solid {colors['border']};
                    border-bottom: none;
                    min-width: 90px;
                }}
                QTabBar::tab:selected {{
                    background: {colors['bg_primary']};
                    color: {colors['accent']};
                    font-weight: 700;
                    border: 1px solid {colors['border']};
                    border-bottom: 2px solid {colors['accent']};
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
                border-top: 1px solid {colors['border']};
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
        if hasattr(self, 'barcode_manager'):
            # stop_all() endi HID filter-ni ham olib tashlaydi.
            self.barcode_manager.stop_all()
        if not self.offline_sync_worker.wait(2000):
            logger.warning("Offline sync worker 2 sekund ichida to'xtamadi")
        super().closeEvent(event)
