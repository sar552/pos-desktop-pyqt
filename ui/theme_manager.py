"""
Theme Manager - Handles theme switching and persistence
"""
from PyQt6.QtWidgets import QApplication
from core.config import load_config, save_config
from ui.styles import get_stylesheet, THEME_COLORS


class ThemeManager:
    """Centralized theme management"""
    
    _current_theme = None
    _app = None
    
    @classmethod
    def initialize(cls, app: QApplication):
        """Initialize theme manager with QApplication instance"""
        cls._app = app
        config = load_config()
        cls._current_theme = config.get("theme", "light")
        cls.apply_theme(cls._current_theme)
    
    @classmethod
    def get_current_theme(cls) -> str:
        """Get current active theme name"""
        return cls._current_theme or "light"
    
    @classmethod
    def apply_theme(cls, theme: str):
        """Apply theme to application"""
        if theme not in THEME_COLORS:
            theme = "light"
        
        cls._current_theme = theme
        
        if cls._app:
            stylesheet = get_stylesheet(theme)
            cls._app.setStyleSheet(stylesheet)
        
        # Persist preference
        config = load_config()
        config["theme"] = theme
        save_config(config)
    
    @classmethod
    def toggle_theme(cls):
        """Toggle between light and dark theme"""
        new_theme = "dark" if cls._current_theme == "light" else "light"
        cls.apply_theme(new_theme)
        return new_theme
    
    @classmethod
    def get_theme_colors(cls, theme: str = None) -> dict:
        """Get color palette for a specific theme"""
        theme = theme or cls._current_theme or "light"
        return THEME_COLORS.get(theme, THEME_COLORS["light"])
    
    @classmethod
    def get_login_styles(cls, theme: str = None) -> dict:
        """Get login window specific styles based on theme"""
        theme = theme or cls._current_theme or "light"
        colors = cls.get_theme_colors(theme)
        
        if theme == "dark":
            return {
                "background": f"""
                    QWidget#loginBg {{
                        background: qlineargradient(
                            x1:0, y1:0, x2:1, y2:1,
                            stop:0 {colors['bg_primary']}, 
                            stop:0.5 {colors['bg_secondary']}, 
                            stop:1 {colors['bg_primary']}
                        );
                    }}
                """,
                "card": f"""
                    QFrame#loginCard {{
                        background: {colors['bg_secondary']};
                        border-radius: 20px;
                        border: 1px solid {colors['border']};
                    }}
                """,
                "title_color": colors['text_primary'],
                "subtitle_color": colors['text_tertiary'],
                "input_style": f"""
                    QLineEdit {{
                        padding: 12px 14px;
                        font-size: 14px;
                        border: 1.5px solid {colors['border']};
                        border-radius: 10px;
                        background: {colors['input_bg']};
                        color: {colors['text_primary']};
                    }}
                    QLineEdit:focus {{
                        border: 1.5px solid {colors['accent']};
                        background: {colors['input_focus_bg']};
                    }}
                    QLineEdit:disabled {{
                        background: {colors['bg_tertiary']};
                        color: {colors['text_tertiary']};
                    }}
                """,
                "input_active_style": f"""
                    QLineEdit {{
                        padding: 12px 14px;
                        font-size: 14px;
                        border: 2px solid {colors['accent']};
                        border-radius: 10px;
                        background: {colors['input_focus_bg']};
                        color: {colors['text_primary']};
                    }}
                    QLineEdit:disabled {{
                        background: {colors['bg_tertiary']};
                        color: {colors['text_tertiary']};
                    }}
                """,
                "label_style": f"""
                    font-size: 12px; font-weight: 700; color: {colors['text_tertiary']};
                    margin-bottom: 4px; margin-top: 10px; background: transparent;
                """,
                "keyboard_panel": f"""
                    QFrame {{
                        background: {colors['bg_secondary']};
                        border-top: 2px solid {colors['border']};
                    }}
                """,
                "kb_display": f"""
                    font-size: 16px; font-weight: 600; color: {colors['text_primary']};
                    background: {colors['input_bg']}; border: 1.5px solid {colors['accent']};
                    border-radius: 8px; padding: 6px 12px;
                """,
            }
        else:  # light theme
            return {
                "background": f"""
                    QWidget#loginBg {{
                        background: qlineargradient(
                            x1:0, y1:0, x2:1, y2:1,
                            stop:0 #e0f2fe, 
                            stop:0.5 #f0f9ff, 
                            stop:1 #e0f2fe
                        );
                    }}
                """,
                "card": f"""
                    QFrame#loginCard {{
                        background: white;
                        border-radius: 20px;
                        border: 1px solid #e2e8f0;
                    }}
                """,
                "title_color": "#0f172a",
                "subtitle_color": "#94a3b8",
                "input_style": f"""
                    QLineEdit {{
                        padding: 12px 14px;
                        font-size: 14px;
                        border: 1.5px solid #e2e8f0;
                        border-radius: 10px;
                        background: #f8fafc;
                        color: #1e293b;
                    }}
                    QLineEdit:focus {{
                        border: 1.5px solid #3b82f6;
                        background: #ffffff;
                    }}
                    QLineEdit:disabled {{
                        background: #f1f5f9;
                        color: #94a3b8;
                    }}
                """,
                "input_active_style": f"""
                    QLineEdit {{
                        padding: 12px 14px;
                        font-size: 14px;
                        border: 2px solid #3b82f6;
                        border-radius: 10px;
                        background: #ffffff;
                        color: #1e293b;
                    }}
                    QLineEdit:disabled {{
                        background: #f1f5f9;
                        color: #94a3b8;
                    }}
                """,
                "label_style": f"""
                    font-size: 12px; font-weight: 700; color: #64748b;
                    margin-bottom: 4px; margin-top: 10px; background: transparent;
                """,
                "keyboard_panel": f"""
                    QFrame {{
                        background: #f1f5f9;
                        border-top: 2px solid #cbd5e1;
                    }}
                """,
                "kb_display": f"""
                    font-size: 16px; font-weight: 600; color: #334155;
                    background: white; border: 1.5px solid #3b82f6;
                    border-radius: 8px; padding: 6px 12px;
                """,
            }
