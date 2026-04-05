"""
UI Component Theme Utilities
Provides theme-aware style generators for all components
Professional design system for POS Desktop application
"""
from ui.theme_manager import ThemeManager


def get_component_styles():
    """Get theme-aware styles for UI components"""
    colors = ThemeManager.get_theme_colors()
    
    return {
        # ==========================================
        # CART WIDGET STYLES
        # ==========================================
        "cart_container": f"background-color: {colors['bg_primary']}; color: {colors['text_primary']};",
        
        "cart_label": f"color: {colors['text_tertiary']}; font-size: 11px; font-weight: 600;",
        
        "cart_input": f"""
            QLineEdit {{
                background: {colors['input_bg']};
                color: {colors['text_primary']};
                border: 1px solid {colors['border']};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
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
                border: 1px solid {colors['border']};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }}
            QComboBox:focus {{ border: 2px solid {colors['accent']}; }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background: {colors['bg_secondary']};
                color: {colors['text_primary']};
                selection-background-color: {colors['selection_bg']};
                selection-color: {colors['text_primary']};
            }}
        """,
        
        "cart_button": f"""
            QPushButton {{
                background: {colors['bg_tertiary']};
                color: {colors['text_secondary']};
                border: 1px solid {colors['border']};
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                padding: 8px 14px;
            }}
            QPushButton:hover {{ 
                background: {colors['border']}; 
                color: {colors['text_primary']}; 
            }}
        """,
        
        "cart_list": f"""
            QListWidget {{
                background: {colors['bg_secondary']};
                color: {colors['text_primary']};
                border: 1px solid {colors['border']};
                border-radius: 6px;
                padding: 4px;
            }}
            QListWidget::item {{ 
                background: transparent;
                padding: 8px 10px;
                border-radius: 4px;
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
                color: {colors['text_primary']};
                gridline-color: {colors['border_light']};
                border: none;
                border-radius: 8px;
            }}
            QTableWidget::item {{ 
                padding: 10px 8px; 
                border-bottom: 1px solid {colors['border_light']};
            }}
            QHeaderView::section {{
                background-color: {colors['bg_tertiary']};
                color: {colors['text_secondary']};
                font-weight: 700;
                font-size: 11px;
                padding: 12px 8px;
                border: none;
                border-bottom: 2px solid {colors['border']};
            }}
        """,
        
        "cart_total_label": f"color: {colors['text_tertiary']}; font-size: 13px; font-weight: 600;",
        
        "cart_total_value": f"""
            color: {colors['success']};
            font-size: 22px;
            font-weight: 900;
            background: {colors['bg_tertiary']};
            padding: 4px 14px;
            border-radius: 8px;
        """,
        
        # ==========================================
        # ITEM BROWSER STYLES
        # ==========================================
        "item_browser_bg": f"background: {colors['bg_primary']};",
        
        "item_card": f"""
            background: {colors['bg_secondary']};
            border-radius: 12px;
            border: 1px solid {colors['border']};
        """,
        
        "item_card_hover": f"""
            background: {colors['bg_tertiary']};
            border: 2px solid {colors['accent']};
        """,
        
        "item_image_container": f"background: {colors['bg_tertiary']}; border-radius: 8px;",
        
        "item_info_container": f"background: {colors['bg_secondary']};",
        
        "item_name": f"color: {colors['text_primary']}; font-size: 14px; font-weight: 600;",
        
        "item_price": f"""
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {colors['accent']}, stop:1 {colors['accent_hover']});
            color: white;
            font-size: 15px;
            font-weight: 700;
            border-radius: 6px;
            padding: 8px 14px;
        """,
        
        "item_stock": f"color: {colors['text_tertiary']}; font-size: 11px; font-weight: 600;",
        
        "item_search": f"""
            QLineEdit {{
                font-size: 14px;
                padding: 12px 16px;
                border-radius: 8px;
                background: {colors['input_bg']};
                color: {colors['text_primary']};
                border: 1px solid {colors['border']};
            }}
            QLineEdit:focus {{ border: 2px solid {colors['accent']}; }}
        """,
        
        # ==========================================
        # DIALOG/WINDOW STYLES
        # ==========================================
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
        
        "dialog_label": f"color: {colors['text_secondary']}; font-size: 13px; font-weight: 500;",
        
        "dialog_title": f"""
            color: {colors['text_primary']}; 
            font-size: 20px; 
            font-weight: 700;
            padding: 8px 0;
        """,
        
        "dialog_section_title": f"""
            color: {colors['text_primary']};
            font-size: 15px;
            font-weight: 600;
            padding: 6px 0;
            border-bottom: 2px solid {colors['border']};
        """,
        
        # ==========================================
        # PAYMENT/CHECKOUT STYLES
        # ==========================================
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
                border: 2px solid {colors['border']};
                border-radius: 12px;
                padding: 20px;
                font-size: 14px;
                font-weight: 600;
                min-height: 80px;
            }}
            QPushButton:hover {{
                background: {colors['bg_tertiary']};
                border: 2px solid {colors['accent']};
            }}
            QPushButton:checked {{
                background: {colors['accent']};
                color: white;
                border: 2px solid {colors['accent']};
            }}
        """,
        
        "payment_input": f"""
            QLineEdit {{
                background: {colors['input_bg']};
                color: {colors['text_primary']};
                border: 2px solid {colors['border']};
                border-radius: 8px;
                padding: 14px 16px;
                font-size: 16px;
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
            font-size: 28px;
            font-weight: 900;
            padding: 16px 24px;
            border-radius: 12px;
        """,
        
        "payment_button_primary": f"""
            QPushButton {{
                background: {colors['success']};
                color: white;
                font-weight: 700;
                font-size: 16px;
                border-radius: 10px;
                padding: 16px 32px;
                border: none;
            }}
            QPushButton:hover {{ background: #059669; }}
            QPushButton:pressed {{ background: #047857; }}
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
                font-size: 14px;
                border: 2px solid {colors['border']};
                border-radius: 10px;
                padding: 14px 28px;
            }}
            QPushButton:hover {{ 
                background: {colors['bg_tertiary']}; 
                border: 2px solid {colors['accent']};
            }}
        """,
        
        # ==========================================
        # POS CLOSING STYLES
        # ==========================================
        "closing_container": f"""
            QWidget {{
                background: {colors['bg_primary']};
                color: {colors['text_primary']};
            }}
        """,
        
        "closing_summary_card": f"""
            QGroupBox {{
                background: {colors['bg_secondary']};
                border: 1px solid {colors['border']};
                border-radius: 12px;
                padding: 16px;
                margin-top: 10px;
                font-weight: 600;
                font-size: 14px;
            }}
            QGroupBox::title {{
                color: {colors['text_primary']};
                subcontrol-origin: margin;
                padding: 0 8px;
            }}
        """,
        
        "closing_amount_label": f"""
            color: {colors['text_secondary']};
            font-size: 14px;
            font-weight: 500;
            padding: 4px 0;
        """,
        
        "closing_amount_value": f"""
            color: {colors['text_primary']};
            font-size: 18px;
            font-weight: 700;
            padding: 4px 0;
        """,
        
        "closing_total": f"""
            background: {colors['accent']};
            color: white;
            font-size: 24px;
            font-weight: 900;
            padding: 12px 20px;
            border-radius: 10px;
        """,
        
        "closing_table": f"""
            QTableWidget {{
                background: {colors['bg_secondary']};
                color: {colors['text_primary']};
                gridline-color: {colors['border_light']};
                border: 1px solid {colors['border']};
                border-radius: 8px;
            }}
            QTableWidget::item {{
                padding: 10px 8px;
                border-bottom: 1px solid {colors['border_light']};
            }}
            QHeaderView::section {{
                background-color: {colors['bg_tertiary']};
                color: {colors['text_secondary']};
                font-weight: 700;
                font-size: 12px;
                padding: 12px 8px;
                border: none;
                border-bottom: 2px solid {colors['border']};
            }}
        """,
        
        # ==========================================
        # HISTORY/LIST STYLES
        # ==========================================
        "list_container": f"""
            QWidget {{
                background: {colors['bg_primary']};
                color: {colors['text_primary']};
            }}
        """,
        
        "list_table": f"""
            QTableWidget {{
                background-color: {colors['bg_secondary']};
                color: {colors['text_primary']};
                gridline-color: {colors['border_light']};
                border: 1px solid {colors['border']};
                border-radius: 8px;
            }}
            QTableWidget::item {{
                padding: 10px 8px;
                border-bottom: 1px solid {colors['border_light']};
            }}
            QTableWidget::item:selected {{
                background: {colors['selection_bg']};
                color: {colors['text_primary']};
            }}
            QHeaderView::section {{
                background-color: {colors['bg_tertiary']};
                color: {colors['text_secondary']};
                padding: 12px 8px;
                border: none;
                border-bottom: 2px solid {colors['border']};
                font-size: 12px;
                font-weight: 700;
            }}
        """,
        
        # ==========================================
        # CHECKOUT WINDOW STYLES
        # ==========================================
        "checkout_container": f"background: {colors['bg_primary']}; color: {colors['text_primary']};",
        
        "checkout_header": f"""
            background: {colors['accent']};
            color: white;
            font-size: 18px;
            font-weight: 700;
            padding: 16px;
            border-radius: 8px 8px 0 0;
        """,
        
        "checkout_discount_input": f"""
            QLineEdit {{
                background: {colors['input_bg']};
                color: {colors['text_primary']};
                border: 2px solid {colors['border']};
                border-radius: 8px;
                padding: 12px;
                font-size: 15px;
            }}
            QLineEdit:focus {{ border: 2px solid {colors['accent']}; }}
        """,
        
        # ==========================================
        # NUMPAD STYLES
        # ==========================================
        "numpad_button": f"""
            QPushButton {{
                background: {colors['bg_secondary']};
                color: {colors['text_primary']};
                border: 1px solid {colors['border']};
                border-radius: 8px;
                font-size: 20px;
                font-weight: 600;
                min-height: 60px;
            }}
            QPushButton:hover {{
                background: {colors['bg_tertiary']};
                border: 2px solid {colors['accent']};
            }}
            QPushButton:pressed {{
                background: {colors['accent']};
                color: white;
            }}
        """,
        
        "numpad_display": f"""
            background: {colors['input_bg']};
            color: {colors['text_primary']};
            border: 2px solid {colors['border']};
            border-radius: 8px;
            padding: 16px;
            font-size: 24px;
            font-weight: 700;
        """,
    }


def apply_theme_to_widget(widget, style_key):
    """Apply theme style to widget by key"""
    styles = get_component_styles()
    if style_key in styles:
        widget.setStyleSheet(styles[style_key])


def get_themed_dialog_style():
    """Get complete dialog stylesheet"""
    styles = get_component_styles()
    return styles["dialog_bg"]

