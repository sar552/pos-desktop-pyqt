import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QLabel, QHBoxLayout,
    QComboBox, QLineEdit, QGroupBox, QFrame,
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QDoubleValidator
from database.models import Customer, PosProfile, db
from core.logger import get_logger
from core.constants import TICKET_ORDER_TYPES, ORDER_TYPES
from core.config import load_config
from core.api import FrappeAPI
from ui.components.keyboard import TouchKeyboard
from ui.components.dialogs import InfoDialog
import json

logger = get_logger(__name__)


class QtyLabel(QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        self.clicked.emit()


class CartWidget(QWidget):
    checkout_requested = pyqtSignal(dict)
    price_list_changed = pyqtSignal(str)
    cart_updated = pyqtSignal(dict)

    def __init__(self, api: FrappeAPI | None = None):
        super().__init__()
        self.api = api
        self.items = {}
        self._all_customers = []
        self._filtered_customers = []
        self._customer_ui_updating = False
        self._customer_info_cache = {}
        self._item_meta_cache = {}
        self._is_repricing = False
        self._current_customer_info = {}
        self._current_profile_data = {}
        self.col_settings = {
            "show_qty": {"label": "QTY (Miqdor) ustunini ko'rsatish", "value": True},
            "show_rate": {"label": "RATE (Narx) ustunini ko'rsatish", "value": True},
            "show_amount": {"label": "AMOUNT (Summa) ustunini ko'rsatish", "value": True},
        }
        self.total_amount = 0.0
        self.gross_total_amount = 0.0
        self.net_total_amount = 0.0
        self.item_discount_total = 0.0
        self.invoice_discount_amount = 0.0
        self.invoice_discount_percentage = 0.0
        self.apply_discount_on = "Grand Total"
        self.current_order_type = ORDER_TYPES[0]
        self.order_type_buttons = {}
        self._numpad_mode = "ticket"   # "ticket" | "qty"
        self._active_qty_item = None
        self.init_ui()
        self.load_customers()
        self.load_price_lists()

    # ─────────────────────────────────────────
    #  UI
    # ─────────────────────────────────────────
    def init_ui(self):
        self.setLayout(QVBoxLayout())
        main_layout = self.layout()
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        self.setStyleSheet("background-color: #111111; color: white;")

        # --- Top Section ---
        top_bar = QHBoxLayout()
        
        # Customer Search
        customer_vbox = QVBoxLayout()
        customer_vbox.setSpacing(2)
        cust_label = QLabel("Customer search")
        cust_label.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        
        self.customer_combo = QComboBox()
        self.customer_combo.setEditable(True)
        self.customer_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.customer_combo.setMaxVisibleItems(12)
        self.customer_combo.setFixedHeight(40)
        self.customer_combo.setStyleSheet("""
            QComboBox { background: #1e1e1e; color: white; border: 1px solid #333; border-radius: 4px; padding: 5px; }
            QComboBox QAbstractItemView { background: #1e1e1e; color: white; }
        """)
        self.customer_combo.lineEdit().setPlaceholderText("Guest Customer")
        self.customer_combo.lineEdit().textEdited.connect(self._on_customer_search_edited)
        self.customer_combo.lineEdit().returnPressed.connect(self._commit_customer_search)
        self.customer_combo.activated.connect(self._on_customer_selected)
        customer_row = QHBoxLayout()
        customer_row.setSpacing(6)
        customer_row.addWidget(self.customer_combo, 1)

        self.customer_clear_btn = QPushButton("✕")
        self.customer_clear_btn.setFixedSize(36, 36)
        self.customer_clear_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.customer_clear_btn.setToolTip("Customer tanlovini tozalash")
        self.customer_clear_btn.setStyleSheet("""
            QPushButton {
                background: #2a2a2a; color: #cbd5e1; border: 1px solid #444;
                border-radius: 6px; font-size: 14px; font-weight: 700;
            }
            QPushButton:hover { background: #334155; color: white; }
        """)
        self.customer_clear_btn.clicked.connect(self._clear_customer_selection)
        customer_row.addWidget(self.customer_clear_btn)
        customer_vbox.addWidget(cust_label)
        customer_vbox.addLayout(customer_row)
        
        # Customer Group
        cg_vbox = QVBoxLayout()
        cg_vbox.setSpacing(2)
        cg_label = QLabel("Customer Group")
        cg_label.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        self.cg_mock = QComboBox()
        self.cg_mock.setFixedHeight(40)
        self.cg_mock.setStyleSheet("background: #1e1e1e; color: white; border: 1px solid #333; border-radius: 4px; padding: 5px;")
        self.cg_mock.currentIndexChanged.connect(self._on_customer_group_changed)
        cg_vbox.addWidget(cg_label)
        cg_vbox.addWidget(self.cg_mock)
        
        top_bar.addLayout(customer_vbox, 3)
        top_bar.addLayout(cg_vbox, 1)
        
        main_layout.addLayout(top_bar)

        # --- Search & Price List ---
        search_bar = QHBoxLayout()
        self.search_item_input = QLineEdit()
        self.search_item_input.setPlaceholderText("Search items or barcode...")
        self.search_item_input.setFixedHeight(40)
        self.search_item_input.setStyleSheet("background: #1e1e1e; color: white; border: 1px solid #333; border-radius: 4px; padding: 5px;")
        
        pl_vbox = QVBoxLayout()
        pl_vbox.setSpacing(2)
        pl_label = QLabel("Price List")
        pl_label.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        self.price_list_combo = QComboBox()
        
        self.price_list_combo.setFixedHeight(35)
        self.price_list_combo.setStyleSheet("background: #1e1e1e; color: white; border: 1px solid #333; border-radius: 4px; padding: 5px;")
        pl_vbox.addWidget(pl_label)
        pl_vbox.addWidget(self.price_list_combo)
        self.price_list_combo.currentTextChanged.connect(self._on_pl_changed)
        
        col_lbl = QPushButton("COLUMNS")
        col_lbl.setStyleSheet("color: #60a5fa; font-weight: bold; font-size: 12px; margin-top: 15px; margin-left: 10px;")
        col_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        col_lbl.clicked.connect(self.open_columns_settings)
        
        search_bar.addWidget(self.search_item_input, 3)
        search_bar.addLayout(pl_vbox, 1)
        search_bar.addWidget(col_lbl)
        main_layout.addLayout(search_bar)

        # ── Table ────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["NAME", "QTY", "RATE", "AMOUNT"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.verticalHeader().setDefaultSectionSize(40)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 120)  # QTY
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(2, 90)   # RATE
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(3, 100)  # AMOUNT
        
        # Make row height dynamic based on content
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setWordWrap(True)
        self.table.setStyleSheet(
            """
            QTableWidget {
                background: transparent; border: none; font-size: 13px;
                selection-background-color: transparent; outline: none;
            }
            QHeaderView::section {
                background-color: #1e293b; color: #94a3b8; font-weight: 700;
                font-size: 11px; padding: 10px 5px; border: none; border-bottom: 1px solid #334155;
            }
            QTableWidget::item { padding: 8px 4px; border-bottom: 1px solid #334155; }
            """
        )

        header.setMinimumHeight(35)
        
        self.table.setStyleSheet("""
            QTableWidget {
                background: #1e1e1e;
                color: #ffffff;
                border: 1px solid #333;
                border-radius: 6px;
                font-size: 13px;
            }
            QHeaderView::section {
                background-color: #2a2a2a;
                color: #ffffff;
                font-weight: 700;
                font-size: 11px;
                border: none;
                border-bottom: 2px solid #444;
                padding-left: 10px;
            }
            QTableWidget::item {
                border-bottom: 1px solid #2a2a2a;
                padding: 4px;
                background-color: transparent;
            }
            QTableWidget::item:selected {
                background-color: transparent;
                outline: none;
            }
        """)
        main_layout.addWidget(self.table)

        # ── Bottom Totals & Buttons (POSAwesome style) ────────────────
        bottom_area = QVBoxLayout()
        bottom_area.setSpacing(12)
        
        # ROW 1: Items Discounts, Total, PAY button
        row1 = QHBoxLayout()
        row1.setSpacing(12)
        
        def _stat_box(title, val_id):
            vbox = QVBoxLayout()
            vbox.setSpacing(4)
            lbl = QLabel(title)
            lbl.setStyleSheet("color: #9ca3af; font-size: 13px; font-weight: 700;")
            val = QLabel("0")
            val.setFixedHeight(50)
            val.setStyleSheet("color: white; font-size: 18px; font-weight: 900; background: #1f2937; padding: 0 14px; border-radius: 6px;")
            val.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            setattr(self, val_id, val)
            vbox.addWidget(lbl)
            vbox.addWidget(val)
            return vbox
        
        row1.addLayout(_stat_box("Items Discounts", "discounts_label"))
        
        t_vbox = QVBoxLayout()
        t_vbox.setSpacing(4)
        t_lbl = QLabel("Total")
        t_lbl.setStyleSheet("color: #9ca3af; font-size: 13px; font-weight: 700;")
        self.total_label = QLabel("UZS 0")
        self.total_label.setFixedHeight(50)
        self.total_label.setStyleSheet("color: #10b981; font-size: 22px; font-weight: 900; background: #1f2937; padding: 0 14px; border-radius: 6px;")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        t_vbox.addWidget(t_lbl)
        t_vbox.addWidget(self.total_label)
        
        self.checkout_btn = QPushButton("PAY")
        self.checkout_btn.setFixedHeight(60)
        self.checkout_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.checkout_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                font-weight: 900; 
                font-size: 20px;
                border-radius: 8px;
                margin-top: 14px;
            }
            QPushButton:hover { background-color: #059669; }
        """)
        self.checkout_btn.clicked.connect(self.handle_checkout)
        
        row1.addLayout(t_vbox)
        row1.addWidget(self.checkout_btn)
        row1.setStretch(0, 1)
        row1.setStretch(1, 1)
        row1.setStretch(2, 2)
        bottom_area.addLayout(row1)
        
        # ROW 2: Total Qty, Cancel Sale button
        row2 = QHBoxLayout()
        row2.setSpacing(12)
        row2.addLayout(_stat_box("Total Qty", "total_qty_label"))
        
        cancel_btn = QPushButton("CANCEL SALE")
        cancel_btn.setFixedHeight(50)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #ec4899; 
                color: white; 
                font-weight: 900; 
                border-radius: 6px; 
                font-size: 15px;
            }
            QPushButton:hover { background-color: #db2777; }
        """)
        cancel_btn.clicked.connect(self.clear_cart)
        
        btn_vbox = QVBoxLayout()
        btn_row = QHBoxLayout()
        btn_row.addWidget(cancel_btn)
        btn_vbox.addSpacing(18)
        btn_vbox.addLayout(btn_row)
        
        row2.addLayout(btn_vbox)
        row2.setStretch(0, 1)
        row2.setStretch(1, 2)
        bottom_area.addLayout(row2)

        main_layout.addLayout(bottom_area)

        # Hidden variables needed by other methods
        self.ticket_input = QLineEdit()
        self.comment_input = QLineEdit()
        self.order_type_buttons = {}
        for t in ORDER_TYPES: self.order_type_buttons[t] = QPushButton()
        # Virtual Keyboards
        self.numpad_panel = self._build_numpad_panel()
        self.numpad_panel.setVisible(False)
        main_layout.addWidget(self.numpad_panel)

        self.keyboard_panel = self._build_keyboard_panel()
        self.keyboard_panel.setVisible(False)
        main_layout.addWidget(self.keyboard_panel)

    def _build_numpad_panel(self):
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame { background: #1e1e1e; border-top: 1px solid #333; }
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        # Display + close
        top = QHBoxLayout()
        self.numpad_display = QLabel("—")
        self.numpad_display.setFixedHeight(42)
        self.numpad_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.numpad_display.setStyleSheet("""
            font-size: 22px; font-weight: 700; color: #1e293b;
            background: white; border: 1.5px solid #3b82f6;
            border-radius: 8px; padding: 4px 12px;
        """)
        np_close = QPushButton("✕")
        np_close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        np_close.setFixedSize(42, 42)
        np_close.setStyleSheet("""
            QPushButton { background:#ef4444; color:white; font-weight:bold;
                font-size:16px; border-radius:8px; border:none; }
            QPushButton:hover { background:#dc2626; }
        """)
        np_close.clicked.connect(self._close_panels)
        top.addWidget(self.numpad_display, stretch=1)
        top.addWidget(np_close)
        layout.addLayout(top)

        # Number grid (3x4)
        keys = [['7','8','9'], ['4','5','6'], ['1','2','3'], ['CLR','0','⌫']]
        for row_keys in keys:
            row = QHBoxLayout()
            row.setSpacing(6)
            for k in row_keys:
                row.addWidget(self._make_numpad_key(k))
            layout.addLayout(row)

        return panel

    def _make_numpad_key(self, key):
        label = 'TOZALASH' if key == 'CLR' else key
        btn = QPushButton(label)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setFixedHeight(52)
        if key == '⌫':
            style = "background:#fee2e2; color:#ef4444; font-size:20px; font-weight:bold;"
        elif key == 'CLR':
            style = "background:#fff7ed; color:#ea580c; font-size:11px; font-weight:bold;"
        else:
            style = "background:white; color:#1e293b; font-size:20px; font-weight:700;"
        btn.setStyleSheet(f"""
            QPushButton {{ {style} border:1px solid #e2e8f0; border-radius:8px; }}
            QPushButton:pressed {{ background:#dbeafe; }}
        """)
        btn.clicked.connect(lambda _, k=key: self._on_numpad_key(k))
        return btn

    def _on_numpad_key(self, key):
        if self._numpad_mode == "qty":
            cur = self.numpad_display.text()
            if cur == "—":
                cur = ""
            if key == '⌫':
                new = cur[:-1]
            elif key == 'CLR':
                new = ''
            else:
                new = cur + key
            self.numpad_display.setText(new or "—")
            # Darhol yangilaymiz
            if new and self._active_qty_item:
                self.update_qty_absolute(self._active_qty_item, new)
        else:
            cur = self.ticket_input.text()
            if key == '⌫':
                new = cur[:-1]
            elif key == 'CLR':
                new = ''
            else:
                new = cur + key
            self.ticket_input.setText(new)
            self.numpad_display.setText(new or "—")

    # ─────────────────────────────────────────
    #  INLINE KEYBOARD  (Izoh uchun)
    # ─────────────────────────────────────────
    def _build_keyboard_panel(self):
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame { background: #1e1e1e; border-top: 1px solid #333; }
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(5)

        # Display + close
        top = QHBoxLayout()
        self.kb_display = QLabel("Izoh...")
        self.kb_display.setFixedHeight(38)
        self.kb_display.setStyleSheet("""
            font-size: 15px; font-weight: 600; color: #334155;
            background: white; border: 1.5px solid #3b82f6;
            border-radius: 8px; padding: 4px 12px;
        """)
        kb_close = QPushButton("✕")
        kb_close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        kb_close.setFixedSize(38, 38)
        kb_close.setStyleSheet("""
            QPushButton { background:#ef4444; color:white; font-weight:bold;
                font-size:14px; border-radius:8px; border:none; }
            QPushButton:hover { background:#dc2626; }
        """)
        kb_close.clicked.connect(self._close_panels)
        top.addWidget(self.kb_display, stretch=1)
        top.addWidget(kb_close)
        layout.addLayout(top)

        # Keyboard rows
        rows = [
            ['1','2','3','4','5','6','7','8','9','0','⌫'],
            ['Q','W','E','R','T','Y','U','I','O','P'],
            ['A','S','D','F','G','H','J','K','L','CLR'],
            ['Z','X','C','V','B','N','M','SPACE'],
        ]
        for row_keys in rows:
            row = QHBoxLayout()
            row.setSpacing(4)
            for k in row_keys:
                row.addWidget(self._make_kb_key(k))
            layout.addLayout(row)

        return panel

    def _make_kb_key(self, key):
        label = '␣' if key == 'SPACE' else ('TOZALASH' if key == 'CLR' else key)
        btn = QPushButton(label)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setFixedHeight(40)
        if key == '⌫':
            style = "background:#fee2e2; color:#ef4444; font-size:16px; font-weight:bold;"
        elif key == 'CLR':
            style = "background:#fff7ed; color:#ea580c; font-size:10px; font-weight:bold;"
        elif key == 'SPACE':
            style = "background:#eff6ff; color:#3b82f6; font-size:14px; font-weight:bold;"
            btn.setMinimumWidth(100)
        elif key.isdigit():
            style = "background:#e0e7ff; color:#3730a3; font-size:14px; font-weight:bold;"
        else:
            style = "background:white; color:#1e293b; font-size:13px; font-weight:600;"
        btn.setStyleSheet(f"""
            QPushButton {{ {style} border:1px solid #e2e8f0; border-radius:6px; }}
            QPushButton:pressed {{ background:#dbeafe; }}
        """)
        btn.clicked.connect(lambda _, k=key: self._on_kb_key(k))
        return btn

    def _on_kb_key(self, key):
        cur = self.comment_input.text()
        if key == '⌫':
            new = cur[:-1]
        elif key == 'CLR':
            new = ''
        elif key == 'SPACE':
            new = cur + ' '
        else:
            new = cur + key
        self.comment_input.setText(new)
        self.kb_display.setText(new or "Izoh...")

    # ─────────────────────────────────────────
    #  Panel open / close
    # ─────────────────────────────────────────
    def _open_ticket_numpad(self, event):
        if not self.ticket_input.isEnabled():
            return
        self.keyboard_panel.setVisible(False)
        self._numpad_mode = "ticket"
        self.ticket_input.setFocus()
        from PyQt6.QtWidgets import QLineEdit
        QLineEdit.mousePressEvent(self.ticket_input, event)
        self._active_qty_item = None
        self.numpad_display.setText(self.ticket_input.text() or "—")
        self.numpad_panel.setVisible(True)

    def _open_comment_keyboard(self, event):
        self.numpad_panel.setVisible(False)
        self.kb_display.setText(self.comment_input.text() or "Izoh...")
        self.keyboard_panel.setVisible(True)
        self.comment_input.setFocus()
        from PyQt6.QtWidgets import QLineEdit
        QLineEdit.mousePressEvent(self.comment_input, event)

    def _close_panels(self):
        self._numpad_mode = "ticket"
        self._active_qty_item = None
        self.numpad_panel.setVisible(False)
        self.keyboard_panel.setVisible(False)

    # ─────────────────────────────────────────
    #  Styles
    # ─────────────────────────────────────────
    @staticmethod
    def _order_type_style(is_active: bool) -> str:
        if is_active:
            return """
                QPushButton {
                    background: #3b82f6; color: white;
                    border: none; border-radius: 10px;
                    font-weight: 700; font-size: 13px;
                }
            """
        return """
            QPushButton {
                background: white; color: #475569;
                border: 1.5px solid #e2e8f0;
                border-radius: 10px; font-weight: 600; font-size: 13px;
            }
            QPushButton:hover { background: #eff6ff; color: #2563eb; border-color: #bfdbfe; }
        """

    @staticmethod
    def _input_style() -> str:
        return """
            QLineEdit, QComboBox {
                padding: 10px 14px;
                font-size: 15px;
                border: 1.5px solid #e2e8f0;
                border-radius: 10px;
                background: white;
                color: #1e293b;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #93c5fd;
            }
            QComboBox::drop-down { border: none; }
            QComboBox::down-arrow { width: 14px; height: 14px; }
        """

    # ─────────────────────────────────────────
    #  Business logic
    # ─────────────────────────────────────────
    def set_order_type(self, order_type: str):
        self.current_order_type = order_type
        for t, btn in self.order_type_buttons.items():
            active = t == order_type
            btn.setChecked(active)
            btn.setStyleSheet(self._order_type_style(active))

        needs_ticket = order_type in TICKET_ORDER_TYPES
        self.ticket_input.setEnabled(needs_ticket)
        if not needs_ticket:
            self.ticket_input.clear()
            self.ticket_input.setStyleSheet(self._input_style() + "background-color: #f3f4f6;")
            self.numpad_panel.setVisible(False)
        else:
            self.ticket_input.setStyleSheet(self._input_style() + "border: 2px solid #3b82f6;")


    def load_price_lists(self):
        from database.models import ItemPrice, db
        db.connect(reuse_if_open=True)
        try:
            pls = [r.price_list for r in ItemPrice.select(ItemPrice.price_list).distinct() if r.price_list]
            if not pls:
                pls = ["Standard Selling"]

            config = load_config()
            preferred_price_list = config.get("price_list", "")

            # Avoid resetting if items are identically same
            current = [self.price_list_combo.itemText(i) for i in range(self.price_list_combo.count())]
            if set(current) != set(pls):
                curr_txt = self.price_list_combo.currentText()
                self.price_list_combo.blockSignals(True)
                self.price_list_combo.clear()
                self.price_list_combo.addItems(pls)
                if curr_txt in pls:
                    self.price_list_combo.setCurrentText(curr_txt)
                elif preferred_price_list in pls:
                    self.price_list_combo.setCurrentText(preferred_price_list)
                self.price_list_combo.blockSignals(False)
            elif not self.price_list_combo.currentText() and preferred_price_list in pls:
                self.price_list_combo.setCurrentText(preferred_price_list)
        finally:
            if not db.is_closed(): db.close()

    def get_selected_price_list(self) -> str:
        current = self.price_list_combo.currentText().strip()
        if current:
            return current
        return load_config().get("price_list", "") or "Standard Selling"

    def _resolve_item_price(self, item_code: str, price_list: str) -> tuple[float, str]:
        from database.models import ItemPrice, Item, db

        db.connect(reuse_if_open=True)
        try:
            price_rec = ItemPrice.get_or_none(
                (ItemPrice.item_code == item_code) & (ItemPrice.price_list == price_list)
            )
            if price_rec:
                return float(price_rec.price_list_rate or 0), price_rec.currency or "UZS"

            item = Item.get_or_none(Item.item_code == item_code)
            if item:
                return float(item.standard_rate or 0), "UZS"

            return 0.0, "UZS"
        finally:
            if not db.is_closed():
                db.close()

    @staticmethod
    def _flt(value, default: float = 0.0) -> float:
        try:
            if value is None or value == "":
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _get_current_profile_data(self) -> dict:
        config = load_config()
        profile_name = (config.get("pos_profile") or "").strip()
        try:
            db.connect(reuse_if_open=True)
            query = PosProfile.select()
            if profile_name:
                profile = query.where(PosProfile.name == profile_name).first()
            else:
                profile = query.first()
            if not profile or not profile.profile_data:
                self._current_profile_data = {}
                return {}
            self._current_profile_data = json.loads(profile.profile_data)
            return self._current_profile_data
        except Exception as e:
            logger.debug("POS Profile ma'lumotlari o'qilmadi: %s", e)
            self._current_profile_data = {}
            return {}
        finally:
            if not db.is_closed():
                db.close()

    def _get_profile_flag(self, key: str, default=0):
        profile = self._current_profile_data or self._get_current_profile_data()
        return profile.get(key, default) if isinstance(profile, dict) else default

    def _resolve_effective_customer_name(self) -> str:
        selected = (self.get_selected_customer_name() or "").strip()
        if selected:
            return selected
        profile = self._current_profile_data or self._get_current_profile_data()
        profile_customer = (profile.get("customer") or "").strip() if isinstance(profile, dict) else ""
        if profile_customer:
            return profile_customer
        return (load_config().get("default_customer") or "").strip()

    def _get_customer_info_local(self, customer_name: str) -> dict:
        if not customer_name:
            return {}
        try:
            db.connect(reuse_if_open=True)
            customer = Customer.get_or_none(Customer.name == customer_name)
            if not customer:
                return {}
            payload = json.loads(customer.posawesome_data or "{}")
            payload.setdefault("name", customer.name)
            payload.setdefault("customer_name", customer.customer_name)
            payload.setdefault("customer_group", customer.customer_group)
            return payload
        except Exception as e:
            logger.debug("Customer info lokal o'qilmadi: %s", e)
            return {}
        finally:
            if not db.is_closed():
                db.close()

    def _get_customer_info(self, customer_name: str) -> dict:
        if not customer_name:
            return {}
        cached = self._customer_info_cache.get(customer_name)
        if cached is not None:
            return dict(cached)

        info = self._get_customer_info_local(customer_name)
        if self.api and self.api.is_configured():
            try:
                success, response = self.api.call_method(
                    "posawesome.posawesome.api.customers.get_customer_info",
                    {"customer": customer_name},
                )
                if success and isinstance(response, dict):
                    info.update(response)
            except Exception as e:
                logger.debug("Customer info serverdan olinmadi: %s", e)

        self._customer_info_cache[customer_name] = dict(info)
        return dict(info)

    def _get_item_meta(self, item_code: str) -> dict:
        cached = self._item_meta_cache.get(item_code)
        if cached is not None:
            return dict(cached)
        try:
            db.connect(reuse_if_open=True)
            item = Item.get_or_none(Item.item_code == item_code)
            if not item:
                self._item_meta_cache[item_code] = {}
                return {}
            payload = json.loads(item.posawesome_data or "{}")
            payload.setdefault("item_code", item.item_code)
            payload.setdefault("item_name", item.item_name)
            payload.setdefault("item_group", item.item_group)
            payload.setdefault("uom", item.uom or item.stock_uom)
            payload.setdefault("stock_uom", item.stock_uom)
            payload.setdefault("image", item.image)
            payload.setdefault("is_stock_item", int(bool(item.is_stock_item)))
            self._item_meta_cache[item_code] = payload
            return dict(payload)
        except Exception as e:
            logger.debug("Item metadata o'qilmadi: %s", e)
            self._item_meta_cache[item_code] = {}
            return {}
        finally:
            if not db.is_closed():
                db.close()

    def _build_item_state(self, item_code: str, item_name: str, price: float, currency: str, qty: int = 1) -> dict:
        meta = self._get_item_meta(item_code)
        price_value = self._flt(price)
        return {
            "item_code": item_code,
            "name": item_name or meta.get("item_name") or item_code,
            "item_name": item_name or meta.get("item_name") or item_code,
            "qty": int(qty),
            "currency": currency or meta.get("currency") or "UZS",
            "price": price_value,
            "price_list_rate": price_value,
            "base_price_list_rate": price_value,
            "rate": price_value,
            "base_rate": price_value,
            "discount_amount": 0.0,
            "base_discount_amount": 0.0,
            "discount_percentage": 0.0,
            "pricing_rules": [],
            "max_discount": self._flt(meta.get("max_discount")),
            "brand": meta.get("brand"),
            "item_group": meta.get("item_group"),
            "uom": meta.get("uom") or meta.get("stock_uom"),
            "warehouse": meta.get("warehouse") or load_config().get("warehouse"),
            "conversion_factor": self._flt(meta.get("conversion_factor"), 1.0) or 1.0,
            "serial_no": meta.get("serial_no"),
            "batch_no": meta.get("batch_no"),
            "is_stock_item": int(bool(meta.get("is_stock_item", 1))),
            "is_free_item": 0,
            "posa_row_id": item_code,
            "_manual_rate_set": False,
            "_manual_rate_value": None,
        }

    def _can_edit_rate(self) -> bool:
        return bool(self._flt(self._get_profile_flag("posa_allow_user_to_edit_rate", 0)))

    def _apply_manual_rate_to_item(self, item: dict, desired_rate: float, persist: bool = True):
        price_list_rate = self._flt(item.get("price_list_rate"))
        if price_list_rate <= 0:
            effective_rate = max(self._flt(desired_rate), 0.0)
        else:
            effective_rate = min(max(self._flt(desired_rate), 0.0), price_list_rate)

        discount_amount = max(price_list_rate - effective_rate, 0.0)
        discount_percentage = (discount_amount / price_list_rate * 100.0) if price_list_rate > 0 else 0.0

        item["rate"] = effective_rate
        item["base_rate"] = effective_rate
        item["price"] = effective_rate
        item["discount_amount"] = discount_amount
        item["base_discount_amount"] = discount_amount
        item["discount_percentage"] = discount_percentage

        manual_enabled = effective_rate > 0 and abs(effective_rate - price_list_rate) > 0.0001
        if persist:
            item["_manual_rate_set"] = manual_enabled
            item["_manual_rate_value"] = effective_rate if manual_enabled else None

    def _commit_inline_rate(self, item_code: str, editor: QLineEdit):
        item = self.items.get(item_code)
        if not item:
            return
        raw = (editor.text() or "").replace(" ", "").strip()
        if not raw:
            self._apply_manual_rate_to_item(
                item,
                self._flt(item.get("price_list_rate"), self._flt(item.get("rate"))),
                persist=True,
            )
            self.refresh_table()
            return
        try:
            new_rate = float(raw)
        except ValueError:
            self.refresh_table()
            return
        self._apply_manual_rate_to_item(item, new_rate, persist=True)
        self.refresh_table()

    def _apply_customer_discount(self, item: dict, customer_info: dict):
        if item.get("is_free_item"):
            return
        discount_percent = self._flt(customer_info.get("posa_discount"))
        if discount_percent <= 0 or discount_percent > 100:
            return

        max_discount = self._flt(item.get("max_discount"))
        if max_discount > 0:
            discount_percent = min(discount_percent, max_discount)

        price_list_rate = self._flt(item.get("price_list_rate"))
        base_price_list_rate = self._flt(item.get("base_price_list_rate"), price_list_rate)
        discount_amount = (price_list_rate * discount_percent) / 100
        base_discount_amount = (base_price_list_rate * discount_percent) / 100

        item["discount_percentage"] = discount_percent
        item["discount_amount"] = discount_amount
        item["base_discount_amount"] = base_discount_amount
        item["rate"] = max(price_list_rate - discount_amount, 0)
        item["base_rate"] = max(base_price_list_rate - base_discount_amount, 0)
        item["price"] = item["rate"]

    @staticmethod
    def _normalize_pricing_rules(value) -> list[str]:
        if not value:
            return []
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            try:
                decoded = json.loads(text)
                if isinstance(decoded, list):
                    return [str(v).strip() for v in decoded if str(v).strip()]
            except (TypeError, ValueError):
                pass
            return [part.strip() for part in text.split(",") if part.strip()]
        return []

    def _build_pricing_context(self, customer_name: str, customer_info: dict) -> dict:
        profile = self._current_profile_data or self._get_current_profile_data()
        config = load_config()
        return {
            "company": profile.get("company") or config.get("company"),
            "currency": profile.get("currency") or config.get("currency", "UZS"),
            "price_list": self.get_selected_price_list(),
            "customer": customer_name,
            "customer_group": customer_info.get("customer_group"),
            "territory": customer_info.get("territory"),
            "date": datetime.date.today().isoformat(),
            "conversion_rate": 1,
        }

    def _apply_server_pricing(self, customer_name: str, customer_info: dict):
        if not self.api or not self.api.is_configured():
            return

        lines = []
        for code, item in self.items.items():
            if item.get("is_free_item"):
                continue
            lines.append(
                {
                    "item_code": item.get("item_code") or code,
                    "qty": self._flt(item.get("qty"), 1),
                    "stock_qty": self._flt(item.get("qty"), 1),
                    "price_list_rate": self._flt(item.get("price_list_rate")),
                    "base_price_list_rate": self._flt(item.get("base_price_list_rate")),
                    "rate": self._flt(item.get("rate"), self._flt(item.get("price_list_rate"))),
                    "base_rate": self._flt(item.get("base_rate"), self._flt(item.get("base_price_list_rate"))),
                    "warehouse": item.get("warehouse"),
                    "uom": item.get("uom"),
                    "item_group": item.get("item_group"),
                    "brand": item.get("brand"),
                    "pricing_rules": item.get("pricing_rules") or [],
                    "posa_row_id": code,
                }
            )

        if not lines:
            return

        payload = {
            "context": self._build_pricing_context(customer_name, customer_info),
            "lines": lines,
            "free_lines": [],
        }
        try:
            success, response = self.api.call_method(
                "posawesome.posawesome.api.pricing_rules.reconcile_line_prices",
                {"cart_payload": json.dumps(payload)},
            )
            if not success or not isinstance(response, dict):
                return

            updates = response.get("updates") or []
            for update in updates:
                row_id = str(update.get("row_id") or "").strip()
                if not row_id or row_id not in self.items:
                    continue
                item = self.items[row_id]
                if item.get("_manual_rate_set"):
                    continue
                price_list_rate = self._flt(update.get("price_list_rate"), self._flt(item.get("price_list_rate")))
                discount_amount = self._flt(update.get("discount_amount"))
                discount_percentage = self._flt(update.get("discount_percentage"))
                rate = self._flt(update.get("rate"), max(price_list_rate - discount_amount, 0))
                item["price_list_rate"] = price_list_rate
                item["base_price_list_rate"] = price_list_rate
                item["discount_amount"] = discount_amount
                item["base_discount_amount"] = discount_amount
                item["discount_percentage"] = discount_percentage
                item["rate"] = rate
                item["base_rate"] = rate
                item["price"] = rate
                item["pricing_rules"] = self._normalize_pricing_rules(update.get("pricing_rules"))

            invoice_updates = response.get("invoice_updates") or {}
            self.invoice_discount_amount = self._flt(invoice_updates.get("discount_amount"))
            self.invoice_discount_percentage = self._flt(
                invoice_updates.get("additional_discount_percentage")
            )
            self.apply_discount_on = invoice_updates.get("apply_discount_on") or "Grand Total"
        except Exception as e:
            logger.debug("Pricing rule reconcile ishlamadi: %s", e)

    def _reprice_cart(self):
        if self._is_repricing:
            return

        self._is_repricing = True
        try:
            if not self.items:
                self.gross_total_amount = 0.0
                self.net_total_amount = 0.0
                self.item_discount_total = 0.0
                self.invoice_discount_amount = 0.0
                self.invoice_discount_percentage = 0.0
                self.apply_discount_on = "Grand Total"
                self._current_customer_info = {}
                self.refresh_table()
                return

            self._current_profile_data = self._get_current_profile_data()
            customer_name = self._resolve_effective_customer_name()
            customer_info = self._get_customer_info(customer_name) if customer_name else {}
            self._current_customer_info = dict(customer_info)

            selected_price_list = self.get_selected_price_list()
            apply_customer_discount = bool(
                self._flt(self._get_profile_flag("posa_apply_customer_discount", 0))
            )

            for code, item in self.items.items():
                manual_rate = item.get("_manual_rate_value") if item.get("_manual_rate_set") else None
                price, currency = self._resolve_item_price(code, selected_price_list)
                meta = self._get_item_meta(code)
                item["currency"] = currency or item.get("currency") or "UZS"
                item["name"] = item.get("name") or meta.get("item_name") or code
                item["item_name"] = item.get("item_name") or meta.get("item_name") or item["name"]
                item["item_group"] = meta.get("item_group") or item.get("item_group")
                item["brand"] = meta.get("brand") or item.get("brand")
                item["uom"] = meta.get("uom") or meta.get("stock_uom") or item.get("uom")
                item["warehouse"] = meta.get("warehouse") or item.get("warehouse") or load_config().get("warehouse")
                item["max_discount"] = self._flt(meta.get("max_discount"), self._flt(item.get("max_discount")))
                item["conversion_factor"] = self._flt(
                    meta.get("conversion_factor"),
                    self._flt(item.get("conversion_factor"), 1.0),
                ) or 1.0
                item["is_stock_item"] = int(bool(meta.get("is_stock_item", item.get("is_stock_item", 1))))
                item["pricing_rules"] = []
                item["price_list_rate"] = price
                item["base_price_list_rate"] = price
                item["rate"] = price
                item["base_rate"] = price
                item["price"] = price
                item["discount_amount"] = 0.0
                item["base_discount_amount"] = 0.0
                item["discount_percentage"] = 0.0

                if apply_customer_discount and customer_info and not item.get("_manual_rate_set"):
                    self._apply_customer_discount(item, customer_info)

                if manual_rate is not None:
                    self._apply_manual_rate_to_item(item, manual_rate, persist=False)

            self.invoice_discount_amount = 0.0
            self.invoice_discount_percentage = 0.0
            self.apply_discount_on = "Grand Total"
            self._apply_server_pricing(customer_name, customer_info)
            self.refresh_table()
        finally:
            self._is_repricing = False

    def _on_pl_changed(self, text):
        try:
            self._reprice_cart()
        except Exception as e:
            logger.debug("Price list update failed: %s", e)
        self.price_list_changed.emit(text)

    def load_customers(self):
        """Mijozlarni lokal bazadan yuklash"""
        try:
            db.connect(reuse_if_open=True)

            config = load_config()
            default_customer = config.get("default_customer", "")

            rows = list(
                Customer.select(
                    Customer.name,
                    Customer.customer_name,
                    Customer.customer_group,
                    Customer.phone,
                )
                .order_by(Customer.customer_name)
                .dicts()
            )

            self._all_customers = rows
            self._load_customer_groups()
            self._apply_customer_filters(
                typed_text="",
                selected_name=default_customer,
                show_popup=False,
            )
        except Exception as e:
            logger.debug("Mijozlar yuklanmadi: %s", e)
        finally:
            if not db.is_closed():
                db.close()

    def refresh_customer_groups(self):
        current_group = self.cg_mock.currentData()
        current_search = self.customer_combo.lineEdit().text().strip()
        current_customer = self.get_selected_customer_name()

        self._load_customer_groups()
        if current_group:
            idx = self.cg_mock.findData(current_group)
            if idx >= 0:
                self.cg_mock.setCurrentIndex(idx)

        self._apply_customer_filters(
            typed_text=current_search,
            selected_name=current_customer,
            show_popup=False,
        )

    def _load_customer_groups(self):
        groups = []
        seen = set()

        # 1. POS Profile ichidagi customer_groups (agar mavjud bo'lsa)
        profile_groups = self._get_profile_customer_groups()
        for group in profile_groups:
            normalized = (group or "").strip()
            if normalized and normalized not in seen:
                groups.append(normalized)
                seen.add(normalized)

        # 2. Webdagi kabi fallback: serverdan Customer Group ro'yxati
        if not groups:
            for group in self._fetch_customer_groups_from_server():
                normalized = (group or "").strip()
                if normalized and normalized not in seen:
                    groups.append(normalized)
                    seen.add(normalized)

        current_value = self.cg_mock.currentData()
        self.cg_mock.blockSignals(True)
        self.cg_mock.clear()
        self.cg_mock.addItem("All Groups", "all")
        for group in sorted(groups):
            self.cg_mock.addItem(group, group)

        if current_value:
            idx = self.cg_mock.findData(current_value)
            if idx >= 0:
                self.cg_mock.setCurrentIndex(idx)
        self.cg_mock.blockSignals(False)
        self.cg_mock.setEnabled(bool(groups))

    def _get_profile_customer_groups(self) -> list[str]:
        try:
            db.connect(reuse_if_open=True)
            profile = PosProfile.select().first()
            if not profile or not profile.profile_data:
                return []

            payload = json.loads(profile.profile_data)
            rows = payload.get("customer_groups") or []
            groups = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                name = (row.get("customer_group") or "").strip()
                if name:
                    groups.append(name)
            return groups
        except Exception as e:
            logger.debug("POS Profile customer_groups o'qilmadi: %s", e)
            return []
        finally:
            if not db.is_closed():
                db.close()

    def _fetch_customer_groups_from_server(self) -> list[str]:
        if not self.api:
            return []
        try:
            success, response = self.api.call_method(
                "frappe.client.get_list",
                {
                    "doctype": "Customer Group",
                    "fields": ["name"],
                    "filters": {"is_group": 0},
                    "limit_page_length": 0,
                },
            )
            if success and isinstance(response, list):
                groups = [str(row.get("name") or "").strip() for row in response if row.get("name")]
                if groups:
                    return groups

            # Ba'zi holatlarda frappe.client.get_list vaqtincha 403/500 qaytarishi mumkin.
            # Shunda /api/resource orqali ham urinib ko'ramiz.
            response = self.api.fetch_data(
                "Customer Group",
                fields='["name"]',
                filters={"is_group": 0},
                limit=0,
            )
            if isinstance(response, list):
                return [str(row.get("name") or "").strip() for row in response if row.get("name")]
            return []
        except Exception as e:
            logger.debug("Customer Group serverdan olinmadi: %s", e)
            return []

    def _normalize_customer_search(self, text: str) -> list[str]:
        return [part for part in (text or "").strip().lower().split() if part]

    def _customer_matches(self, row: dict, parts: list[str]) -> bool:
        if not parts:
            return True
        values = [
            str(row.get("customer_name") or "").lower(),
            str(row.get("name") or "").lower(),
            str(row.get("phone") or "").lower(),
        ]
        return all(any(part in value for value in values) for part in parts)

    def _get_selected_customer_group(self) -> str:
        return self.cg_mock.currentData() or "all"

    def _format_customer_label(self, row: dict) -> str:
        name = (row.get("name") or "").strip()
        customer_name = (row.get("customer_name") or name).strip()
        phone = (row.get("phone") or "").strip()

        label = customer_name
        if name and name != customer_name:
            label += f" ({name})"
        if phone:
            label += f"  |  {phone}"
        return label

    def _find_customer_by_text(self, text: str, candidates=None):
        lookup = (text or "").strip().lower()
        if not lookup:
            return None

        rows = candidates if candidates is not None else self._all_customers
        for row in rows:
            name = str(row.get("name") or "").strip().lower()
            customer_name = str(row.get("customer_name") or "").strip().lower()
            phone = str(row.get("phone") or "").strip().lower()
            if lookup in {name, customer_name, phone}:
                return row

        for row in rows:
            values = [
                str(row.get("customer_name") or "").lower(),
                str(row.get("name") or "").lower(),
                str(row.get("phone") or "").lower(),
            ]
            if any(lookup in value for value in values):
                return row
        return None

    def _apply_customer_filters(self, typed_text: str | None = None, selected_name: str = "", show_popup: bool = False):
        line_edit = self.customer_combo.lineEdit()
        search_text = typed_text if typed_text is not None else line_edit.text()
        parts = self._normalize_customer_search(search_text)
        selected_group = self._get_selected_customer_group()

        filtered = []
        for row in self._all_customers:
            group = (row.get("customer_group") or "").strip()
            if selected_group != "all" and group != selected_group:
                continue
            if not self._customer_matches(row, parts):
                continue
            filtered.append(row)

        self._filtered_customers = filtered

        self._customer_ui_updating = True
        self.customer_combo.blockSignals(True)
        line_edit.blockSignals(True)
        self.customer_combo.clear()
        for row in filtered:
            self.customer_combo.addItem(self._format_customer_label(row), row.get("name"))

        target_name = selected_name.strip()
        if not target_name:
            matched = self._find_customer_by_text(search_text, filtered)
            if matched and search_text.strip().lower() in {
                str(matched.get("name") or "").strip().lower(),
                str(matched.get("customer_name") or "").strip().lower(),
            }:
                target_name = matched.get("name", "")

        if target_name:
            idx = self.customer_combo.findData(target_name)
            if idx >= 0:
                self.customer_combo.setCurrentIndex(idx)
                line_edit.setText(self.customer_combo.itemText(idx) if not search_text.strip() else search_text)
            else:
                self.customer_combo.setCurrentIndex(-1)
                line_edit.setText(search_text or target_name)
        else:
            self.customer_combo.setCurrentIndex(-1)
            line_edit.setText(search_text)

        line_edit.setCursorPosition(len(line_edit.text()))
        line_edit.blockSignals(False)
        self.customer_combo.blockSignals(False)
        self._customer_ui_updating = False

        if show_popup and filtered:
            self.customer_combo.showPopup()
        elif show_popup:
            self.customer_combo.hidePopup()

    def _on_customer_search_edited(self, text: str):
        if self._customer_ui_updating:
            return
        self._apply_customer_filters(typed_text=text, show_popup=True)

    def _on_customer_group_changed(self, _index: int):
        if self._customer_ui_updating:
            return
        line_edit = self.customer_combo.lineEdit()
        line_edit.blockSignals(True)
        line_edit.clear()
        line_edit.blockSignals(False)
        self._apply_customer_filters(typed_text="", show_popup=True)

    def _clear_customer_selection(self):
        line_edit = self.customer_combo.lineEdit()
        line_edit.blockSignals(True)
        line_edit.clear()
        line_edit.blockSignals(False)
        self._apply_customer_filters(typed_text="", selected_name="", show_popup=True)
        self._reprice_cart()

    def _on_customer_selected(self, index: int):
        if index < 0:
            return
        name = self.customer_combo.itemData(index)
        if not name:
            return
        self._apply_customer_filters(typed_text="", selected_name=str(name), show_popup=False)
        self._reprice_cart()

    def _commit_customer_search(self):
        typed = self.customer_combo.lineEdit().text().strip()
        matched = self._find_customer_by_text(typed, self._filtered_customers or self._all_customers)
        if matched:
            self._apply_customer_filters(
                typed_text="",
                selected_name=str(matched.get("name") or ""),
                show_popup=False,
            )
        elif self._filtered_customers:
            first = self._filtered_customers[0]
            self._apply_customer_filters(
                typed_text="",
                selected_name=str(first.get("name") or ""),
                show_popup=False,
            )
        self._reprice_cart()

    def get_selected_customer_name(self) -> str:
        current_index = self.customer_combo.currentIndex()
        if current_index >= 0:
            customer_name = self.customer_combo.itemData(current_index)
            if customer_name:
                return str(customer_name).strip()

        typed = self.customer_combo.lineEdit().text().strip()
        matched = self._find_customer_by_text(typed, self._filtered_customers or self._all_customers)
        if matched:
            return str(matched.get("name") or "").strip()

        return typed

    def add_item(self, item_code: str, item_name: str, price: float, currency: str):
        if item_code in self.items:
            self.items[item_code]["qty"] = int(self.items[item_code]["qty"] + 1)
        else:
            self.items[item_code] = self._build_item_state(item_code, item_name, price, currency, qty=1)
        self._reprice_cart()
        self._emit_cart_updated()

    def update_qty(self, item_code: str, change: int):
        if item_code in self.items:
            self.items[item_code]["qty"] = int(self.items[item_code]["qty"] + change)
            if self.items[item_code]["qty"] <= 0:
                del self.items[item_code]
            self._reprice_cart()
            self._emit_cart_updated()

    def update_qty_absolute(self, item_code: str, new_qty_str: str):
        try:
            new_qty = int(float(new_qty_str))
            if new_qty > 0:
                self.items[item_code]["qty"] = new_qty
            else:
                del self.items[item_code]
            self._reprice_cart()
            self._emit_cart_updated()
        except (ValueError, KeyError):
            pass


    def open_columns_settings(self):
        from ui.components.dialogs import SettingsDialog
        dlg = SettingsDialog(self, "Ustunlar sozlanmasi", self.col_settings)
        if dlg.exec():
            res = dlg.get_results()
            for k in res:
                self.col_settings[k]["value"] = res[k]
            
            # Apply column visibility (0 is Name, 1 is Qty, 2 is Rate, 3 is Amount)
            self.table.setColumnHidden(1, not self.col_settings["show_qty"]["value"])
            self.table.setColumnHidden(2, not self.col_settings["show_rate"]["value"])
            self.table.setColumnHidden(3, not self.col_settings["show_amount"]["value"])

    def refresh_table(self):
        self.table.setRowCount(0)
        total_qty = 0
        self.gross_total_amount = 0.0
        self.net_total_amount = 0.0
        self.item_discount_total = 0.0

        for row, (code, item) in enumerate(self.items.items()):
            self.table.insertRow(row)



            # QTY with +/-
            qty_widget = QWidget()
            qty_widget.setStyleSheet("background-color: transparent;")
            qty_layout = QHBoxLayout(qty_widget)
            qty_layout.setContentsMargins(0, 0, 0, 0)
            
            minus_btn = QPushButton("−")
            minus_btn.setFixedSize(28, 28)
            minus_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            minus_btn.setStyleSheet("background: transparent; color: #ef4444; border: 1px solid #ef4444; border-radius: 4px; font-weight: bold; font-size: 14px; padding-bottom: 2px;")
            minus_btn.clicked.connect(lambda _, c=code: self.update_qty(c, -1))
            
            qty_lbl = QtyLabel(str(item['qty']))
            qty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            qty_lbl.setStyleSheet("font-weight: 900; font-size: 14px; color: white; min-width: 30px;")
            qty_lbl.clicked.connect(lambda c=code, q=str(item['qty']): self._open_qty_numpad(c, q))
            
            plus_btn = QPushButton("+")
            plus_btn.setFixedSize(28, 28)
            plus_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            plus_btn.setStyleSheet("background: transparent; color: #10b981; border: 1px solid #10b981; border-radius: 4px; font-weight: bold; font-size: 14px; padding-bottom: 2px;")
            plus_btn.clicked.connect(lambda _, c=code: self.update_qty(c, 1))
            
            qty_layout.addStretch()
            qty_layout.addWidget(minus_btn)
            qty_layout.addWidget(qty_lbl)
            qty_layout.addWidget(plus_btn)
            qty_layout.addStretch()
            qty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 1, qty_widget)

            # RATE
            if self._can_edit_rate():
                rate_lbl = QLineEdit(f"{self._flt(item.get('price'), 0):.0f}")
                rate_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                rate_lbl.setValidator(QDoubleValidator(0.0, 9999999999.0, 2))
                rate_lbl.setPlaceholderText("Rate")
                rate_lbl.setToolTip("Rate ni shu joyda o'zgartiring")
                rate_lbl.editingFinished.connect(lambda c=code, w=rate_lbl: self._commit_inline_rate(c, w))
                rate_lbl.setStyleSheet(
                    "color: #60a5fa; font-weight: 700; font-size: 13px; background:#0f172a; border:1px solid #334155; border-radius:6px; padding:4px;"
                )
            else:
                rate_lbl = QLabel(f"UZS {item['price']:,.0f}")
                rate_lbl.setStyleSheet("color: #94a3b8; font-weight: 600; font-size: 13px;")
            rate_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 2, rate_lbl)

            # AMOUNT
            qty = self._flt(item.get('qty'), 0)
            price_list_rate = self._flt(item.get('price_list_rate'), self._flt(item.get('price')))
            line_discount = self._flt(item.get('discount_amount'))
            rate = self._flt(item.get('rate'), self._flt(item.get('price')))
            amt = qty * rate
            amt_lbl = QLabel(f"UZS {amt:,.0f}")
            amt_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            amt_lbl.setStyleSheet("font-weight: 900; font-size: 14px; color: white;")
            amt_lbl.setContentsMargins(0, 0, 10, 0)
            self.table.setCellWidget(row, 3, amt_lbl)

            # Name with compact delete button
            name_widget = QWidget()
            name_widget.setStyleSheet("background-color: transparent;")
            name_layout = QHBoxLayout(name_widget)
            name_layout.setContentsMargins(10, 0, 5, 0)
            name_layout.setSpacing(10)
            
            del_btn = QPushButton("×")
            del_btn.setFixedSize(22, 22)
            del_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            del_btn.setStyleSheet("background: transparent; color: #ef4444; font-size: 18px; font-weight: 900; border: none;")
            del_btn.clicked.connect(lambda _, c=code: self.update_qty_absolute(c, "0"))
            
            name_lbl = QLabel(item['name'])
            name_lbl.setStyleSheet("font-weight: 600; font-size: 13px; color: white;")
            name_lbl.setWordWrap(True)
            
            name_layout.addWidget(del_btn)
            name_layout.addWidget(name_lbl, 1)
            self.table.setCellWidget(row, 0, name_widget)

            total_qty += int(qty)
            self.gross_total_amount += qty * price_list_rate
            self.item_discount_total += qty * line_discount
            self.net_total_amount += amt

        invoice_discount = min(max(self.invoice_discount_amount, 0.0), max(self.net_total_amount, 0.0))
        self.invoice_discount_amount = invoice_discount
        if self.net_total_amount > 0 and invoice_discount > 0 and self.invoice_discount_percentage <= 0:
            self.invoice_discount_percentage = (invoice_discount / self.net_total_amount) * 100
        self.total_amount = max(self.net_total_amount - invoice_discount, 0.0)

        # Update totals
        if hasattr(self, 'total_label'):
            self.total_label.setText(f"UZS {self.total_amount:,.0f}")
        if hasattr(self, 'total_qty_label'):
            self.total_qty_label.setText(str(total_qty))
        if hasattr(self, 'discounts_label'):
            self.discounts_label.setText(f"UZS {self.item_discount_total:,.0f}")
        
        # Re-apply column visibility after refresh
        self.table.setColumnHidden(1, not self.col_settings["show_qty"]["value"])
        self.table.setColumnHidden(2, not self.col_settings["show_rate"]["value"])
        self.table.setColumnHidden(3, not self.col_settings["show_amount"]["value"])
        
        # Re-apply column visibility after refresh
        self.table.setColumnHidden(1, not self.col_settings["show_qty"]["value"])
        self.table.setColumnHidden(2, not self.col_settings["show_rate"]["value"])
        self.table.setColumnHidden(3, not self.col_settings["show_amount"]["value"])
            
        # Re-apply column visibility after refresh
        self.table.setColumnHidden(1, not self.col_settings["show_qty"]["value"])
        self.table.setColumnHidden(2, not self.col_settings["show_rate"]["value"])
        self.table.setColumnHidden(3, not self.col_settings["show_amount"]["value"])
        
    def _dummy_refresh(self): pass
    def _open_qty_numpad(self, item_code: str, current_qty: str):
        """Inline numpad panel yordamida miqdorni o'zgartirish."""
        self._active_qty_item = item_code
        self.keyboard_panel.setVisible(False)
        self.numpad_display.setText(current_qty or "—")
        # Numpad input stiker o'rniga qty ga bog'laymiz
        self._numpad_mode = "qty"
        self.numpad_panel.setVisible(True)

    def clear_cart(self):
        self.items.clear()
        self.ticket_input.clear()
        self.comment_input.clear()
        self._close_panels()
        self.invoice_discount_amount = 0.0
        self.invoice_discount_percentage = 0.0
        self.item_discount_total = 0.0
        self.gross_total_amount = 0.0
        self.net_total_amount = 0.0
        self._current_customer_info = {}
        self.refresh_table()
        self._emit_cart_updated()

    def _emit_cart_updated(self):
        snapshot = {}
        for code, item in self.items.items():
            try:
                qty = int(float(item.get("qty", 0)))
            except (TypeError, ValueError):
                qty = 0
            if qty > 0:
                snapshot[code] = qty
        self.cart_updated.emit(snapshot)

    def handle_checkout(self):
        if not self.items:
            InfoDialog(self, "Xatolik", "Savat bo'sh!", kind="warning").exec()
            return

        ticket_number = self.ticket_input.text().strip()
        selected_customer = self.get_selected_customer_name() or "guest"

        # if self.current_order_type in TICKET_ORDER_TYPES and not ticket_number:
        #    InfoDialog(self, "Xatolik", "Stiker raqamini kiriting!", kind="warning").exec()
        #    return

        order_data = {
            "items": [{"item_code": k, **v} for k, v in self.items.items()],
            "total_amount": self.total_amount,
            "gross_total_amount": self.gross_total_amount,
            "net_total_amount": self.net_total_amount,
            "item_discount_total": self.item_discount_total,
            "invoice_discount_amount": self.invoice_discount_amount,
            "invoice_discount_percentage": self.invoice_discount_percentage,
            "apply_discount_on": self.apply_discount_on,
            "allow_additional_discount": bool(
                self._flt(self._get_profile_flag("posa_allow_user_to_edit_additional_discount", 0))
            ),
            "max_discount_percentage": self._flt(self._get_profile_flag("posa_max_discount_allowed", 0)),
            "order_type": self.current_order_type,
            "ticket_number": ticket_number,
            "customer": self._resolve_effective_customer_name() or selected_customer,
            "selling_price_list": self.get_selected_price_list(),
            "comment": self.comment_input.text().strip(),
        }
        self.checkout_requested.emit(order_data)
