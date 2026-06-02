import sys

from core.paths import BASE_DIR
# Add project root to sys.path
sys.path.insert(0, BASE_DIR)

from PyQt6.QtWidgets import QApplication

from core.api import FrappeAPI
from core.config import clear_credentials
from core.logger import get_logger
from database.models import db
from ui.login_window import LoginWindow
from ui.main_window import MainWindow
from ui.theme_manager import ThemeManager

logger = get_logger(__name__)


def main():
    # Windows monoblok/notebooklarda ekran masshtabi (125%/150%) tufayli
    # tugmalar siqilib/yopishib qolmasligi uchun — Qt fractional scaling'ni
    # silliq boshqarsin. QApplication'dan OLDIN o'rnatilishi shart.
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QGuiApplication
    try:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass

    app = QApplication(sys.argv)
    ThemeManager.initialize(app)

    shared_api = FrappeAPI()
    windows = {"main": None, "login": None}

    def show_login():
        if windows["main"]:
            windows["main"].close()
            windows["main"] = None
        windows["login"] = LoginWindow(shared_api)
        windows["login"].login_successful.connect(show_main)
        windows["login"].show()

    def show_main():
        if windows["login"]:
            windows["login"].close()
            windows["login"] = None
        if windows["main"]:
            # Mavjud oynani yopamiz (til o'zgarganda qayta qurish uchun).
            windows["main"].close()
            windows["main"].deleteLater()
            windows["main"] = None
        windows["main"] = MainWindow(shared_api)
        windows["main"].logout_requested.connect(handle_logout)
        windows["main"].relaunch_requested.connect(handle_relaunch)
        windows["main"].show()

    def handle_relaunch():
        # Til o'zgarganda asosiy oynani yangi tilda qaytadan quramiz.
        logger.info("Asosiy oyna qayta yuklanmoqda (til o'zgardi)")
        show_main()

    def handle_logout():
        logger.info("Foydalanuvchi tizimdan chiqdi")
        clear_credentials()
        shared_api.reload_config()
        show_login()

    if shared_api.is_configured():
        show_main()
    else:
        show_login()

    logger.info("Ilova ishga tushdi")
    try:
        exit_code = app.exec()
    finally:
        # Ilova yopilganda SQLite ulanishini toza qilib yopamiz.
        try:
            if not db.is_closed():
                db.close()
        except Exception as e:
            logger.debug("DB yopishda xato: %s", e)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
