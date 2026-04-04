import json
import uuid
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QWidget, QFrame, QGridLayout,
)
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QDoubleValidator

from core.api import FrappeAPI
from core.config import load_config
from core.logger import get_logger
from database.models import PendingInvoice, db
from core.printer import print_receipt
from ui.components.numpad import TouchNumpad
from ui.components.dialogs import ClickableLineEdit

logger = get_logger(__name__)

class CheckoutWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, invoice_data: dict, payments: list, offline_id: str, api: FrappeAPI):
        super().__init__()
        self.invoice_data = invoice_data
        self.payments = payments
        self.offline_id = offline_id
        self.api = api

    def run(self):
        try:
            # POSAwesome submit_invoice API ishlatish
            # Invoice payload tayyorlash
            invoice_payload = dict(self.invoice_data)
            invoice_payload["doctype"] = "Sales Invoice"
            invoice_payload["is_pos"] = 1
            invoice_payload["update_stock"] = 1
            
            # Payments to'g'ri formatda
            formatted_payments = []
            for p in self.payments:
                formatted_payments.append({
                    "mode_of_payment": p.get("mode_of_payment"),
                    "amount": p.get("amount", 0),
                    "type": p.get("type", "Cash"),
                })
            invoice_payload["payments"] = formatted_payments
            
            # data payload (bo'sh dict yoki qo'shimcha ma'lumotlar)
            data_payload = {
                "payments": formatted_payments,
            }
            
            # POSAwesome API: submit_invoice(invoice, data, submit_in_background)
            # invoice va data JSON string bo'lishi kerak
            success, response = self.api.call_method(
                "posawesome.posawesome.api.invoices.submit_invoice",
                {
                    "invoice": json.dumps(invoice_payload),
                    "data": json.dumps(data_payload),
                    "submit_in_background": 0
                }
            )

            if success and response:
                if isinstance(response, dict):
                    doc_name = response.get("name", "")
                    self.finished.emit(True, f"To'lov muvaffaqiyatli! #{doc_name}")
                else:
                    self.finished.emit(True, "To'lov muvaffaqiyatli yakunlandi!")
                return
            else:
                # Server xatosi - oflayn saqlash
                logger.error(f"Invoice submit xatosi: {response}")
                self._save_offline(str(response))
                
        except Exception as e:
            logger.error(f"Checkout exception: {e}")
            self._save_offline(str(e))

    def _save_offline(self, error):
        try:
            db.connect(reuse_if_open=True)
            if not PendingInvoice.select().where(PendingInvoice.offline_id == self.offline_id).exists():
                save_data = dict(self.invoice_data)
                save_data["_payments"] = self.payments
                PendingInvoice.create(
                    offline_id=self.offline_id,
                    invoice_data=json.dumps(save_data),
                    status="Pending",
                    error_message=str(error),
                )
            self.finished.emit(False, "Server bilan aloqa yo'qligi sababli chek oflayn saqlandi!")
        except Exception as e:
            logger.error(f"Oflayn saqlashda xatolik: {e}")
            self.finished.emit(False, f"Oflayn saqlashda xatolik: {e}")
        finally:
            if not db.is_closed():
                db.close()


class CheckoutWindow(QDialog):
    checkout_completed = pyqtSignal()

    def __init__(self, parent, order_data: dict, api: FrappeAPI):
        super().__init__(parent)
        self.api = api
        self.order_data = order_data
        self.total_amount = float(order_data.get("total_amount", 0.0))
        self.payment_inputs = {}
        self.active_input = None
        self._is_calculating = False
        self.offline_id = str(uuid.uuid4())
        
        self.init_ui()
        QTimer.singleShot(50, self._center_on_parent)

    def _center_on_parent(self):
        if self.parent():
            p_geo = self.parent().frameGeometry()
            c_geo = self.frameGeometry()
            c_geo.moveCenter(p_geo.center())
            self.move(c_geo.topLeft())

    def init_ui(self):
        self.setWindowTitle("To'lov")
        self.setFixedSize(880, 620)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet("background: white;")
        
        main_h_layout = QHBoxLayout(self)
        
        # CHAP TOMON (To'lov turlari va Ma'lumotlar)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # Jami summa ko'rsatkichi
        summary_frame = QFrame()
        summary_frame.setStyleSheet("background: #f8f9fa; border-radius: 8px; padding: 15px;")
        summary_layout = QVBoxLayout(summary_frame)
        
        self.lbl_total = QLabel(f"Umumiy: {self.total_amount:,.0f} UZS")
        self.lbl_total.setStyleSheet("font-size: 24px; font-weight: bold; color: #2c3e50;")
        self.lbl_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_balance = QLabel(f"Qoldiq: {self.total_amount:,.0f} UZS")
        self.lbl_balance.setStyleSheet("font-size: 20px; font-weight: bold; color: #e74c3c;")
        self.lbl_balance.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_change = QLabel("Qaytim: 0 UZS")
        self.lbl_change.setStyleSheet("font-size: 20px; font-weight: bold; color: #27ae60;")
        self.lbl_change.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        summary_layout.addWidget(self.lbl_total)
        summary_layout.addWidget(self.lbl_balance)
        summary_layout.addWidget(self.lbl_change)
        
        left_layout.addWidget(summary_frame)
        
        # To'lov tullari qismi
        payment_area = QScrollArea()
        payment_area.setWidgetResizable(True)
        payment_area.setStyleSheet("border: none;")
        
        payment_widget = QWidget()
        self.payment_layout = QGridLayout(payment_widget)
        
        config = load_config()
        methods = config.get("payment_methods", ["Naqd", "Plastik", "Payme"])
        
        row = 0
        for method in methods:
            lbl = QLabel(method)
            lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
            
            inp = ClickableLineEdit()
            inp.setPlaceholderText("0")
            inp.setStyleSheet("font-size: 18px; padding: 10px; border: 2px solid #bdc3c7; border-radius: 6px;")
            val = QDoubleValidator(0.0, 999999999.0, 2)
            inp.setValidator(val)
            
            inp.clicked.connect(lambda i=inp: self._set_active_input(i))
            inp.textChanged.connect(self._recalculate)
            
            self.payment_inputs[method] = inp
            
            self.payment_layout.addWidget(lbl, row, 0)
            self.payment_layout.addWidget(inp, row, 1)
            row += 1
            
        if methods:
            self._set_active_input(self.payment_inputs[methods[0]])
            
        payment_area.setWidget(payment_widget)
        left_layout.addWidget(payment_area)
        
        # Tugmalar
        btn_layout = QHBoxLayout()
        
        btn_exact = QPushButton("Aynan")
        btn_exact.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_exact.setStyleSheet("background: #0083B0; color: white; font-size: 16px; font-weight: bold; border-radius: 5px; padding: 15px;")
        btn_exact.clicked.connect(self._set_exact_amount)
        
        btn_clear = QPushButton("Tozalash")
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.setStyleSheet("background: #e74c3c; color: white; font-size: 16px; font-weight: bold; border-radius: 5px; padding: 15px;")
        btn_clear.clicked.connect(self._clear_amounts)
        
        btn_layout.addWidget(btn_exact)
        btn_layout.addWidget(btn_clear)
        left_layout.addLayout(btn_layout)
        
        self.btn_pay = QPushButton("To'lash (Enter)")
        self.btn_pay.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pay.setStyleSheet("background: #27ae60; color: white; font-size: 20px; font-weight: bold; border-radius: 6px; padding: 20px;")
        self.btn_pay.clicked.connect(self._process_payment)
        left_layout.addWidget(self.btn_pay)
        
        main_h_layout.addWidget(left_widget, stretch=1)
        
        # O'NG TOMON (Numpad)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        self.numpad = TouchNumpad()
        self.numpad.digit_clicked.connect(self._on_numpad_key)
        right_layout.addWidget(self.numpad)
        
        main_h_layout.addWidget(right_widget, stretch=1)

    def _set_active_input(self, input_widget):
        if self.active_input:
            self.active_input.setStyleSheet("font-size: 18px; padding: 10px; border: 2px solid #bdc3c7; border-radius: 6px;")
        self.active_input = input_widget
        self.active_input.setStyleSheet("font-size: 18px; padding: 10px; border: 2px solid #3498db; border-radius: 6px; background: #ebf5fb;")
        self.active_input.setFocus()
        
    def _on_numpad_key(self, key):
        if not self.active_input:
            return
            
        current = self.active_input.text()
        if key == "C":
            self.active_input.clear()
        elif key == "<-":
            self.active_input.setText(current[:-1])
        elif key == "+50K":
            val = float(current.replace(" ", "") or 0) + 50000
            self.active_input.setText(str(int(val)))
        elif key == "Enter":
            self._process_payment()
        else:
            if current == "0" and key != ".":
                self.active_input.setText(key)
            else:
                self.active_input.setText(current + key)

    def _set_exact_amount(self):
        if not self.active_input:
            return
        self._clear_amounts()
        self.active_input.setText(str(int(self.total_amount)))
        
    def _clear_amounts(self):
        for inp in self.payment_inputs.values():
            inp.clear()
            
    def _recalculate(self):
        if self._is_calculating:
            return
            
        self._is_calculating = True
        try:
            paid = 0.0
            for inp in self.payment_inputs.values():
                val = inp.text().replace(" ", "")
                if val:
                    try:
                        paid += float(val)
                    except (ValueError, TypeError):
                        pass
                        
            diff = paid - self.total_amount
            
            if diff < 0:
                self.lbl_balance.setText(f"Qoldiq: {abs(diff):,.0f} UZS")
                self.lbl_change.setText("Qaytim: 0 UZS")
                self.btn_pay.setEnabled(False)
                self.btn_pay.setStyleSheet("background: #95a5a6; color: white; font-size: 20px; font-weight: bold; border-radius: 6px; padding: 20px;")
            else:
                self.lbl_balance.setText("Qoldiq: 0 UZS")
                self.lbl_change.setText(f"Qaytim: {diff:,.0f} UZS")
                self.btn_pay.setEnabled(True)
                self.btn_pay.setStyleSheet("background: #27ae60; color: white; font-size: 20px; font-weight: bold; border-radius: 6px; padding: 20px;")
        finally:
            self._is_calculating = False

    def _process_payment(self):
        paid_total = 0.0
        payments = []
        for method, inp in self.payment_inputs.items():
            val = inp.text().replace(" ", "")
            if val:
                try:
                    num = float(val)
                    if num > 0:
                        paid_total += num
                        payments.append({
                            "mode_of_payment": method,
                            "amount": num
                        })
                except (ValueError, TypeError):
                    pass
                    
        if paid_total < self.total_amount:
            return
            
        excess = paid_total - self.total_amount
        if excess > 0 and len(payments) > 0:
            payments[0]["amount"] -= excess
            
        config = load_config()

        customer = self.order_data.get("customer", "").strip()
        if not customer:
            customer = config.get("default_customer") or "Guest Customer"

        selected_price_list = (
            self.order_data.get("selling_price_list", "").strip() or config.get("price_list")
        )
        
        invoice_data = {
            "doctype": "Sales Invoice",
            "naming_series": "ACC-SINV-.YYYY.-",
            "company": config.get("company"),
            "customer": customer,
            "pos_profile": config.get("pos_profile"),
            "selling_price_list": selected_price_list,
            "set_warehouse": config.get("warehouse"),
            "currency": config.get("currency", "UZS"),
            "is_pos": 1,
            "update_stock": 1,
            "items": [],
            "payments": payments
        }
        
        for item in self.order_data.get("items", []):
            rate = item.get("rate") or item.get("price", 0)
            qty = item.get("qty", 1)
            invoice_data["items"].append({
                "item_code": item["item_code"],
                "qty": qty,
                "rate": rate,
                "amount": item.get("amount", rate * qty)
            })

        self.btn_pay.setEnabled(False)
        self.btn_pay.setText("Kuting...")
        
        self.worker = CheckoutWorker(invoice_data, payments, self.offline_id, self.api)
        self.worker.finished.connect(self._on_checkout_finished)
        self.worker.start()

    def _on_checkout_finished(self, success, msg):
        receipt_data = dict(self.order_data)
        receipt_data.update({
            "paid_amount": sum(p["amount"] for p in self.payments_list()),
            "offline_id": self.offline_id
        })
        print_receipt(self, receipt_data, self.payments_list())
        self.checkout_completed.emit()
        self.accept()
        
    def payments_list(self):
        payments = []
        for method, inp in self.payment_inputs.items():
            val = inp.text().replace(" ", "")
            if val:
                try:
                    num = float(val)
                    if num > 0:
                        payments.append({"mode_of_payment": method, "amount": num})
                except (ValueError, TypeError):
                    pass
        return payments

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Enter or event.key() == Qt.Key.Key_Return:
            if self.btn_pay.isEnabled():
                self._process_payment()
        elif event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)
