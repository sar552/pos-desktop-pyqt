"""
Barcode listeners for HID (keyboard-emulation) scanners and Serial/COM scanners.

Design notes
------------
* `BarcodeManager` owns all listeners and re-emits a single `barcode_scanned`
  signal so the UI has one entry-point.

* `BarcodeKeyboardListener` is a QApplication-wide event filter.  Distinguishing
  a real human typing from a fast HID scanner burst requires looking at the
  inter-key interval.  Because the interval can only be measured starting from
  the *second* key, naive implementations leak the first burst character into
  whichever widget happens to be focused.

  To avoid that, the listener swallows the first key, stores it as
  `_pending_first`, and starts a short timer.  If a second key arrives within
  `barcode_keyboard_threshold_ms` the pair is treated as a scanner burst.
  Otherwise the pending key is "released" back into the original target —
  preserving normal typing with a tiny (~30–40 ms) latency.

* Inputs may opt out via the dynamic property `disable_barcode_capture=True`
  (or the legacy `disable_virtual_keyboard=True`).  For an opted-out input
  the listener does NOT delay or capture anything — the field behaves like a
  regular QLineEdit.  Use this only for fields where scanner input is never
  expected (passwords, customer names typed by hand).

* `BarcodeSerialListener` runs in its own QThread and emits `error_occurred`
  so the UI can surface port problems instead of silently failing.
"""

from __future__ import annotations

import time

from PyQt6.QtCore import QCoreApplication, QEvent, QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QLineEdit

from core.config import load_config
from core.logger import get_logger

try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:  # pragma: no cover - environment dependent
    SERIAL_AVAILABLE = False

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Serial / COM scanner
# ─────────────────────────────────────────────────────────────────────────────
class BarcodeSerialListener(QThread):
    """Listen for barcode data on a Serial/COM port and emit complete codes."""

    barcode_scanned = pyqtSignal(str)
    error_occurred = pyqtSignal(str, str)  # (port, message)

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 0.1):
        super().__init__()
        self.port = port
        self.baudrate = int(baudrate or 9600)
        self.timeout = float(timeout or 0.1)
        self._running = False
        self._serial_conn = None

    def run(self):
        if not SERIAL_AVAILABLE:
            msg = "pyserial kutubxonasi topilmadi. `pip install pyserial` qiling."
            logger.error(msg)
            self.error_occurred.emit(self.port, msg)
            return

        try:
            self._serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
            )
        except Exception as e:
            msg = f"Serial port {self.port} ulanishda xato: {e}"
            logger.error(msg)
            self.error_occurred.emit(self.port, str(e))
            return

        self._running = True
        logger.info("Skaner porti ochildi: %s @ %d", self.port, self.baudrate)
        buffer = ""
        try:
            while self._running:
                try:
                    in_waiting = self._serial_conn.in_waiting
                except Exception as e:
                    logger.error("Port %s holatini o'qishda xato: %s", self.port, e)
                    self.error_occurred.emit(self.port, str(e))
                    break

                if in_waiting <= 0:
                    time.sleep(0.01)
                    continue

                try:
                    data = self._serial_conn.read(in_waiting).decode("utf-8", errors="ignore")
                except Exception as e:
                    logger.error("Portdan o'qishda xato (%s): %s", self.port, e)
                    continue

                for ch in data:
                    if ch in ("\r", "\n"):
                        code = buffer.strip()
                        buffer = ""
                        if code:
                            self.barcode_scanned.emit(code)
                    elif ch.isprintable():
                        buffer += ch
                        if len(buffer) > 256:  # safety bound — drop garbage
                            buffer = buffer[-256:]
        finally:
            try:
                if self._serial_conn and self._serial_conn.is_open:
                    self._serial_conn.close()
            except Exception:
                pass
            self._running = False
            logger.info("Skaner porti yopildi: %s", self.port)

    def stop(self):
        self._running = False
        self.wait(2000)


# ─────────────────────────────────────────────────────────────────────────────
#  HID (keyboard-emulation) scanner
# ─────────────────────────────────────────────────────────────────────────────
BARCODE_OPT_OUT_PROPERTIES = ("disable_barcode_capture", "disable_virtual_keyboard")


def _input_opts_out(widget) -> bool:
    if widget is None:
        return False
    for prop in BARCODE_OPT_OUT_PROPERTIES:
        try:
            if bool(widget.property(prop)):
                return True
        except Exception:
            continue
    return False


class BarcodeKeyboardListener(QObject):
    """Global event filter that distinguishes scanner bursts from human typing.

    Emits ``barcode_scanned(str)`` and ``input_polluted(QObject, str)``.  The
    latter fires when a scanner burst was detected mid-stream and the prefix
    had already leaked into a QLineEdit — the UI layer should clean it up.
    """

    barcode_scanned = pyqtSignal(str)
    input_polluted = pyqtSignal(object, str)  # (widget, leaked_prefix)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.buffer = ""
        self.last_key_time = 0.0
        self.last_scan_emit_time = 0.0
        self._is_scanner_active = False
        # Burst boshlanganda fokuslangan widget — agar prefix leak bo'lsa,
        # emit qilinganida tozalash uchun input_polluted bilan yuboramiz.
        self._burst_leak_target = None

        # First-key-delay state.
        self._pending_first: tuple[str, float, object] | None = None
        self._first_key_timer = QTimer(self)
        self._first_key_timer.setSingleShot(True)
        self._first_key_timer.timeout.connect(self._on_first_key_timeout)

        # Idle flush — burst without terminator.
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._emit_if_ready)

        # Re-entrancy guard for replayed events.
        self._replaying = False

        self._load_thresholds()

    # ── config ────────────────────────────────────────────────────────────
    def _load_thresholds(self):
        cfg = load_config()
        # Real HID skanerlar 5-20ms da yozadi, odam ~80-150ms — 30ms xavfsiz chegara.
        self.threshold = max(0.005, (cfg.get("barcode_keyboard_threshold_ms", 30) or 30) / 1000.0)
        # Idle: burst tugagandan keyin shu vaqt o'tsa buferni emit qilamiz.
        self.idle_timeout = max(0.01, (cfg.get("barcode_keyboard_idle_ms", 80) or 80) / 1000.0)
        self.min_length = max(1, int(cfg.get("barcode_min_length", 5) or 5))
        self.max_length = max(self.min_length, int(cfg.get("barcode_max_length", 64) or 64))
        # Skanerdan keyin trailing Enter/Tab-ni "yutish" oynasi.
        self.trailing_terminator_window = 0.25
        # Delay timer: threshold + biroz zaxira jitter uchun.
        self._first_key_delay_ms = int(self.threshold * 1000) + 15

    def reload_config(self):
        """Sozlamalar UI orqali o'zgartirilganda chaqiriladi."""
        self._reset_all()
        self._load_thresholds()

    # ── internals ─────────────────────────────────────────────────────────
    def _reset_all(self):
        """Hech qanday yon ta'sirsiz holatni tozalaydi."""
        self.buffer = ""
        self._is_scanner_active = False
        self._burst_leak_target = None
        if self._idle_timer.isActive():
            self._idle_timer.stop()
        if self._first_key_timer.isActive():
            self._first_key_timer.stop()
        self._pending_first = None

    def _arm_idle_timer(self):
        self._idle_timer.start(int(self.idle_timeout * 1000))

    def _clean(self, text: str) -> str:
        return "".join(ch for ch in text if ch.isprintable()).strip()

    def _emit_buffer_if_ready(self, leak_target=None) -> bool:
        """If the buffer holds a valid burst, emit it.  Returns True if emitted."""
        cleaned = self._clean(self.buffer)
        # leak_target ko'rsatilmasa, burst boshlanganda eslab qolingan widget'ni olamiz.
        if leak_target is None:
            leak_target = self._burst_leak_target
        self._reset_all()
        if len(cleaned) >= self.min_length:
            self.last_scan_emit_time = time.time()
            # Har doim emit qilamiz — qabul qiluvchi prefix mosligini tekshirib tozalaydi.
            self.input_polluted.emit(leak_target, cleaned)
            self.barcode_scanned.emit(cleaned)
            return True
        return False

    def _emit_if_ready(self):
        """Idle timer callback."""
        self._emit_buffer_if_ready()

    def _on_first_key_timeout(self):
        """Delay expired without a follow-up key — it was human typing.  Release."""
        if self._pending_first is None:
            return
        text, _, target = self._pending_first
        self._pending_first = None
        self._release_key(target, text)

    def _release_key(self, target, text: str):
        """Re-deliver a previously-swallowed key to its original target."""
        if not text:
            return
        # Saqlangan target o'chirilgan (deleted C++ object) bo'lishi mumkin —
        # masalan checkout oynasi yopilgandan keyin. Tekshiramiz; o'chirilgan
        # bo'lsa joriy fokusga qaytamiz (aks holda postEvent crash beradi).
        if target is not None:
            try:
                target.objectName()  # arzon chaqiruv — o'chirilgan bo'lsa RuntimeError
            except RuntimeError:
                target = None
        if target is None:
            try:
                target = QApplication.focusWidget()
            except Exception:
                target = None
        if target is None:
            return
        self._replaying = True
        try:
            # QLineEdit'da insert() — eng aniq usul, signallar to'g'ri ishlaydi.
            if isinstance(target, QLineEdit):
                try:
                    target.insert(text)
                    return
                except RuntimeError:
                    return
                except Exception:
                    pass
            # Boshqa widgetlar uchun event qayta yuboramiz.
            ev = QKeyEvent(
                QEvent.Type.KeyPress,
                Qt.Key.Key_unknown,
                Qt.KeyboardModifier.NoModifier,
                text,
            )
            try:
                QCoreApplication.postEvent(target, ev)
            except RuntimeError:
                pass
        finally:
            self._replaying = False

    # ── event filter ──────────────────────────────────────────────────────
    def eventFilter(self, obj, event):
        if self._replaying:
            return False  # o'zimiz qayta yuborgan event — qo'l tegmaslik
        if event.type() != QEvent.Type.KeyPress:
            return False

        modifiers = event.modifiers()
        if modifiers & (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
        ):
            # Modifier kombinatsiyalari — har doim foydalanuvchi.
            self._flush_pending_as_human()
            self._reset_all()
            return False

        key = event.key()

        # ── Terminator: Enter / Return / Tab ──────────────────────────────
        if key in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Tab):
            # Pending first key — burst'ning bir qismi ekan.
            if self._pending_first is not None:
                text, _, target = self._pending_first
                self._first_key_timer.stop()
                self._pending_first = None
                # Burst hali boshlanmagan (faqat 1 belgi) — barcode juda qisqa.
                # min_length tekshiruvi keyin baribir filtrlaydi; lekin agar
                # leak bo'lgan bo'lsa, target inputni tozalashga ishora qoldiramiz.
                self.buffer = text + self.buffer
                self._is_scanner_active = True
                emitted = self._emit_buffer_if_ready()
                if emitted:
                    return True
                # Min uzunlikdan kichik — pending'ni release qilamiz va terminator'ni o'tkazib yuboramiz.
                self._release_key(target, text)
                return False

            # Burst aktiv edi — flush qilamiz.
            if self._is_scanner_active and self.buffer:
                if self._emit_buffer_if_ready():
                    return True

            # Trailing terminator window — yutib yuboramiz.
            now = time.time()
            if (now - self.last_scan_emit_time) < self.trailing_terminator_window:
                self._reset_all()
                return True

            self._reset_all()
            return False

        # ── Matn ─────────────────────────────────────────────────────────
        text = event.text()
        if not text or not all(ch.isprintable() for ch in text):
            # Backspace, arrow keys va h.k. — odam.
            self._flush_pending_as_human()
            self._reset_all()
            return False

        # ── Opt-out QLineEdit: hech qanday ushlash yo'q ────────────────────
        if isinstance(obj, QLineEdit) and _input_opts_out(obj):
            self._flush_pending_as_human()
            self._reset_all()
            return False

        now = time.time()

        # ── Pending first key bo'lsa, hozir ikkinchi tugma keldi ─────────
        if self._pending_first is not None:
            pending_text, pending_time, pending_target = self._pending_first
            interval = now - pending_time
            self._first_key_timer.stop()
            self._pending_first = None

            if interval < self.threshold:
                # ✅ Burst tasdiqlandi: pending + bu = boshlang'ich bufer.
                self.buffer = pending_text + text
                if len(self.buffer) > self.max_length:
                    self.buffer = self.buffer[-self.max_length:]
                self._is_scanner_active = True
                # Burst boshlangan paytdagi fokus — leak bo'lsa shuni tozalaymiz.
                self._burst_leak_target = pending_target or obj
                self.last_key_time = now
                self._arm_idle_timer()
                return True

            # ❌ Tezligi past edi — pending'ni release qilib, bu tugmani ham
            # o'tkazib yuboramiz (odam yozyapti).
            self._release_key(pending_target, pending_text)
            self.last_key_time = now
            return False

        # ── Burst davom etmoqda ───────────────────────────────────────────
        if self._is_scanner_active and self.buffer:
            interval = now - self.last_key_time
            self.last_key_time = now
            if interval < self.threshold:
                self.buffer += text
                if len(self.buffer) > self.max_length:
                    self.buffer = self.buffer[-self.max_length:]
                # Fokus o'zgargan bo'lsa — yangilab qo'yamiz.
                if self._burst_leak_target is None:
                    self._burst_leak_target = obj
                self._arm_idle_timer()
                return True
            # Burst sekinlashdi — buferni flush qilamiz va bu tugmani yangi
            # potential first key sifatida qabul qilamiz.
            self._emit_buffer_if_ready()
            # Pastdagi "yangi pending" mantig'iga tushadi.

        # ── Yangi potential first key — kichik kechikish bilan ushlab turamiz
        # `obj` — bu eventning aniq qabul qiluvchisi (odatda fokuslangan widget).
        target = obj if obj is not None else QApplication.focusWidget()
        self._pending_first = (text, now, target)
        self._first_key_timer.start(self._first_key_delay_ms)
        self.last_key_time = now
        return True  # swallow until we know what it is

    def _flush_pending_as_human(self):
        """Pending bo'lsa, uni release qilamiz (timerdan tashqari sabablarda)."""
        if self._pending_first is None:
            return
        text, _, target = self._pending_first
        self._first_key_timer.stop()
        self._pending_first = None
        self._release_key(target, text)


# ─────────────────────────────────────────────────────────────────────────────
#  Manager
# ─────────────────────────────────────────────────────────────────────────────
class BarcodeManager(QObject):
    """Aggregates HID + multiple Serial scanners under one signal."""

    barcode_scanned = pyqtSignal(str)
    scanner_error = pyqtSignal(str, str)  # (port, message)
    input_polluted = pyqtSignal(object, str)  # (widget, leaked_prefix)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.serial_listeners: dict[str, BarcodeSerialListener] = {}
        self.keyboard_listener = BarcodeKeyboardListener(self)
        self.keyboard_listener.barcode_scanned.connect(self.barcode_scanned.emit)
        self.keyboard_listener.input_polluted.connect(self.input_polluted.emit)
        self._event_filter_installed_on = None

    # ── HID lifecycle ─────────────────────────────────────────────────────
    def install_keyboard_filter(self, app):
        """MainWindow ochilganda chaqiring — Login oynasi key'larni ushlamaydi."""
        if self._event_filter_installed_on is app:
            return
        if self._event_filter_installed_on is not None:
            try:
                self._event_filter_installed_on.removeEventFilter(self.keyboard_listener)
            except Exception:
                pass
        app.installEventFilter(self.keyboard_listener)
        self._event_filter_installed_on = app

    def uninstall_keyboard_filter(self):
        if self._event_filter_installed_on is None:
            return
        try:
            self._event_filter_installed_on.removeEventFilter(self.keyboard_listener)
        except Exception:
            pass
        self._event_filter_installed_on = None

    # ── Serial lifecycle ──────────────────────────────────────────────────
    def setup_scanners(self, ports: list):
        """Re-create serial listeners for the given list."""
        self.stop_all_serial()
        for port_cfg in ports or []:
            if isinstance(port_cfg, str):
                port_name, baud = port_cfg, 9600
            elif isinstance(port_cfg, dict):
                port_name = port_cfg.get("port")
                baud = port_cfg.get("baudrate", 9600)
            else:
                continue
            if not port_name:
                continue

            listener = BarcodeSerialListener(port_name, baudrate=baud)
            listener.barcode_scanned.connect(self.barcode_scanned.emit)
            listener.error_occurred.connect(self.scanner_error.emit)
            listener.start()
            self.serial_listeners[port_name] = listener
            logger.info("Skaner qo'shildi: %s @ %s", port_name, baud)

    def stop_all_serial(self):
        for listener in list(self.serial_listeners.values()):
            try:
                listener.stop()
            except Exception as e:
                logger.debug("Listener to'xtatishda xato: %s", e)
        self.serial_listeners.clear()

    # Backward-compatible alias used by older callers.
    def stop_all(self):
        self.stop_all_serial()
        self.uninstall_keyboard_filter()

    # ── Settings ──────────────────────────────────────────────────────────
    def reload_config(self):
        """Skaner sozlamalari o'zgartirilganda chaqiring."""
        self.keyboard_listener.reload_config()
