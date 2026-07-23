from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QGraphicsDropShadowEffect, QScrollArea, QComboBox,
)
from PyQt6.QtCore import pyqtSignal, Qt, QThread
from PyQt6.QtGui import QColor
from core.api import FrappeAPI
from core.config import save_credentials, load_config
from core.i18n import tr, i18n, SUPPORTED_LANGUAGES
from core.logger import get_logger
from ui.components.dialogs import ClickableLineEdit
from ui.components.keyboard import TouchKeyboard
from ui.theme_manager import ThemeManager

logger = get_logger(__name__)


class _LoginWorker(QThread):
    """Run the network login off the GUI thread so the window stays responsive."""

    finished_signal = pyqtSignal(bool, str)

    def __init__(self, api: FrappeAPI, url: str, user: str, password: str, site: str):
        super().__init__()
        self.api = api
        self.url = url
        self.user = user
        self.password = password
        self.site = site

    def run(self):
        try:
            success, message = self.api.login(self.url, self.user, self.password, self.site)
        except Exception as e:
            logger.error("Login background xatosi: %s", e)
            success, message = False, f"Kutilmagan xatolik: {e}"
        self.finished_signal.emit(bool(success), str(message))


class LoginWindow(QWidget):
    login_successful = pyqtSignal()

    def __init__(self, api: FrappeAPI):
        super().__init__()
        self.api = api
        self._active_field = None
        # Bitta umumiy TouchKeyboard ishlatiladi (asosiy oynadagi bilan bir
        # xil) — oldingi ichki panel bilan ikkita klaviatura chiqib qolardi.
        self._kb = None
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("POSAwesome — Kirish")
        self.setMinimumSize(480, 600)
        self.showMaximized()

        # Get theme-aware styles
        theme_styles = ThemeManager.get_login_styles()

        # ——— Asosiy fon ———
        self.setStyleSheet(theme_styles["background"])
        self.setObjectName("loginBg")

        # ——— Asosiy tuzilma: yuqori (karta) + pastki (keyboard) ———
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # --- Yuqori qism: karta markazda ---
        top_area = QWidget()
        top_area.setStyleSheet("background: transparent;")
        top_layout = QVBoxLayout(top_area)
        top_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("loginCard")
        card.setMinimumWidth(340)
        card.setMaximumWidth(460)
        card.setStyleSheet(theme_styles["card"])

        # Soya effekti
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 60))
        card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(36, 32, 36, 32)
        layout.setSpacing(0)

        # ——— Logo / Branding ———
        logo = QLabel("💻")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("font-size: 48px; margin-bottom: 4px; background: transparent;")
        layout.addWidget(logo)

        title = QLabel("POSAwesome")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"""
            font-size: 26px; font-weight: 900; color: {theme_styles['title_color']};
            letter-spacing: 2px; margin-bottom: 2px; background: transparent;
        """)
        layout.addWidget(title)

        self.subtitle = QLabel(tr("Kassir tizimiga kirish"))
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setStyleSheet(f"""
            font-size: 13px; color: {theme_styles['subtitle_color']}; margin-bottom: 16px; background: transparent;
        """)
        layout.addWidget(self.subtitle)

        # ——— Til tanlash ———
        lang_row = QHBoxLayout()
        lang_row.setContentsMargins(0, 0, 0, 12)
        self.lang_label = QLabel(tr("Til") + ":")
        self.lang_label.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {theme_styles['subtitle_color']}; background: transparent;")
        self.lang_combo = QComboBox()
        self.lang_combo.setFixedHeight(36)
        self.lang_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        for code, name in SUPPORTED_LANGUAGES.items():
            self.lang_combo.addItem(name, code)
        cur = self.lang_combo.findData(i18n.language)
        if cur >= 0:
            self.lang_combo.setCurrentIndex(cur)
        # MUHIM: ranglar ThemeManager'dan — avval har doim oq fon tushib,
        # dark rejimda och matn ko'rinmay qolardi.
        _c = ThemeManager.get_theme_colors()
        self.lang_combo.setStyleSheet(f"""
            QComboBox {{
                background: {_c['input_bg']}; color: {_c['text_primary']};
                border: 1px solid {_c['border']}; border-radius: 8px;
                padding: 4px 10px; font-size: 13px; font-weight: 600;
            }}
            QComboBox:focus {{ border: 2px solid {_c['accent']}; }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox QAbstractItemView {{
                background: {_c['bg_secondary']}; color: {_c['text_primary']};
                border: 1px solid {_c['border']};
                selection-background-color: {_c['accent']};
                selection-color: white;
                outline: 0;
            }}
        """)
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        lang_row.addStretch()
        lang_row.addWidget(self.lang_label)
        lang_row.addWidget(self.lang_combo)
        lang_row.addStretch()
        layout.addLayout(lang_row)

        # ——— Separator ———
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        colors = ThemeManager.get_theme_colors()
        sep.setStyleSheet(f"background: {colors['border_light']}; max-height: 1px; margin-bottom: 16px;")
        layout.addWidget(sep)

        # ——— Formalar ———
        config = load_config()
        # Production rejim: server manzili bir marta kiritilgach (yoki
        # o'rnatuvchi config.json'da `default_server_url` bilan berilgach)
        # eslab qolinadi — kassir faqat login+parol yozadi. Logout .env'ni
        # o'chirsa ham bu qiymat config.json'da saqlanib qoladi.
        saved_server = (config.get("default_server_url") or "").strip()
        default_url = saved_server or config.get("url", "")
        self._has_default_server = bool(saved_server)

        INPUT_STYLE = theme_styles["input_style"]
        INPUT_ACTIVE_STYLE = theme_styles["input_active_style"]

        self._input_style = INPUT_STYLE
        self._input_active_style = INPUT_ACTIVE_STYLE

        LABEL_STYLE = theme_styles["label_style"]

        # Server URL
        self.url_label = self._label(tr("Server manzili"), LABEL_STYLE)
        layout.addWidget(self.url_label)
        self.url_input = ClickableLineEdit()
        self.url_input.setPlaceholderText(tr("masalan: http://192.168.1.53:8000"))
        self.url_input.setText(default_url)
        self.url_input.setMinimumHeight(46)
        self.url_input.setStyleSheet(INPUT_STYLE)
        self.url_input.clicked.connect(lambda: self._activate_field(self.url_input, tr("Server manzili")))
        layout.addWidget(self.url_input)

        # Server oldindan sozlangan bo'lsa — maydonni yashiramiz (kassir faqat
        # login+parol ko'radi); kerak bo'lsa "Kengaytirilgan sozlamalar"da ochiladi.
        if self._has_default_server:
            self.url_label.setVisible(False)
            self.url_input.setVisible(False)

        # Login (Email)
        self.user_label = self._label(tr("Email yoki Login"), LABEL_STYLE)
        layout.addWidget(self.user_label)
        self.user_input = ClickableLineEdit()
        self.user_input.setPlaceholderText("cashier@example.uz")
        self.user_input.setMinimumHeight(46)
        self.user_input.setStyleSheet(INPUT_STYLE)
        self.user_input.clicked.connect(lambda: self._activate_field(self.user_input, tr("Email yoki Login")))
        layout.addWidget(self.user_input)

        # Parol
        self.password_label = self._label(tr("Parol"), LABEL_STYLE)
        layout.addWidget(self.password_label)
        self.password_input = ClickableLineEdit()
        self.password_input.setPlaceholderText("••••••••")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setMinimumHeight(46)
        self.password_input.setStyleSheet(INPUT_STYLE)
        self.password_input.clicked.connect(lambda: self._activate_field(self.password_input, tr("Parol")))
        layout.addWidget(self.password_input)

        # ——— Kengaytirilgan sozlamalar (Site name) ———
        self.advanced_toggle = QPushButton(tr("Kengaytirilgan sozlamalar ▸"))
        self.advanced_toggle.setFixedHeight(44)
        self.advanced_toggle.setCheckable(True)
        _c = ThemeManager.get_theme_colors()
        self.advanced_toggle.setStyleSheet(f"""
            QPushButton {{
                font-size: 12px; font-weight: 600; color: {_c['text_tertiary']};
                background: transparent; border: none; margin-top: 8px;
                text-align: left; padding-left: 4px;
            }}
            QPushButton:checked {{ color: {_c['accent']}; }}
        """)
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        layout.addWidget(self.advanced_toggle)

        # Site name (yashirin)
        self.site_frame = QFrame()
        self.site_frame.setVisible(False)
        self.site_frame.setStyleSheet("background: transparent;")
        site_layout = QVBoxLayout(self.site_frame)
        site_layout.setContentsMargins(0, 0, 0, 0)
        site_layout.setSpacing(2)

        self.site_hint = QLabel(tr("Multi-site bench uchun (ixtiyoriy)"))
        self.site_hint.setStyleSheet("font-size: 11px; color: #94a3b8; background: transparent;")
        site_layout.addWidget(self.site_hint)

        self.site_input = ClickableLineEdit()
        self.site_input.setPlaceholderText(tr("sayt nomi (masalan: mysite.local)"))
        self.site_input.setText(config.get("site", "") or config.get("default_site", ""))
        self.site_input.setMinimumHeight(46)
        self.site_input.setStyleSheet(INPUT_STYLE)
        self.site_input.clicked.connect(lambda: self._activate_field(self.site_input, tr("Sayt nomi")))
        site_layout.addWidget(self.site_input)
        layout.addWidget(self.site_frame)

        # ——— Xatolik xabari ———
        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        _c = ThemeManager.get_theme_colors()
        self.error_label.setStyleSheet(f"""
            font-size: 12px; color: {_c['error']};
            background: {_c.get('error_bg', _c['bg_tertiary'])};
            border: 1px solid {_c.get('error_border', _c['border'])};
            border-radius: 8px; padding: 8px 12px; margin-top: 10px;
        """)
        layout.addWidget(self.error_label)

        # ——— Login tugma ———
        
        # Ekran klaviaturasini boshqarish tugmasi
        self.kb_toggle_btn = QPushButton(tr("⌨️ Ekran Klaviaturasi"))
        self.kb_toggle_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.kb_toggle_btn.setFixedHeight(40)
        _c = ThemeManager.get_theme_colors()
        self.kb_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_c['bg_tertiary']}; color: {_c['text_primary']};
                font-weight: bold; border-radius: 8px;
                border: 1px solid {_c['border']}; margin-bottom: 5px;
            }}
            QPushButton:hover {{ background: {_c['bg_hover']}; }}
        """)
        self.kb_toggle_btn.clicked.connect(self._toggle_keyboard_panel)
        layout.addWidget(self.kb_toggle_btn)

        self.login_btn = QPushButton(tr("KIRISH"))

        self.login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_btn.setFixedHeight(56)
        self.login_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2563eb, stop:1 #3b82f6
                );
                color: white;
                font-weight: 800;
                font-size: 15px;
                border-radius: 12px;
                border: none;
                letter-spacing: 1px;
                margin-top: 16px;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1d4ed8, stop:1 #2563eb
                );
            }
            QPushButton:pressed {
                background: #1e40af;
            }
            QPushButton:disabled {
                background: #cbd5e1;
                color: #94a3b8;
            }
        """)
        self.login_btn.clicked.connect(self._handle_login)
        layout.addWidget(self.login_btn)

        # ——— Pastki yozuv ———
        from core.version import __version__
        footer = QLabel(f"POSAwesome Desktop v{__version__}")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(f"""
            font-size: 11px; color: {ThemeManager.get_theme_colors()['text_tertiary']};
            margin-top: 14px; background: transparent;
        """)
        layout.addWidget(footer)

        top_layout.addWidget(card)

        # Kartani scroll ichiga o'raymiz — klaviatura ochilganda yuqori qism
        # SIQILMAYDI: joy yetmasa scroll chiqadi, maydonlar o'z balandligida
        # qoladi.
        self._card_scroll = QScrollArea()
        self._card_scroll.setWidgetResizable(True)
        self._card_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._card_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._card_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._card_scroll.setWidget(top_area)
        root_layout.addWidget(self._card_scroll, stretch=1)

    # ─── Ekran klaviaturasi (umumiy TouchKeyboard) ────────
    def _toggle_keyboard_panel(self):
        kb = self._kb
        if kb is not None:
            try:
                if kb.isVisible():
                    kb.hide()
                    return
            except RuntimeError:
                self._kb = None
        target = self._active_field or self.user_input
        title = tr("Parol") if target is self.password_input else tr("Email yoki Login")
        self._activate_field(target, title)

    def _activate_field(self, widget, title: str):
        # Avvalgi field stilini qaytarish
        if self._active_field and self._active_field != widget:
            self._active_field.setStyleSheet(self._input_style)
            try:
                self._active_field.textChanged.disconnect(self._on_field_text_changed)
            except (TypeError, RuntimeError):
                pass
        self._active_field = widget
        widget.setStyleSheet(self._input_active_style)
        try:
            widget.textChanged.disconnect(self._on_field_text_changed)
        except (TypeError, RuntimeError):
            pass
        widget.textChanged.connect(self._on_field_text_changed)
        self._open_keyboard_for(widget, title)
        # Aktiv maydon klaviatura ostida qolib ketmasin — scroll qilib
        # ko'rinadigan joyga keltiramiz.
        if hasattr(self, "_card_scroll"):
            self._card_scroll.ensureWidgetVisible(widget, 50, 80)

    def _open_keyboard_for(self, widget, title: str):
        is_password = widget is self.password_input
        kb = self._kb
        if kb is not None:
            try:
                if kb.is_password != is_password:
                    kb.close()
                    kb.deleteLater()
                    kb = None
            except RuntimeError:
                kb = None
        if kb is None:
            kb = TouchKeyboard(
                self, initial_text=widget.text(), title=title,
                is_numeric=False, is_password=is_password,
            )
            kb.text_changed.connect(self._on_kb_text_changed)
            self._kb = kb
        else:
            kb.set_target(widget.text(), title)
        kb.show()

    def _on_kb_text_changed(self, text: str):
        if self._active_field is None:
            return
        try:
            if self._active_field.text() != text:
                self._active_field.setText(text)
        except RuntimeError:
            self._active_field = None

    def _on_field_text_changed(self, text: str):
        # Hardware klaviaturada yozilsa — ekran klaviaturasi ham sinxron.
        kb = self._kb
        if kb is None:
            return
        try:
            kb.sync_text(text)
        except RuntimeError:
            self._kb = None

    def _close_keyboard(self):
        if self._active_field:
            self._active_field.setStyleSheet(self._input_style)
            self._active_field = None
        kb = self._kb
        if kb is not None:
            try:
                kb.hide()
            except RuntimeError:
                self._kb = None

    # ─── Helpers ─────────────────────────────────────────
    @staticmethod
    def _label(text: str, style: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(style)
        return lbl

    def _toggle_advanced(self, checked: bool):
        self.site_frame.setVisible(checked)
        # Server oldindan sozlangan bo'lsa — manzil maydoni faqat shu yerda
        # ochiladi (o'zgartirish kerak bo'lib qolsa).
        if getattr(self, "_has_default_server", False):
            self.url_label.setVisible(checked)
            self.url_input.setVisible(checked)
        self.advanced_toggle.setText(tr("Kengaytirilgan sozlamalar ▾") if checked else tr("Kengaytirilgan sozlamalar ▸"))

    def _on_language_changed(self, _index):
        code = self.lang_combo.currentData()
        if code:
            i18n.set_language(code)
            self._retranslate()

    def _retranslate(self):
        """Til o'zgarganda login oynasidagi matnlarni yangilaydi."""
        self.subtitle.setText(tr("Kassir tizimiga kirish"))
        self.lang_label.setText(tr("Til") + ":")
        self.url_label.setText(tr("Server manzili"))
        self.url_input.setPlaceholderText(tr("masalan: http://192.168.1.53:8000"))
        self.user_label.setText(tr("Email yoki Login"))
        self.password_label.setText(tr("Parol"))
        self.site_hint.setText(tr("Multi-site bench uchun (ixtiyoriy)"))
        self.site_input.setPlaceholderText(tr("sayt nomi (masalan: mysite.local)"))
        self.advanced_toggle.setText(
            tr("Kengaytirilgan sozlamalar ▾") if self.advanced_toggle.isChecked()
            else tr("Kengaytirilgan sozlamalar ▸")
        )
        self.kb_toggle_btn.setText(tr("⌨️ Ekran Klaviaturasi"))
        self.login_btn.setText(tr("KIRISH"))

    def _show_error(self, msg: str):
        self.error_label.setText(f"⚠  {msg}")
        self.error_label.setVisible(True)

    def _hide_error(self):
        self.error_label.setVisible(False)

    # ─── Login handler ───────────────────────────────────
    def _handle_login(self):
        self._close_keyboard()
        self._hide_error()

        url = self.url_input.text().strip()
        user = self.user_input.text().strip()
        password = self.password_input.text().strip()
        # Sayt nomi yashirin bo'lsa ham yuboriladi — u default_site'dan
        # oldindan to'ldirilgan bo'lishi mumkin (multi-site production).
        site = self.site_input.text().strip()

        # Validatsiya
        if not url:
            self._show_error(tr("Server manzilini kiriting!"))
            self.url_input.setFocus()
            return
        if not user:
            self._show_error(tr("Email yoki loginni kiriting!"))
            self.user_input.setFocus()
            return
        if not password:
            self._show_error(tr("Parolni kiriting!"))
            self.password_input.setFocus()
            return

        # http:// avtomatik qo'shish
        if not url.startswith("http"):
            url = "http://" + url

        # UI holati
        self.login_btn.setText(tr("⏳  Kirilmoqda..."))
        self.login_btn.setEnabled(False)
        self.url_input.setEnabled(False)
        self.user_input.setEnabled(False)
        self.password_input.setEnabled(False)

        # Login background thread'da — GUI muzlamaydi
        self._login_worker = _LoginWorker(self.api, url, user, password, site)
        self._pending_credentials = (url, user, password, site)
        self._login_worker.finished_signal.connect(self._on_login_finished)
        self._login_worker.start()

    def _on_login_finished(self, success: bool, message: str):
        url, user, password, site = getattr(self, "_pending_credentials", ("", "", "", ""))
        self._pending_credentials = None
        if success:
            save_credentials(url, user, password, site)
            # Serverni doimiy eslab qolamiz — keyingi login (logoutdan keyin
            # ham) faqat login+parol so'raydi.
            try:
                from core.config import save_config
                save_config({"default_server_url": url, "default_site": site})
            except Exception as e:
                logger.debug("Default server saqlanmadi: %s", e)
            self.api.reload_config()
            logger.info("Login muvaffaqiyatli: %s (User: %s)", url, user)
            self.login_successful.emit()
            self.close()
            return

        # Xatolik xabarini foydalanuvchiga tushunarli qilish
        lower = message.lower()
        if "aloqa" in lower or "connection" in lower:
            friendly = (
                "Serverga ulanib bo'lmadi.\n"
                "Server manzilini tekshiring yoki internet ulanishini tekshiring."
            )
        elif "noto'g'ri" in lower or "incorrect" in lower:
            friendly = "Login yoki parol noto'g'ri.\nIltimos, qayta tekshirib ko'ring."
        elif "timeout" in lower:
            friendly = (
                "Server javob bermadi.\n"
                "Internet ulanishini yoki server manzilini tekshiring."
            )
        else:
            friendly = message
        self._show_error(friendly)
        self._reset_form()

    def _reset_form(self):
        self.login_btn.setText(tr("KIRISH"))
        self.login_btn.setEnabled(True)
        self.url_input.setEnabled(True)
        self.user_input.setEnabled(True)
        self.password_input.setEnabled(True)
