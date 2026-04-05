"""Shared modern dialogs and widgets for the POS application.

InfoDialog — success / warning / error
ConfirmDialog — yes / no
ClickableLineEdit — click signal bilan QLineEdit
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QLineEdit, QCheckBox,
)
from PyQt6.QtCore import pyqtSignal
from ui.theme_manager import ThemeManager


class ClickableLineEdit(QLineEdit):
    """Bosilganda signal chiqaradigan QLineEdit — numpad bilan ishlash uchun."""
    clicked = pyqtSignal(object)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.clicked.emit(self)


class InfoDialog(QDialog):
    """kind: 'success' | 'warning' | 'error'"""
    _ICONS = {"success": "✓", "warning": "⚠️", "error": "✕"}
    _COLORS = {"success": "#16a34a", "warning": "#d97706", "error": "#dc2626"}
    _BG = {"success": "#f0fdf4", "warning": "#fffbeb", "error": "#fef2f2"}
    _BORDER = {"success": "#bbf7d0", "warning": "#fde68a", "error": "#fecaca"}

    def __init__(self, parent, title: str, message: str, kind: str = "success"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(320)
        self.setMaximumWidth(500)
        colors = ThemeManager.get_theme_colors()
        self.setStyleSheet(f"background: {colors['bg_secondary']}; color: {colors['text_primary']};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)

        top = QHBoxLayout()
        ic = QLabel(self._ICONS.get(kind, "ℹ"))
        ic.setStyleSheet(
            f"font-size:26px; background:{self._BG.get(kind, '#f8fafc')};"
            f"border:1.5px solid {self._BORDER.get(kind, '#e2e8f0')};"
            f"border-radius:10px; padding:6px 12px;"
        )
        top.addWidget(ic)
        ttl = QLabel(title)
        ttl.setStyleSheet(f"font-size:16px; font-weight:800; color:{self._COLORS.get(kind, colors['text_primary'])};")
        top.addWidget(ttl, 1)
        layout.addLayout(top)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background:{colors['border_light']}; max-height:1px;")
        layout.addWidget(sep)

        msg = QLabel(message)
        msg.setWordWrap(True)
        msg.setStyleSheet(f"font-size:13px; color:{colors['text_primary']}; line-height:1.5;")
        layout.addWidget(msg)

        ok = QPushButton("OK")
        ok.setMinimumHeight(38)
        ok.setStyleSheet(
            f"QPushButton{{background:{self._COLORS.get(kind, colors['accent'])};"
            f"color:white;font-weight:700;border-radius:10px;border:none;}}"
            f"QPushButton:hover{{opacity:0.9;}}"
        )
        ok.clicked.connect(self.accept)
        layout.addWidget(ok)


class ConfirmDialog(QDialog):
    """Tasdiqlash dialogi — Ha / Yo'q"""
    def __init__(self, parent, title: str, message: str, icon: str = "❓",
                 yes_text: str = "Ha", no_text: str = "Yo'q",
                 yes_color: str = "#dc2626"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(320)
        self.setMaximumWidth(500)
        colors = ThemeManager.get_theme_colors()
        self.setStyleSheet(f"background: {colors['bg_secondary']}; color: {colors['text_primary']};")
        self.result_accepted = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)

        top = QHBoxLayout()
        ic = QLabel(icon)
        ic.setStyleSheet(
            "font-size:26px; background:#fffbeb;"
            "border:1.5px solid #fde68a; border-radius:10px; padding:6px 12px;"
        )
        top.addWidget(ic)
        ttl = QLabel(title)
        ttl.setStyleSheet(f"font-size:16px; font-weight:800; color:{colors['text_primary']};")
        top.addWidget(ttl, 1)
        layout.addLayout(top)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background:{colors['border_light']}; max-height:1px;")
        layout.addWidget(sep)

        msg = QLabel(message)
        msg.setWordWrap(True)
        msg.setStyleSheet(f"font-size:13px; color:{colors['text_primary']};")
        layout.addWidget(msg)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        no_btn = QPushButton(no_text)
        no_btn.setMinimumHeight(38)
        no_btn.setStyleSheet(
            f"QPushButton{{background:{colors['bg_tertiary']};color:{colors['text_secondary']};font-weight:700;"
            f"border-radius:10px;border:none;}}"
            f"QPushButton:hover{{background:{colors['border']};}}"
        )
        no_btn.clicked.connect(self.reject)

        yes_btn = QPushButton(yes_text)
        yes_btn.setMinimumHeight(38)
        yes_btn.setStyleSheet(
            f"QPushButton{{background:{yes_color};color:white;font-weight:700;"
            f"border-radius:10px;border:none;}}"
            f"QPushButton:hover{{opacity:0.9;}}"
        )
        yes_btn.clicked.connect(self._on_yes)

        btn_row.addWidget(no_btn, 1)
        btn_row.addWidget(yes_btn, 1)
        layout.addLayout(btn_row)

    def _on_yes(self):
        self.result_accepted = True
        self.accept()


class SettingsDialog(QDialog):
    '''Asosiy Settings (Jadvallar) dialogi — POSAwesome veb-uslubida'''
    def __init__(self, parent, title: str, options: dict):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedWidth(360)
        colors = ThemeManager.get_theme_colors()
        self.setStyleSheet(f"background: {colors['bg_secondary']}; color: {colors['text_primary']};")
        
        self.options = options
        self.checkboxes = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        lbl = QLabel(title)
        lbl.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {colors['text_primary']};")
        layout.addWidget(lbl)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background: {colors['border']}; max-height: 1px;")
        layout.addWidget(line)

        for key, details in options.items():
            label_text = details.get("label", key)
            is_checked = details.get("value", False)
            cb = QCheckBox(label_text)
            cb.setChecked(is_checked)
            cb.setStyleSheet(f"""
                QCheckBox {{ font-size: 14px; font-weight: 500; color: {colors['text_primary']}; padding: 4px 0; }}
                QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 4px; border: 1px solid {colors['border']}; background: {colors['input_bg']}; }}
                QCheckBox::indicator:checked {{ background: {colors['accent']}; border: 1px solid {colors['accent']}; }}
            """)
            self.checkboxes[key] = cb
            layout.addWidget(cb)

        layout.addStretch()

        btn_row = QHBoxLayout()
        
        cancel_btn = QPushButton("Bekor qilish")
        cancel_btn.setFixedHeight(40)
        cancel_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {colors['text_secondary']}; font-weight: 600; border: none; font-size: 14px; }}"
            f"QPushButton:hover {{ color: #f43f5e; background: {colors['bg_tertiary']}; border-radius: 6px; }}"
        )
        cancel_btn.clicked.connect(self.reject)
        
        save_btn = QPushButton("Saqlash")
        save_btn.setFixedHeight(40)
        save_btn.setStyleSheet(
            f"QPushButton {{ background: {colors['accent']}; color: white; font-weight: 600; border-radius: 6px; border: none; font-size: 14px; padding: 0 20px; }}"
            f"QPushButton:hover {{ background: {colors['accent_hover']}; }}"
        )
        save_btn.clicked.connect(self.accept)

        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def get_results(self) -> dict:
        return {key: cb.isChecked() for key, cb in self.checkboxes.items()}
