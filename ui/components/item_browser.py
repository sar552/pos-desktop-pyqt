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
from ui.components.keyboard import TouchKeyboard

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
        self.api = api
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
        self.image_container.setStyleSheet("""
            background: #222222;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
        """)

        img_inner = QVBoxLayout(self.image_container)
        img_inner.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.image_label = QLabel()
        self.image_label.setMinimumSize(70, 70)
        self.image_label.setMaximumSize(100, 100)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("""
            background: rgba(0,0,0,0.3);
            border-radius: 10px;
            color: #94a3b8;
            font-size: 28px;
        """)
        self.image_label.setText("📦")

        if image_url and api:
            self.loader = ImageLoader(image_url, api)
            self.loader.image_loaded.connect(self._set_pixmap)
            self.loader.start()

        img_inner.addWidget(self.image_label)
        layout.addWidget(self.image_container)

        # --- Ma'lumot qismi (karta pastki qismi) ---
        info_container = QWidget()
        info_container.setStyleSheet("""
            background: #1e1e1e;
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
        name_label.setStyleSheet("""
            font-size: 13px;
            font-weight: 700;
            color: #ffffff;
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
        price_label.setStyleSheet("""
            font-size: 13px;
            font-weight: 800;
            color: white;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #3b82f6, stop:1 #6366f1);
            border-radius: 8px;
            padding: 4px 8px;
            border: none;
        """)
        price_label.setMinimumHeight(24)
        price_label.setMaximumHeight(32)

        
        # Stock Info
        stock_label = QLabel(f"{stock_qty:g} {uom}")
        stock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stock_label.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        
        info_layout.addWidget(name_label)
        info_layout.addWidget(price_label)
        info_layout.addWidget(stock_label)
        layout.addWidget(info_container)



    def _apply_normal_style(self):
        self.setStyleSheet("""
            QFrame {
                background: #1e1e1e;
                border: 1px solid #333;
                border-radius: 8px;
            }
        """)

    def _apply_hover_style(self):
        self.setStyleSheet("""
            QFrame {
                background: #2a2a2a;
                border: 1px solid #3b82f6;
                border-radius: 8px;
            }
        """)

    def _apply_pressed_style(self):
        self.setStyleSheet("""
            QFrame {
                background: #333333;
                border: 1px solid #2563eb;
                border-radius: 8px;
            }
        """)

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

    def __init__(self, api: FrappeAPI):
        super().__init__()
        self.api = api
        self.current_category = None
        self.kb = None
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
        self.setStyleSheet("background: #111111;")
        self.view_mode = "card"

        # Top row: Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍  Search Items...")
        self.search_input.setMinimumHeight(38)
        self.search_input.setMaximumHeight(52)
        self.search_input.setStyleSheet("""
            QLineEdit {
                padding: 10px 16px;
                font-size: 14px;
                border: 1px solid #333;
                border-radius: 4px;
                background: #1e1e1e;
                color: white;
            }
            QLineEdit:focus { border: 1px solid #3b82f6; }
        """)
        self.search_input.textChanged.connect(self.filter_items)
        self.search_input.mousePressEvent = self._open_search_keyboard
        self.search_input.textChanged.connect(lambda t: self.kb_display.setText(t if t else "Qidiruv..."))
        main_layout.addWidget(self.search_input)
        
        # Top Settings Header (optional visible mostly in List View context in UI, but we can show always)
        header_row = QHBoxLayout()
        s_lbl = QPushButton("SETTINGS")
        s_lbl.setStyleSheet("color: #0ea5e9; font-weight: bold; font-size: 11px; background: transparent; border: none; text-align: left;")
        s_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        sync_lbl = QLabel("Last sync: 00:00:00 PM")
        sync_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        sync_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        r_lbl = QPushButton("RELOAD ITEMS")
        r_lbl.setStyleSheet("color: #0ea5e9; font-weight: bold; font-size: 11px; background: transparent; border: none; text-align: right;")
        r_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        r_lbl.clicked.connect(lambda: self.load_items(self.search_input.text()))
        
        
        header_row.addWidget(s_lbl)
        header_row.addWidget(sync_lbl, 1)
        header_row.addWidget(r_lbl)
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
        self.items_table.setShowGrid(False)
        self.items_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.items_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.items_table.setStyleSheet("""
            QTableWidget { background: #1e1e1e; color: #ffffff; border: 1px solid #333; border-radius: 6px; font-size: 13px; }
            QHeaderView::section { background-color: #2a2a2a; color: #60a5fa; font-weight: 700; font-size: 11px; border: none; border-bottom: 2px solid #444; padding: 10px; }
            QTableWidget::item { border-bottom: 1px solid #333; padding: 10px; color: white; font-weight: bold; }
            QTableWidget::item:selected { background-color: #334155; }
        """)
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
        
        l_offers = QLabel("0 OFFERS")
        l_offers.setStyleSheet("color: #f59e0b; font-weight: bold; font-size: 11px;")
        l_coupons = QLabel("0 COUPONS")
        l_coupons.setStyleSheet("color: #0ea5e9; font-weight: bold; font-size: 11px;")
        
        bottom_bar.addWidget(self.btn_list_view)
        bottom_bar.addWidget(self.btn_card_view)
        bottom_bar.addStretch()
        bottom_bar.addWidget(l_offers)
        bottom_bar.addSpacing(30)
        bottom_bar.addWidget(l_coupons)
        bottom_bar.addSpacing(10)

        main_layout.addLayout(bottom_bar)

        # --- Inline Keyboard Panel (pastda ko'rinmas) ---
        self.keyboard_panel = self._build_keyboard_panel()
        self.keyboard_panel.setVisible(False)
        main_layout.addWidget(self.keyboard_panel)

    def set_view_mode(self, mode):
        self.view_mode = mode
        if mode == "list":
            self.items_stack.setCurrentIndex(1)
        else:
            self.items_stack.setCurrentIndex(0)
        self._update_toggle_styles()

    def _update_toggle_styles(self):
        active_style = """
            QPushButton {
                background: #0ea5e9; color: white; font-weight: bold; font-size: 11px;
                border-radius: 4px; padding: 0 15px; border: none;
            }
        """
        inactive_style = """
            QPushButton {
                background: #2a2a2a; color: white; font-weight: bold; font-size: 11px;
                border-radius: 4px; padding: 0 15px; border: 1px solid #333;
            }
            QPushButton:hover { background: #333; }
        """
        if self.view_mode == "list":
            self.btn_list_view.setStyleSheet(active_style)
            self.btn_card_view.setStyleSheet(inactive_style)
        else:
            self.btn_list_view.setStyleSheet(inactive_style)
            self.btn_card_view.setStyleSheet(active_style)

    def _on_table_item_clicked(self, item):
        row = item.row()
        item_code = self.items_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        # Fetch details to emit
        code = item_code
        name = self.items_table.item(row, 0).text()
        rate_text = self.items_table.item(row, 2).text().replace(" UZS", "").replace(" ", "")
        try:
            rate = float(rate_text)
        except:
            rate = 0.0
            
        self.item_selected.emit(code, name, rate, "UZS")

    def _build_keyboard_panel(self):
        """Pastdan chiqadigan inline klaviatura paneli"""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background: #222222;
                border-top: 2px solid #e2e8f0;
                border-radius: 0px;
            }
        """)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(10, 8, 10, 10)
        panel_layout.setSpacing(6)

        # Yuqori qator: yozilgan matn + yopish tugmasi
        top_row = QHBoxLayout()

        self.kb_display = QLabel("Qidiruv...")
        self.kb_display.setStyleSheet("""
            font-size: 16px;
            font-weight: 600;
            color: #ffffff;
            background: #1e1e1e;
            border: 1.5px solid #3b82f6;
            border-radius: 8px;
            padding: 6px 12px;
        """)
        self.kb_display.setFixedHeight(40)

        close_btn = QPushButton("✕")
        close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_btn.setFixedSize(40, 40)
        close_btn.setStyleSheet("""
            QPushButton {
                background: #ef4444;
                color: white;
                font-weight: bold;
                font-size: 16px;
                border-radius: 8px;
                border: none;
            }
            QPushButton:hover { background: #dc2626; }
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
        label = key.strip()
        if label == 'SPACE': label = '␣'
        elif label == 'CLR': label = 'TOZALASH'
        elif label == 'CAPS': label = '⇧ Aa'

        btn = QPushButton(label)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setFixedHeight(44)

        if key.strip() == '⌫':
            style = "background:#fee2e2; color:#ef4444; font-size:18px; font-weight:bold;"
        elif key.strip() == 'CLR':
            style = "background:#fff7ed; color:#ea580c; font-size:11px; font-weight:bold;"
        elif key.strip() == 'CAPS':
            style = "background:#e0e7ff; color:#4338ca; font-size:13px; font-weight:bold;"
        elif 'SPACE' in key:
            style = "background:#eff6ff; color:#3b82f6; font-size:14px; font-weight:bold;"
            btn.setMinimumWidth(120)
        elif key.strip().isdigit():
            style = "background:#e0e7ff; color:#3730a3; font-size:16px; font-weight:bold;"
        else:
            style = "background:white; color:#1e293b; font-size:15px; font-weight:600;"

        btn.setStyleSheet(f"""
            QPushButton {{
                {style}
                border: 1px solid #333;
                border-radius: 7px;
            }}
            QPushButton:pressed {{ background: #dbeafe; }}
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
        btn.setStyleSheet("""
            QPushButton {
                font-size: 13px;
                font-weight: 600;
                text-align: center;
                padding: 0 16px;
                border-radius: 4px;
                background: #1e1e1e;
                color: #a0a0a0;
                border: 1px solid #3b82f6;
            }
            QPushButton:checked {
                background: #3b82f6;
                color: white;
                border: 1px solid #3b82f6;
            }
            QPushButton:hover:!checked {
                background: #222222;
                color: #ffffff;
            }
        """)
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
                price_rec = ItemPrice.get_or_none(ItemPrice.item_code == item.item_code)
                p = price_rec.price_list_rate if price_rec else 0
                cur = price_rec.currency if price_rec else "UZS"
                st_qty = float(json.loads(item.posawesome_data).get("actual_qty", 0)) if item.posawesome_data else 0.0
                uom_val = item.uom or item.stock_uom or "Nos"

                # 1. Update Grid Card
                card = ItemButton(item.item_code, item.item_name, p, cur, item.image, self.api, stock_qty=st_qty, uom=uom_val)
                card.clicked.connect(
                    lambda i=item, pr=p, c=cur: self.item_selected.emit(i.item_code, i.item_name, float(pr), c)
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

