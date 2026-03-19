import sys
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow
from ui.login_window import LoginWindow
from core.api import FrappeAPI
from core.config import clear_credentials
from database.migrations import initialize_db

class POSApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.api = FrappeAPI()
        self.main_window = None
        self.login_window = None
        
        # 1. Baza jadvallarini yaratish/tekshirish
        initialize_db()

    def show_login(self):
        if self.main_window:
            self.main_window.close()
            self.main_window = None
            
        self.login_window = LoginWindow(self.api)
        if self.login_window.exec() == LoginWindow.DialogCode.Accepted:
            self.show_main()
        else:
            sys.exit(0)

    def show_main(self):
        if self.login_window:
            self.login_window.close()
            self.login_window = None
            
        self.main_window = MainWindow(self.api)
        self.main_window.logout_requested.connect(self.handle_logout)
        self.main_window.show()

    def handle_logout(self):
        clear_credentials()
        self.api.reload_config()
        self.show_login()

    def run(self):
        if not self.api.is_configured():
            self.show_login()
        else:
            self.show_main()
        sys.exit(self.app.exec())

def main():
    pos_app = POSApp()
    pos_app.run()

if __name__ == "__main__":
    main()
