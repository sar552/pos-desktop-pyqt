"""
UI Component Theme Utilities
Professional design system component styles for POS Desktop application.
All components reference design tokens from styles.py.
"""
from ui.theme_manager import ThemeManager
from ui.styles import FONT_SIZES, SPACING, RADIUS

FS = FONT_SIZES
SP = SPACING
R = RADIUS


def get_component_styles():
    """Get theme-aware style dict for every UI component."""
    colors = ThemeManager.get_theme_colors()

    return {
        # =====================================================
        #  CART WIDGET
        # =====================================================
        "cart_container": (
            f"background-color: {colors['bg_primary']}; "
            f"color: {colors['text_primary']};"
        ),

        "cart_label": (
            f"color: {colors['text_tertiary']}; "
            f"font-size: {FS['xs']}px; font-weight: 600; "
            f"letter-spacing: 0.5px; text-transform: uppercase;"
        ),

        "cart_input": f"""
            QLineEdit {{
                background: {colors['input_bg']};
                color: {colors['text_primary']};
                border: 1.5px solid {colors.get('input_border', colors['border'])};
                border-radius: {R['md']}px;
                padding: {SP['sm']}px {SP['md']}px;
                font-size: {FS['base']}px;
            }}
            QLineEdit:focus {{
                border: 2px solid {colors['accent']};
                background: {colors['input_focus_bg']};
            }}
        """,

        "cart_combo": f"""
            QComboBox {{
                background: {colors['input_bg']};
                color: {colors['text_primary']};
                border: 1.5px solid {colors.get('input_border', colors['border'])};
                border-radius: {R['md']}px;
                padding: 6px {SP['md']}px;
                font-size: {FS['sm']}px;
                font-weight: 600;
                min-height: 24px;
            }}
            QComboBox:focus {{ border: 2px solid {colors['accent']}; }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox::down-arrow {{ width: 12px; height: 12px; margin-right: 6px; }}
            QComboBox QAbstractItemView {{
                background: {colors['bg_secondary']};
                color: {colors['text_primary']};
                selection-background-color: {colors['selection_bg']};
                selection-color: {colors['text_primary']};
                padding: 4px;
                outline: 0;
            }}
        """,

        "cart_button": f"""
            QPushButton {{
                background: {colors['bg_secondary']};
                color: {colors['text_secondary']};
                border: 1.5px solid {colors['border']};
                border-radius: {R['md']}px;
                font-size: {FS['sm']}px;
                font-weight: 600;
                padding: {SP['sm']}px {SP['lg']}px;
            }}
            QPushButton:hover {{
                background: {colors['bg_tertiary']};
                border-color: {colors.get('input_border', colors['border'])};
                color: {colors['text_primary']};
            }}
            QPushButton:pressed {{ background: {colors['bg_hover']}; }}
        """,

        "cart_list": f"""
            QListWidget {{
                background: {colors['bg_secondary']};
                color: {colors['text_primary']};
                border: 1px solid {colors['border']};
                border-radius: {R['md']}px;
                padding: 4px;
                outline: 0;
            }}
            QListWidget::item {{
                background: transparent;
                padding: {SP['sm']}px {SP['md']}px;
                border-radius: {R['sm']}px;
            }}
            QListWidget::item:hover {{ background: {colors['bg_tertiary']}; }}
            QListWidget::item:selected {{
                background: {colors['accent']};
                color: white;
            }}
        """,

        "cart_table": f"""
            QTableWidget {{
                background: {colors['bg_secondary']};
                alternate-background-color: {colors['bg_tertiary']};
                color: {colors['text_primary']};
                gridline-color: transparent;
                border: none;
                border-radius: {R['lg']}px;
                outline: 0;
            }}
            QTableWidget::item {{
                padding: {SP['sm'] + 2}px {SP['sm']}px;
                border-bottom: 1px solid {colors['border_light']};
            }}
            QTableWidget::item:selected {{
                background: {colors['selection_bg']};
                color: {colors['text_primary']};
            }}
            QHeaderView::section {{
                background-color: {colors['bg_tertiary']};
                color: {colors['text_secondary']};
                font-weight: 700;
                font-size: {FS['xs']}px;
                padding: {SP['md']}px {SP['sm']}px;
                border: none;
                border-bottom: 2px solid {colors['border']};
                letter-spacing: 0.3px;
            }}
        """,

        "cart_total_label": (
            f"color: {colors['text_tertiary']}; "
            f"font-size: {FS['sm']}px; font-weight: 600; "
            f"text-transform: uppercase; letter-spacing: 0.5px;"
        ),

        "cart_total_value": (
            f"color: {colors['success']}; "
            f"font-size: {FS['xl']}px; font-weight: 800; "
            f"background: {colors.get('success_bg', colors['bg_tertiary'])}; "
            f"padding: 6px {SP['lg']}px; "
            f"border-radius: {R['md']}px; "
            f"border: 1px solid {colors.get('success_border', colors['border'])};"
        ),

        # =====================================================
        #  ITEM BROWSER
        # =====================================================
        "item_browser_bg": f"background: {colors['bg_primary']};",

        "item_card": f"""
            background: {colors['bg_secondary']};
            border-radius: {R['lg']}px;
            border: 1px solid {colors['border']};
        """,

        "item_card_hover": f"""
            background: {colors['bg_tertiary']};
            border: 1.5px solid {colors['accent']};
        """,

        "item_image_container": (
            f"background: {colors['bg_tertiary']}; "
            f"border-radius: {R['md']}px;"
        ),

        "item_info_container": f"background: {colors['bg_secondary']};",

        "item_name": (
            f"color: {colors['text_primary']}; "
            f"font-size: {FS['base']}px; font-weight: 600;"
        ),

        "item_price": f"""
            background: {colors['accent']};
            color: white;
            font-size: {FS['sm']}px;
            font-weight: 700;
            border-radius: {R['sm']}px;
            padding: 6px {SP['md']}px;
        """,

        "item_stock": (
            f"color: {colors['text_tertiary']}; "
            f"font-size: {FS['xs']}px; font-weight: 600;"
        ),

        "item_search": f"""
            QLineEdit {{
                font-size: {FS['base']}px;
                padding: {SP['md']}px {SP['lg']}px;
                border-radius: {R['md']}px;
                background: {colors['input_bg']};
                color: {colors['text_primary']};
                border: 1.5px solid {colors.get('input_border', colors['border'])};
            }}
            QLineEdit:focus {{
                border: 2px solid {colors['accent']};
                background: {colors['input_focus_bg']};
            }}
        """,

        # =====================================================
        #  DIALOG / WINDOW BASE
        # =====================================================
        "dialog_bg": f"""
            QDialog {{
                background: {colors['bg_primary']};
                color: {colors['text_primary']};
            }}
            QWidget {{
                background: transparent;
                color: {colors['text_primary']};
            }}
        """,

        "dialog_label": (
            f"color: {colors['text_secondary']}; "
            f"font-size: {FS['sm']}px; font-weight: 500;"
        ),

        "dialog_title": (
            f"color: {colors['text_primary']}; "
            f"font-size: {FS['lg']}px; font-weight: 700; "
            f"padding: {SP['sm']}px 0;"
        ),

        "dialog_section_title": f"""
            color: {colors['text_primary']};
            font-size: {FS['md']}px;
            font-weight: 600;
            padding: {SP['sm']}px 0;
            border-bottom: 2px solid {colors['border']};
        """,

        # =====================================================
        #  PAYMENT / CHECKOUT
        # =====================================================
        "payment_container": f"""
            QWidget {{
                background: {colors['bg_primary']};
                color: {colors['text_primary']};
            }}
        """,

        "payment_method_button": f"""
            QPushButton {{
                background: {colors['bg_secondary']};
                color: {colors['text_primary']};
                border: 1.5px solid {colors['border']};
                border-radius: {R['lg']}px;
                padding: {SP['xl']}px;
                font-size: {FS['base']}px;
                font-weight: 600;
                min-height: 72px;
            }}
            QPushButton:hover {{
                background: {colors['bg_tertiary']};
                border: 1.5px solid {colors['accent']};
            }}
            QPushButton:checked {{
                background: {colors['accent']};
                color: white;
                border: 1.5px solid {colors['accent']};
            }}
        """,

        "payment_input": f"""
            QLineEdit {{
                background: {colors['input_bg']};
                color: {colors['text_primary']};
                border: 1.5px solid {colors.get('input_border', colors['border'])};
                border-radius: {R['md']}px;
                padding: {SP['md']}px {SP['lg']}px;
                font-size: {FS['md']}px;
                font-weight: 500;
            }}
            QLineEdit:focus {{
                border: 2px solid {colors['accent']};
                background: {colors['input_focus_bg']};
            }}
        """,

        "payment_total": f"""
            background: {colors['accent']};
            color: white;
            font-size: {FS['xxl']}px;
            font-weight: 800;
            padding: {SP['lg']}px {SP['xl']}px;
            border-radius: {R['lg']}px;
        """,

        "payment_button_primary": f"""
            QPushButton {{
                background: {colors['success']};
                color: white;
                font-weight: 700;
                font-size: {FS['md']}px;
                border-radius: {R['md']}px;
                padding: {SP['lg']}px {SP['xxl']}px;
                border: none;
            }}
            QPushButton:hover {{ background: #15803D; }}
            QPushButton:pressed {{ background: #166534; }}
            QPushButton:disabled {{
                background: {colors['bg_tertiary']};
                color: {colors['text_tertiary']};
            }}
        """,

        "payment_button_secondary": f"""
            QPushButton {{
                background: {colors['bg_secondary']};
                color: {colors['text_primary']};
                font-weight: 600;
                font-size: {FS['base']}px;
                border: 1.5px solid {colors['border']};
                border-radius: {R['md']}px;
                padding: {SP['md']}px {SP['xl']}px;
            }}
            QPushButton:hover {{
                background: {colors['bg_tertiary']};
                border-color: {colors.get('input_border', colors['border'])};
            }}
        """,

        "payment_button_danger": f"""
            QPushButton {{
                background: {colors['error']};
                color: white;
                font-weight: 700;
                font-size: {FS['md']}px;
                border-radius: {R['md']}px;
                padding: {SP['lg']}px {SP['xxl']}px;
                border: none;
            }}
            QPushButton:hover {{ background: #B91C1C; }}
            QPushButton:pressed {{ background: #991B1B; }}
            QPushButton:disabled {{
                background: {colors['bg_tertiary']};
                color: {colors['text_tertiary']};
            }}
        """,

        # =====================================================
        #  POS CLOSING / CASH MANAGEMENT
        # =====================================================
        "closing_container": f"""
            QWidget {{
                background: {colors['bg_primary']};
                color: {colors['text_primary']};
            }}
        """,

        "closing_summary_card": f"""
            QGroupBox, QFrame {{
                background: {colors['bg_secondary']};
                border: none;
                border-radius: {R['xl']}px;
                padding: {SP['lg']}px;
                margin-top: {SP['sm']}px;
            }}
            QGroupBox::title {{
                color: {colors['text_primary']};
                subcontrol-origin: margin;
                padding: 0 {SP['sm']}px;
                font-weight: 700;
                font-size: {FS['base']}px;
            }}
        """,

        "closing_amount_label": f"""
            color: {colors['text_secondary']};
            font-size: {FS['base']}px;
            font-weight: 500;
            padding: 4px 0;
        """,

        "closing_amount_value": f"""
            color: {colors['text_primary']};
            font-size: {FS['lg']}px;
            font-weight: 700;
            padding: 4px 0;
            font-family: "IBM Plex Mono", "Cascadia Code", "Consolas", monospace;
        """,

        "closing_total": f"""
            background: {colors['accent']};
            color: white;
            font-size: {FS['xl']}px;
            font-weight: 800;
            padding: {SP['md']}px {SP['xl']}px;
            border-radius: {R['lg']}px;
        """,

        "closing_table": f"""
            QTableWidget {{
                background: {colors['bg_secondary']};
                alternate-background-color: {colors['bg_tertiary']};
                color: {colors['text_primary']};
                gridline-color: transparent;
                border: 1px solid {colors['border']};
                border-radius: {R['lg']}px;
                outline: 0;
            }}
            QTableWidget::item {{
                padding: {SP['sm'] + 2}px {SP['sm']}px;
                border-bottom: 1px solid {colors['border_light']};
            }}
            QHeaderView::section {{
                background-color: {colors['bg_tertiary']};
                color: {colors['text_secondary']};
                font-weight: 700;
                font-size: {FS['xs']}px;
                padding: {SP['md']}px {SP['sm']}px;
                border: none;
                border-bottom: 2px solid {colors['border']};
                letter-spacing: 0.3px;
            }}
        """,

        # =====================================================
        #  HISTORY / LISTS
        # =====================================================
        "list_container": f"""
            QWidget {{
                background: {colors['bg_primary']};
                color: {colors['text_primary']};
            }}
        """,

        "list_table": f"""
            QTableWidget {{
                background-color: {colors['bg_secondary']};
                alternate-background-color: {colors['bg_tertiary']};
                color: {colors['text_primary']};
                gridline-color: transparent;
                border: 1px solid {colors['border']};
                border-radius: {R['lg']}px;
                outline: 0;
            }}
            QTableWidget::item {{
                padding: {SP['sm'] + 2}px {SP['sm']}px;
                border-bottom: 1px solid {colors['border_light']};
            }}
            QTableWidget::item:selected {{
                background: {colors['selection_bg']};
                color: {colors['text_primary']};
            }}
            QHeaderView::section {{
                background-color: {colors['bg_tertiary']};
                color: {colors['text_secondary']};
                padding: {SP['md']}px {SP['sm']}px;
                border: none;
                border-bottom: 2px solid {colors['border']};
                font-size: {FS['xs']}px;
                font-weight: 700;
                letter-spacing: 0.3px;
            }}
        """,

        # =====================================================
        #  CHECKOUT WINDOW
        # =====================================================
        "checkout_container": (
            f"background: {colors['bg_primary']}; "
            f"color: {colors['text_primary']};"
        ),

        "checkout_header": f"""
            background: {colors['accent']};
            color: white;
            font-size: {FS['lg']}px;
            font-weight: 700;
            padding: {SP['lg']}px;
            border-radius: {R['md']}px {R['md']}px 0 0;
        """,

        "checkout_discount_input": f"""
            QLineEdit {{
                background: {colors['input_bg']};
                color: {colors['text_primary']};
                border: 1.5px solid {colors.get('input_border', colors['border'])};
                border-radius: {R['md']}px;
                padding: {SP['md']}px;
                font-size: {FS['base']}px;
            }}
            QLineEdit:focus {{ border: 2px solid {colors['accent']}; }}
        """,

        # =====================================================
        #  NUMPAD
        # =====================================================
        "numpad_button": f"""
            QPushButton {{
                background: {colors['bg_secondary']};
                color: {colors['text_primary']};
                border: 1.5px solid {colors['border']};
                border-radius: {R['md']}px;
                font-size: {FS['lg']}px;
                font-weight: 600;
                min-height: 56px;
            }}
            QPushButton:hover {{
                background: {colors['bg_tertiary']};
                border-color: {colors['accent']};
            }}
            QPushButton:pressed {{
                background: {colors['accent']};
                color: white;
            }}
        """,

        "numpad_display": f"""
            background: {colors['input_bg']};
            color: {colors['text_primary']};
            border: 1.5px solid {colors.get('input_border', colors['border'])};
            border-radius: {R['md']}px;
            padding: {SP['lg']}px;
            font-size: {FS['xl']}px;
            font-weight: 700;
            font-family: "IBM Plex Mono", "Cascadia Code", monospace;
        """,

        # =====================================================
        #  CARD COMPONENT (reusable)
        # =====================================================
        "card": f"""
            QFrame {{
                background: {colors['bg_secondary']};
                border: 1px solid {colors['border']};
                border-radius: {R['lg']}px;
            }}
        """,

        "card_header": f"""
            font-size: {FS['md']}px;
            font-weight: 700;
            color: {colors['text_primary']};
            padding-bottom: {SP['sm']}px;
        """,

        # =====================================================
        #  BADGE / PILL COMPONENTS
        # =====================================================
        "badge_success": f"""
            background: {colors.get('success_bg', colors['bg_tertiary'])};
            color: {colors['success']};
            border: 1px solid {colors.get('success_border', colors['border'])};
            border-radius: {R['pill']}px;
            padding: 2px {SP['sm']}px;
            font-size: {FS['xs']}px;
            font-weight: 700;
        """,

        "badge_error": f"""
            background: {colors.get('error_bg', colors['bg_tertiary'])};
            color: {colors['error']};
            border: 1px solid {colors.get('error_border', colors['border'])};
            border-radius: {R['pill']}px;
            padding: 2px {SP['sm']}px;
            font-size: {FS['xs']}px;
            font-weight: 700;
        """,

        "badge_warning": f"""
            background: {colors.get('warning_bg', colors['bg_tertiary'])};
            color: {colors['warning']};
            border: 1px solid {colors.get('warning_border', colors['border'])};
            border-radius: {R['pill']}px;
            padding: 2px {SP['sm']}px;
            font-size: {FS['xs']}px;
            font-weight: 700;
        """,

        "badge_info": f"""
            background: {colors.get('info_bg', colors['bg_tertiary'])};
            color: {colors.get('info', colors['accent'])};
            border: 1px solid {colors.get('info_border', colors['border'])};
            border-radius: {R['pill']}px;
            padding: 2px {SP['sm']}px;
            font-size: {FS['xs']}px;
            font-weight: 700;
        """,

        # =====================================================
        #  TOP-BAR BUTTON PRESETS
        # =====================================================
        "topbar_btn": f"""
            QPushButton {{
                background: {colors['bg_secondary']};
                color: {colors['text_primary']};
                font-weight: 600;
                font-size: {FS['sm']}px;
                border-radius: {R['md']}px;
                border: 1.5px solid {colors['border']};
                padding: 0 {SP['lg']}px;
                min-height: 36px;
            }}
            QPushButton:hover {{
                background: {colors['bg_tertiary']};
                border-color: {colors.get('input_border', colors['border'])};
            }}
            QPushButton:pressed {{ background: {colors['bg_hover']}; }}
            QPushButton:disabled {{
                background: {colors['bg_tertiary']};
                color: {colors['text_tertiary']};
            }}
        """,

        "topbar_btn_accent": f"""
            QPushButton {{
                background: {colors['accent']};
                color: white;
                font-weight: 600;
                font-size: {FS['sm']}px;
                border-radius: {R['md']}px;
                border: none;
                padding: 0 {SP['lg']}px;
                min-height: 36px;
            }}
            QPushButton:hover {{ background: {colors['accent_hover']}; }}
            QPushButton:pressed {{ background: {colors['accent_pressed']}; }}
            QPushButton:disabled {{
                background: {colors['bg_tertiary']};
                color: {colors['text_tertiary']};
            }}
        """,

        "topbar_btn_success": f"""
            QPushButton {{
                background: {colors['success']};
                color: white;
                font-weight: 700;
                font-size: {FS['sm']}px;
                border-radius: {R['md']}px;
                border: none;
                padding: 0 {SP['lg']}px;
                min-height: 36px;
            }}
            QPushButton:hover {{ background: #15803D; }}
            QPushButton:pressed {{ background: #166534; }}
            QPushButton:disabled {{
                background: {colors['bg_tertiary']};
                color: {colors['text_tertiary']};
            }}
        """,

        "topbar_btn_danger": f"""
            QPushButton {{
                background: {colors['error']};
                color: white;
                font-weight: 700;
                font-size: {FS['sm']}px;
                border-radius: {R['md']}px;
                border: none;
                padding: 0 {SP['lg']}px;
                min-height: 36px;
            }}
            QPushButton:hover {{ background: #B91C1C; }}
            QPushButton:pressed {{ background: #991B1B; }}
            QPushButton:disabled {{
                background: {colors['bg_tertiary']};
                color: {colors['text_tertiary']};
            }}
        """,

        # =====================================================
        #  POS OPENING STYLES
        # =====================================================
        "opening_container": f"""
            background: {colors['bg_primary']};
            color: {colors['text_primary']};
        """,

        "opening_header": f"""
            background: {colors['accent']};
            border-radius: {R['lg']}px;
            padding: {SP['lg']}px;
        """,

        "opening_combo": f"""
            QComboBox {{
                background: {colors['bg_secondary']};
                color: {colors['text_primary']};
                border-radius: {R['sm']}px;
                padding: {SP['sm']}px {SP['md']}px;
                font-weight: 600;
                font-size: {FS['base']}px;
                border: 1.5px solid {colors['border']};
            }}
            QComboBox:focus {{ border: 2px solid white; }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background: {colors['bg_secondary']};
                color: {colors['text_primary']};
                selection-background-color: {colors['selection_bg']};
                outline: 0;
            }}
        """,

        "opening_section_label": f"""
            font-size: {FS['xs']}px;
            font-weight: 700;
            color: {colors['text_tertiary']};
            letter-spacing: 1px;
            text-transform: uppercase;
        """,

        "opening_input_active": f"""
            padding: {SP['sm'] + 2}px {SP['md']}px;
            font-size: {FS['md']}px;
            font-weight: 600;
            border: 2px solid {colors['accent']};
            border-radius: {R['md']}px;
            background: {colors['input_focus_bg']};
            color: {colors['text_primary']};
        """,

        "opening_input_idle": f"""
            padding: {SP['sm'] + 2}px {SP['md']}px;
            font-size: {FS['md']}px;
            font-weight: 600;
            border: 1.5px solid {colors.get('input_border', colors['border'])};
            border-radius: {R['md']}px;
            background: {colors['input_bg']};
            color: {colors['text_primary']};
        """,

        "opening_btn_primary": f"""
            QPushButton {{
                background: {colors['accent']};
                color: white;
                font-weight: 700;
                font-size: {FS['base']}px;
                border-radius: {R['lg']}px;
                border: none;
                min-height: 44px;
            }}
            QPushButton:hover {{ background: {colors['accent_hover']}; }}
            QPushButton:disabled {{
                background: {colors['bg_tertiary']};
                color: {colors['text_tertiary']};
            }}
        """,

        "opening_btn_secondary": f"""
            QPushButton {{
                background: {colors['bg_tertiary']};
                color: {colors['text_secondary']};
                font-weight: 600;
                font-size: {FS['sm']}px;
                border-radius: {R['lg']}px;
                border: none;
                min-height: 44px;
            }}
            QPushButton:hover {{ background: {colors['bg_hover']}; color: {colors['text_primary']}; }}
        """,

        "opening_btn_warning": f"""
            QPushButton {{
                background: {colors.get('warning_bg', '#FFFBEB')};
                color: {colors['warning']};
                font-weight: 700;
                font-size: {FS['sm']}px;
                border-radius: {R['lg']}px;
                border: 1px solid {colors.get('warning_border', '#FDE68A')};
                min-height: 44px;
            }}
            QPushButton:hover {{ background: {colors.get('warning_border', '#FDE68A')}; }}
        """,
    }


def apply_theme_to_widget(widget, style_key):
    """Apply theme style to widget by key."""
    styles = get_component_styles()
    if style_key in styles:
        widget.setStyleSheet(styles[style_key])


def get_themed_dialog_style():
    """Get complete dialog stylesheet."""
    styles = get_component_styles()
    return styles["dialog_bg"]
