from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QPushButton, QLineEdit, QWidget, QFrame, QApplication,
                             QLabel, QGraphicsDropShadowEffect, QSizePolicy)
from PyQt6.QtCore import pyqtSignal, Qt, QSize
from PyQt6.QtGui import QGuiApplication, QColor

from ui.theme_manager import ThemeManager
from core.i18n import tr, i18n


class TouchKeyboard(QDialog):
    text_confirmed = pyqtSignal(str)
    text_changed = pyqtSignal(str)  # Emitted on every key press

    def __init__(self, parent=None, initial_text="", title="Matn kiriting", is_numeric=False, is_password=False):
        super().__init__(parent)
        self.is_password = is_password
        self.setWindowTitle(title)
        # Sarlavha paneli kerak emas — ekran pastiga yopishib turadigan panel.
        # WindowDoesNotAcceptFocus: klaviatura yozilayotgan maydondan fokusni
        # o'g'irlamaydi — caret asl maydonda qoladi, telefondagidek.
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        # Ko'rsatilganda asl oynani faollashtirmaydi (fokus joyida qoladi).
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        # Yumaloq burchaklar ko'rinishi uchun fon shaffof bo'lsin.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(False)  # Allows interaction with parent (Item Grid)
        self.is_numeric = is_numeric
        self._caps = False
        self._letter_buttons = []
        # Klaviatura yozuv tili (UI tilidan mustaqil — telefondagi globus kabi).
        self._kb_lang = i18n.language if i18n.language in ("uz", "ru", "en") else "uz"
        self.colors = ThemeManager.get_theme_colors()
        self.init_ui(initial_text)
        self._dock_to_bottom()

    def set_target(self, text: str, title: str = ""):
        """Boshqa maydonga moslanganda matn va sarlavhani yangilaydi."""
        if title:
            self.setWindowTitle(title)
            if hasattr(self, "title_label"):
                self.title_label.setText(title)
        # Joriy matnni ko'rsatamiz (signal asl maydonga qaytib yozadi — zararsiz).
        self.input_field.setText(text or "")
        self.input_field.setCursorPosition(len(text or ""))

    def sync_text(self, text: str):
        """Target maydonda qo'lda (hardware klaviaturada) yozilgan matnni
        signal chiqarmasdan qabul qilish.

        Aks holda klaviaturaning ichki nusxasi eskirib, keyingi virtual tugma
        bosilganda foydalanuvchi yozgan harflar o'chib ketardi.
        """
        text = text or ""
        if self.input_field.text() == text:
            return
        self.input_field.blockSignals(True)
        self.input_field.setText(text)
        self.input_field.setCursorPosition(len(text))
        self.input_field.blockSignals(False)

    # ── Joylashuv ──────────────────────────────────────────────────────────
    def _dock_to_bottom(self):
        """Klaviaturani ekran pastiga, to'liq kenglikda joylashtiradi."""
        screen = self.screen() or QGuiApplication.primaryScreen()
        if self.parent() is not None and self.parent().screen() is not None:
            screen = self.parent().screen()
        geo = screen.availableGeometry()

        if self.is_numeric:
            height = min(460, int(geo.height() * 0.50))
            width = min(520, geo.width())
        else:
            # To'liq ekran kengligiga cho'zilmasin — keng ekranlarda tugmalar
            # juda keng/yassi bo'lib ketadi. Oqilona kenglikda, markazda.
            # 0.60 — 1366x768 monobloklarda pastki belgi qatori kesilmasligi
            # uchun (5 qator × min balandlik + sarlavha + footer sig'ishi kerak).
            height = min(640, int(geo.height() * 0.60))
            width = min(1180, int(geo.width() * 0.96))

        x = geo.x() + (geo.width() - width) // 2  # har doim markazda
        y = geo.y() + geo.height() - height
        self.setFixedSize(width, height)
        self.move(x, y)

    def showEvent(self, event):
        super().showEvent(event)
        # Ko'rsatilganda qayta joylashtiramiz (ekran/monitor o'zgargan bo'lishi mumkin).
        self._dock_to_bottom()

    # ── UI qurish ──────────────────────────────────────────────────────────
    def init_ui(self, initial_text):
        c = self.colors

        # Tashqi shaffof konteyner — ichida yumaloq panel turadi.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.panel = QFrame()
        self.panel.setObjectName("kbPanel")
        self.panel.setStyleSheet(f"""
            QFrame#kbPanel {{
                background: {c['bg_secondary']};
                border-top: 2px solid {c['accent']};
                border-top-left-radius: 18px;
                border-top-right-radius: 18px;
            }}
        """)
        # Panelga yengil soya — ustidagi kontentdan ajralib tursin.
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, -4)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.panel.setGraphicsEffect(shadow)
        outer.addWidget(self.panel)

        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(22, 14, 22, 18)
        layout.setSpacing(12)

        # 0. Sarlavha qatori — sarlavha matni + o'ng tomonda yopish (X)
        header = QHBoxLayout()
        header.setContentsMargins(2, 0, 2, 0)
        self.title_label = QLabel(self.windowTitle())
        self.title_label.setStyleSheet(
            f"border: none; background: transparent; color: {c['text_secondary']}; "
            f"font-size: 14px; font-weight: 700; letter-spacing: 0.3px;"
        )
        header.addWidget(self.title_label)
        header.addStretch(1)

        close_x = QPushButton("✕")
        close_x.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_x.setFixedSize(34, 34)
        close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        close_x.setStyleSheet(f"""
            QPushButton {{
                background: {c['bg_tertiary']};
                color: {c['text_secondary']};
                border: none; border-radius: 17px;
                font-size: 16px; font-weight: 700; padding: 0;
            }}
            QPushButton:hover {{ background: {c['error']}; color: white; }}
        """)
        close_x.clicked.connect(self.close)
        header.addWidget(close_x)
        layout.addLayout(header)

        # 1. Matn ko'rsatish maydoni
        display_frame = QFrame()
        display_frame.setStyleSheet(f"""
            QFrame {{
                background: {c['input_bg']};
                border: 1.5px solid {c['accent']};
                border-radius: 12px;
            }}
        """)
        display_layout = QVBoxLayout(display_frame)
        display_layout.setContentsMargins(6, 4, 6, 4)

        self.input_field = QLineEdit(initial_text)
        if self.is_password:
            # Parol maydoni uchun — displayda ham yulduzcha ko'rinadi.
            self.input_field.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_field.setStyleSheet(
            f"border: none; background: transparent; font-size: 26px; "
            f"font-weight: bold; padding: 10px; color: {c['text_primary']};"
        )
        self.input_field.textChanged.connect(lambda t: self.text_changed.emit(t))
        display_layout.addWidget(self.input_field)
        layout.addWidget(display_frame)

        # 2. Tugmalar maydoni — har bir qator alohida HBox (ustma-ust tushmaydi)
        self.keys_widget = QWidget()
        self.keys_widget.setStyleSheet("background: transparent;")
        self.keys_layout = QVBoxLayout(self.keys_widget)
        self.keys_layout.setSpacing(8)
        self.keys_layout.setContentsMargins(0, 0, 0, 0)

        if self.is_numeric:
            self.setup_numeric_layout()
        else:
            self.setup_full_layout()

        layout.addWidget(self.keys_widget, 1)

        # 3. Pastki tugmalar
        footer = QHBoxLayout()
        footer.setSpacing(10)
        btn_cancel = QPushButton(tr("YOPISH"))
        btn_cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_cancel.setMinimumHeight(54)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background: {c['bg_tertiary']}; color: {c['text_secondary']};
                font-weight: bold; font-size: 16px; border-radius: 12px;
                border: 1px solid {c['border']};
            }}
            QPushButton:hover {{ background: {c['bg_hover']}; }}
            QPushButton:pressed {{ background: {c['border']}; }}
        """)
        btn_cancel.clicked.connect(self.close)

        btn_ok = QPushButton(tr("TASDIQLASH  (OK)"))
        btn_ok.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_ok.setMinimumHeight(54)
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.setStyleSheet(f"""
            QPushButton {{
                background: {c['success']}; color: white;
                font-weight: bold; border-radius: 12px; font-size: 18px;
                border: none;
            }}
            QPushButton:hover {{ background: {c.get('success_border', c['success'])}; }}
            QPushButton:pressed {{ background: {c['success']}; }}
        """)
        btn_ok.clicked.connect(self.confirm)

        footer.addWidget(btn_cancel, 1)
        footer.addWidget(btn_ok, 2)
        layout.addLayout(footer)

    # Kengroq (bir necha tugma o'rnini egallaydigan) maxsus tugmalar uchun cho'zish koeffitsienti.
    _KEY_STRETCH = {'SPACE': 3, '⌫': 2, 'CLEAR': 2, 'CAPS': 2}

    def _add_row(self, keys):
        """Bitta qatorni HBox sifatida qo'shadi — tugmalar teng cho'ziladi."""
        row_layout = QHBoxLayout()
        row_layout.setSpacing(8)
        row_layout.setContentsMargins(0, 0, 0, 0)
        for key in keys:
            btn = self.create_key(key)
            row_layout.addWidget(btn, self._KEY_STRETCH.get(key, 1))
        self.keys_layout.addLayout(row_layout, 1)

    def setup_numeric_layout(self):
        rows = [
            ['7', '8', '9'],
            ['4', '5', '6'],
            ['1', '2', '3'],
            ['.', '0', '⌫'],
        ]
        for row in rows:
            self._add_row(row)

    # Yozuv tili bo'yicha harf qatorlari (uz/en — lotin, ru — kirill).
    _LETTER_ROWS = {
        "uz": [
            ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P', '⌫'],
            ['CAPS', 'A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', 'CLEAR'],
            ['Z', 'X', 'C', 'V', 'B', 'N', 'M', ',', '.', 'SPACE'],
        ],
        "en": [
            ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P', '⌫'],
            ['CAPS', 'A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', 'CLEAR'],
            ['Z', 'X', 'C', 'V', 'B', 'N', 'M', ',', '.', 'SPACE'],
        ],
        "ru": [
            ['Й', 'Ц', 'У', 'К', 'Е', 'Н', 'Г', 'Ш', 'Щ', 'З', 'Х', 'Ъ', '⌫'],
            ['CAPS', 'Ф', 'Ы', 'В', 'А', 'П', 'Р', 'О', 'Л', 'Д', 'Ж', 'Э', 'CLEAR'],
            ['Я', 'Ч', 'С', 'М', 'И', 'Т', 'Ь', 'Б', 'Ю', 'Ё', ',', '.', 'SPACE'],
        ],
    }
    _KB_LANG_ORDER = ["uz", "ru", "en"]

    def setup_full_layout(self):
        self._letter_buttons = []
        letter_rows = self._LETTER_ROWS.get(self._kb_lang, self._LETTER_ROWS["uz"])
        rows = [
            ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
            *letter_rows,
            # Apostrof (') — o'zbek lotinchada o'/g' uchun majburiy belgi.
            ['🌐', "'", '@', '-', '_', ':', '/', '#', '+', '='],
        ]
        for row in rows:
            self._add_row(row)

    def _cycle_kb_language(self):
        """Globus tugmasi: yozuv tilini uz → ru → en → uz tartibida almashtiradi."""
        try:
            idx = self._KB_LANG_ORDER.index(self._kb_lang)
        except ValueError:
            idx = 0
        self._kb_lang = self._KB_LANG_ORDER[(idx + 1) % len(self._KB_LANG_ORDER)]
        self._caps = False
        self._rebuild_keys()

    def _rebuild_keys(self):
        """Tugmalar maydonini joriy yozuv tili bo'yicha qayta quradi."""
        while self.keys_layout.count():
            item = self.keys_layout.takeAt(0)
            child = item.layout()
            if child is not None:
                while child.count():
                    w = child.takeAt(0).widget()
                    if w is not None:
                        w.setParent(None)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self.setup_full_layout()

    def create_key(self, text):
        c = self.colors
        display_text = text
        if text == 'CLEAR':
            display_text = tr("TOZALASH")
        elif text == 'SPACE':
            display_text = tr("PROBEL")
        elif text == 'CAPS':
            display_text = tr("⇧ Katta harf")
        elif len(text) == 1 and text.isalpha():
            # Tugmadagi harf yozilayotgan harfga mos bo'lsin (boshda kichik).
            display_text = text.upper() if self._caps else text.lower()

        btn = QPushButton(display_text)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # Minimal o'lcham — har qanday ekran/masshtabda tugmalar o'qiladigan
        # va bir-biriga yopishmaydigan bo'lib qoladi. 42px — touch uchun
        # yetarli, ammo past (768px) ekranlarda qatorlar sig'adi.
        btn.setMinimumHeight(42)
        btn.setMinimumWidth(36)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        # Globus tugmasi — yozuv tilini almashtiradi (telefondagidek).
        if text == '🌐':
            btn.setText(f"🌐 {self._kb_lang.upper()}")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {c['accent']}; color: white;
                    border: none; border-radius: 10px;
                    font-size: 14px; font-weight: 800;
                }}
                QPushButton:hover {{ background: {c.get('accent_hover', c['accent'])}; }}
                QPushButton:pressed {{ background: {c['accent']}; }}
            """)
            btn.clicked.connect(self._cycle_kb_language)
            return btn

        # CAPS tugmasini alohida boshqaramiz (yoniq/o'chiq holati ko'rinsin).
        if text == 'CAPS':
            self._caps_btn = btn
            btn.clicked.connect(lambda: self.on_key_pressed(text))
            self._update_caps_style()
            return btn

        # Oddiy tugma — theme rangiga mos.
        bg = c['bg_tertiary']
        fg = c['text_primary']
        font_size = 18

        if text == '⌫':
            bg, fg = c['error'], "white"
        elif text == 'CLEAR':
            bg, fg, font_size = c['warning'], "white", 12
        elif text == 'SPACE':
            bg, fg = c.get('accent_light', c['bg_hover']), c['text_primary']

        btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                border: 1px solid {c['border']};
                border-radius: 10px;
                font-size: {font_size}px;
                font-weight: bold;
                color: {fg};
            }}
            QPushButton:hover {{ border: 1px solid {c['accent']}; }}
            QPushButton:pressed {{ background: {c['accent']}; color: white; }}
        """)
        btn.clicked.connect(lambda: self.on_key_pressed(text))

        if len(text) == 1 and text.isalpha():
            self._letter_buttons.append(btn)

        return btn

    def _update_caps_style(self):
        """CAPS tugmasi yoniq/o'chiq holatiga qarab ko'rinishini yangilaydi."""
        btn = getattr(self, "_caps_btn", None)
        if btn is None:
            return
        c = self.colors
        if self._caps:
            # YONIQ — yorqin yashil, "● KATTA HARF"
            btn.setText(tr("⇧ KATTA HARF ●"))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {c['success']}; color: white;
                    border: 2px solid white; border-radius: 10px;
                    font-size: 12px; font-weight: 800;
                }}
            """)
        else:
            # O'CHIQ — xira kulrang
            btn.setText(tr("⇧ Katta harf"))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {c['bg_tertiary']}; color: {c['text_secondary']};
                    border: 1px solid {c['border']}; border-radius: 10px;
                    font-size: 12px; font-weight: bold;
                }}
                QPushButton:hover {{ border: 1px solid {c['accent']}; }}
            """)

    def on_key_pressed(self, key):
        if key == 'CAPS':
            self._caps = not self._caps
            self._update_caps_style()
            for btn in self._letter_buttons:
                txt = btn.text()
                btn.setText(txt.upper() if self._caps else txt.lower())
            return
        current = self.input_field.text()
        if key == '⌫':
            self.input_field.setText(current[:-1])
        elif key == 'CLEAR':
            self.input_field.clear()
        elif key == 'SPACE':
            self.input_field.setText(current + " ")
        else:
            # Raqamli rejimda ikkinchi nuqta kiritilmasin — "12.3.4" keyin
            # float() da yiqilib, summa 0 bo'lib ketardi.
            if self.is_numeric and key == '.' and '.' in current:
                return
            char = key.lower() if not self._caps else key.upper()
            self.input_field.setText(current + char)

    def confirm(self):
        self.text_confirmed.emit(self.input_field.text())
        self.accept()
