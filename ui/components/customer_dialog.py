from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
)
from PyQt6.QtCore import Qt
from database.models import Customer, db


class CustomerDialog(QDialog):
    def __init__(self, selected_customer: str = "Walk-in Customer"):
        super().__init__()
        self.selected_customer = selected_customer
        self._all_customers = []
        self.init_ui()
        self.load_customers()

    def init_ui(self):
        self.setWindowTitle("Mijoz tanlash")
        self.setMinimumSize(520, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Mijozlar")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(title)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Qidirish: name, customer_name, phone")
        self.search_input.textChanged.connect(self.filter_customers)
        layout.addWidget(self.search_input)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._accept_selected)
        layout.addWidget(self.list_widget)

        footer = QHBoxLayout()
        self.walk_in_btn = QPushButton("Walk-in Customer")
        self.walk_in_btn.clicked.connect(self._select_walk_in)
        footer.addWidget(self.walk_in_btn)

        footer.addStretch()

        cancel_btn = QPushButton("Bekor qilish")
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)

        select_btn = QPushButton("Tanlash")
        select_btn.clicked.connect(self._accept_selected)
        footer.addWidget(select_btn)

        layout.addLayout(footer)

    def load_customers(self):
        rows = []
        try:
            db.connect(reuse_if_open=True)
            query = (
                Customer.select(Customer.name, Customer.customer_name, Customer.phone)
                .order_by(Customer.customer_name)
                .dicts()
            )
            rows = list(query)
        finally:
            if not db.is_closed():
                db.close()

        self._all_customers = rows
        self.filter_customers()

    def filter_customers(self):
        text = self.search_input.text().strip().lower()
        self.list_widget.clear()

        for row in self._all_customers:
            name = row.get("name") or ""
            display = row.get("customer_name") or name
            phone = row.get("phone") or ""
            haystack = f"{name} {display} {phone}".lower()
            if text and text not in haystack:
                continue

            label = f"{display} ({name})"
            if phone:
                label += f"  |  {phone}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _select_walk_in(self):
        self.selected_customer = "Walk-in Customer"
        self.accept()

    def _accept_selected(self):
        current = self.list_widget.currentItem()
        if current:
            self.selected_customer = current.data(Qt.ItemDataRole.UserRole)
        self.accept()
