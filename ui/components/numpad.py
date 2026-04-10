from PyQt6.QtWidgets import QWidget, QGridLayout, QPushButton, QVBoxLayout
from PyQt6.QtCore import pyqtSignal, QSize
from ui.theme_manager import ThemeManager

class TouchNumpad(QWidget):
    digit_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QGridLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(0, 0, 0, 0)

        colors = ThemeManager.get_theme_colors()

        buttons = [
            ('7', 0, 0), ('8', 0, 1), ('9', 0, 2),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
            ('1', 2, 0), ('2', 2, 1), ('3', 2, 2),
            ('C', 3, 0), ('0', 3, 1), ('.', 3, 2),
            ('BACK', 4, 0, 1, 3)
        ]

        digit_style = f"""
            QPushButton {{
                background: {colors['bg_secondary']};
                border: 1.5px solid {colors['border']};
                border-radius: 8px;
                font-size: 20px;
                font-weight: 600;
                color: {colors['text_primary']};
            }}
            QPushButton:hover {{
                background: {colors['bg_tertiary']};
                border-color: {colors['accent']};
            }}
            QPushButton:pressed {{
                background: {colors['accent']};
                color: white;
                border-color: {colors['accent']};
            }}
        """

        clear_style = f"""
            QPushButton {{
                background: {colors.get('warning_bg', colors['bg_tertiary'])};
                border: 1.5px solid {colors.get('warning_border', colors['border'])};
                border-radius: 8px;
                font-size: 18px;
                font-weight: 700;
                color: {colors['warning']};
            }}
            QPushButton:hover {{
                background: {colors.get('warning_border', colors['bg_hover'])};
            }}
            QPushButton:pressed {{
                background: {colors['warning']};
                color: white;
            }}
        """

        back_style = f"""
            QPushButton {{
                background: {colors.get('error_bg', colors['bg_tertiary'])};
                border: 1.5px solid {colors.get('error_border', colors['border'])};
                border-radius: 8px;
                font-size: 14px;
                font-weight: 700;
                color: {colors['error']};
            }}
            QPushButton:hover {{
                background: {colors.get('error_border', colors['bg_hover'])};
            }}
            QPushButton:pressed {{
                background: {colors['error']};
                color: white;
            }}
        """

        for b in buttons:
            text = b[0]
            btn = QPushButton()
            
            if text == 'BACK':
                btn.setText("⌫ O'CHIRISH")
                btn.setStyleSheet(back_style)
            elif text == 'C':
                btn.setText("C")
                btn.setStyleSheet(clear_style)
            else:
                btn.setText(text)
                btn.setStyleSheet(digit_style)
            
            btn.setMinimumHeight(48)
            btn.setMaximumHeight(64)
            btn.setMinimumWidth(80)
            btn.setCursor(__import__('PyQt6.QtCore', fromlist=['Qt']).Qt.CursorShape.PointingHandCursor)
            
            btn.clicked.connect(lambda checked, t=text: self.on_btn_click(t))
            
            if len(b) == 3:
                layout.addWidget(btn, b[1], b[2])
            else:
                layout.addWidget(btn, b[1], b[2], b[3], b[4])

    def on_btn_click(self, text):
        action = text
        if text == 'BACK': action = 'BACKSPACE'
        elif text == 'C': action = 'CLEAR'
        self.digit_clicked.emit(action)
