from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QFrame, QComboBox, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
import json
from core.config import load_config

class PosOpeningDialog(QDialog):
    opening_completed = pyqtSignal(dict)

    def __init__(self, api, pos_profile):
        super().__init__()
        self.api = api
        self.pos_profile = pos_profile
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Kassani ochish")
        self.setFixedSize(400, 450)
        self.setStyleSheet("""
            QDialog { background-color: #121212; }
            QLabel { color: #aaaaaa; }
            QLineEdit { 
                background-color: #1e1e1e; border: 1px solid #333; 
                border-radius: 8px; padding: 10px; color: white;
            }
            QPushButton#OpenBtn {
                background-color: #66bb6a; color: black; 
                font-weight: bold; border-radius: 8px; padding: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        layout.addWidget(QLabel(f"POS Profil: {self.pos_profile}"))
        
        layout.addWidget(QLabel("Kassa qoldig'i (Naqd pul):"))
        self.input_amount = QLineEdit()
        self.input_amount.setPlaceholderText("0.00")
        self.input_amount.setText("0")
        layout.addWidget(self.input_amount)

        layout.addStretch()

        self.btn_open = QPushButton("KASSANI OCHISH")
        self.btn_open.setObjectName("OpenBtn")
        self.btn_open.clicked.connect(self.handle_open)
        layout.addWidget(self.btn_open)

    def handle_open(self):
        amount = self.input_amount.text()
        if not amount:
            QMessageBox.warning(self, "Xatolik", "Summani kiriting!")
            return

        self.btn_open.setEnabled(False)
        self.btn_open.setText("OCHILMOQDA...")

        # Frappe metodini chaqirish: posawesome.posawesome.api.shifts.create_opening_voucher
        # Bu metod posawesome backendida smena ochadi
        balance_details = [{"mode_of_payment": "Cash", "opening_amount": float(amount)}]
        config = load_config()
        company = config.get("company")
        if not company:
            QMessageBox.warning(self, "Xatolik", "Company sozlanmagan. Avval Sync qiling.")
            self.btn_open.setEnabled(True)
            self.btn_open.setText("KASSANI OCHISH")
            return
        
        success, response = self.api.call_method(
            "posawesome.posawesome.api.shifts.create_opening_voucher",
            {
                "pos_profile": self.pos_profile,
                "company": company,
                "balance_details": json.dumps(balance_details)
            }
        )

        if success:
            payload = response if isinstance(response, dict) else {"response": response}
            self.opening_completed.emit(payload)
            self.accept()
        else:
            QMessageBox.critical(self, "Xatolik", f"Smenani ochib bo'lmadi: {response}")
            self.btn_open.setEnabled(True)
            self.btn_open.setText("KASSANI OCHISH")
