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
from database.models import PendingInvoice, PosShift, db
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
        self.gross_total_amount = float(order_data.get("gross_total_amount", self.total_amount) or 0.0)
        self.net_total_amount = float(order_data.get("net_total_amount", self.total_amount) or 0.0)
        self.item_discount_total = float(order_data.get("item_discount_total", 0.0) or 0.0)
        self.base_invoice_discount_amount = float(order_data.get("invoice_discount_amount", 0.0) or 0.0)
        self.invoice_discount_percentage = float(
            order_data.get("invoice_discount_percentage", 0.0) or 0.0
        )
        self.allow_additional_discount = bool(order_data.get("allow_additional_discount"))
        self.max_discount_percentage = float(order_data.get("max_discount_percentage", 0.0) or 0.0)
        self.apply_discount_on = order_data.get("apply_discount_on") or "Grand Total"
        self.extra_discount_amount = 0.0
        self.payment_inputs = {}
        self._payment_method_order = []
        self._initial_payment_method = ""
        self._default_payment_method = ""
        self._syncing_payment_inputs = False
        self.active_input = None
        self._is_calculating = False
        self.offline_id = str(uuid.uuid4())
        self._submitted_payments = []
        
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
        self.setFixedSize(560, 680)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet("background: #f3f6fb;")
        
        main_h_layout = QHBoxLayout(self)
        main_h_layout.setContentsMargins(18, 18, 18, 18)
        main_h_layout.setSpacing(16)
        
        # CHAP TOMON (To'lov turlari va Ma'lumotlar)
        left_widget = QWidget()
        left_widget.setStyleSheet("background: transparent;")
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(14)
        
        # Jami summa ko'rsatkichi
        summary_frame = QFrame()
        summary_frame.setStyleSheet("""
            background: #ffffff;
            border: 1px solid #dbe4f0;
            border-radius: 16px;
        """)
        summary_layout = QVBoxLayout(summary_frame)
        summary_layout.setContentsMargins(18, 18, 18, 18)
        summary_layout.setSpacing(10)

        summary_title = QLabel("Payment Summary")
        summary_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #64748b;")
        summary_title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        summary_layout.addWidget(summary_title)
        
        self.lbl_total = QLabel()
        self.lbl_total.setMinimumHeight(34)
        self.lbl_total.setStyleSheet("""
            font-size: 15px; font-weight: 600; color: #334155;
            background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 8px 12px;
        """)
        self.lbl_total.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.lbl_discount = QLabel()
        self.lbl_discount.setMinimumHeight(34)
        self.lbl_discount.setStyleSheet("""
            font-size: 15px; font-weight: 700; color: #d97706;
            background: #fff7ed; border: 1px solid #fed7aa; border-radius: 10px; padding: 8px 12px;
        """)
        self.lbl_discount.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.lbl_payable = QLabel()
        self.lbl_payable.setMinimumHeight(46)
        self.lbl_payable.setStyleSheet("""
            font-size: 19px; font-weight: 800; color: #0f766e;
            background: #ecfeff; border: 1px solid #a5f3fc; border-radius: 12px; padding: 10px 12px;
        """)
        self.lbl_payable.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.lbl_balance = QLabel()
        self.lbl_balance.setMinimumHeight(40)
        self.lbl_balance.setStyleSheet("""
            font-size: 15px; font-weight: 700; color: #b91c1c;
            background: #fef2f2; border: 1px solid #fecaca; border-radius: 10px; padding: 10px 12px;
        """)
        self.lbl_balance.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.lbl_change = QLabel("Qaytim: 0 UZS")
        self.lbl_change.setMinimumHeight(40)
        self.lbl_change.setStyleSheet("""
            font-size: 15px; font-weight: 700; color: #15803d;
            background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 10px; padding: 10px 12px;
        """)
        self.lbl_change.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        summary_layout.addWidget(self.lbl_total)
        summary_layout.addWidget(self.lbl_discount)
        summary_layout.addWidget(self.lbl_payable)
        summary_layout.addWidget(self.lbl_balance)
        summary_layout.addWidget(self.lbl_change)
        
        left_layout.addWidget(summary_frame)
        
        # To'lov tullari qismi
        methods_title = QLabel("Payment Methods")
        methods_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #64748b;")
        left_layout.addWidget(methods_title)

        payment_widget = QFrame()
        payment_widget.setStyleSheet("""
            background: #ffffff;
            border: 1px solid #dbe4f0;
            border-radius: 16px;
        """)
        self.payment_layout = QGridLayout(payment_widget)
        self.payment_layout.setContentsMargins(14, 14, 14, 14)
        self.payment_layout.setHorizontalSpacing(10)
        self.payment_layout.setVerticalSpacing(10)
        
        config = load_config()
        methods = config.get("payment_methods", ["Naqd", "Plastik", "Payme"])
        self._payment_method_order = list(methods)
        self._initial_payment_method = methods[0] if methods else ""
        self._default_payment_method = self._initial_payment_method
        
        row = 0
        for method in methods:
            method_header = QWidget()
            method_header.setStyleSheet("background: transparent;")
            method_header_layout = QHBoxLayout(method_header)
            method_header_layout.setContentsMargins(0, 0, 0, 0)
            method_header_layout.setSpacing(8)

            lbl = QLabel(method)
            lbl.setStyleSheet("""
                font-size: 13px; font-weight: 700; color: #334155;
                background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px;
                padding: 12px 14px;
            """)
            method_header_layout.addWidget(lbl, 1)

            fill_btn = QPushButton("Fill")
            fill_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            fill_btn.setMinimumHeight(42)
            fill_btn.setStyleSheet("""
                QPushButton {
                    background: #eff6ff; color: #1d4ed8; font-size: 13px; font-weight: 700;
                    border-radius: 12px; padding: 0 14px; border: 1px solid #bfdbfe;
                }
                QPushButton:hover { background: #dbeafe; color: #1e40af; }
            """)
            fill_btn.clicked.connect(lambda _, m=method: self._fill_payment_method(m))
            method_header_layout.addWidget(fill_btn)
            
            inp = ClickableLineEdit()
            inp.setPlaceholderText("0")
            inp.setMinimumHeight(46)
            inp.setStyleSheet("""
                font-size: 18px; font-weight: 700; color: #0f172a;
                background: #ffffff; border: 1px solid #cbd5e1; border-radius: 12px; padding: 10px 14px;
            """)
            val = QDoubleValidator(0.0, 999999999.0, 2)
            inp.setValidator(val)
            
            inp.clicked.connect(lambda i=inp: self._set_active_input(i))
            inp.textChanged.connect(lambda _text, m=method: self._on_payment_input_changed(m))
            
            self.payment_inputs[method] = inp
            
            self.payment_layout.addWidget(method_header, row, 0)
            self.payment_layout.addWidget(inp, row, 1)
            row += 1
            
        if methods:
            self._set_active_input(self.payment_inputs[methods[0]])

        left_layout.addWidget(payment_widget)
        
        # Tugmalar
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        btn_clear = QPushButton("Tozalash")
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.setMinimumHeight(48)
        btn_clear.setStyleSheet("""
            background: #ffffff; color: #dc2626; font-size: 15px; font-weight: 700;
            border-radius: 12px; padding: 12px 16px; border: 1px solid #fecaca;
        """)
        btn_clear.clicked.connect(self._clear_amounts)
        
        btn_layout.addWidget(btn_clear)
        left_layout.addLayout(btn_layout)
        
        self.btn_pay = QPushButton("To'lash (Enter)")
        self.btn_pay.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pay.setMinimumHeight(58)
        self.btn_pay.setStyleSheet("""
            background: #22c55e; color: #ffffff; font-size: 20px; font-weight: 800;
            border-radius: 14px; padding: 16px; border: none;
        """)
        self.btn_pay.clicked.connect(self._process_payment)
        left_layout.addWidget(self.btn_pay)
        
        main_h_layout.addWidget(left_widget, stretch=1)
        if methods:
            self._reset_payment_distribution()
        self._refresh_summary_labels()

    def _set_active_input(self, input_widget):
        if self.active_input:
            self.active_input.setStyleSheet("""
                font-size: 18px; font-weight: 700; color: #0f172a;
                background: #ffffff; border: 1px solid #cbd5e1; border-radius: 12px; padding: 10px 14px;
            """)
        self.active_input = input_widget
        self.active_input.setStyleSheet("""
            font-size: 18px; font-weight: 700; color: #0f172a;
            background: #ffffff; border: 2px solid #3b82f6; border-radius: 12px; padding: 10px 14px;
        """)
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

    def _fill_payment_method(self, method: str):
        if method not in self.payment_inputs:
            return
        self._default_payment_method = method
        self._syncing_payment_inputs = True
        try:
            for name, inp in self.payment_inputs.items():
                inp.blockSignals(True)
                inp.setText(str(int(self.total_amount if name == method else 0)))
                inp.blockSignals(False)
            self._set_active_input(self.payment_inputs[method])
        finally:
            self._syncing_payment_inputs = False
        self._recalculate()
        
    def _clear_amounts(self):
        self._reset_payment_distribution(reset_to_initial=True)

    def _reset_payment_distribution(self, reset_to_initial: bool = False):
        if not self.payment_inputs:
            return
        if (
            reset_to_initial
            and self._initial_payment_method
            and self._initial_payment_method in self.payment_inputs
        ):
            self._default_payment_method = self._initial_payment_method
        self._syncing_payment_inputs = True
        try:
            for name, inp in self.payment_inputs.items():
                value = self.total_amount if name == self._default_payment_method else 0
                inp.blockSignals(True)
                inp.setText(str(int(value)))
                inp.blockSignals(False)
            if self._default_payment_method:
                self._set_active_input(self.payment_inputs[self._default_payment_method])
        finally:
            self._syncing_payment_inputs = False
        self._recalculate()

    def _parse_input_amount(self, method: str) -> float:
        inp = self.payment_inputs.get(method)
        if not inp:
            return 0.0
        val = (inp.text() or "").replace(" ", "").strip()
        if not val:
            return 0.0
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0

    def _set_input_amount(self, method: str, amount: float):
        inp = self.payment_inputs.get(method)
        if not inp:
            return
        inp.blockSignals(True)
        inp.setText(str(int(max(amount, 0.0))))
        inp.blockSignals(False)

    def _rebalance_default_payment(self, changed_method: str):
        if not self._default_payment_method or self._default_payment_method not in self.payment_inputs:
            return
        if changed_method == self._default_payment_method:
            return
        other_total = 0.0
        for method in self._payment_method_order:
            if method == self._default_payment_method:
                continue
            other_total += self._parse_input_amount(method)
        default_amount = max(self.total_amount - other_total, 0.0)
        self._set_input_amount(self._default_payment_method, default_amount)

    def _on_payment_input_changed(self, method: str):
        if self._syncing_payment_inputs:
            return
        self._syncing_payment_inputs = True
        try:
            self._rebalance_default_payment(method)
        finally:
            self._syncing_payment_inputs = False
        self._recalculate()
            
    def _recalculate(self):
        if self._is_calculating:
            return
            
        self._is_calculating = True
        try:
            paid = self._get_paid_total()
            shortage = max(self.total_amount - paid, 0.0)
            self.extra_discount_amount = 0.0

            if shortage > 0:
                if self._can_apply_underpayment_discount(shortage):
                    self.extra_discount_amount = shortage
                    self.lbl_balance.setText("Qoldiq: 0 UZS")
                    self.lbl_change.setText("Qaytim: 0 UZS")
                    self._set_pay_button_enabled(True)
                else:
                    self.lbl_balance.setText(f"Qoldiq: {shortage:,.0f} UZS")
                    self.lbl_change.setText("Qaytim: 0 UZS")
                    self._set_pay_button_enabled(False)
            else:
                diff = paid - self.total_amount
                self.lbl_balance.setText("Qoldiq: 0 UZS")
                self.lbl_change.setText(f"Qaytim: {diff:,.0f} UZS")
                self._set_pay_button_enabled(True)

            self._refresh_summary_labels()
        finally:
            self._is_calculating = False

    def _get_paid_total(self) -> float:
        paid = 0.0
        for method in self._payment_method_order:
            paid += self._parse_input_amount(method)
        return paid

    def _remaining_discount_capacity(self) -> float:
        if not self.allow_additional_discount:
            return 0.0
        if self.max_discount_percentage <= 0:
            return max(self.net_total_amount, 0.0)
        limit = self.net_total_amount * (self.max_discount_percentage / 100.0)
        return max(limit - self.base_invoice_discount_amount, 0.0)

    def _can_apply_underpayment_discount(self, shortage: float) -> bool:
        if shortage <= 0:
            return True
        if not self.allow_additional_discount:
            return False
        return shortage <= self._remaining_discount_capacity() + 0.0001

    def _current_invoice_discount_amount(self) -> float:
        total_discount = self.base_invoice_discount_amount + self.extra_discount_amount
        return max(total_discount, 0.0)

    def _refresh_summary_labels(self):
        total_discount = self._current_invoice_discount_amount()
        self.lbl_total.setText(f"Subtotal: {self.net_total_amount:,.0f} UZS")
        self.lbl_discount.setText(f"Chegirma: {total_discount:,.0f} UZS")
        self.lbl_payable.setText(f"To'lanadi: {max(self.net_total_amount - total_discount, 0.0):,.0f} UZS")

    def _set_pay_button_enabled(self, enabled: bool):
        self.btn_pay.setEnabled(enabled)
        if enabled:
            self.btn_pay.setStyleSheet(
                "background: #22c55e; color: #ffffff; font-size: 20px; font-weight: 800; border-radius: 14px; padding: 16px; border: none;"
            )
        else:
            self.btn_pay.setStyleSheet(
                "background: #cbd5e1; color: #64748b; font-size: 20px; font-weight: 800; border-radius: 14px; padding: 16px; border: none;"
            )

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

        shortage = max(self.total_amount - paid_total, 0.0)
        extra_discount = shortage if self._can_apply_underpayment_discount(shortage) else 0.0
        final_invoice_discount = self.base_invoice_discount_amount + extra_discount
        final_payable_total = max(self.net_total_amount - final_invoice_discount, 0.0)

        if paid_total + 0.0001 < final_payable_total:
            return

        excess = max(paid_total - final_payable_total, 0.0)
        if excess > 0 and len(payments) > 0:
            payments[0]["amount"] -= excess
            
        config = load_config()

        customer = self.order_data.get("customer", "").strip()
        if not customer:
            customer = config.get("default_customer") or "Guest Customer"

        selected_price_list = (
            self.order_data.get("selling_price_list", "").strip() or config.get("price_list")
        )
        opening_entry = self.order_data.get("opening_entry") or self._get_opening_entry()
        
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
            "apply_discount_on": self.apply_discount_on or "Grand Total",
            "discount_amount": final_invoice_discount,
            "base_discount_amount": final_invoice_discount,
            "additional_discount_percentage": (
                (final_invoice_discount / self.net_total_amount) * 100 if self.net_total_amount > 0 else 0.0
            ),
            "total": self.net_total_amount,
            "net_total": self.net_total_amount,
            "base_total": self.net_total_amount,
            "base_net_total": self.net_total_amount,
            "items": [],
            "payments": payments
        }
        if opening_entry:
            invoice_data["posa_pos_opening_shift"] = opening_entry
        
        for item in self.order_data.get("items", []):
            rate = float(item.get("rate") or item.get("price", 0) or 0)
            qty = float(item.get("qty", 1) or 1)
            discount_amount = float(item.get("discount_amount", 0) or 0)
            price_list_rate = float(item.get("price_list_rate", rate) or rate)
            invoice_data["items"].append(
                {
                    "item_code": item["item_code"],
                    "item_name": item.get("item_name") or item.get("name") or item["item_code"],
                    "qty": qty,
                    "uom": item.get("uom"),
                    "conversion_factor": float(item.get("conversion_factor", 1) or 1),
                    "warehouse": item.get("warehouse") or config.get("warehouse"),
                    "rate": rate,
                    "base_rate": float(item.get("base_rate", rate) or rate),
                    "amount": item.get("amount", rate * qty),
                    "base_amount": float(item.get("base_amount", rate * qty) or (rate * qty)),
                    "price_list_rate": price_list_rate,
                    "base_price_list_rate": float(item.get("base_price_list_rate", price_list_rate) or price_list_rate),
                    "discount_amount": discount_amount,
                    "base_discount_amount": float(item.get("base_discount_amount", discount_amount) or discount_amount),
                    "discount_percentage": float(item.get("discount_percentage", 0) or 0),
                    "is_stock_item": int(bool(item.get("is_stock_item", 1))),
                }
            )

        self.order_data["invoice_discount_amount"] = final_invoice_discount
        self.order_data["invoice_discount_percentage"] = invoice_data["additional_discount_percentage"]
        self.order_data["total_amount"] = final_payable_total
        self.order_data["net_total_amount"] = self.net_total_amount
        self.order_data["paid_amount"] = sum(p["amount"] for p in payments)

        self._submitted_payments = list(payments)

        self.btn_pay.setEnabled(False)
        self.btn_pay.setText("Kuting...")
        
        self.worker = CheckoutWorker(invoice_data, payments, self.offline_id, self.api)
        self.worker.finished.connect(self._on_checkout_finished)
        self.worker.start()

    def _get_opening_entry(self) -> str:
        try:
            db.connect(reuse_if_open=True)
            shift = (
                PosShift.select()
                .where(PosShift.status == "Open")
                .order_by(PosShift.id.desc())
                .first()
            )
            return (shift.opening_entry or "").strip() if shift else ""
        except Exception as e:
            logger.debug("Opening entry olinmadi: %s", e)
            return ""
        finally:
            if not db.is_closed():
                db.close()

    def _on_checkout_finished(self, success, msg):
        receipt_data = dict(self.order_data)
        receipt_data.update({
            "paid_amount": sum(p["amount"] for p in self._submitted_payments),
            "offline_id": self.offline_id
        })
        print_receipt(self, receipt_data, self._submitted_payments)
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
