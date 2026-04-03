from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QLabel, QHBoxLayout,
    QComboBox, QLineEdit, QGroupBox, QFrame,
)
from PyQt6.QtCore import pyqtSignal, Qt
from database.models import Customer, db
from core.logger import get_logger
from core.constants import TICKET_ORDER_TYPES, ORDER_TYPES
from ui.components.keyboard import TouchKeyboard
from ui.components.dialogs import InfoDialog

logger = get_logger(__name__)


class QtyLabel(QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        self.clicked.emit()


class CartWidget(QWidget):
    checkout_requested = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.items = {}
        self.total_amount = 0.0
        self.current_order_type = ORDER_TYPES[0]
        self.order_type_buttons = {}
        self._numpad_mode = "ticket"   # "ticket" | "qty"
        self._active_qty_item = None
        self.init_ui()
        self.load_customers()

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
        self.customer_combo.setMinimumHeight(34)
        self.customer_combo.setMaximumHeight(44)
        self.customer_combo.setStyleSheet("""
            QComboBox { background: #1e1e1e; color: white; border: 1px solid #333; border-radius: 4px; padding: 5px; }
            QComboBox QAbstractItemView { background: #1e1e1e; color: white; }
        """)
        customer_vbox.addWidget(cust_label)
        customer_vbox.addWidget(self.customer_combo)
        
        # Customer Group
        cg_vbox = QVBoxLayout()
        cg_vbox.setSpacing(2)
        cg_label = QLabel("Customer Group")
        cg_label.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        self.cg_mock = QComboBox()
        self.cg_mock.addItems(["All Groups", "Commercial", "Government", "Individual"])
        self.cg_mock.setMinimumHeight(34)
        self.cg_mock.setMaximumHeight(44)
        self.cg_mock.setStyleSheet("background: #1e1e1e; color: white; border: 1px solid #333; border-radius: 4px; padding: 5px;")
        cg_vbox.addWidget(cg_label)
        cg_vbox.addWidget(self.cg_mock)
        
        top_bar.addLayout(customer_vbox, 3)
        top_bar.addLayout(cg_vbox, 1)
        
        main_layout.addLayout(top_bar)

        # --- Search & Price List ---
        search_bar = QHBoxLayout()
        self.search_item_input = QLineEdit()
        self.search_item_input.setPlaceholderText("Search items or barcode...")
        self.search_item_input.setMinimumHeight(34)
        self.search_item_input.setMaximumHeight(44)
        self.search_item_input.setStyleSheet("background: #1e1e1e; color: white; border: 1px solid #333; border-radius: 4px; padding: 5px;")
        
        pl_vbox = QVBoxLayout()
        pl_vbox.setSpacing(2)
        pl_label = QLabel("Price List")
        pl_label.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        self.pl_mock = QComboBox()
        self.pl_mock.addItems(["Standard Selling...", "Wholesale"])
        self.pl_mock.setMinimumHeight(26)
        self.pl_mock.setMaximumHeight(36)
        self.pl_mock.setStyleSheet("background: #1e1e1e; color: white; border: 1px solid #333; border-radius: 4px; padding: 5px;")
        pl_vbox.addWidget(pl_label)
        pl_vbox.addWidget(self.pl_mock)
        
        col_lbl = QPushButton("COLUMNS")
        col_lbl.setStyleSheet("color: #60a5fa; font-weight: bold; font-size: 12px; margin-top: 15px; margin-left: 10px;")
        
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
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

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
        bottom_area.setSpacing(10)
        
        row1 = QHBoxLayout()
        
        def _stat_box(title, val_id):
            vbox = QVBoxLayout()
            lbl = QLabel(title)
            lbl.setStyleSheet("color: #a0a0a0; font-size: 11px;")
            val = QLabel("0")
            val.setStyleSheet("color: white; font-size: 14px; font-weight: bold; background: #2a2a2a; padding: 10px; border-radius: 4px;")
            setattr(self, val_id, val)
            vbox.addWidget(lbl)
            vbox.addWidget(val)
            return vbox
        
        row1.addLayout(_stat_box("Total Qty", "total_qty_label"))
        # Final Price Box (mock)
        fp_vbox = QVBoxLayout()
        fp_lbl = QLabel("Final Price")
        fp_lbl.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        fp_val = QLineEdit()
        fp_val.setPlaceholderText("Final Price")
        fp_val.setStyleSheet("background: #2a2a2a; color: #a0a0a0; padding: 10px; border: none; border-radius: 4px; font-size: 14px;")
        fp_vbox.addWidget(fp_lbl)
        fp_vbox.addWidget(fp_val)
        row1.addLayout(fp_vbox)
        
        # Action Buttons
        save_btn = QPushButton("SAVE & CLEAR")
        save_btn.setMinimumHeight(38)
        save_btn.setMaximumHeight(50)
        save_btn.setStyleSheet("background: #f97316; color: white; font-weight: 900; border-radius: 4px; font-size: 12px;")
        save_btn.clicked.connect(self.clear_cart)
        
        cancel_btn = QPushButton("CANCEL SALE")
        cancel_btn.setMinimumHeight(38)
        cancel_btn.setMaximumHeight(50)
        cancel_btn.setStyleSheet("background: #ec4899; color: white; font-weight: 900; border-radius: 4px; font-size: 12px;")
        cancel_btn.clicked.connect(self.clear_cart)
        
        btn_vbox = QVBoxLayout()
        btn_row = QHBoxLayout()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        # Spacer for top alignment matching the stat boxes
        btn_vbox.addSpacing(15)
        btn_vbox.addLayout(btn_row)
        
        row1.addLayout(btn_vbox)
        row1.setStretch(0, 1)
        row1.setStretch(1, 1)
        row1.setStretch(2, 2)
        bottom_area.addLayout(row1)
        
        row2 = QHBoxLayout()
        row2.addLayout(_stat_box("Items Discounts", "discounts_label"))
        
        t_vbox = QVBoxLayout()
        t_lbl = QLabel("Total")
        t_lbl.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        self.total_label = QLabel("UZS 0")
        self.total_label.setStyleSheet("color: #10b981; font-size: 18px; font-weight: 900; background: #2a2a2a; padding: 10px; border-radius: 4px;")
        t_vbox.addWidget(t_lbl)
        t_vbox.addWidget(self.total_label)
        
        self.checkout_btn = QPushButton("PAY")
        self.checkout_btn.setMinimumHeight(42)
        self.checkout_btn.setMaximumHeight(56)
        self.checkout_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.checkout_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                font-weight: 800; font-size: 16px;
                border-radius: 4px;
                margin-top: 15px;
            }
            QPushButton:hover { background-color: #059669; }
        """)
        self.checkout_btn.clicked.connect(self.handle_checkout)
        
        row2.addLayout(t_vbox)
        row2.addWidget(self.checkout_btn)
        row2.setStretch(0, 1)
        row2.setStretch(1, 1)
        row2.setStretch(2, 2)
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

    def load_customers(self):
        try:
            db.connect(reuse_if_open=True)
            customers = ["guest"]
            customers.extend([c.name for c in Customer.select()])
            self.customer_combo.addItems(customers)
        except Exception as e:
            logger.debug("Mijozlar yuklanmadi: %s", e)
        finally:
            if not db.is_closed():
                db.close()

    def add_item(self, item_code: str, item_name: str, price: float, currency: str):
        if item_code in self.items:
            self.items[item_code]["qty"] = int(self.items[item_code]["qty"] + 1)
        else:
            self.items[item_code] = {"name": item_name, "price": price, "qty": 1, "currency": currency}
        self.refresh_table()

    def update_qty(self, item_code: str, change: int):
        if item_code in self.items:
            self.items[item_code]["qty"] = int(self.items[item_code]["qty"] + change)
            if self.items[item_code]["qty"] <= 0:
                del self.items[item_code]
            self.refresh_table()

    def update_qty_absolute(self, item_code: str, new_qty_str: str):
        try:
            new_qty = int(float(new_qty_str))
            if new_qty > 0:
                self.items[item_code]["qty"] = new_qty
            else:
                del self.items[item_code]
            self.refresh_table()
        except (ValueError, KeyError):
            pass

    def refresh_table(self):
        self.table.setRowCount(0)
        total_qty = 0
        self.total_amount = 0.0

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
            qty_lbl.setStyleSheet("font-weight: 700; font-size: 14px; color: white; min-width: 30px;")
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
            rate_lbl = QLabel(f"UZS {item['price']:,.0f}")
            rate_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rate_lbl.setStyleSheet("color: #94a3b8; font-weight: 600; font-size: 13px;")
            self.table.setCellWidget(row, 2, rate_lbl)

            # AMOUNT
            amt = item['qty'] * item['price']
            amt_lbl = QLabel(f"UZS {amt:,.0f}")
            amt_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            amt_lbl.setStyleSheet("font-weight: 700; font-size: 14px; color: white;")
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

            total_qty += item['qty']
            self.total_amount += amt

        # Update totals
        if hasattr(self, 'total_label'):
            self.total_label.setText(f"UZS {self.total_amount:,.0f}")
        if hasattr(self, 'total_qty_label'):
            self.total_qty_label.setText(str(total_qty))
        
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
        self.refresh_table()

    def handle_checkout(self):
        if not self.items:
            InfoDialog(self, "Xatolik", "Savat bo'sh!", kind="warning").exec()
            return

        ticket_number = self.ticket_input.text().strip()
        selected_customer = self.customer_combo.currentText().strip() or "guest"

        # if self.current_order_type in TICKET_ORDER_TYPES and not ticket_number:
        #    InfoDialog(self, "Xatolik", "Stiker raqamini kiriting!", kind="warning").exec()
        #    return

        order_data = {
            "items": [{"item_code": k, **v} for k, v in self.items.items()],
            "total_amount": self.total_amount,
            "order_type": self.current_order_type,
            "ticket_number": ticket_number,
            "customer": selected_customer,
            "comment": self.comment_input.text().strip(),
        }
        self.checkout_requested.emit(order_data)
