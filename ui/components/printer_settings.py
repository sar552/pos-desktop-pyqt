import platform
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QFrame, QScrollArea, QWidget,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from core.api import FrappeAPI
from core.config import load_config, save_config
from core.printer import send_test_print, get_printer_issue, list_linux_printers
from core.logger import get_logger

logger = get_logger(__name__)


# ──────────────────────────────────────────────────
#  Printer detection
# ──────────────────────────────────────────────────
def detect_printers() -> list[dict]:
    """Tizimda ulangan printerlarni aniqlash."""
    printers = []
    if platform.system() == "Windows":
        try:
            import win32print
            for flags, desc, name, comment in win32print.EnumPrinters(2):
                printers.append({"label": name, "device": "", "win_name": name, "cups_name": ""})
        except ImportError:
            pass
    else:
        return list_linux_printers()
    return printers


# ──────────────────────────────────────────────────
#  Production unit sync worker
# ──────────────────────────────────────────────────
class ProductionUnitSyncWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, api: FrappeAPI):
        super().__init__()
        self.api = api

    def run(self):
        try:
            config = load_config()
            pos_profile = config.get("pos_profile")
            if not pos_profile:
                self.finished.emit(False, "POS profil topilmadi")
                return

            success, units = self.api.call_method("frappe.client.get_list", {
                "doctype": "URY Production Unit",
                "filters": {"pos_profile": pos_profile},
                "fields": ["name", "production"],
                "limit_page_length": 50,
            })

            if not success or not isinstance(units, list):
                existing_units = config.get("production_units", [])
                self.finished.emit(False, self._format_sync_error(units, existing_units))
                return

            # Mavjud printer sozlamalarini saqlash
            existing = config.get("production_units", [])
            existing_printers = {
                u.get("name", ""): {
                    "printer_device": u.get("printer_device", ""),
                    "printer_win_name": u.get("printer_win_name", ""),
                    "printer_cups_name": u.get("printer_cups_name", ""),
                    "printer_mode": u.get("printer_mode", "auto"),
                }
                for u in existing
            }

            production_units = []
            for unit in units:
                unit_name = unit.get("production", unit.get("name", ""))

                success2, unit_doc = self.api.call_method(
                    "frappe.client.get",
                    {"doctype": "URY Production Unit", "name": unit["name"]}
                )
                item_groups = []
                if success2 and isinstance(unit_doc, dict):
                    item_groups = [
                        ig.get("item_group", "")
                        for ig in unit_doc.get("item_groups", [])
                        if ig.get("item_group")
                    ]

                ep = existing_printers.get(unit_name, {})
                production_units.append({
                    "name": unit_name,
                    "item_groups": item_groups,
                    "printer_device": ep.get("printer_device", ""),
                    "printer_win_name": ep.get("printer_win_name", ""),
                    "printer_cups_name": ep.get("printer_cups_name", ""),
                    "printer_mode": ep.get("printer_mode", "auto"),
                })

            save_config({"production_units": production_units})
            self.finished.emit(True, f"{len(production_units)} ta production unit yangilandi")

        except Exception as e:
            logger.error("Production unit sync xatosi: %s", e)
            self.finished.emit(False, str(e))

    @staticmethod
    def _format_sync_error(error, existing_units: list) -> str:
        error_text = str(error or "").strip()
        existing_count = len(existing_units or [])

        if "403" in error_text:
            message = (
                "Production unitlarni serverdan o'qib bo'lmadi.\n"
                "Sabab: 'URY Production Unit' uchun List ruxsati yo'q (403)."
            )
            if existing_count:
                return (
                    f"{message}\n\n"
                    f"Mavjud {existing_count} ta lokal production unit sozlamasi saqlab qolindi."
                )
            return (
                f"{message}\n\n"
                "Administrator shu doctype uchun o'qish/List ruxsatini berishi kerak."
            )

        if error_text:
            if existing_count:
                return (
                    "Production unitlarni serverdan yangilab bo'lmadi.\n"
                    f"Xabar: {error_text}\n\n"
                    f"Mavjud {existing_count} ta lokal production unit sozlamasi saqlab qolindi."
                )
            return f"Production unitlarni serverdan olib bo'lmadi.\nXabar: {error_text}"

        if existing_count:
            return (
                "Production unitlarni serverdan olib bo'lmadi.\n"
                f"Mavjud {existing_count} ta lokal production unit sozlamasi saqlab qolindi."
            )

        return "Serverdan ma'lumot olib bo'lmadi"


# ──────────────────────────────────────────────────
#  Printer Settings Dialog
# ──────────────────────────────────────────────────
class PrinterSettingsDialog(QDialog):
    def __init__(self, parent, api: FrappeAPI):
        super().__init__(parent)
        self.api = api
        self.available_printers = detect_printers()
        self.printer_rows = []  # list of {"combo": QComboBox, "key": str, "type": str}
        self.setWindowTitle("Printer sozlamalari")
        self.setMinimumSize(600, 480)
        self.setStyleSheet("background: white;")
        self._init_ui()
        self._center_on_parent()

    def _center_on_parent(self):
        if self.parent():
            pg = self.parent().geometry()
            x = pg.x() + (pg.width() - self.width()) // 2
            y = pg.y() + (pg.height() - self.height()) // 2
            self.move(x, y)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ──
        hdr = QFrame()
        hdr.setMinimumHeight(48)
        hdr.setMaximumHeight(64)
        hdr.setStyleSheet("background: #1e293b;")
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(20, 0, 20, 0)

        title = QLabel("PRINTER SOZLAMALARI")
        title.setStyleSheet(
            "font-size: 16px; font-weight: 800; color: white; "
            "letter-spacing: 1px; background: transparent;"
        )
        hdr_layout.addWidget(title)
        hdr_layout.addStretch()

        # Yangilash tugmasi
        refresh_btn = QPushButton("⟳  Yangilash")
        refresh_btn.setMinimumHeight(34)
        refresh_btn.setMaximumHeight(44)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background: #3b82f6; color: white;
                font-weight: 700; font-size: 13px;
                border-radius: 8px; border: none; padding: 0 16px;
            }
            QPushButton:pressed { background: #2563eb; }
        """)
        refresh_btn.clicked.connect(self._on_refresh)
        self.refresh_btn = refresh_btn
        hdr_layout.addWidget(refresh_btn)

        close_btn = QPushButton("✕")
        close_btn.setMinimumSize(34, 34)
        close_btn.setMaximumSize(44, 44)
        close_btn.setStyleSheet("""
            QPushButton {
                background: #475569; color: white;
                font-weight: bold; font-size: 16px;
                border-radius: 8px; border: none;
            }
            QPushButton:pressed { background: #334155; }
        """)
        close_btn.clicked.connect(self.reject)
        hdr_layout.addWidget(close_btn)
        layout.addWidget(hdr)

        # ── Scroll area ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(20, 16, 20, 16)
        self.content_layout.setSpacing(16)

        self._build_printer_rows()

        self.content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, stretch=1)

        # ── Save button ──
        bottom = QFrame()
        bottom.setStyleSheet("background: #f8fafc; border-top: 1px solid #e2e8f0;")
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(20, 12, 20, 12)

        save_btn = QPushButton("SAQLASH")
        save_btn.setMinimumHeight(44)
        save_btn.setMaximumHeight(58)
        save_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #2563eb, stop:1 #3b82f6);
                color: white; font-weight: 800; font-size: 15px;
                border-radius: 12px; border: none; letter-spacing: 1px;
            }
            QPushButton:pressed { background: #1e40af; }
        """)
        save_btn.clicked.connect(self._on_save)
        bottom_layout.addWidget(save_btn)
        layout.addWidget(bottom)

    def _build_printer_rows(self):
        # Eski rowlarni tozalash
        for i in reversed(range(self.content_layout.count())):
            item = self.content_layout.itemAt(i)
            w = item.widget()
            if w:
                w.setParent(None)
            elif item.layout():
                # stretch
                self.content_layout.removeItem(item)

        self.printer_rows.clear()
        config = load_config()

        # ── Mijoz printeri ──
        section_lbl = QLabel("MIJOZ PRINTERI")
        section_lbl.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: #94a3b8; "
            "letter-spacing: 1px; background: transparent;"
        )
        self.content_layout.addWidget(section_lbl)

        customer_printers = config.get("printers", [])
        if customer_printers:
            cp = customer_printers[0]
        else:
            cp = {"name": "Mijoz", "device": "", "type": "customer", "win_name": "", "mode": "auto"}

        self._add_printer_row(
            label="Mijoz cheki",
            current_device=cp.get("device", ""),
            current_win_name=cp.get("win_name", ""),
            current_cups_name=cp.get("cups_name", ""),
            current_mode=cp.get("mode", "auto"),
            row_key="customer",
            row_type="customer",
        )

        # ── Production unit printerlar ──
        prod_units = config.get("production_units", [])
        if prod_units:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet("background: #e2e8f0; max-height: 1px; margin: 4px 0;")
            self.content_layout.addWidget(sep)

            prod_lbl = QLabel("PRODUCTION PRINTERLAR")
            prod_lbl.setStyleSheet(
                "font-size: 11px; font-weight: 700; color: #94a3b8; "
                "letter-spacing: 1px; background: transparent;"
            )
            self.content_layout.addWidget(prod_lbl)

            for unit in prod_units:
                groups = ", ".join(unit.get("item_groups", []))
                self._add_printer_row(
                    label=unit.get("name", ""),
                    subtitle=f"Guruhlar: {groups}" if groups else "",
                    current_device=unit.get("printer_device", ""),
                    current_win_name=unit.get("printer_win_name", ""),
                    current_cups_name=unit.get("printer_cups_name", ""),
                    current_mode=unit.get("printer_mode", "auto"),
                    row_key=unit.get("name", ""),
                    row_type="production",
                )

        if not prod_units:
            no_units = QLabel("Production unitlar topilmadi. Yangilash tugmasini bosing.")
            no_units.setStyleSheet("color: #94a3b8; font-size: 13px; font-style: italic;")
            self.content_layout.addWidget(no_units)

    def _add_printer_row(self, label, current_device, current_win_name, current_cups_name, current_mode,
                         row_key, row_type, subtitle=""):
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(8)

        # Nomi
        name_lbl = QLabel(label)
        name_lbl.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #1e293b; "
            "background: transparent; border: none;"
        )
        card_layout.addWidget(name_lbl)

        if subtitle:
            sub_lbl = QLabel(subtitle)
            sub_lbl.setStyleSheet(
                "font-size: 11px; color: #64748b; "
                "background: transparent; border: none;"
            )
            card_layout.addWidget(sub_lbl)

        # Combo + mode + Test print tugmasi
        row = QHBoxLayout()
        row.setSpacing(8)

        combo = QComboBox()
        combo.setMinimumHeight(48)
        combo.setStyleSheet("""
            QComboBox {
                font-size: 14px; font-weight: 600; color: #1e293b;
                background: white; border: 1.5px solid #e2e8f0;
                border-radius: 10px; padding: 8px 12px;
            }
            QComboBox:focus { border: 1.5px solid #3b82f6; }
            QComboBox::drop-down {
                border: none; width: 36px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #64748b;
                margin-right: 10px;
            }
            QComboBox QAbstractItemView {
                font-size: 14px; padding: 4px;
                selection-background-color: #dbeafe;
                selection-color: #1e40af;
            }
        """)

        # Birinchi item — tanlanmagan
        combo.addItem("Tanlanmagan", {"device": "", "win_name": "", "cups_name": ""})

        # Mavjud printerlar
        selected_idx = 0
        is_win = platform.system() == "Windows"
        for i, p in enumerate(self.available_printers):
            combo.addItem(p["label"], {
                "device": p.get("device", ""),
                "win_name": p.get("win_name", ""),
                "cups_name": p.get("cups_name", ""),
            })
            if is_win:
                if p["win_name"] and p["win_name"] == current_win_name:
                    selected_idx = i + 1
            else:
                if p.get("cups_name") and p.get("cups_name") == current_cups_name:
                    selected_idx = i + 1
                elif p["device"] and p["device"] == current_device:
                    selected_idx = i + 1

        combo.setCurrentIndex(selected_idx)
        row.addWidget(combo, stretch=1)

        mode_combo = QComboBox()
        mode_combo.setMinimumHeight(48)
        mode_combo.setMinimumWidth(120)
        mode_combo.setStyleSheet(combo.styleSheet())
        mode_options = [
            ("Auto", "auto"),
            ("Thermal", "thermal"),
            ("Office", "office"),
        ]
        selected_mode_idx = 0
        for idx, (label_text, value) in enumerate(mode_options):
            mode_combo.addItem(label_text, value)
            if value == (current_mode or "auto"):
                selected_mode_idx = idx
        mode_combo.setCurrentIndex(selected_mode_idx)
        row.addWidget(mode_combo)

        test_btn = QPushButton("Sinov")
        test_btn.setMinimumSize(70, 40)
        test_btn.setMaximumSize(100, 54)
        test_btn.setStyleSheet("""
            QPushButton {
                background: #22c55e; color: white;
                font-weight: 700; font-size: 13px;
                border-radius: 10px; border: none;
            }
            QPushButton:pressed { background: #16a34a; }
        """)
        test_btn.clicked.connect(lambda _, c=combo, m=mode_combo, n=label: self._on_test(c, m, n))
        row.addWidget(test_btn)

        card_layout.addLayout(row)
        self.content_layout.addWidget(card)

        self.printer_rows.append({
            "combo": combo,
            "mode_combo": mode_combo,
            "key": row_key,
            "type": row_type,
        })

    # ── Actions ──

    def _on_test(self, combo: QComboBox, mode_combo: QComboBox, name: str):
        from ui.components.dialogs import InfoDialog
        data = combo.currentData() or {"device": "", "win_name": "", "cups_name": ""}
        if not data.get("device") and not data.get("win_name") and not data.get("cups_name"):
            InfoDialog(self, "Xato", "Avval printerni tanlang!", kind="warning").exec()
            return

        printer_config = {
            "name": name,
            "device": data.get("device", ""),
            "win_name": data.get("win_name", ""),
            "cups_name": data.get("cups_name", ""),
            "mode": mode_combo.currentData() or "auto",
        }
        issue = get_printer_issue(printer_config)
        if issue:
            InfoDialog(self, "Printer muammosi", issue, kind="warning").exec()
            return

        success = send_test_print(printer_config)
        if success:
            InfoDialog(self, "Muvaffaqiyatli", f"{name} — sinov cheki chop etildi!", kind="success").exec()
        else:
            InfoDialog(self, "Xato", f"{name} — printer javob bermadi.\nUlangan va yoqilganligini tekshiring.", kind="error").exec()

    def _on_refresh(self):
        self.refresh_btn.setText("Yuklanmoqda...")
        self.refresh_btn.setEnabled(False)
        self.sync_worker = ProductionUnitSyncWorker(self.api)
        self.sync_worker.finished.connect(self._on_sync_done)
        self.sync_worker.start()

    def _on_sync_done(self, success: bool, message: str):
        from ui.components.dialogs import InfoDialog
        self.refresh_btn.setText("⟳  Yangilash")
        self.refresh_btn.setEnabled(True)

        # Lokal printer ro'yxati har doim yangilanadi, server sync muvaffaqiyatsiz
        # bo'lsa ham foydalanuvchi yangi ulanган printerni tanlay olishi kerak.
        self.available_printers = detect_printers()
        self._build_printer_rows()
        self.content_layout.addStretch()

        if success:
            InfoDialog(self, "Yangilandi", message, kind="success").exec()
        else:
            InfoDialog(self, "Ogohlantirish", message, kind="warning").exec()

    def _on_save(self):
        from ui.components.dialogs import InfoDialog
        config = load_config()
        is_win = platform.system() == "Windows"

        for row in self.printer_rows:
            data = row["combo"].currentData() or {"device": "", "win_name": ""}
            data = {
                "device": data.get("device", ""),
                "win_name": data.get("win_name", ""),
                "cups_name": data.get("cups_name", ""),
                "mode": row["mode_combo"].currentData() or "auto",
            }

            if row["type"] == "customer":
                printers = config.get("printers", [])
                if printers:
                    printers[0]["device"] = data.get("device", "")
                    printers[0]["win_name"] = data.get("win_name", "")
                    printers[0]["cups_name"] = data.get("cups_name", "")
                    printers[0]["mode"] = data.get("mode", "auto")
                else:
                    printers = [{
                        "name": "Mijoz",
                        "device": data.get("device", ""),
                        "type": "customer",
                        "win_name": data.get("win_name", ""),
                        "cups_name": data.get("cups_name", ""),
                        "mode": data.get("mode", "auto"),
                    }]
                save_config({"printers": printers})

            elif row["type"] == "production":
                prod_units = config.get("production_units", [])
                for unit in prod_units:
                    if unit.get("name") == row["key"]:
                        unit["printer_device"] = data.get("device", "")
                        unit["printer_win_name"] = data.get("win_name", "")
                        unit["printer_cups_name"] = data.get("cups_name", "")
                        unit["printer_mode"] = data.get("mode", "auto")
                        break
                save_config({"production_units": prod_units})

        InfoDialog(self, "Saqlandi", "Printer sozlamalari saqlandi!", kind="success").exec()
        self.accept()
