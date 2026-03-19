from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QFrame, QGridLayout, QWidget, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from core.config import load_config
from database.invoice_processor import save_offline_invoice

class CheckoutWindow(QDialog):
    payment_submitted = pyqtSignal(object)

    def __init__(self, cart_data):
        super().__init__()
        self.cart_data = cart_data
        self.grand_total = cart_data["grand_total"]
        self.selected_mop = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("To'lovni amalga oshirish")
        self.setFixedSize(550, 700)
        self.setStyleSheet("""
            QDialog { background-color: #121212; }
            QLabel { color: #888; font-weight: bold; font-size: 13px; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(25)

        # 1. Grand Total Display (Hero section)
        total_frame = QFrame()
        total_frame.setStyleSheet("""
            background-color: #1e1e1e; 
            border-radius: 16px; 
            border: 1px solid #333;
        """)
        total_layout = QVBoxLayout(total_frame)
        total_layout.setContentsMargins(20, 30, 20, 30)
        total_layout.setSpacing(10)
        
        lbl_h = QLabel("TO'LANISHI KERAK")
        lbl_h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        total_layout.addWidget(lbl_h)
        
        self.lbl_grand = QLabel(f"{self.grand_total:,.2f} UZS")
        self.lbl_grand.setStyleSheet("font-size: 42px; font-weight: 900; color: #00d4ff;")
        self.lbl_grand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        total_layout.addWidget(self.lbl_grand)
        
        layout.addWidget(total_frame)

        # 2. Payment Methods
        layout.addWidget(QLabel("TO'LOV USULINI TANLANG"))
        self.mop_container = QWidget()
        self.mop_layout = QGridLayout(self.mop_container)
        self.mop_layout.setContentsMargins(0, 0, 0, 0)
        self.mop_layout.setSpacing(12)
        
        config = load_config()
        mops = config.get("payment_methods", ["Cash"])
        self.mop_buttons = []
        
        for i, mop in enumerate(mops):
            btn = QPushButton(mop.upper())
            btn.setCheckable(True)
            btn.setFixedHeight(55)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #1e1e1e;
                    border: 1px solid #333;
                    border-radius: 10px;
                    color: #FFFFFF;
                    font-weight: 900;
                    letter-spacing: 0.5px;
                }
                QPushButton:checked {
                    background-color: #00d4ff;
                    color: #000000;
                    border: none;
                }
                QPushButton:hover:!checked {
                    background-color: #252525;
                }
            """)
            btn.clicked.connect(lambda checked, m=mop, b=btn: self.select_mop(m, b))
            self.mop_layout.addWidget(btn, i // 2, i % 2)
            self.mop_buttons.append(btn)
            
            if i == 0:
                btn.setChecked(True)
                self.selected_mop = mop

        layout.addWidget(self.mop_container)

        # 3. Input Amount
        input_layout = QVBoxLayout()
        input_layout.setSpacing(10)
        input_layout.addWidget(QLabel("TO'LANGAN SUMMA"))
        
        self.input_paid = QLineEdit()
        self.input_paid.setFixedHeight(65)
        self.input_paid.setText(str(int(self.grand_total)))
        self.input_paid.setStyleSheet("""
            font-size: 32px; 
            font-weight: 900; 
            color: #FFFFFF; 
            text-align: center;
            background-color: #1e1e1e;
            border: 1px solid #333;
        """)
        self.input_paid.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.input_paid.textChanged.connect(self.calculate_change)
        input_layout.addWidget(self.input_paid)
        layout.addLayout(input_layout)

        # 4. Change (Qaytim)
        change_layout = QHBoxLayout()
        change_layout.addWidget(QLabel("QAYTIM:"))
        self.lbl_change = QLabel("0.00 UZS")
        self.lbl_change.setStyleSheet("font-size: 24px; font-weight: 900; color: #66bb6a;")
        self.lbl_change.setAlignment(Qt.AlignmentFlag.AlignRight)
        change_layout.addWidget(self.lbl_change)
        layout.addLayout(change_layout)

        layout.addStretch()

        # 5. Submit Button
        self.btn_submit = QPushButton("TO'LOVNI YAKUNLASH")
        self.btn_submit.setObjectName("PrimaryBtn") # Uses GLOBAL_STYLE
        self.btn_submit.setFixedHeight(75)
        self.btn_submit.clicked.connect(self.on_submit)
        layout.addWidget(self.btn_submit)

    def select_mop(self, mop, button):
        for btn in self.mop_buttons:
            btn.setChecked(False)
        button.setChecked(True)
        self.selected_mop = mop

    def calculate_change(self):
        try:
            val = self.input_paid.text().replace(',', '')
            paid = float(val or 0)
            change = max(0, paid - self.grand_total)
            self.lbl_change.setText(f"{change:,.2f} UZS")
        except ValueError:
            self.lbl_change.setText("0.00 UZS")

    def on_submit(self):
        try:
            val = self.input_paid.text().replace(',', '')
            paid = float(val or 0)
            if not self.selected_mop:
                QMessageBox.warning(self, "To'lov", "To'lov usulini tanlang.")
                return

            if paid <= 0:
                QMessageBox.warning(self, "To'lov", "To'langan summa 0 dan katta bo'lishi kerak.")
                return

            if paid < self.grand_total:
                QMessageBox.warning(self, "To'lov", "To'langan summa umumiy summadan kam bo'lmasligi kerak.")
                return

            config = load_config()
            invoice_payload = {
                "customer": self.cart_data["customer"],
                "pos_profile": config.get("pos_profile"),
                "company": config.get("company"),
                "total_qty": sum(it["qty"] for it in self.cart_data["items"]),
                "grand_total": self.grand_total,
                "net_total": self.cart_data.get("subtotal", self.grand_total),
                "discount_amount": self.cart_data.get("discount", 0),
                "paid_amount": paid,
                "items": self.cart_data["items"],
                "payments": [
                    {
                        "mode_of_payment": self.selected_mop,
                        "amount": paid,
                        "account": None
                    }
                ]
            }
            
            inv = save_offline_invoice(invoice_payload)
            self.payment_submitted.emit(inv)
            self.accept()
        except ValueError:
            QMessageBox.warning(self, "To'lov", "To'langan summani to'g'ri formatda kiriting.")
