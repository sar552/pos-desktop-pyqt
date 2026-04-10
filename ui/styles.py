# ══════════════════════════════════════════════════════════════
# DESIGN SYSTEM — POS Desktop
# Modern SaaS-grade design tokens (Stripe / Shopify inspired)
# ══════════════════════════════════════════════════════════════

# ── Typography Scale ──────────────────────────────────────────
FONT_SIZES = {
    "xs": 11,
    "sm": 12,
    "base": 14,
    "md": 16,
    "lg": 20,
    "xl": 24,
    "xxl": 32,
}

# ── Spacing (8px grid) ───────────────────────────────────────
SPACING = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 24,
    "xxl": 32,
    "xxxl": 48,
}

# ── Border Radius ─────────────────────────────────────────────
RADIUS = {
    "sm": 6,
    "md": 8,
    "lg": 12,
    "xl": 16,
    "pill": 9999,
}

# ── Shadows (light mode only — dark uses border emphasis) ─────
SHADOWS = {
    "sm": "0 1px 2px rgba(0,0,0,0.05)",
    "md": "0 2px 8px rgba(0,0,0,0.08)",
    "lg": "0 4px 16px rgba(0,0,0,0.10)",
    "xl": "0 8px 32px rgba(0,0,0,0.12)",
}

# ── Transitions ───────────────────────────────────────────────
TRANSITION_FAST = "0.12s"
TRANSITION_BASE = "0.2s"

# ══════════════════════════════════════════════════════════════
# COLOR TOKENS
# ══════════════════════════════════════════════════════════════
THEME_COLORS = {
    "light": {
        # Backgrounds — clean whites / soft grays
        "bg_primary": "#F7F8FA",       # App canvas — soft warm gray
        "bg_secondary": "#FFFFFF",     # Cards / elevated surfaces
        "bg_tertiary": "#F0F2F5",      # Subtle section fills / headers
        "bg_hover": "#EBEDF0",         # Interactive hover state

        # Text — high-contrast neutrals
        "text_primary": "#1A1D23",     # Headings / body
        "text_secondary": "#5E6370",   # Secondary labels
        "text_tertiary": "#9DA3AE",    # Hints / placeholders

        # Borders — subtle, structural
        "border": "#E1E4EA",           # Default border
        "border_light": "#EBEDF0",     # Lighter dividers

        # Accent — indigo-teal (trustworthy, modern)
        "accent": "#635BFF",           # Primary brand (Stripe violet)
        "accent_hover": "#5348DB",     # Hover
        "accent_pressed": "#453BBF",   # Active / pressed
        "accent_light": "#F0EEFF",     # Light accent fill
        "accent_action": "#E8590C",    # High-attention CTA (orange)

        # Selection
        "selection_bg": "#F0EEFF",     # Light accent selection
        "selection_text": "#1A1D23",

        # Inputs
        "input_bg": "#FFFFFF",
        "input_focus_bg": "#FFFFFF",
        "input_border": "#D0D4DB",

        # Scrollbars
        "scrollbar_bg": "#F0F2F5",
        "scrollbar_handle": "#C7CBD2",

        # Status — accessible contrast
        "success": "#16A34A",
        "success_bg": "#F0FDF4",
        "success_border": "#BBF7D0",
        "error": "#DC2626",
        "error_bg": "#FEF2F2",
        "error_border": "#FECACA",
        "warning": "#D97706",
        "warning_bg": "#FFFBEB",
        "warning_border": "#FDE68A",
        "info": "#2563EB",
        "info_bg": "#EFF6FF",
        "info_border": "#BFDBFE",
    },
    "dark": {
        # Backgrounds — deep charcoal (no pure black)
        "bg_primary": "#111318",       # Canvas — warm dark
        "bg_secondary": "#1A1D24",     # Cards / surfaces
        "bg_tertiary": "#23262F",      # Fills / headers
        "bg_hover": "#2C2F38",         # Hover

        # Text — balanced light
        "text_primary": "#ECEEF1",     # Body / headings
        "text_secondary": "#9DA3AE",   # Secondary
        "text_tertiary": "#6B7280",    # Hints

        # Borders — subtle warm
        "border": "#2E3139",           # Default
        "border_light": "#23262F",     # Lighter

        # Accent
        "accent": "#7C75FF",           # Bright violet (visible on dark)
        "accent_hover": "#6E66F0",     # Hover
        "accent_pressed": "#5F56E0",   # Pressed
        "accent_light": "#1E1B35",     # Dark accent fill
        "accent_action": "#F97316",    # Bright orange CTA

        # Selection
        "selection_bg": "#1E1B35",
        "selection_text": "#C4BFFF",

        # Inputs
        "input_bg": "#1A1D24",
        "input_focus_bg": "#23262F",
        "input_border": "#3A3D46",

        # Scrollbars
        "scrollbar_bg": "#1A1D24",
        "scrollbar_handle": "#3A3D46",

        # Status — bright on dark
        "success": "#22C55E",
        "success_bg": "#14261D",
        "success_border": "#1A4D2E",
        "error": "#EF4444",
        "error_bg": "#2A1515",
        "error_border": "#4D1A1A",
        "warning": "#FBBF24",
        "warning_bg": "#2A2510",
        "warning_border": "#4D4417",
        "info": "#3B82F6",
        "info_bg": "#151D2E",
        "info_border": "#1A3352",
    }
}


def get_stylesheet(theme="light"):
    """Generate global application stylesheet based on active theme."""
    colors = THEME_COLORS.get(theme, THEME_COLORS["light"])
    fs = FONT_SIZES
    r = RADIUS
    sp = SPACING

    return f"""
/* ══════════════════════════════════════════════════════════════
   GLOBAL FOUNDATION
   ══════════════════════════════════════════════════════════════ */
QWidget {{
    background-color: {colors['bg_primary']};
    font-family: "Segoe UI", "Inter", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
    font-size: {fs['base']}px;
    color: {colors['text_primary']};
}}

QLabel {{
    background-color: transparent;
    border: none;
}}

/* ══════════════════════════════════════════════════════════════
   INPUT CONTROLS
   ══════════════════════════════════════════════════════════════ */
QLineEdit, QComboBox {{
    padding: {sp['sm'] + 2}px {sp['md']}px;
    font-size: {fs['base']}px;
    border: 1.5px solid {colors.get('input_border', colors['border'])};
    border-radius: {r['md']}px;
    background-color: {colors['input_bg']};
    color: {colors['text_primary']};
}}
QLineEdit:focus, QComboBox:focus {{
    border: 2px solid {colors['accent']};
    background-color: {colors['input_focus_bg']};
}}
QLineEdit:disabled, QComboBox:disabled {{
    background-color: {colors['bg_tertiary']};
    color: {colors['text_tertiary']};
}}

QComboBox QAbstractItemView {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_primary']};
    border: 1px solid {colors['border']};
    selection-background-color: {colors['selection_bg']};
    selection-color: {colors['selection_text']};
    border-radius: {r['sm']}px;
    padding: 4px;
    outline: 0;
}}
QComboBox::drop-down {{ border: none; }}

/* ══════════════════════════════════════════════════════════════
   TABLE SYSTEM — Financial-grade data presentation
   ══════════════════════════════════════════════════════════════ */
QTableWidget {{
    background-color: {colors['bg_secondary']};
    alternate-background-color: {colors['bg_tertiary']};
    border: 1px solid {colors['border']};
    border-radius: {r['lg']}px;
    gridline-color: transparent;
    color: {colors['text_primary']};
    font-size: {fs['base']}px;
    selection-background-color: {colors['selection_bg']};
    selection-color: {colors['text_primary']};
    outline: 0;
}}
QTableWidget::item {{
    padding: {sp['sm'] + 2}px {sp['sm']}px;
    border-bottom: 1px solid {colors['border_light']};
}}
QTableWidget::item:selected {{
    background-color: {colors['selection_bg']};
}}

QHeaderView::section {{
    background-color: {colors['bg_tertiary']};
    color: {colors['text_secondary']};
    padding: {sp['md']}px {sp['sm']}px;
    border: none;
    border-bottom: 2px solid {colors['border']};
    font-size: {fs['xs']}px;
    font-weight: 700;
    letter-spacing: 0.3px;
    text-transform: uppercase;
}}

/* ══════════════════════════════════════════════════════════════
   SCROLLBARS — thin, minimal
   ══════════════════════════════════════════════════════════════ */
QScrollBar:vertical {{
    border: none;
    background: {colors['scrollbar_bg']};
    width: 8px;
    margin: 2px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {colors['scrollbar_handle']};
    min-height: 32px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: {colors['accent_hover']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}

QScrollBar:horizontal {{
    border: none;
    background: {colors['scrollbar_bg']};
    height: 8px;
    margin: 2px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {colors['scrollbar_handle']};
    min-width: 32px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {colors['accent_hover']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}

/* ══════════════════════════════════════════════════════════════
   GROUP BOX
   ══════════════════════════════════════════════════════════════ */
QGroupBox {{
    font-weight: 600;
    font-size: {fs['base']}px;
    border: 1px solid {colors['border']};
    border-radius: {r['lg']}px;
    margin-top: {sp['lg']}px;
    padding: {sp['lg']}px;
    background-color: {colors['bg_secondary']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: {sp['lg']}px;
    padding: 0 {sp['sm']}px;
    color: {colors['text_secondary']};
    font-size: {fs['sm']}px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}

/* ══════════════════════════════════════════════════════════════
   BUTTON SYSTEM
   ══════════════════════════════════════════════════════════════ */
QPushButton {{
    background-color: {colors['bg_secondary']};
    border: 1.5px solid {colors['border']};
    color: {colors['text_primary']};
    border-radius: {r['md']}px;
    padding: {sp['sm']}px {sp['lg']}px;
    font-weight: 600;
    font-size: {fs['sm']}px;
}}
QPushButton:hover {{
    background-color: {colors['bg_tertiary']};
    border-color: {colors.get('input_border', colors['border'])};
}}
QPushButton:pressed {{
    background-color: {colors['bg_hover']};
}}
QPushButton:disabled {{
    background-color: {colors['bg_tertiary']};
    color: {colors['text_tertiary']};
    border-color: {colors['border_light']};
}}

/* ══════════════════════════════════════════════════════════════
   TOOLTIPS
   ══════════════════════════════════════════════════════════════ */
QToolTip {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_primary']};
    border: 1px solid {colors['border']};
    border-radius: {r['sm']}px;
    padding: {sp['sm']}px {sp['md']}px;
    font-size: {fs['sm']}px;
}}

/* ══════════════════════════════════════════════════════════════
   STATUS BAR
   ══════════════════════════════════════════════════════════════ */
QStatusBar {{
    background-color: {colors['bg_secondary']};
    border-top: 1px solid {colors['border']};
    color: {colors['text_secondary']};
    font-size: {fs['xs']}px;
    padding: 2px {sp['sm']}px;
}}
"""


# Legacy support — default to light theme
GLOBAL_STYLE = get_stylesheet("light")
