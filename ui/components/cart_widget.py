from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QTableWidget, QTableWidgetItem, QPushButton, 
    QHeaderView, QFrame, QLineEdit, QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSignal

class CartWidget(QWidget):
    checkout_requested = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Mijoz tanlash (Header)
        self.customer_frame = QFrame()
        self.customer_frame.setStyleSheet("background-color: #252525; border-bottom: 1px solid #333333;")
        cust_layout = QHBoxLayout(self.customer_frame)
        cust_layout.setContentsMargins(20, 15, 20, 15)
        
        self.btn_customer = QPushButton("Walk-in Customer")
        self.btn_customer.setStyleSheet("text-align: left; background: transparent; color: #00d4ff; font-weight: bold; font-size: 16px; border: none;")
        cust_layout.addWidget(self.btn_customer)
        
        btn_add_cust = QPushButton("+")
        btn_add_cust.setFixedSize(32, 32)
        btn_add_cust.setStyleSheet("background: #333333; color: white; border-radius: 16px; font-weight: bold;")
        self.btn_add_customer = btn_add_cust
        cust_layout.addWidget(btn_add_cust)
        
        layout.addWidget(self.customer_frame)

        # 2. Savat jadvali (Table)
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Item", "Qty", "Total", ""])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 40)
        
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setStyleSheet("padding: 10px;")
        
        layout.addWidget(self.table)

        # 3. Summalar (Totals)
        self.totals_frame = QFrame()
        self.totals_frame.setObjectName("TotalsFrame")
        totals_layout = QVBoxLayout(self.totals_frame)
        totals_layout.setContentsMargins(20, 20, 20, 20)
        totals_layout.setSpacing(10)
        
        self.lbl_subtotal = self._create_total_row(totals_layout, "Subtotal:", "14px")
        self.lbl_tax = self._create_total_row(totals_layout, "Tax:", "14px")

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background-color: #444; margin: 5px 0;")
        totals_layout.addWidget(line)

        row_grand = QHBoxLayout()
        lbl_grand_text = QLabel("GRAND TOTAL")
        lbl_grand_text.setStyleSheet("font-size: 18px; font-weight: 900; color: #FFFFFF;")
        row_grand.addWidget(lbl_grand_text)
        
        self.lbl_grand_total = QLabel("0.00")
        self.lbl_grand_total.setStyleSheet("font-size: 24px; font-weight: 900; color: #00d4ff;")
        self.lbl_grand_total.setAlignment(Qt.AlignmentFlag.AlignRight)
        row_grand.addWidget(self.lbl_grand_total)
        totals_layout.addLayout(row_grand)
        
        layout.addWidget(self.totals_frame)

        # 4. Checkout Tugmasi
        self.btn_pay = QPushButton("PAY")
        self.btn_pay.setObjectName("PayBtn")
        self.btn_pay.clicked.connect(self.on_checkout)
        layout.addWidget(self.btn_pay)

    def _create_total_row(self, layout, label_text, font_size):
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setStyleSheet(f"color: #888; font-size: {font_size};")
        row.addWidget(lbl)
        
        val = QLabel("0.00")
        val.setStyleSheet(f"color: white; font-size: {font_size}; font-weight: bold;")
        val.setAlignment(Qt.AlignmentFlag.AlignRight)
        row.addWidget(val)
        layout.addLayout(row)
        return val

    def add_item(self, item_data, qty=1):
        item_code = item_data['item_code']
        found_row = -1
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == item_code:
                found_row = row
                break
        
        if found_row >= 0:
            self._update_item_qty(found_row, qty)
        else:
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # Item Name
            name_item = QTableWidgetItem(item_data['item_name'])
            name_item.setData(Qt.ItemDataRole.UserRole, item_code)
            name_item.setData(Qt.ItemDataRole.UserRole + 1, item_data)
            name_item.setToolTip(item_data['item_name'])
            self.table.setItem(row, 0, name_item)
            
            # Qty (with buttons)
            qty_widget = QWidget()
            qty_layout = QHBoxLayout(qty_widget)
            qty_layout.setContentsMargins(0, 0, 0, 0)
            qty_layout.setSpacing(5)
            
            btn_minus = QPushButton("-")
            btn_minus.setFixedSize(24, 24)
            btn_minus.setStyleSheet("background: #333; color: white; border-radius: 4px; font-weight: bold;")
            btn_minus.clicked.connect(lambda: self._change_qty_from_sender(-1))
            
            lbl_qty = QLabel(str(qty))
            lbl_qty.setFixedWidth(20)
            lbl_qty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_qty.setStyleSheet("font-weight: bold;")
            
            btn_plus = QPushButton("+")
            btn_plus.setFixedSize(24, 24)
            btn_plus.setStyleSheet("background: #333; color: white; border-radius: 4px; font-weight: bold;")
            btn_plus.clicked.connect(lambda: self._change_qty_from_sender(1))
            
            qty_layout.addWidget(btn_minus)
            qty_layout.addWidget(lbl_qty)
            qty_layout.addWidget(btn_plus)
            
            self.table.setCellWidget(row, 1, qty_widget)
            
            # Amount
            self.table.setItem(row, 2, QTableWidgetItem(f"{qty * item_data['price']:,}"))
            
            # Remove
            btn_remove = QPushButton("×")
            btn_remove.setStyleSheet("color: #ff5252; font-size: 18px; background: transparent; border: none;")
            btn_remove.clicked.connect(self._remove_row_from_sender)
            self.table.setCellWidget(row, 3, btn_remove)
            
        self.update_totals()

    def _update_item_qty(self, row, delta):
        qty_widget = self.table.cellWidget(row, 1)
        if not qty_widget: return
        lbl_qty = qty_widget.layout().itemAt(1).widget()
        current_qty = float(lbl_qty.text())
        new_qty = max(0, current_qty + delta)
        
        if new_qty == 0:
            self.table.removeRow(row)
        else:
            lbl_qty.setText(str(new_qty))
            item_info = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1)
            price = item_info['price']
            self.table.setItem(row, 2, QTableWidgetItem(f"{new_qty * price:,}"))
        
        self.update_totals()

    def _find_row_by_widget(self, widget):
        for row in range(self.table.rowCount()):
            for col in (1, 3):
                cell_widget = self.table.cellWidget(row, col)
                if cell_widget is widget:
                    return row
                if cell_widget and cell_widget.isAncestorOf(widget):
                    return row
        return -1

    def _change_qty_from_sender(self, delta):
        sender = self.sender()
        row = self._find_row_by_widget(sender)
        if row >= 0:
            self._update_item_qty(row, delta)

    def _remove_row_from_sender(self):
        sender = self.sender()
        row = self._find_row_by_widget(sender)
        if row >= 0:
            self.remove_row(row)

    def remove_row(self, row):
        self.table.removeRow(row)
        self.update_totals()

    def update_totals(self):
        subtotal = 0
        tax = 0
        for row in range(self.table.rowCount()):
            total_str = self.table.item(row, 2).text().replace(',', '')
            line_total = float(total_str)
            subtotal += line_total

            item_info = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1) or {}
            qty_widget = self.table.cellWidget(row, 1)
            if qty_widget:
                lbl_qty = qty_widget.layout().itemAt(1).widget()
                qty = float(lbl_qty.text())
                tax_rate = float(item_info.get("tax_rate") or 0)
                # tax_rate item narxidan kelgan foiz stavka bo'lsa, satr bo'yicha qo'shamiz.
                tax += ((item_info.get("price", 0) * qty) * tax_rate) / 100.0

        grand_total = subtotal + tax
        
        self.lbl_subtotal.setText(f"{subtotal:,.2f}")
        self.lbl_tax.setText(f"{tax:,.2f}")
        self.lbl_grand_total.setText(f"{grand_total:,.2f}")
        
        self.btn_pay.setEnabled(grand_total > 0)

    def on_checkout(self):
        cart_data = {
            "items": [],
            "subtotal": 0,
            "tax": 0,
            "discount": 0,
            "grand_total": 0,
            "customer": self.btn_customer.text()
        }
        
        for row in range(self.table.rowCount()):
            item_info = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1)
            qty_widget = self.table.cellWidget(row, 1)
            lbl_qty = qty_widget.layout().itemAt(1).widget()
            qty = float(lbl_qty.text())
            
            cart_data["items"].append({
                **item_info,
                "qty": qty,
                "amount": qty * item_info['price']
            })
            cart_data["subtotal"] += qty * item_info['price']
            cart_data["tax"] += ((item_info.get("price", 0) * qty) * float(item_info.get("tax_rate") or 0)) / 100.0

        cart_data["grand_total"] = cart_data["subtotal"] + cart_data["tax"]
        self.checkout_requested.emit(cart_data)

    def set_customer(self, customer_name: str):
        self.btn_customer.setText(customer_name or "Walk-in Customer")
