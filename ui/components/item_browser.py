from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QScrollArea, QGridLayout, QPushButton, 
    QFrame, QSizePolicy, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from database.models import Item, ItemPrice, ItemGroup, db

class ItemCard(QFrame):
    clicked = pyqtSignal(dict)

    def __init__(self, item_data):
        super().__init__()
        self.item_data = item_data
        self.init_ui()

    def init_ui(self):
        self.setFixedSize(180, 240)
        self.setObjectName("ItemCard")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # Image
        self.img_label = QLabel("🖼️")
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setStyleSheet("background-color: #252525; border-radius: 8px; font-size: 40px;")
        self.img_label.setFixedHeight(120)
        layout.addWidget(self.img_label)

        # Name
        name_label = QLabel(self.item_data.get("item_name", ""))
        name_label.setObjectName("ItemName")
        name_label.setWordWrap(True)
        name_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        name_label.setFixedHeight(45)
        layout.addWidget(name_label)

        # Price
        price = self.item_data.get("price", 0)
        price_label = QLabel(f"{price:,.0f} UZS")
        price_label.setObjectName("ItemPrice")
        layout.addWidget(price_label)

    def mousePressEvent(self, event):
        self.clicked.emit(self.item_data)

class ItemBrowser(QWidget):
    item_selected = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.current_group = None
        self.all_items_data = []
        self.init_ui()
        self.load_categories()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

        # 1. Search Bar (Hidden by default, used as a bridge for global search)
        self.search_input = QLineEdit()
        self.search_input.setVisible(False)
        layout.addWidget(self.search_input)
        self.search_input.textChanged.connect(self.filter_items)

        # 2. Categories (Horizontal Scroll)
        self.cat_scroll = QScrollArea()
        self.cat_scroll.setObjectName("CategoryScroll")
        self.cat_scroll.setWidgetResizable(True)
        self.cat_scroll.setFixedHeight(50)
        self.cat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cat_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.cat_container = QWidget()
        self.cat_container.setObjectName("CategoryContainer")
        self.cat_layout = QHBoxLayout(self.cat_container)
        self.cat_layout.setContentsMargins(0, 0, 0, 0)
        self.cat_layout.setSpacing(10)
        self.cat_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.cat_scroll.setWidget(self.cat_container)
        layout.addWidget(self.cat_scroll)

        # 3. Item Grid
        self.item_scroll = QScrollArea()
        self.item_scroll.setWidgetResizable(True)
        self.item_scroll.setStyleSheet("background: transparent; border: none;")
        
        self.grid_container = QWidget()
        self.grid = QGridLayout(self.grid_container)
        self.grid.setSpacing(20)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        
        self.item_scroll.setWidget(self.grid_container)
        layout.addWidget(self.item_scroll)

    def load_categories(self):
        try:
            db.connect(reuse_if_open=True)
            groups = ItemGroup.select().order_by(ItemGroup.name)
            
            # Clear layout
            for i in reversed(range(self.cat_layout.count())): 
                self.cat_layout.itemAt(i).widget().setParent(None)

            # "All" button
            btn_all = QPushButton("BARCHASI")
            btn_all.setCheckable(True)
            btn_all.setChecked(True)
            btn_all.setProperty("class", "CategoryBtn")
            btn_all.clicked.connect(lambda: self.on_category_clicked(None, btn_all))
            self.cat_layout.addWidget(btn_all)
            self.category_buttons = [btn_all]

            for g in groups:
                btn = QPushButton(g.name.upper())
                btn.setCheckable(True)
                btn.setProperty("class", "CategoryBtn")
                btn.clicked.connect(lambda checked, name=g.name, b=btn: self.on_category_clicked(name, b))
                self.cat_layout.addWidget(btn)
                self.category_buttons.append(btn)
                
        except Exception as e:
            print(f"Categories error: {e}")
        finally:
            if not db.is_closed():
                db.close()

    def on_category_clicked(self, group_name, button):
        for btn in self.category_buttons:
            btn.setChecked(False)
        button.setChecked(True)
        self.current_group = group_name
        self.filter_items()

    def load_items(self, items):
        self.all_items_data = items
        self.filter_items()

    def filter_items(self):
        search_text = self.search_input.text().lower()
        
        # Clear grid
        for i in reversed(range(self.grid.count())): 
            widget = self.grid.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        filtered = []
        for it in self.all_items_data:
            match_group = True
            if self.current_group:
                match_group = it.get("item_group") == self.current_group
            
            match_search = True
            if search_text:
                item_name = str(it.get("item_name") or "").lower()
                item_code = str(it.get("item_code") or "").lower()
                barcode = str(it.get("barcode") or "").lower()
                match_search = (
                    search_text in item_name
                    or search_text in item_code
                    or search_text in barcode
                )
            
            if match_group and match_search:
                filtered.append(it)

        # Dinamik ustunlar soni
        cols = 5
        if self.width() < 800:
            cols = 3
        elif self.width() < 1000:
            cols = 4

        for index, item in enumerate(filtered):
            card = ItemCard(item)
            card.clicked.connect(self.item_selected.emit)
            self.grid.addWidget(card, index // cols, index % cols)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.filter_items()
