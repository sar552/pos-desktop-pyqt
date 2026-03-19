GLOBAL_STYLE = """
/* --- ASOSIY --- */
QMainWindow, QDialog {
    background-color: #f4f5f6;
    color: #1d2129;
    font-family: 'Inter', 'Roboto', 'Segoe UI', sans-serif;
}

/* --- SIDEBAR (Chap) --- */
#Sidebar {
    background-color: #ffffff;
    border-right: 1px solid #ebedef;
    min-width: 80px;
    max-width: 80px;
}

.SidebarBtn {
    background-color: transparent;
    border: none;
    color: #4e5969;
    padding: 20px 0;
    font-size: 24px;
    border-radius: 0;
}

.SidebarBtn:hover {
    color: #165dff;
    background-color: #f2f3f5;
}

.SidebarBtn:checked {
    color: #165dff;
    background-color: #e8f3ff;
    border-right: 3px solid #165dff;
}

/* --- TOP BAR (Tepa) --- */
#TopBar {
    background-color: #ffffff;
    border-bottom: 1px solid #ebedef;
    min-height: 64px;
}

#TopBar QLineEdit {
    background-color: #f2f3f5;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 10px 16px;
    color: #1d2129;
    font-size: 14px;
}

#TopBar QLineEdit:focus {
    background-color: #ffffff;
    border: 1px solid #165dff;
}

#CustomerBtn, #SyncBtn {
    background-color: #f2f3f5;
    color: #4e5969;
    border: none;
    border-radius: 6px;
    padding: 0 16px;
    font-weight: 500;
    font-size: 14px;
}

#CustomerBtn:hover, #SyncBtn:hover {
    background-color: #e5e6eb;
}

/* --- ITEM BROWSER (Markaz) --- */
#CategoryScroll {
    background-color: transparent;
    border: none;
}

.CategoryBtn {
    background-color: #ffffff;
    color: #4e5969;
    border: 1px solid #e5e6eb;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: 500;
    font-size: 13px;
    margin-right: 8px;
}

.CategoryBtn:hover {
    background-color: #f2f3f5;
    border-color: #c9cdd4;
}

.CategoryBtn:checked {
    background-color: #165dff;
    color: #ffffff;
    border-color: #165dff;
}

#ItemCard {
    background-color: #ffffff;
    border-radius: 8px;
    border: 1px solid #e5e6eb;
}

#ItemCard:hover {
    border: 1px solid #165dff;
    box-shadow: 0 4px 10px rgba(0,0,0,0.05);
}

#ItemCard #ItemName {
    color: #1d2129;
    font-weight: 500;
    font-size: 14px;
}

#ItemCard #ItemPrice {
    color: #165dff;
    font-weight: 700;
    font-size: 16px;
}

/* --- CART (O'ng) --- */
#CartPanel {
    background-color: #ffffff;
    border-left: 1px solid #ebedef;
    min-width: 400px;
}

QTableWidget {
    background-color: transparent;
    border: none;
    gridline-color: transparent;
    color: #1d2129;
    selection-background-color: #e8f3ff;
    selection-color: #165dff;
}

QHeaderView::section {
    background-color: #f7f8fa;
    color: #4e5969;
    border: none;
    border-bottom: 1px solid #ebedef;
    font-weight: 600;
    font-size: 12px;
    padding: 12px;
}

#TotalsFrame {
    background-color: #ffffff;
    border-top: 1px solid #ebedef;
    padding: 24px;
}

#PayBtn {
    background-color: #00b42a;
    color: #ffffff;
    font-size: 18px;
    font-weight: 600;
    border-radius: 4px;
    height: 60px;
    margin: 0 24px 24px 24px;
    border: none;
}

#PayBtn:hover {
    background-color: #23c343;
}

#PayBtn:pressed {
    background-color: #009a29;
}

#PayBtn:disabled {
    background-color: #f2f3f5;
    color: #c9cdd4;
}

/* --- SCROLLBAR --- */
QScrollBar:vertical {
    border: none;
    background: #f2f3f5;
    width: 6px;
}
QScrollBar::handle:vertical {
    background: #c9cdd4;
    border-radius: 3px;
}
QScrollBar::handle:vertical:hover {
    background: #86909c;
}
"""
