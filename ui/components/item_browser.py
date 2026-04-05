from ui.components.dialogs import InfoDialog
from ui.component_styles import get_component_styles
from ui.theme_manager import ThemeManager
import json
from PyQt6.QtWidgets import QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
import requests
from PyQt6.QtWidgets import (
    QScroller,
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QScrollArea, QGridLayout, QLabel, QSizePolicy, QFrame,
)
from PyQt6.QtCore import pyqtSignal, Qt, QSize, QThread, QObject, QTimer
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPainterPath
from database.models import Item, ItemPrice, db
from core.api import FrappeAPI
from core.logger import get_logger
from core.constants import ITEM_LOAD_LIMIT, IMAGE_TIMEOUT
logger = get_logger(__name__)


class ImageLoader(QThread):
    """Rasmlarni fonda yuklash uchun maxsus thread"""
    image_loaded = pyqtSignal(QPixmap)

    def __init__(self, url, api):
        super().__init__()
        self.url = url
        self.api = api

    def run(self):
        try:
            full_url = self.url if self.url.startswith("http") else f"{self.api.url}{self.url}"
            response = self.api.session.get(full_url, timeout=IMAGE_TIMEOUT)
            if response.status_code == 200:
                image = QImage()
                if image.loadFromData(response.content):
                    pixmap = QPixmap.fromImage(image)
                    self.image_loaded.emit(pixmap)
        except Exception:
            pass


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
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._apply_normal_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Rasm qismi (karta yuqori qismi) ---
        self.image_container = QWidget()
        self.image_container.setMinimumHeight(100)
        self.image_container.setMaximumHeight(150)
        self.image_container.setStyleSheet(f"""
            background: {self.colors['bg_tertiary']};
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
        """)

        img_inner = QVBoxLayout(self.image_container)
        img_inner.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.image_label = QLabel()
        self.image_label.setMinimumSize(70, 70)
        self.image_label.setMaximumSize(100, 100)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet(f"""
            background: {self.colors['bg_secondary']};
            border-radius: 10px;
            color: {self.colors['text_tertiary']};
            font-size: 28px;
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
            border-bottom-left-radius: 14px;
            border-bottom-right-radius: 14px;
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
        stock_label = QLabel(f"{stock_qty:g} {uom}")
        stock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stock_label.setStyleSheet(
            f"color: {self.colors['text_tertiary']}; font-size: 11px; font-weight: bold; background: transparent; border: none;"
        )
        
        info_layout.addWidget(name_label)
        info_layout.addWidget(price_label)
        info_layout.addWidget(stock_label)
        layout.addWidget(info_container)



    def _apply_normal_style(self):
        self.setStyleSheet(f"""
            QFrame {{
                background: {self.colors['bg_secondary']};
                border: 1px solid {self.colors['border']};
                border-radius: 8px;
            }}
        """)

    def _apply_hover_style(self):
        self.setStyleSheet(f"""
            QFrame {{
                background: {self.colors['bg_tertiary']};
                border: 1px solid {self.colors['accent']};
                border-radius: 8px;
            }}
        """)

    def _apply_pressed_style(self):
        self.setStyleSheet(f"""
            QFrame {{
                background: {self.colors['selection_bg']};
                border: 1px solid {self.colors['accent_hover']};
                border-radius: 8px;
            }}
        """)

    def _on_loader_finished(self):
        """ImageLoader tugaganda resurslarni tozalash"""
        if self.loader:
            self.loader.deleteLater()
            self.loader = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._apply_pressed_style()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._apply_normal_style()
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class ItemBrowser(QWidget):
    item_selected = pyqtSignal(str, str, float, str)
    settings_clicked = pyqtSignal()

    def __init__(self, api: FrappeAPI):
        super().__init__()
        self.api = api
        self.reserved_quantities = {}
        self.settings = {
            "hide_zero_stock": {"label": "0 qoldiqchilarni yashirish", "value": False},
            "hide_zero_rate": {"label": "Nol narxlilarni yashirish", "value": False},
            "hide_decimals": {"label": "O'nli kasrlarni yashirish", "value": False},
        }
        self.current_price_list = "Standard Selling"

        self.current_category = None
        self._last_columns = 0
        self._caps = False
        self._letter_buttons = []
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(150)
        self._resize_timer.timeout.connect(self._on_resize_done)
        self.init_ui()
        self.load_categories()
        self.load_items()

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
        self.search_input.setPlaceholderText("🔍  Search Items...")
        self.search_input.setMinimumHeight(38)
        self.search_input.setMaximumHeight(52)
        self.search_input.setProperty("disable_virtual_keyboard", True)
        self.search_input.setStyleSheet(styles["item_search"])
        self.search_input.textChanged.connect(self.filter_items)
        main_layout.addWidget(self.search_input)
        
        # Top Settings Header (optional visible mostly in List View context in UI, but we can show always)
        header_row = QHBoxLayout()
        self.settings_btn = QPushButton("SETTINGS")
        self.settings_btn.setStyleSheet(
            f"color: {colors['accent']}; font-weight: bold; font-size: 11px; background: transparent; border: none; text-align: left;"
        )
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.clicked.connect(self.open_settings)
        self.sync_label = QLabel("Last sync: 00:00:00 PM")
        self.sync_label.setStyleSheet(f"color: {colors['text_tertiary']}; font-size: 11px;")
        self.sync_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reload_btn = QPushButton("RELOAD ITEMS")
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
        self.items_table.setHorizontalHeaderLabels(["NAME", "QTY", "RATE", "UOM"])
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
        
        self.btn_list_view = QPushButton("LIST")
        self.btn_list_view.setMinimumHeight(34)
        self.btn_list_view.setMaximumHeight(44)
        self.btn_list_view.clicked.connect(lambda: self.set_view_mode("list"))
        
        self.btn_card_view = QPushButton("CARD")
        self.btn_card_view.setMinimumHeight(34)
        self.btn_card_view.setMaximumHeight(44)
        self.btn_card_view.clicked.connect(lambda: self.set_view_mode("card"))
        
        self._update_toggle_styles()
        
        self.offers_label = QLabel("0 OFFERS")
        self.offers_label.setStyleSheet(f"color: {colors['warning']}; font-weight: bold; font-size: 11px;")
        self.coupons_label = QLabel("0 COUPONS")
        self.coupons_label.setStyleSheet(f"color: {colors['accent']}; font-weight: bold; font-size: 11px;")
        
        bottom_bar.addWidget(self.btn_list_view)
        bottom_bar.addWidget(self.btn_card_view)
        bottom_bar.addStretch()
        bottom_bar.addWidget(self.offers_label)
        bottom_bar.addSpacing(30)
        bottom_bar.addWidget(self.coupons_label)
        bottom_bar.addSpacing(10)

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
        if hasattr(self, "offers_label"):
            self.offers_label.setStyleSheet(f"color: {colors['warning']}; font-weight: bold; font-size: 11px;")
        if hasattr(self, "coupons_label"):
            self.coupons_label.setStyleSheet(f"color: {colors['accent']}; font-weight: bold; font-size: 11px;")

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
            p_data = json.loads(it.posawesome_data) if it.posawesome_data else {}
            st_qty = self._get_effective_stock_qty(code, float(p_data.get("actual_qty", 0)))
            allow_negative = bool(p_data.get("allow_negative_stock", 0))
            is_stock = bool(p_data.get("is_stock_item", 1))
            if is_stock and not allow_negative and st_qty <= 0:
                InfoDialog(self, "Xatolik", f"{name} omborda qolmagan!", kind="warning").exec()
                return
        self.item_selected.emit(code, name, rate, currency)

    def set_reserved_quantities(self, reservations: dict | None):
        normalized = {}
        for code, qty in (reservations or {}).items():
            key = str(code).strip()
            if not key:
                continue
            try:
                numeric_qty = int(float(qty))
            except (TypeError, ValueError):
                continue
            if numeric_qty > 0:
                normalized[key] = numeric_qty

        if normalized == self.reserved_quantities:
            return

        self.reserved_quantities = normalized
        self.load_items(self.search_input.text())

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

        self.kb_display = QLabel("Qidiruv...")
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
            self._add_cat_btn("Barchasi", True)
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
        min_card_width = 170
        cols = max(2, (available + spacing) // (min_card_width + spacing))
        return cols

    def _handle_item_click(self, item, price, currency):
        p_data = json.loads(item.posawesome_data) if item.posawesome_data else {}
        st_qty = self._get_effective_stock_qty(item.item_code, float(p_data.get("actual_qty", 0)))
        allow_negative = bool(p_data.get("allow_negative_stock", 0))
        is_stock = bool(p_data.get("is_stock_item", 1))
        
        if is_stock and not allow_negative and st_qty <= 0:
            InfoDialog(self, "Xatolik", f"{item.item_name} omborda qolmagan (0 qt)!", kind="warning").exec()
            return
            
        self.item_selected.emit(item.item_code, item.item_name, float(price), currency)
        
    def set_price_list(self, price_list):
        self.current_price_list = price_list
        self.load_items(self.search_input.text())


    def open_settings(self):
        from ui.components.dialogs import SettingsDialog
        dlg = SettingsDialog(self, "Jadvallar Sozlanmalari", self.settings)
        if dlg.exec():
            res = dlg.get_results()
            for k in res:
                self.settings[k]["value"] = res[k]
            # Reload to apply filters
            self.load_items(self.search_input.text())
    def load_items(self, search=""):
        # Gridni tozalash
        while self.items_grid.count():
            child = self.items_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        # List (Table) ni tozalash
        if hasattr(self, 'items_table'):
            self.items_table.setRowCount(0)

        columns = self._calc_grid_columns()
        self._last_columns = columns

        from PyQt6.QtWidgets import QTableWidgetItem
        from PyQt6.QtCore import Qt

        try:
            db.connect(reuse_if_open=True)
            query = Item.select()
            if self.current_category:
                query = query.where(Item.item_group == self.current_category)
            if search:
                query = query.where(Item.item_name.contains(search) | Item.item_code.contains(search))

            row, col = 0, 0
            table_row = 0
            
            for item in query.limit(ITEM_LOAD_LIMIT):
                p, cur = self._resolve_display_price(item)
                raw_qty = float(json.loads(item.posawesome_data).get("actual_qty", 0)) if item.posawesome_data else 0.0
                st_qty = self._get_effective_stock_qty(item.item_code, raw_qty)
                uom_val = item.uom or item.stock_uom or "Nos"

                # Apply Settings Filters
                if self.settings["hide_zero_stock"]["value"] and st_qty <= 0:
                    continue
                if self.settings["hide_zero_rate"]["value"] and p <= 0:
                    continue
                
                # Apply Decimals Setting
                if self.settings["hide_decimals"]["value"]:
                    st_qty = int(st_qty)
                    p = int(p)

                # 1. Update Grid Card
                card = ItemButton(item.item_code, item.item_name, p, cur, item.image, self.api, stock_qty=st_qty, uom=uom_val)
                card.clicked.connect(
                    lambda i=item, pr=p, c=cur: self._handle_item_click(i, float(pr), c)
                )
                self.items_grid.addWidget(card, row, col)
                col += 1
                if col >= columns:
                    col = 0
                    row += 1
                    
                # 2. Update Table (List View)
                if hasattr(self, 'items_table'):
                    self.items_table.insertRow(table_row)
                    
                    item_name_widget = QTableWidgetItem(item.item_name)
                    item_name_widget.setData(Qt.ItemDataRole.UserRole, item.item_code)
                    item_name_widget.setData(Qt.ItemDataRole.UserRole + 1, float(p))
                    item_name_widget.setData(Qt.ItemDataRole.UserRole + 2, cur)
                    
                    qty_widget = QTableWidgetItem(f"{st_qty:g}")
                    
                    price_str = f"{p:,.0f}".replace(",", " ") + f" {cur}"
                    rate_widget = QTableWidgetItem(price_str)
                    
                    uom_widget = QTableWidgetItem(uom_val)
                    
                    self.items_table.setItem(table_row, 0, item_name_widget)
                    self.items_table.setItem(table_row, 1, qty_widget)
                    self.items_table.setItem(table_row, 2, rate_widget)
                    self.items_table.setItem(table_row, 3, uom_widget)
                    table_row += 1

        finally:
            db.close()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start()

    def _on_resize_done(self):
        new_cols = self._calc_grid_columns()
        if new_cols != self._last_columns:
            self.load_items(self.search_input.text())

    def filter_items(self, t):
        self.load_items(t)
