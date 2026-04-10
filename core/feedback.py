import sys
import threading

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from core.logger import get_logger

logger = get_logger(__name__)


class SoundFeedback:
    _timers = []

    @classmethod
    def success(cls):
        if sys.platform == "win32":
            cls._play_windows_pattern([(1046, 70), (1318, 90)])
            return
        cls._play_beep_pattern([0, 110])

    @classmethod
    def error(cls):
        if sys.platform == "win32":
            cls._play_windows_pattern([(220, 120), (180, 170)])
            return
        cls._play_beep_pattern([0, 90, 210])

    @classmethod
    def _play_windows_pattern(cls, notes):
        try:
            import winsound
        except Exception:
            cls._play_beep_pattern([0, 110] if len(notes) <= 2 else [0, 90, 210])
            return

        def worker():
            try:
                for freq, duration in notes:
                    winsound.Beep(int(freq), int(duration))
            except Exception as e:
                logger.debug("Windows tone chalmadi: %s", e)
                QTimer.singleShot(0, QApplication.beep)

        threading.Thread(target=worker, daemon=True).start()

    @classmethod
    def _play_beep_pattern(cls, delays_ms):
        app = QApplication.instance()
        if not app:
            return

        for delay in delays_ms:
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(lambda t=timer: cls._on_timer_timeout(t))
            cls._timers.append(timer)
            timer.start(max(int(delay), 0))

    @classmethod
    def _on_timer_timeout(cls, timer: QTimer):
        try:
            app = QApplication.instance()
            if app:
                app.beep()
        finally:
            try:
                cls._timers.remove(timer)
            except ValueError:
                pass
            timer.deleteLater()
