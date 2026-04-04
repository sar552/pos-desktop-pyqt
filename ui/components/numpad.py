from PyQt6.QtWidgets import QWidget, QGridLayout, QPushButton, QVBoxLayout
from PyQt6.QtCore import pyqtSignal, QSize

class TouchNumpad(QWidget):
    digit_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QGridLayout(self)
        layout.setSpacing(8) # Space between buttons
        layout.setContentsMargins(0, 0, 0, 0)

        # Standard 3x4 Numpad layout
        buttons = [
            ('7', 0, 0), ('8', 0, 1), ('9', 0, 2),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
            ('1', 2, 0), ('2', 2, 1), ('3', 2, 2),
            ('C', 3, 0), ('0', 3, 1), ('.', 3, 2),
            ('BACK', 4, 0, 1, 3) # Span 3 columns
        ]

        for b in buttons:
            text = b[0]
            btn = QPushButton()
            
            if text == 'BACK':
                btn.setText("⌫ O'CHIRISH")
                btn.setObjectName("backspace")
            else:
                btn.setText(text)
            
            # Match width with Quick Amount buttons
            btn.setMinimumHeight(48)
            btn.setMaximumHeight(70)
            btn.setMinimumWidth(80)
            
            btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(51, 65, 85, 0.8), 
                        stop:1 rgba(30, 41, 59, 0.9));
                    border: 1px solid #334155;
                    border-radius: 10px;
                    font-size: 22px;
                    font-weight: bold;
                    color: #F8FAFC;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(71, 85, 105, 0.9), 
                        stop:1 rgba(51, 65, 85, 1));
                    border: 1px solid #22C55E;
                }
                QPushButton:pressed { 
                    background: rgba(34, 197, 94, 0.2);
                    border: 1px solid #22C55E;
                }
                QPushButton#backspace { 
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 rgba(220, 38, 38, 0.2), 
                        stop:1 rgba(185, 28, 28, 0.3)); 
                    color: #FCA5A5; 
                    font-size: 16px;
                    font-weight: 700;
                    border: 1px solid rgba(220, 38, 38, 0.4);
                }
                QPushButton#backspace:hover { 
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 rgba(220, 38, 38, 0.3), 
                        stop:1 rgba(185, 28, 28, 0.4));
                    color: #FEE2E2;
                }
            """)
            
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
