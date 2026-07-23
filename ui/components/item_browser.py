from ui.components.dialogs import InfoDialog
from ui.component_styles import get_component_styles
from ui.theme_manager import ThemeManager
import json
from PyQt6.QtWidgets import QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
import requests
from PyQt6.QtWidgets import (
    QScroller, QApplication,
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QScrollArea, QGridLayout, QLabel, QSizePolicy, QFrame,
)
from PyQt6.QtCore import pyqtSignal, Qt, QSize, QThread, QObject, QTimer
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPainterPath
from database.models import Item, ItemPrice, db
from peewee import fn
from core.api import FrappeAPI
from core.config import load_config
from core.feedback import SoundFeedback
from ui.components.keyboard import TouchKeyboard
from core.logger import get_logger
from core.constants import ITEM_LOAD_LIMIT, IMAGE_TIMEOUT
from core.i18n import tr
logger = get_logger(__name__)


class _OnlineBarcodeLookupWorker(QThread):
    """Resolve an unknown barcode on the server, off the GUI thread."""

    finished_signal = pyqtSignal(str, object)  # (search, payload-or-None)

    def __init__(self, api, barcode: str, price_list: str, currency: str):
        super().__init__()
        self.api = api
        self.barcode = barcode
        self.price_list = price_list
        self.currency = currency

    def run(self):
        payload = None
        try:
            if self.api and self.api.is_configured():
                success, response = self.api.call_method(
                    "posawesome.posawesome.api.items.get_items_from_barcode",
                    {
                        "selling_price_list": self.price_list,
                        "currency": self.currency,
                        "barcode": self.barcode,
                    },
                )
                if success and isinstance(response, dict) and response.get("item_code"):
                    payload = {
                        "item_code": response.get("item_code"),
                        "item_name": response.get("item_name") or response.get("item_code"),
                        "rate": float(response.get("price_list_rate") or response.get("rate") or 0),
                        "currency": response.get("currency") or self.currency,
                        "qty": response.get("scale_qty") or 1,
                        "uom": response.get("uom"),
                        "manual_rate": response.get("scale_price") is not None,
                    }
        except Exception as e:
            logger.debug("Online barcode resolve xatosi: %s", e)
        self.finished_signal.emit(self.barcode, payload)


class ImageLoader(QThread):
    """Rasmlarni fonda yuklash uchun maxsus thread.

    MUHIM: QPixmap faqat GUI thread'da yaratilishi mumkin — shu sababli
    worker QImage emit qiladi, qabul qiluvchi uni QPixmap'ga o'giradi.

    Karta (ItemButton) har qidiruv harfida deleteLater() bo'ladi; agar thread
    ob'ektiga oxirgi reference karta bilan birga yo'qolsa, Qt "QThread:
    Destroyed while thread is still running" bilan butun ilovani o'ldiradi.
    Shuning uchun ishlayotgan loaderlarni class-level registrda ushlab turamiz
    va faqat thread tugagach qo'yib yuboramiz.
    """
    image_loaded = pyqtSignal(QImage)

    _active_loaders = set()

    def __init__(self, url, api):
        super().__init__()
        self.url = url
        self.api = api

    def start(self, *args, **kwargs):
        ImageLoader._active_loaders.add(self)
        self.finished.connect(self._release_ref)
        super().start(*args, **kwargs)

    def _release_ref(self):
        ImageLoader._active_loaders.discard(self)

    def run(self):
        try:
            full_url = self.url if self.url.startswith("http") else f"{self.api.url}{self.url}"
            headers = {"Accept": "image/*,*/*"}
            if self.api.api_key and self.api.api_secret:
                headers["Authorization"] = f"token {self.api.api_key}:{self.api.api_secret}"
            if self.api.site:
                headers["X-Frappe-Site-Name"] = self.api.site
            response = self.api.session.get(full_url, headers=headers, timeout=IMAGE_TIMEOUT)
            if response.status_code == 200:
                image = QImage()
                if image.loadFromData(response.content):
                    self.image_loaded.emit(image)
            else:
                logger.debug("Image yuklanmadi: %s — HTTP %d", full_url, response.status_code)
        except Exception as e:
            logger.debug("Image yuklash xatosi: %s — %s", self.url, e)


class ItemButton(QFrame):
    """Premium karta ko'rinishidagi mahsulot kartochkasi"""
    clicked = pyqtSignal()

    def __init__(self, item_code, item_name, price, currency, image_url=None, api=None, parent=None, stock_qty=0.0, uom='Nos'):
        super().__init__(parent)
        self.item_code = item_code
        self.item_name = item_name
        self.price = price
        self.currency = currency
        self.colors = ThemeManager.get_theme_colors()
        self.api = api
        self.loader = None  # ImageLoader reference
        self._original_pixmap = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Standart va o'zgarmas o'lcham (Natural look uchun)
        self.setFixedWidth(180)
        self.setFixedHeight(240)
        
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        # Consolidate styling into a single scoped stylesheet with pseudo-states
        # to prevent layout recalculations and flickering on events.
        self.setObjectName("ItemCard")
        self.setStyleSheet(f"""
            QFrame#ItemCard {{
                background: {self.colors['bg_secondary']};
                border: 1.5px solid {self.colors['border']};
                border-radius: 12px;
            }}
            QFrame#ItemCard:hover {{
                background: {self.colors['bg_tertiary']};
                border-color: {self.colors['accent']};
            }}
            QFrame#ItemCard:pressed {{
                background: {self.colors['selection_bg']};
                border-color: {self.colors['accent_hover']};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Rasm qismi (karta yuqori qismi) ---
        self.image_container = QWidget()
        self.image_container.setFixedHeight(120)
        self.image_container.setStyleSheet(f"""
            background: {self.colors['bg_tertiary']};
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
        """)

        img_inner = QVBoxLayout(self.image_container)
        img_inner.setContentsMargins(0, 0, 0, 0)
        img_inner.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.image_label = QLabel()
        self.image_label.setFixedSize(120, 90)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet(f"""
            background: {self.colors['bg_secondary']};
            border-radius: 10px;
            color: {self.colors['text_tertiary']};
            font-size: 32px;
        """)
        self.image_label.setText("📦")

        if image_url and api:
            self.loader = ImageLoader(image_url, api)
            self.loader.image_loaded.connect(self._set_pixmap)
            self.loader.finished.connect(self._on_loader_finished)
            self.loader.start()

        img_inner.addWidget(self.image_label)
        layout.addWidget(self.image_container)

        # --- Ma'lumot qismi (karta pastki qismi) ---
        info_container = QWidget()
        info_container.setStyleSheet(f"""
            background: {self.colors['bg_secondary']};
            border-bottom-left-radius: 12px;
            border-bottom-right-radius: 12px;
        """)
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(10, 10, 10, 12)
        info_layout.setSpacing(6)

        # Mahsulot nomi
        # Uzun nomlarni qisqartirish
        display_name = item_name if len(item_name) <= 22 else item_name[:20] + "…"
        name_label = QLabel(display_name)
        name_label.setWordWrap(True)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setToolTip(item_name)
        name_label.setStyleSheet(f"""
            font-size: 13px;
            font-weight: 700;
            color: {self.colors['text_primary']};
            background: transparent;
            border: none;
            line-height: 1.3;
        """)
        name_label.setMinimumHeight(30)
        name_label.setMaximumHeight(42)

        # Narx badge
        price_str = f"{price:,.0f}".replace(",", " ") + f" {currency}"
        price_label = QLabel(price_str)
        price_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        price_label.setStyleSheet(f"""
            font-size: 13px;
            font-weight: 800;
            color: white;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {self.colors['accent']}, stop:1 {self.colors['accent_hover']});
            border-radius: 8px;
            padding: 4px 8px;
            border: none;
        """)
        price_label.setMinimumHeight(24)
        price_label.setMaximumHeight(32)

        
        # Stock Info
        self._uom = uom
        self.stock_label = QLabel(f"{stock_qty:g} {uom}")
        self.stock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stock_label.setStyleSheet(
            f"color: {self.colors['text_tertiary']}; font-size: 11px; font-weight: bold; background: transparent; border: none;"
        )

        info_layout.addWidget(name_label)
        info_layout.addWidget(price_label)
        info_layout.addWidget(self.stock_label)
        layout.addWidget(info_container)

    def set_stock_qty(self, qty: float):
        """In-place update of the stock badge — no widget re-creation."""
        try:
            self.stock_label.setText(f"{float(qty):g} {self._uom}")
        except Exception:
            pass


    def _set_pixmap(self, image: QImage):
        """Yuklangan rasmni image_label'ga o'rnatish (QImage -> QPixmap GUI threadda)"""
        if image is None or image.isNull():
            return
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            return
        self._original_pixmap = pixmap
        self.image_label.setText("")
        self.image_label.setStyleSheet("background: transparent; border-radius: 10px; border: none;")
        self._render_pixmap()

    def _render_pixmap(self):
        """Rasmni container o'lchamiga moslab qayta chizish"""
        if not self._original_pixmap or self._original_pixmap.isNull():
            return
        target_size = self.image_label.size()
        if target_size.width() <= 0 or target_size.height() <= 0:
            return
        scaled = self._original_pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = max(0, (scaled.width() - target_size.width()) // 2)
        y = max(0, (scaled.height() - target_size.height()) // 2)
        self.image_label.setPixmap(scaled.copy(x, y, target_size.width(), target_size.height()))

    def _on_loader_finished(self):
        """ImageLoader tugaganda resurslarni tozalash"""
        if self.loader:
            self.loader.deleteLater()
            self.loader = None

    def resizeEvent(self, event):
        self._render_pixmap()
        super().resizeEvent(event)

    def enterEvent(self, event):
        super().enterEvent(event)

    def leaveEvent(self, event):
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class ItemBrowser(QWidget):
    item_selected = pyqtSignal(str, str, float, str)
    search_resolved = pyqtSignal(dict)
    settings_clicked = pyqtSignal()

    def __init__(self, api: FrappeAPI):
        super().__init__()
        self.api = api
        self.reserved_quantities = {}
        self.settings = {
            "hide_zero_stock": {"label": tr("0 qoldiqchilarni yashirish"), "value": False},
            "hide_zero_rate": {"label": tr("Nol narxlilarni yashirish"), "value": False},
            "hide_decimals": {"label": tr("O'nli kasrlarni yashirish"), "value": False},
        }
        self.current_price_list = "Standard Selling"

        self.current_category = None
        self._last_columns = 0
        self._caps = False
        self._letter_buttons = []
        # Barcode -> item_code xaritasi: har skanda butun jadvalni JSON bilan
        # qayta o'qib chiqmaslik uchun (sinxrondan keyin yangilanadi).
        self._barcode_cache = None
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(150)
        self._resize_timer.timeout.connect(self._on_resize_done)
        # Qidiruv debounce — har harfda emas, yozish to'xtagach ro'yxatni
        # qayta quramiz (har keystroke'da butun grid + rasm threadlari
        # qayta yaratilishi GUI'ni muzlatib qo'yardi).
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(
            lambda: self.load_items(self.search_input.text())
        )
        self.init_ui()
        self.load_categories()
        self.load_items()
        # Search klaviaturasi tashqariga bosilganda avtomatik yopilishi uchun.
        QApplication.instance().installEventFilter(self)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(10)
        
        styles = get_component_styles()
        self.colors = ThemeManager.get_theme_colors()
        colors = self.colors
        self.setStyleSheet(styles["item_browser_bg"])
        self.view_mode = "card"

        # Top row: Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(tr("🔍  Search Items..."))
        self.search_input.setMinimumHeight(38)
        self.search_input.setMaximumHeight(52)
        self.search_input.setProperty("disable_virtual_keyboard", True)
        self.search_input.setStyleSheet(styles["item_search"])
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.filter_items)
        self.search_input.returnPressed.connect(lambda: self.submit_search(self.search_input.text()))

        # Skanersiz monoblokda nom bo'yicha qidirish uchun ekran klaviaturasi tugmasi.
        self.search_kb_btn = QPushButton("⌨")
        self.search_kb_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_kb_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.search_kb_btn.setFixedWidth(52)
        self.search_kb_btn.setMinimumHeight(38)
        self.search_kb_btn.setMaximumHeight(52)
        self.search_kb_btn.setStyleSheet(f"""
            QPushButton {{
                background: {colors['bg_tertiary']}; color: {colors['text_secondary']};
                border: 1px solid {colors['border']}; border-radius: 10px; font-size: 20px;
            }}
            QPushButton:hover {{ background: {colors['bg_hover']}; color: {colors['accent']}; }}
            QPushButton:pressed {{ background: {colors['accent']}; color: white; }}
        """)
        self.search_kb_btn.clicked.connect(self._toggle_search_keyboard)
        self._search_kb = None

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(self.search_kb_btn)
        main_layout.addLayout(search_row)
        
        # Top Settings Header (optional visible mostly in List View context in UI, but we can show always)
        header_row = QHBoxLayout()
        self.settings_btn = QPushButton(tr("SETTINGS"))
        self.settings_btn.setStyleSheet(
            f"color: {colors['accent']}; font-weight: bold; font-size: 11px; background: transparent; border: none; text-align: left;"
        )
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.clicked.connect(self.open_settings)
        self.sync_label = QLabel(f"{tr('Oxirgi sinxron')}: —")
        self.sync_label.setStyleSheet(f"color: {colors['text_tertiary']}; font-size: 11px;")
        self.sync_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reload_btn = QPushButton(tr("RELOAD ITEMS"))
        self.reload_btn.setStyleSheet(
            f"color: {colors['accent']}; font-weight: bold; font-size: 11px; background: transparent; border: none; text-align: right;"
        )
        self.reload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reload_btn.clicked.connect(lambda: self.load_items(self.search_input.text()))
        
        
        header_row.addWidget(self.settings_btn)
        header_row.addWidget(self.sync_label, 1)
        header_row.addWidget(self.reload_btn)
        main_layout.addLayout(header_row)

        self.items_stack = QStackedWidget()
        
        # CARD VIEW
        self.items_scroll = QScrollArea()
        self.items_scroll.setWidgetResizable(True)
        self.items_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        self.items_container = QWidget()
        self.items_container.setStyleSheet("background: transparent;")
        self.items_grid = QGridLayout(self.items_container)
        self.items_grid.setContentsMargins(0, 0, 0, 0)
        self.items_grid.setSpacing(12)
        self.items_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.items_scroll.setWidget(self.items_container)
        self.items_stack.addWidget(self.items_scroll)

        # LIST VIEW
        self.items_table = QTableWidget()
        self.items_table.setColumnCount(4)
        self.items_table.setHorizontalHeaderLabels([tr("NAME"), tr("QTY"), tr("RATE"), tr("UOM")])
        # ERPNext'dan kelgan ma'lumot — faqat o'qish uchun. Aks holda katak
        # bosilganda tahrir ochilib, o'zgartirilgan nom savatga ham tushardi.
        self.items_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.verticalHeader().setDefaultSectionSize(50)
        self.items_table.setShowGrid(False)
        self.items_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.items_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.items_table.setStyleSheet(self._items_table_style())
        header = self.items_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setMinimumHeight(40)
        self.items_table.itemClicked.connect(self._on_table_item_clicked)
        self.items_stack.addWidget(self.items_table)

        main_layout.addWidget(self.items_stack, stretch=1)

        # Categories - Horizontal Scroll
        self.category_scroll = QScrollArea()
        self.category_scroll.setMinimumHeight(48)
        self.category_scroll.setMaximumHeight(70)
        self.category_scroll.setWidgetResizable(True)
        self.category_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.category_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.category_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        QScroller.grabGesture(self.category_scroll.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)

        
        self.category_container = QWidget()
        self.category_container.setStyleSheet("background: transparent;")
        self.category_layout = QHBoxLayout(self.category_container)
        self.category_layout.setContentsMargins(0, 4, 0, 4)
        self.category_layout.setSpacing(10)
        self.category_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.category_scroll.setWidget(self.category_container)
        main_layout.addWidget(self.category_scroll)

        # Bottom Bar: View Toggles & Badges
        bottom_bar = QHBoxLayout()
        
        self.btn_list_view = QPushButton(tr("LIST"))
        self.btn_list_view.setMinimumHeight(34)
        self.btn_list_view.setMaximumHeight(44)
        self.btn_list_view.clicked.connect(lambda: self.set_view_mode("list"))
        
        self.btn_card_view = QPushButton(tr("CARD"))
        self.btn_card_view.setMinimumHeight(34)
        self.btn_card_view.setMaximumHeight(44)
        self.btn_card_view.clicked.connect(lambda: self.set_view_mode("card"))
        
        self._update_toggle_styles()

        bottom_bar.addWidget(self.btn_list_view)
        bottom_bar.addWidget(self.btn_card_view)
        bottom_bar.addStretch()

        main_layout.addLayout(bottom_bar)

    def set_view_mode(self, mode):
        self.view_mode = mode
        if mode == "list":
            self.items_stack.setCurrentIndex(1)
        else:
            self.items_stack.setCurrentIndex(0)
        self._update_toggle_styles()

    def _items_table_style(self) -> str:
        colors = ThemeManager.get_theme_colors()
        return f"""
            QTableWidget {{ background: {colors['bg_secondary']}; color: {colors['text_primary']}; border: 1px solid {colors['border']}; border-radius: 6px; font-size: 13px; }}
            QHeaderView::section {{ background-color: {colors['bg_tertiary']}; color: {colors['text_secondary']}; font-weight: 700; font-size: 11px; border: none; border-bottom: 2px solid {colors['border']}; padding: 10px; }}
            QTableWidget::item {{ border-bottom: 1px solid {colors['border_light']}; padding: 10px; color: {colors['text_primary']}; font-weight: bold; }}
            QTableWidget::item:selected {{ background-color: {colors['selection_bg']}; color: {colors['selection_text']}; }}
        """

    def _category_button_style(self) -> str:
        colors = ThemeManager.get_theme_colors()
        return f"""
            QPushButton {{
                font-size: 13px;
                font-weight: 600;
                text-align: center;
                padding: 0 16px;
                border-radius: 4px;
                background: {colors['bg_secondary']};
                color: {colors['text_secondary']};
                border: 1px solid {colors['border']};
            }}
            QPushButton:checked {{
                background: {colors['accent']};
                color: white;
                border: 1px solid {colors['accent']};
            }}
            QPushButton:hover:!checked {{
                background: {colors['bg_tertiary']};
                color: {colors['text_primary']};
            }}
        """

    def apply_theme(self):
        """Re-apply theme styles for runtime light/dark switching."""
        styles = get_component_styles()
        colors = ThemeManager.get_theme_colors()
        self.colors = colors

        self.setStyleSheet(styles["item_browser_bg"])
        if hasattr(self, "search_input"):
            self.search_input.setStyleSheet(styles["item_search"])
        if hasattr(self, "settings_btn"):
            self.settings_btn.setStyleSheet(
                f"color: {colors['accent']}; font-weight: bold; font-size: 11px; background: transparent; border: none; text-align: left;"
            )
        if hasattr(self, "sync_label"):
            self.sync_label.setStyleSheet(f"color: {colors['text_tertiary']}; font-size: 11px;")
        if hasattr(self, "reload_btn"):
            self.reload_btn.setStyleSheet(
                f"color: {colors['accent']}; font-weight: bold; font-size: 11px; background: transparent; border: none; text-align: right;"
            )
        if hasattr(self, "items_table"):
            self.items_table.setStyleSheet(self._items_table_style())

        self._update_toggle_styles()

        if hasattr(self, "category_layout"):
            for i in range(self.category_layout.count()):
                btn = self.category_layout.itemAt(i).widget()
                if isinstance(btn, QPushButton):
                    btn.setStyleSheet(self._category_button_style())

        self.load_items(self.search_input.text())

    def _update_toggle_styles(self):
        colors = ThemeManager.get_theme_colors()
        active_style = f"""
            QPushButton {{
                background: {colors['accent']}; color: white; font-weight: bold; font-size: 11px;
                border-radius: 4px; padding: 0 15px; border: none;
            }}
        """
        inactive_style = f"""
            QPushButton {{
                background: {colors['bg_secondary']}; color: {colors['text_primary']}; font-weight: bold; font-size: 11px;
                border-radius: 4px; padding: 0 15px; border: 1px solid {colors['border']};
            }}
            QPushButton:hover {{ background: {colors['bg_tertiary']}; }}
        """
        if self.view_mode == "list":
            self.btn_list_view.setStyleSheet(active_style)
            self.btn_card_view.setStyleSheet(inactive_style)
        else:
            self.btn_list_view.setStyleSheet(inactive_style)
            self.btn_card_view.setStyleSheet(active_style)

    def _on_table_item_clicked(self, item):
        row = item.row()
        item_meta = self.items_table.item(row, 0)
        item_code = item_meta.data(Qt.ItemDataRole.UserRole)
        # Fetch details to emit
        code = item_code
        name = item_meta.text()
        rate = float(item_meta.data(Qt.ItemDataRole.UserRole + 1) or 0.0)
        currency = item_meta.data(Qt.ItemDataRole.UserRole + 2) or "UZS"
            
        from database.models import Item
        import json
        it = Item.get_or_none(Item.item_code == code)
        if it:
            try:
                p_data = json.loads(it.posawesome_data) if it.posawesome_data else {}
            except (TypeError, ValueError):
                p_data = {}
            try:
                actual_qty = float(p_data.get("actual_qty", 0) or 0)
            except (TypeError, ValueError):
                actual_qty = 0.0
            st_qty = self._get_effective_stock_qty(code, actual_qty)
            allow_negative = bool(p_data.get("allow_negative_stock", 0))
            is_stock = bool(p_data.get("is_stock_item", 1))
            if is_stock and not allow_negative and st_qty <= 0:
                SoundFeedback.error()
                InfoDialog(self, tr("Xatolik"), f"{name}: {tr('omborda qolmagan!')}", kind="warning").exec()
                return
        self.item_selected.emit(code, name, rate, currency)

    def set_reserved_quantities(self, reservations: dict | None):
        normalized = {}
        for code, qty in (reservations or {}).items():
            key = str(code).strip()
            if not key:
                continue
            try:
                numeric_qty = float(qty)
            except (TypeError, ValueError):
                continue
            if numeric_qty > 0:
                normalized[key] = numeric_qty

        if normalized == self.reserved_quantities:
            return

        # hide_zero_stock yoqiq bo'lsa: savatdan tovar olib tashlanganda
        # (rezerv kamayganda) yashiringan karta qayta ko'rinishi kerak —
        # badge yangilash buni sezmaydi, to'liq reload kerak.
        hide_zero = bool(self.settings.get("hide_zero_stock", {}).get("value"))
        released = hide_zero and any(
            qty > normalized.get(code, 0)
            for code, qty in self.reserved_quantities.items()
        )

        self.reserved_quantities = normalized
        if released:
            self.load_items(self.search_input.text())
        else:
            self._refresh_badges_in_place()

    def _refresh_badges_in_place(self):
        """Update stock badges on existing cards/rows without rebuilding the grid.

        Falls back to a full `load_items` only when the displayed item set
        could change (e.g. `hide_zero_stock` would hide newly-zero items).
        """
        from PyQt6.QtWidgets import QTableWidgetItem
        hide_zero = bool(self.settings.get("hide_zero_stock", {}).get("value"))

        needs_full_reload = False

        # 1. Grid view: walk existing ItemButton widgets.
        for i in range(self.items_grid.count()):
            w = self.items_grid.itemAt(i).widget() if self.items_grid.itemAt(i) else None
            if not isinstance(w, ItemButton):
                continue
            actual = self._actual_qty_for_code(w.item_code)
            effective = self._get_effective_stock_qty(w.item_code, actual)
            if hide_zero and effective <= 0:
                needs_full_reload = True
                break
            display = int(effective) if self.settings["hide_decimals"]["value"] else effective
            w.set_stock_qty(display)

        # 2. Table view (List mode): update qty column.
        if not needs_full_reload and hasattr(self, "items_table"):
            for row in range(self.items_table.rowCount()):
                name_item = self.items_table.item(row, 0)
                if name_item is None:
                    continue
                code = name_item.data(Qt.ItemDataRole.UserRole)
                if not code:
                    continue
                actual = self._actual_qty_for_code(code)
                effective = self._get_effective_stock_qty(code, actual)
                if hide_zero and effective <= 0:
                    needs_full_reload = True
                    break
                display = int(effective) if self.settings["hide_decimals"]["value"] else effective
                self.items_table.setItem(row, 1, QTableWidgetItem(f"{display:g}"))

        if needs_full_reload:
            self.load_items(self.search_input.text())

    def _actual_qty_for_code(self, item_code: str) -> float:
        """Lookup the cached `actual_qty` for an item without re-reading the DB."""
        try:
            db.connect(reuse_if_open=True)
            row = Item.get_or_none(Item.item_code == item_code)
            if not row or not row.posawesome_data:
                return 0.0
            return float(json.loads(row.posawesome_data).get("actual_qty", 0) or 0)
        except Exception:
            return 0.0
        finally:
            if not db.is_closed():
                db.close()

    def _get_effective_stock_qty(self, item_code: str, actual_qty: float) -> float:
        reserved_qty = float(self.reserved_quantities.get(item_code, 0) or 0)
        return float(actual_qty or 0) - reserved_qty

    def _resolve_display_price(self, item) -> tuple[float, str]:
        price_rec = ItemPrice.get_or_none(
            (ItemPrice.item_code == item.item_code) & (ItemPrice.price_list == self.current_price_list)
        )
        if price_rec:
            return float(price_rec.price_list_rate or 0), price_rec.currency or "UZS"
        return float(item.standard_rate or 0), "UZS"

    def _build_keyboard_panel(self):
        """Pastdan chiqadigan inline klaviatura paneli"""
        colors = ThemeManager.get_theme_colors()
        panel = QFrame()
        panel.setStyleSheet(f"""
            QFrame {{
                background: {colors['bg_secondary']};
                border-top: 2px solid {colors['border']};
                border-radius: 0px;
            }}
        """)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(10, 8, 10, 10)
        panel_layout.setSpacing(6)

        # Yuqori qator: yozilgan matn + yopish tugmasi
        top_row = QHBoxLayout()

        self.kb_display = QLabel(tr("Qidiruv..."))
        self.kb_display.setStyleSheet(f"""
            font-size: 16px;
            font-weight: 600;
            color: {colors['text_primary']};
            background: {colors['input_bg']};
            border: 1.5px solid {colors['accent']};
            border-radius: 8px;
            padding: 6px 12px;
        """)
        self.kb_display.setFixedHeight(40)

        close_btn = QPushButton("✕")
        close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_btn.setFixedSize(40, 40)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {colors['error']};
                color: white;
                font-weight: bold;
                font-size: 16px;
                border-radius: 8px;
                border: none;
            }}
            QPushButton:hover {{ background: {colors['accent_action']}; }}
        """)
        close_btn.clicked.connect(self._close_keyboard)

        top_row.addWidget(self.kb_display, stretch=1)
        top_row.addWidget(close_btn)
        panel_layout.addLayout(top_row)

        # Klaviatura qatorlari
        self._letter_buttons = []
        rows = [
            ['1','2','3','4','5','6','7','8','9','0','⌫'],
            ['Q','W','E','R','T','Y','U','I','O','P'],
            ['CAPS','A','S','D','F','G','H','J','K','L','CLR'],
            ['Z','X','C','V','B','N','M',' SPACE '],
        ]
        for row_keys in rows:
            row_layout = QHBoxLayout()
            row_layout.setSpacing(5)
            for key in row_keys:
                btn = self._make_key(key)
                row_layout.addWidget(btn)
            panel_layout.addLayout(row_layout)

        return panel

    def _make_key(self, key):
        colors = ThemeManager.get_theme_colors()
        label = key.strip()
        if label == 'SPACE': label = '␣'
        elif label == 'CLR': label = 'TOZALASH'
        elif label == 'CAPS': label = '⇧ Aa'

        btn = QPushButton(label)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setFixedHeight(44)

        if key.strip() == '⌫':
            style = f"background:{colors['bg_tertiary']}; color:{colors['error']}; font-size:18px; font-weight:bold;"
        elif key.strip() == 'CLR':
            style = f"background:{colors['bg_tertiary']}; color:{colors['accent_action']}; font-size:11px; font-weight:bold;"
        elif key.strip() == 'CAPS':
            style = f"background:{colors['bg_tertiary']}; color:{colors['accent_hover']}; font-size:13px; font-weight:bold;"
        elif 'SPACE' in key:
            style = f"background:{colors['bg_tertiary']}; color:{colors['accent']}; font-size:14px; font-weight:bold;"
            btn.setMinimumWidth(120)
        elif key.strip().isdigit():
            style = f"background:{colors['bg_tertiary']}; color:{colors['text_secondary']}; font-size:16px; font-weight:bold;"
        else:
            style = f"background:{colors['input_bg']}; color:{colors['text_primary']}; font-size:15px; font-weight:600;"

        btn.setStyleSheet(f"""
            QPushButton {{
                {style}
                border: 1px solid {colors['border']};
                border-radius: 7px;
            }}
            QPushButton:pressed {{ background: {colors['selection_bg']}; }}
        """)
        btn.clicked.connect(lambda _, k=key.strip(): self._on_key(k))

        if len(key.strip()) == 1 and key.strip().isalpha():
            self._letter_buttons.append(btn)

        return btn

    def _on_key(self, key):
        if key == 'CAPS':
            self._caps = not self._caps
            for btn in self._letter_buttons:
                txt = btn.text()
                btn.setText(txt.upper() if self._caps else txt.lower())
            return
        current = self.search_input.text()
        if key == '⌫':
            new_text = current[:-1]
        elif key == 'CLR':
            new_text = ''
        elif key == 'SPACE':
            new_text = current + ' '
        else:
            char = key.lower() if not self._caps else key.upper()
            new_text = current + char
        self.search_input.setText(new_text)
        # Display yangilash
        self.kb_display.setText(new_text if new_text else "Qidiruv...")

    def _open_search_keyboard(self, event):
        self.keyboard_panel.setVisible(True)
        self.kb_display.setText(self.search_input.text() or "Qidiruv...")
        self.search_input.setFocus()
        from PyQt6.QtWidgets import QLineEdit
        QLineEdit.mousePressEvent(self.search_input, event)

    def _close_keyboard(self):
        self.keyboard_panel.setVisible(False)

    def load_categories(self):
        try:
            db.connect(reuse_if_open=True)
            cats = [r.item_group for row in Item.select(Item.item_group).distinct() if (r := row).item_group]
            self._add_cat_btn(tr("Barchasi"), True)
            for c in sorted(cats):
                self._add_cat_btn(c)
        finally:
            db.close()

    def _add_cat_btn(self, name, is_all=False):
        btn = QPushButton(name)
        btn.setCheckable(True)
        btn.setChecked(is_all)

        btn.setFixedHeight(40)
        btn.setStyleSheet(self._category_button_style())
        btn.clicked.connect(lambda: self._on_cat_click(btn, name, is_all))
        self.category_layout.addWidget(btn)

    def _on_cat_click(self, btn, cat, is_all):
        for i in range(self.category_layout.count()):
            w = self.category_layout.itemAt(i).widget()
            if isinstance(w, QPushButton):
                w.setChecked(w == btn)
        self.current_category = None if is_all else cat
        self.load_items(self.search_input.text())

    def _calc_grid_columns(self):
        """Mavjud kenglikka qarab ustunlar sonini hisoblash"""
        available = self.items_scroll.viewport().width()
        if available <= 0:
            available = 600
        spacing = self.items_grid.spacing()
        # Kartalar setFixedWidth(180) — kichikroq qiymat olsak, ustunlar
        # viewportga sig'may gorizontal scroll chiqadi.
        card_width = 180
        cols = max(2, (available + spacing) // (card_width + spacing))
        return cols

    def _handle_item_click(self, item, price, currency):
        try:
            p_data = json.loads(item.posawesome_data) if item.posawesome_data else {}
        except (TypeError, ValueError):
            p_data = {}
        try:
            actual_qty = float(p_data.get("actual_qty", 0) or 0)
        except (TypeError, ValueError):
            actual_qty = 0.0
        st_qty = self._get_effective_stock_qty(item.item_code, actual_qty)
        allow_negative = bool(p_data.get("allow_negative_stock", 0))
        is_stock = bool(p_data.get("is_stock_item", 1))

        if is_stock and not allow_negative and st_qty <= 0:
            SoundFeedback.error()
            InfoDialog(self, tr("Xatolik"), f"{item.item_name}: {tr('omborda qolmagan!')}", kind="warning").exec()
            return

        self.item_selected.emit(item.item_code, item.item_name, float(price), currency)
        
    def set_price_list(self, price_list):
        self.current_price_list = price_list
        self.load_items(self.search_input.text())

    def set_last_sync_now(self):
        """Sinxronizatsiya tugaganda haqiqiy vaqtni ko'rsatish."""
        from datetime import datetime
        self.sync_label.setText(f"{tr('Oxirgi sinxron')}: {datetime.now().strftime('%H:%M:%S')}")
        # Yangi tovarlar/barcodelar kelgan bo'lishi mumkin.
        self.invalidate_barcode_cache()

    def set_search_text(self, text: str, trigger: bool = True):
        normalized = str(text or "")
        # Kutayotgan debounce eski matn bilan keyinroq ishga tushmasin.
        self._search_timer.stop()
        self.search_input.blockSignals(True)
        self.search_input.setText(normalized)
        self.search_input.blockSignals(False)
        if trigger:
            self.load_items(normalized)

    def _extract_item_barcodes(self, item: Item) -> list[str]:
        values = []
        if item.barcode:
            values.append(str(item.barcode).strip())
        try:
            payload = json.loads(item.posawesome_data or "{}")
        except Exception:
            payload = {}
        for row in payload.get("item_barcode") or []:
            if isinstance(row, dict) and row.get("barcode"):
                values.append(str(row.get("barcode")).strip())
        for row in payload.get("barcodes") or []:
            if row:
                values.append(str(row).strip())
        deduped = []
        seen = set()
        for value in values:
            if value and value not in seen:
                deduped.append(value)
                seen.add(value)
        return deduped

    def _get_scale_settings(self) -> dict:
        settings = load_config().get("scale_barcode_settings") or {}
        return settings if isinstance(settings, dict) else {}

    def _parse_scale_barcode_local(self, barcode: str) -> dict | None:
        settings = self._get_scale_settings()
        barcode_value = str(barcode or "").strip()
        if not barcode_value:
            return None
        try:
            prefix = str(settings.get("prefix") or "").strip()
            prefix_included = int(settings.get("prefix_included_or_not") or 0)
            prefix_length = int(settings.get("no_of_prefix_characters") or 0) if prefix_included else 0
            item_start = int(settings.get("item_code_starting_digit") or 0)
            item_digits = int(settings.get("item_code_total_digits") or 0)
            weight_start = int(settings.get("weight_starting_digit") or 0)
            weight_digits = int(settings.get("weight_total_digits") or 0)
            weight_decimals = int(settings.get("weight_decimals") or 0)
            price_enabled = int(settings.get("price_included_in_barcode_or_not") or 0)
            price_start = int(settings.get("price_starting_digit") or 0)
            price_digits = int(settings.get("price_total_digit") or 0)
            price_decimals = int(settings.get("price_decimals") or 0)
        except Exception:
            return None

        if prefix and not barcode_value.startswith(prefix):
            return None
        if not (item_start and item_digits):
            return None

        def extract_numeric_segment(start: int, length: int, decimals: int = 0):
            if not (start and length):
                return None
            start_idx = max(start - 1, 0)
            end_idx = start_idx + length
            if len(barcode_value) < end_idx:
                return None
            whole = barcode_value[start_idx:end_idx]
            decimal_part = ""
            if decimals > 0:
                decimal_end = end_idx + decimals
                if len(barcode_value) < decimal_end:
                    return None
                decimal_part = barcode_value[end_idx:decimal_end]
            try:
                return float(f"{whole}.{decimal_part}" if decimal_part else whole)
            except Exception:
                return None

        item_start_idx = max(item_start - 1, 0)
        item_end_idx = item_start_idx + item_digits
        if len(barcode_value) < item_end_idx:
            return None
        item_code = barcode_value[item_start_idx:item_end_idx]
        result = {"barcode": barcode_value, "item_code": item_code}
        qty = extract_numeric_segment(weight_start, weight_digits, weight_decimals)
        if qty is not None:
            result["qty"] = qty
        if price_enabled:
            price = extract_numeric_segment(price_start, price_digits, price_decimals)
            if price is not None:
                result["price"] = price
        if prefix_length:
            result["prefix_length"] = prefix_length
        return result

    def _find_local_item_for_search(self, search: str):
        normalized = str(search or "").strip()
        if not normalized:
            return None, None
        
        scale_data = self._parse_scale_barcode_local(normalized)
        target_code = str(scale_data.get("item_code") if scale_data else normalized).strip()
        
        try:
            db.connect(reuse_if_open=True)
            
            # 1. Global qidiruv (item_code bo'yicha)
            item = Item.select().where(fn.LOWER(Item.item_code) == target_code.lower()).first()
            if item:
                return item, scale_data
            
            # 2. Global qidiruv (barcode bo'yicha)
            item = Item.select().where(fn.LOWER(Item.barcode) == normalized.lower()).first()
            if item:
                return item, scale_data
                
            # 3. JSON barcodelar — oldindan qurilgan xarita orqali
            # (har skanda to'liq jadval skani GUI'ni sekinlatardi)
            code_hit = self._barcode_map().get(normalized.lower())
            if code_hit:
                item = Item.get_or_none(Item.item_code == code_hit)
                if item:
                    return item, scale_data

            return None, scale_data
        finally:
            if not db.is_closed():
                db.close()

    def _barcode_map(self) -> dict:
        if self._barcode_cache is not None:
            return self._barcode_cache
        mapping = {}
        try:
            db.connect(reuse_if_open=True)
            for item in Item.select(Item.item_code, Item.barcode, Item.posawesome_data):
                for b in self._extract_item_barcodes(item):
                    mapping[b.lower()] = item.item_code
        except Exception as e:
            logger.debug("Barcode xarita qurilmadi: %s", e)
        finally:
            if not db.is_closed():
                db.close()
        self._barcode_cache = mapping
        return mapping

    def invalidate_barcode_cache(self):
        self._barcode_cache = None

    def _resolve_online_barcode(self, search: str) -> dict | None:
        if not self.api or not self.api.is_configured():
            return None
        try:
            success, response = self.api.call_method(
                "posawesome.posawesome.api.items.get_items_from_barcode",
                {
                    "selling_price_list": self.current_price_list or load_config().get("price_list") or "Standard Selling",
                    "currency": load_config().get("currency") or "UZS",
                    "barcode": search,
                },
            )
            if not success or not isinstance(response, dict) or not response.get("item_code"):
                return None
            return {
                "item_code": response.get("item_code"),
                "item_name": response.get("item_name") or response.get("item_code"),
                "rate": float(response.get("price_list_rate") or response.get("rate") or 0),
                "currency": response.get("currency") or load_config().get("currency") or "UZS",
                "qty": response.get("scale_qty") or 1,
                "uom": response.get("uom"),
                "manual_rate": response.get("scale_price") is not None,
            }
        except Exception as e:
            logger.debug("Barcode server resolve xatosi: %s", e)
            return None

    def submit_search(self, search: str, add_to_cart: bool = True):
        search = str(search or "").strip()
        if not search:
            return

        if add_to_cart:
            item, scale_data = self._find_local_item_for_search(search)
            if item:
                price, currency = self._resolve_display_price(item)
                payload = {
                    "item_code": item.item_code,
                    "item_name": item.item_name,
                    "rate": scale_data.get("price") if scale_data and scale_data.get("price") is not None else price,
                    "currency": currency,
                    "qty": scale_data.get("qty") if scale_data and scale_data.get("qty") is not None else 1,
                    "manual_rate": bool(scale_data and scale_data.get("price") is not None),
                }
                # MUHIM: emit'dan oldin tozalaymiz — chunki signal sinxron
                # ketma-ketlikda cart_updated -> set_reserved_quantities ->
                # load_items(search_input.text()) zanjirini ishga tushiradi.
                self.set_search_text("", trigger=False)
                self.search_resolved.emit(payload)
                return

            # Lokal bazada topilmadi — serverdan online so'raymiz, lekin GUI
            # muzlamasligi uchun background thread'da.
            self._start_online_barcode_lookup(search)
            return

        # Filter only mode (add_to_cart=False)
        self.load_items(search)
        if self.items_table.rowCount() == 0 and self.items_grid.count() == 0:
            SoundFeedback.error()

    def _start_online_barcode_lookup(self, search: str):
        """Resolve a barcode via the server without blocking the GUI."""
        existing = getattr(self, "_online_lookup_worker", None)
        if existing is not None and existing.isRunning():
            return  # avvalgi so'rov hali tugamagan

        worker = _OnlineBarcodeLookupWorker(
            self.api,
            barcode=search,
            price_list=self.current_price_list or load_config().get("price_list") or "Standard Selling",
            currency=load_config().get("currency") or "UZS",
        )
        self._online_lookup_worker = worker
        worker.finished_signal.connect(self._on_online_barcode_resolved)
        worker.start()

    def _on_online_barcode_resolved(self, search: str, payload: dict | None):
        if payload:
            self.set_search_text("", trigger=False)
            self.search_resolved.emit(payload)
            return
        # Topilmadi — tovushli signal.  MUHIM: search box bo'sh bo'lsa,
        # ro'yxatni ko'rinmas matn bilan filtrlab qo'ymaymiz (kassir sababini
        # ko'rmay bo'sh grid bilan qolardi).
        SoundFeedback.error()
        if self.search_input.text().strip() == search.strip():
            self.load_items(search)


    def open_settings(self):
        from ui.components.dialogs import SettingsDialog
        dlg = SettingsDialog(self, tr("Jadvallar Sozlanmalari"), self.settings)
        if dlg.exec():
            res = dlg.get_results()
            for k in res:
                self.settings[k]["value"] = res[k]
            # Reload to apply filters
            self.load_items(self.search_input.text())

    def _item_matches_search(self, item: Item, search: str) -> bool:
        normalized = str(search or "").strip().lower()
        if not normalized:
            return True

        parts = [part for part in normalized.split() if part]
        try:
            payload = json.loads(item.posawesome_data or "{}")
        except Exception:
            payload = {}

        values = [
            str(item.item_code or "").lower(),
            str(item.item_name or "").lower(),
            str(item.barcode or "").lower(),
            str(item.description or "").lower(),
        ]
        for row in payload.get("item_barcode") or []:
            if isinstance(row, dict) and row.get("barcode"):
                values.append(str(row.get("barcode")).lower())
        for row in payload.get("barcodes") or []:
            if row:
                values.append(str(row).lower())

        return all(any(part in value for value in values) for part in parts)

    def load_items(self, search=""):
        # Gridni tozalash
        while self.items_grid.count():
            child = self.items_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        # List (Table) ni tozalash
        if hasattr(self, 'items_table'):
            self.items_table.setRowCount(0)

        # Grid sozlamalarini qat'iylashtirish
        self.items_grid.setSpacing(15)
        
        columns = self._calc_grid_columns()
        self._last_columns = columns

        from PyQt6.QtWidgets import QTableWidgetItem
        from PyQt6.QtCore import Qt

        try:
            db.connect(reuse_if_open=True)
            query = Item.select()

            # Agar qidiruv bo'lsa - hamma kategoriyadan qidiramiz (Global search)
            # Agar qidiruv bo'masa - tanlangan kategoriya bo'yicha filtrlaymiz
            if self.current_category and not search:
                query = query.where(Item.item_group == self.current_category)

            # MUHIM: limitni DB darajasida emas, filtrlardan KEYIN qo'llaymiz.
            # Aks holda hide_zero_stock yoqilganda birinchi ITEM_LOAD_LIMIT
            # qatorning hammasi 0-qoldiqli bo'lsa, ro'yxat bo'sh ko'rinardi.
            rendered = 0

            # Narxlarni BITTA so'rov bilan oldindan olamiz — har karta uchun
            # alohida query GUI'ni sekinlatardi.
            price_map = {}
            for pr in ItemPrice.select().where(ItemPrice.price_list == self.current_price_list):
                price_map[pr.item_code] = (float(pr.price_list_rate or 0), pr.currency or "UZS")

            row, col = 0, 0
            table_row = 0

            for item in query:
                if search and not self._item_matches_search(item, search):
                    continue
                p, cur = price_map.get(
                    item.item_code, (float(item.standard_rate or 0), "UZS")
                )
                try:
                    raw_qty = float(
                        json.loads(item.posawesome_data or "{}").get("actual_qty", 0) or 0
                    )
                except (TypeError, ValueError):
                    raw_qty = 0.0
                st_qty = self._get_effective_stock_qty(item.item_code, raw_qty)
                uom_val = item.uom or item.stock_uom or "Nos"

                # Apply Settings Filters
                if self.settings["hide_zero_stock"]["value"] and st_qty <= 0:
                    continue
                if self.settings["hide_zero_rate"]["value"] and p <= 0:
                    continue

                # Decimals sozlamasi FAQAT ko'rinishga ta'sir qiladi.
                # Narx (p) o'z holicha qoladi — aks holda kesilgan narx
                # savatga tushib, mijozdan kam pul olinardi.
                display_qty = int(st_qty) if self.settings["hide_decimals"]["value"] else st_qty

                # 1. Update Grid Card
                card = ItemButton(item.item_code, item.item_name, p, cur, item.image, self.api, stock_qty=display_qty, uom=uom_val)
                card.clicked.connect(
                    lambda i=item, pr=p, c=cur: self._handle_item_click(i, float(pr), c)
                )
                self.items_grid.addWidget(card, row, col)
                col += 1
                if col >= columns:
                    col = 0
                    row += 1

                # 2. Update Table (List View) — same iteration
                if hasattr(self, 'items_table'):
                    self.items_table.insertRow(table_row)

                    item_name_widget = QTableWidgetItem(item.item_name)
                    item_name_widget.setData(Qt.ItemDataRole.UserRole, item.item_code)
                    item_name_widget.setData(Qt.ItemDataRole.UserRole + 1, float(p))
                    item_name_widget.setData(Qt.ItemDataRole.UserRole + 2, cur)

                    qty_widget = QTableWidgetItem(f"{display_qty:g}")

                    price_str = f"{p:,.0f}".replace(",", " ") + f" {cur}"
                    rate_widget = QTableWidgetItem(price_str)

                    uom_widget = QTableWidgetItem(uom_val)

                    self.items_table.setItem(table_row, 0, item_name_widget)
                    self.items_table.setItem(table_row, 1, qty_widget)
                    self.items_table.setItem(table_row, 2, rate_widget)
                    self.items_table.setItem(table_row, 3, uom_widget)
                    table_row += 1

                rendered += 1
                if rendered >= ITEM_LOAD_LIMIT:
                    break

        finally:
            db.close()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start()

    def _on_resize_done(self):
        new_cols = self._calc_grid_columns()
        if new_cols != self._last_columns:
            self.load_items(self.search_input.text())

    def filter_items(self, _t):
        self._search_timer.start()

    def _toggle_search_keyboard(self):
        """Qidiruv maydoni uchun ekran klaviaturasini ochadi/yopadi.

        Mahsulot qidiruvida avtomatik klaviatura o'chirilgan (skaner uchun),
        shu sababli bu tugma orqali qo'lda ochiladi. Yozilgan harf darhol
        search_input ga tushib, ro'yxatni filtrlaydi.
        """
        kb = self._search_kb
        if kb is not None:
            try:
                if kb.isVisible():
                    kb.hide()
                    return
            except RuntimeError:
                self._search_kb = None
                kb = None
        if kb is None:
            kb = TouchKeyboard(
                self.window(),
                initial_text=self.search_input.text(),
                title=tr("Mahsulot qidirish"),
                is_numeric=False,
            )
            kb.text_changed.connect(self.search_input.setText)
            self._search_kb = kb
        else:
            kb.set_target(self.search_input.text(), tr("Mahsulot qidirish"))
        kb.show()
        kb.raise_()

    def eventFilter(self, obj, event):
        """Search klaviaturasi tashqariga bosilganda avtomatik yopiladi."""
        try:
            from PyQt6.QtCore import QEvent
            if event.type() == QEvent.Type.MouseButtonPress:
                self._maybe_close_search_kb(obj)
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _maybe_close_search_kb(self, obj):
        kb = getattr(self, "_search_kb", None)
        if kb is None:
            return
        try:
            if not kb.isVisible():
                return
            # Klaviaturaning o'zini bossa — yopmaymiz (yozish davom etadi).
            if obj is kb or kb.isAncestorOf(obj):
                return
        except RuntimeError:
            self._search_kb = None
            return
        # Qidiruv maydoni yoki ⌨ tugmasini bossa — yopmaymiz.
        si = getattr(self, "search_input", None)
        btn = getattr(self, "search_kb_btn", None)
        if obj is si or obj is btn:
            return
        try:
            if si is not None and si.isAncestorOf(obj):
                return
        except Exception:
            pass
        kb.hide()
