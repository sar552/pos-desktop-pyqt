# Theme color palettes - Based on design system for POS/Retail
THEME_COLORS = {
    "light": {
        # Backgrounds - Light teal-based
        "bg_primary": "#F0FDFA",      # Very light teal background
        "bg_secondary": "#FFFFFF",     # Pure white for cards
        "bg_tertiary": "#CCFBF1",      # Light teal for headers
        
        # Text colors - Dark teal/gray
        "text_primary": "#134E4A",     # Dark teal for primary text
        "text_secondary": "#0F766E",   # Teal for secondary text
        "text_tertiary": "#64748B",    # Gray for disabled/hints
        
        # Borders
        "border": "#99F6E4",           # Light teal border
        "border_light": "#CCFBF1",     # Very light teal
        
        # Accent colors - Teal primary, Orange for actions
        "accent": "#0D9488",           # Teal primary
        "accent_hover": "#0F766E",     # Darker teal on hover
        "accent_pressed": "#115E59",   # Even darker on press
        "accent_action": "#EA580C",    # Orange for important actions
        
        # Selection
        "selection_bg": "#CCFBF1",     # Light teal selection
        "selection_text": "#134E4A",   # Dark teal text
        
        # Inputs
        "input_bg": "#FFFFFF",         # White input background
        "input_focus_bg": "#F0FDFA",   # Very light teal on focus
        
        # Scrollbars
        "scrollbar_bg": "#F0FDFA",
        "scrollbar_handle": "#99F6E4",
        
        # Status colors
        "success": "#10B981",
        "error": "#DC2626",
        "warning": "#F59E0B",
    },
    "dark": {
        # Backgrounds - Deep blacks and dark grays
        "bg_primary": "#0A0A0C",       # Deep dark background
        "bg_secondary": "#1C1C1E",     # Dark gray for cards
        "bg_tertiary": "#2C2C2E",      # Lighter gray for headers
        
        # Text colors - Light grays and whites
        "text_primary": "#EDEDEF",     # Almost white for primary text
        "text_secondary": "#ADADB0",   # Medium gray for secondary
        "text_tertiary": "#8A8F98",    # Darker gray for hints
        
        # Borders
        "border": "#3A3A3C",           # Dark gray border
        "border_light": "#2C2C2E",     # Very dark gray
        
        # Accent colors - Bright teal/cyan for visibility
        "accent": "#14B8A6",           # Bright teal
        "accent_hover": "#0D9488",     # Medium teal on hover
        "accent_pressed": "#0F766E",   # Darker teal on press
        "accent_action": "#FB923C",    # Bright orange for actions
        
        # Selection
        "selection_bg": "#2C4A47",     # Dark teal selection
        "selection_text": "#5EEAD4",   # Light teal text
        
        # Inputs
        "input_bg": "#1C1C1E",         # Dark input background
        "input_focus_bg": "#2C2C2E",   # Lighter on focus
        
        # Scrollbars
        "scrollbar_bg": "#1C1C1E",
        "scrollbar_handle": "#3A3A3C",
        
        # Status colors
        "success": "#22C55E",
        "error": "#EF4444",
        "warning": "#FBBF24",
    }
}


def get_stylesheet(theme="light"):
    """Generate stylesheet based on theme"""
    colors = THEME_COLORS.get(theme, THEME_COLORS["light"])
    
    return f"""
/* General Application Background and Font */
QWidget {{
    background-color: {colors['bg_primary']};
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: {colors['text_primary']};
}}

/* Base styles for labels */
QLabel {{
    background-color: transparent;
    border: none;
}}

/* Specific styling for large input fields */
QLineEdit, QComboBox {{
    padding: 12px;
    font-size: 16px;
    border: 1px solid {colors['border']};
    border-radius: 8px;
    background-color: {colors['input_bg']};
    color: {colors['text_primary']};
}}

QLineEdit:focus, QComboBox:focus {{
    border: 2px solid {colors['accent']};
    background-color: {colors['input_focus_bg']};
}}

/* ComboBox dropdown styling */
QComboBox QAbstractItemView {{
    background-color: {colors['input_bg']};
    color: {colors['text_primary']};
    border: 1px solid {colors['border']};
    selection-background-color: {colors['selection_bg']};
    selection-color: {colors['selection_text']};
}}
QComboBox::drop-down {{
    border: none;
}}

/* Table Widget (Cart) styling */
QTableWidget {{
    background-color: {colors['bg_secondary']};
    border: 1px solid {colors['border_light']};
    border-radius: 8px;
    gridline-color: {colors['border_light']};
    color: {colors['text_primary']};
    font-size: 15px;
    selection-background-color: {colors['selection_bg']};
    selection-color: {colors['text_primary']};
}}

QTableWidget::item {{
    border-bottom: 1px solid {colors['border_light']};
}}

/* Table Header styling */
QHeaderView::section {{
    background-color: {colors['bg_tertiary']};
    color: {colors['text_secondary']};
    padding: 12px 5px;
    border: none;
    border-bottom: 2px solid {colors['border']};
    font-size: 14px;
    font-weight: bold;
    text-transform: uppercase;
}}

/* Scrollbars */
QScrollBar:vertical {{
    border: none;
    background: {colors['scrollbar_bg']};
    width: 10px;
    margin: 0px 0px 0px 0px;
}}
QScrollBar::handle:vertical {{
    background: {colors['scrollbar_handle']};
    min-height: 20px;
    border-radius: 5px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    border: none;
    background: {colors['scrollbar_bg']};
    height: 10px;
    margin: 0px 0px 0px 0px;
}}
QScrollBar::handle:horizontal {{
    background: {colors['scrollbar_handle']};
    min-width: 20px;
    border-radius: 5px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* GroupBox styling */
QGroupBox {{
    font-weight: bold;
    font-size: 16px;
    border: 1px solid {colors['border_light']};
    border-radius: 8px;
    margin-top: 15px;
    background-color: {colors['bg_secondary']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 15px;
    padding: 0 5px;
    color: {colors['text_secondary']};
}}

/* Custom general buttons */
QPushButton {{
    background-color: {colors['bg_secondary']};
    border: 1px solid {colors['border']};
    color: {colors['text_secondary']};
    border-radius: 8px;
    padding: 8px;
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: {colors['bg_tertiary']};
}}
QPushButton:pressed {{
    background-color: {colors['border_light']};
}}
"""


# Legacy support - default to light theme
GLOBAL_STYLE = get_stylesheet("light")
