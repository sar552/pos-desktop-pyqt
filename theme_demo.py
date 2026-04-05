#!/usr/bin/env python3
"""
Minimal theme demo - Tests that theme actually changes on button click
"""
import sys
sys.path.insert(0, '/home/sherzod/Projects/pos-desktop-pyqt')

from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import Qt
from ui.theme_manager import ThemeManager

class ThemeDemo(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Theme Demo - POS Desktop")
        self.setMinimumSize(600, 400)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Title
        self.title = QLabel("Theme Test")
        self.title.setStyleSheet("font-size: 32px; font-weight: bold; padding: 20px;")
        layout.addWidget(self.title)
        
        # Info label
        self.info_label = QLabel()
        self.info_label.setStyleSheet("font-size: 16px; padding: 10px;")
        layout.addWidget(self.info_label)
        
        # Theme toggle button
        self.toggle_btn = QPushButton("Toggle Theme")
        self.toggle_btn.setMinimumHeight(50)
        self.toggle_btn.clicked.connect(self.toggle_theme)
        layout.addWidget(self.toggle_btn)
        
        # Update display
        self.update_theme_info()
    
    def toggle_theme(self):
        """Toggle theme and update UI"""
        new_theme = ThemeManager.toggle_theme()
        self.update_theme_info()
        print(f"Theme switched to: {new_theme}")
    
    def update_theme_info(self):
        """Update label with current theme info"""
        current = ThemeManager.get_current_theme()
        colors = ThemeManager.get_theme_colors()
        
        icon = "🌙" if current == "light" else "☀️"
        self.toggle_btn.setText(f"{icon} Toggle Theme")
        
        info_text = f"""
        Current Theme: <b>{current.upper()}</b><br><br>
        Background: {colors['bg_primary']}<br>
        Text: {colors['text_primary']}<br>
        Accent: {colors['accent']}<br>
        """
        self.info_label.setText(info_text)

def main():
    app = QApplication(sys.argv)
    
    # Initialize theme system
    ThemeManager.initialize(app)
    print(f"Initial theme: {ThemeManager.get_current_theme()}")
    
    # Show demo window
    window = ThemeDemo()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
