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
        self._caps = False
        self._letter_buttons = []
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

        title = QLabel("POKIZA POS")
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
        self.lang_combo.setStyleSheet(f"""
            QComboBox {{
                background: {theme_styles.get('input_bg', '#ffffff')}; color: {theme_styles['title_color']};
                border: 1px solid #cbd5e1; border-radius: 8px; padding: 4px 10px; font-size: 13px; font-weight: 600;
            }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
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
        default_url = config.get("url", "")

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
        # # self.url_input.setReadOnly(True)
        self.url_input.setStyleSheet(INPUT_STYLE)
        self.url_input.clicked.connect(lambda: self._activate_field(self.url_input, tr("Server manzili")))
        layout.addWidget(self.url_input)

        # Login (Email)
        self.user_label = self._label(tr("Email yoki Login"), LABEL_STYLE)
        layout.addWidget(self.user_label)
        self.user_input = ClickableLineEdit()
        self.user_input.setPlaceholderText("cashier@example.uz")
        # # self.user_input.setReadOnly(True)
        self.user_input.setStyleSheet(INPUT_STYLE)
        self.user_input.clicked.connect(lambda: self._activate_field(self.user_input, tr("Email yoki Login")))
        layout.addWidget(self.user_input)

        # Parol
        self.password_label = self._label(tr("Parol"), LABEL_STYLE)
        layout.addWidget(self.password_label)
        self.password_input = ClickableLineEdit()
        self.password_input.setPlaceholderText("••••••••")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        # # self.password_input.setReadOnly(True)
        self.password_input.setStyleSheet(INPUT_STYLE)
        self.password_input.clicked.connect(lambda: self._activate_field(self.password_input, tr("Parol")))
        layout.addWidget(self.password_input)

        # ——— Kengaytirilgan sozlamalar (Site name) ———
        self.advanced_toggle = QPushButton(tr("Kengaytirilgan sozlamalar ▸"))
        self.advanced_toggle.setFixedHeight(44)
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setStyleSheet("""
            QPushButton {
                font-size: 12px; font-weight: 600; color: #94a3b8;
                background: transparent; border: none; margin-top: 8px;
                text-align: left; padding-left: 4px;
            }
            QPushButton:checked { color: #3b82f6; }
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
        self.site_input.setText(config.get("site", ""))
        # # self.site_input.setReadOnly(True)
        self.site_input.setStyleSheet(INPUT_STYLE)
        self.site_input.clicked.connect(lambda: self._activate_field(self.site_input, tr("Sayt nomi")))
        site_layout.addWidget(self.site_input)
        layout.addWidget(self.site_frame)

        # ——— Xatolik xabari ———
        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        self.error_label.setStyleSheet("""
            font-size: 12px; color: #dc2626; background: #fef2f2;
            border: 1px solid #fecaca; border-radius: 8px;
            padding: 8px 12px; margin-top: 10px;
        """)
        layout.addWidget(self.error_label)

        # ——— Login tugma ———
        
        # Ekran klaviaturasini boshqarish tugmasi
        self.kb_toggle_btn = QPushButton(tr("⌨️ Ekran Klaviaturasi"))
        self.kb_toggle_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.kb_toggle_btn.setFixedHeight(40)
        self.kb_toggle_btn.setStyleSheet("""
            QPushButton {
                background: #f1f5f9; color: #475569; font-weight: bold; border-radius: 8px; border: 1px solid #e2e8f0; margin-bottom: 5px;
            }
            QPushButton:hover { background: #e2e8f0; }
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
        footer = QLabel("POSAwesome Desktop v1.0")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet("""
            font-size: 11px; color: #cbd5e1; margin-top: 14px; background: transparent;
        """)
        layout.addWidget(footer)

        top_layout.addWidget(card)
        root_layout.addWidget(top_area, stretch=1)

        # --- Pastki qism: inline keyboard ---
        self.keyboard_panel = self._build_keyboard_panel()
        self.keyboard_panel.setVisible(False)
        root_layout.addWidget(self.keyboard_panel)

    # ─── Inline Keyboard ──────────────────────────────────
    def _build_keyboard_panel(self):
        theme_styles = ThemeManager.get_login_styles()
        colors = ThemeManager.get_theme_colors()
        
        panel = QFrame()
        panel.setStyleSheet(theme_styles["keyboard_panel"])
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(16, 10, 16, 12)
        panel_layout.setSpacing(6)

        # Yuqori qator: aktiv field nomi + display + yopish
        top_row = QHBoxLayout()

        self.kb_field_label = QLabel("")
        self.kb_field_label.setStyleSheet(f"""
            font-size: 12px; font-weight: 700; color: {colors['accent']};
            background: transparent; padding: 0 4px;
        """)

        self.kb_display = QLabel("")
        self.kb_display.setStyleSheet(theme_styles["kb_display"])
        self.kb_display.setFixedHeight(40)

        close_btn = QPushButton("✕")
        close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_btn.setFixedSize(44, 44)
        close_btn.setStyleSheet("""
            QPushButton {
                background: #ef4444; color: white;
                font-weight: bold; font-size: 16px;
                border-radius: 8px; border: none;
            }
            QPushButton:pressed { background: #dc2626; }
        """)
        close_btn.clicked.connect(self._close_keyboard)

        top_row.addWidget(self.kb_field_label)
        top_row.addWidget(self.kb_display, stretch=1)
        top_row.addWidget(close_btn)
        panel_layout.addLayout(top_row)

        # Klaviatura qatorlari
        self._letter_buttons = []
        rows = [
            ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '⌫'],
            ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
            ['CAPS', 'A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', 'CLR'],
            ['Z', 'X', 'C', 'V', 'B', 'N', 'M', ',', '.', ' SPACE '],
            ['@', '-', '_', ':', '/', '#', '+', '='],
        ]
        for row_keys in rows:
            row_layout = QHBoxLayout()
            row_layout.setSpacing(5)
            for key in row_keys:
                btn = self._make_key(key)
                row_layout.addWidget(btn)
            panel_layout.addLayout(row_layout)

        return panel

    def _make_key(self, key):
        label = key.strip()
        if label == 'SPACE':
            label = tr('PROBEL')
        elif label == 'CLR':
            label = tr('TOZALASH')
        elif label == 'CAPS':
            label = '⇧ Aa'

        btn = QPushButton(label)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setFixedHeight(48)

        if key.strip() == '⌫':
            style = "background:#fee2e2; color:#ef4444; font-size:18px; font-weight:bold;"
        elif key.strip() == 'CLR':
            style = "background:#fff7ed; color:#ea580c; font-size:11px; font-weight:bold;"
        elif key.strip() == 'CAPS':
            style = "background:#e0e7ff; color:#4338ca; font-size:13px; font-weight:bold;"
        elif 'SPACE' in key:
            style = "background:#eff6ff; color:#3b82f6; font-size:13px; font-weight:bold;"
            btn.setMinimumWidth(120)
        elif key.strip().isdigit():
            style = "background:#e0e7ff; color:#3730a3; font-size:16px; font-weight:bold;"
        else:
            style = "background:white; color:#1e293b; font-size:15px; font-weight:600;"

        btn.setStyleSheet(f"""
            QPushButton {{
                {style}
                border: 1px solid #e2e8f0;
                border-radius: 7px;
            }}
            QPushButton:pressed {{ background: #dbeafe; }}
        """)
        btn.clicked.connect(lambda _, k=key.strip(): self._on_key(k))

        # Harf tugmalarini saqlash (caps uchun)
        if len(key.strip()) == 1 and key.strip().isalpha():
            self._letter_buttons.append(btn)

        return btn

    def _on_key(self, key):
        if key == 'CAPS':
            self._caps = not self._caps
            for btn in self._letter_buttons:
                txt = btn.text()
                btn.setText(txt.upper() if self._caps else txt.lower())
            return
        if not self._active_field:
            return
        current = self._active_field.text()
        if key == '⌫':
            new_text = current[:-1]
        elif key == 'CLR':
            new_text = ''
        elif key == 'SPACE':
            new_text = current + ' '
        else:
            char = key.lower() if not self._caps else key.upper()
            new_text = current + char
        self._active_field.setText(new_text)
        # Display yangilash — parol uchun yashirish
        if self._active_field == self.password_input:
            self.kb_display.setText('•' * len(new_text) if new_text else "")
        else:
            self.kb_display.setText(new_text)

    
    def _sync_display(self, widget, text):
        if self._active_field == widget:
            if widget == self.password_input:
                self.kb_display.setText('•' * len(text) if text else "")
            else:
                self.kb_display.setText(text)

    def _toggle_keyboard_panel(self):
        self.keyboard_panel.setVisible(not self.keyboard_panel.isVisible())

    def _activate_field(self, widget, title: str):
        # Avvalgi field stilini qaytarish
        if self._active_field and self._active_field != widget:
            self._active_field.setStyleSheet(self._input_style)
        self._active_field = widget
        widget.setStyleSheet(self._input_active_style)
        self.kb_field_label.setText(title)
        # Display yangilash
        if widget == self.password_input:
            self.kb_display.setText('•' * len(widget.text()) if widget.text() else "")
        else:
            self.kb_display.setText(widget.text())
        self.keyboard_panel.setVisible(True)

    def _close_keyboard(self):
        if self._active_field:
            self._active_field.setStyleSheet(self._input_style)
            self._active_field = None
        self.keyboard_panel.setVisible(False)

    # ─── Helpers ─────────────────────────────────────────
    @staticmethod
    def _label(text: str, style: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(style)
        return lbl

    def _toggle_advanced(self, checked: bool):
        self.site_frame.setVisible(checked)
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
        site = self.site_input.text().strip() if self.advanced_toggle.isChecked() else ""

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
