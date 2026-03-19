from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QFrame, QDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from core.api import FrappeAPI
from core.config import persist_login_config

class LoginWindow(QDialog):
    login_successful = pyqtSignal()

    def __init__(self, api: FrappeAPI):
        super().__init__()
        self.api = api
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Kirish - PosAwesome")
        self.setFixedSize(400, 600)
        self.setStyleSheet("""
            QDialog { background-color: #121212; }
            QLabel { color: #aaaaaa; font-size: 14px; }
            QLineEdit { 
                background-color: #1e1e1e; 
                border: 1px solid #333; 
                border-radius: 8px; 
                padding: 12px; 
                color: white;
                font-size: 14px;
            }
            QLineEdit:focus { border: 1px solid #00d4ff; }
            QPushButton#LoginBtn {
                background-color: #00d4ff;
                color: black;
                font-weight: bold;
                font-size: 16px;
                border-radius: 8px;
                padding: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 40, 30, 40)

        # Logo
        logo = QLabel("PosAwesome")
        logo.setStyleSheet("color: #00d4ff; font-size: 32px; font-weight: bold; margin-bottom: 20px;")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        # Server URL
        layout.addWidget(QLabel("Server URL:"))
        self.input_url = QLineEdit()
        self.input_url.setPlaceholderText("http://localhost:8000")
        layout.addWidget(self.input_url)

        # Site Name (Optional for single site, required for multi-site bench)
        layout.addWidget(QLabel("Site Name (Multi-site uchun):"))
        self.input_site = QLineEdit()
        self.input_site.setPlaceholderText("posawesome.local")
        layout.addWidget(self.input_site)

        # API Key / User
        layout.addWidget(QLabel("Username:"))
        self.input_user = QLineEdit()
        self.input_user.setPlaceholderText("Administrator")
        layout.addWidget(self.input_user)

        # API Secret / Password
        layout.addWidget(QLabel("Parol:"))
        self.input_pwd = QLineEdit()
        self.input_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.input_pwd)

        layout.addStretch()

        # Xatolik xabari
        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color: #ff5252; font-size: 12px;")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_error)

        # Kirish tugmasi
        self.btn_login = QPushButton("KIRISH")
        self.btn_login.setObjectName("LoginBtn")
        self.btn_login.clicked.connect(self.handle_login)
        layout.addWidget(self.btn_login)

    def handle_login(self):
        url = self.input_url.text().strip()
        site = self.input_site.text().strip()
        user = self.input_user.text().strip()
        pwd = self.input_pwd.text().strip()

        if not url or not user or not pwd:
            self.lbl_error.setText("Barcha maydonlarni to'ldiring!")
            return

        self.btn_login.setEnabled(False)
        self.btn_login.setText("TEKSHIRILMOQDA...")
        self.lbl_error.setText("")
        
        # Login mantiqi
        success, message, data = self.api.login_with_password(url, user, pwd, site)
        
        if success:
            # Parolni faylda saqlamasdan auth sozlamalarini saqlaymiz.
            persist_login_config(url=url, site=site, user=user, save_password=False)
            self.api.reload_config()
            self.login_successful.emit()
            self.accept()
        else:
            self.lbl_error.setText(message)
            self.btn_login.setEnabled(True)
            self.btn_login.setText("KIRISH")
