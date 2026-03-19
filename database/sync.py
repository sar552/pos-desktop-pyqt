import json
from PyQt6.QtCore import QThread, pyqtSignal
from core.api import FrappeAPI
from core.config import load_config, save_config
from core.logger import get_logger
from core.constants import CUSTOMER_SYNC_LIMIT, DEFAULT_CURRENCY, DEFAULT_CUSTOMER, DEFAULT_UOM
from database.models import (
    Item, Customer, ItemPrice, SalesInvoice, 
    SalesInvoiceItem, SalesInvoicePayment, ItemGroup, db
)
from database.invoice_processor import process_pending_invoice

logger = get_logger(__name__)

class SyncWorker(QThread):
    progress_update = pyqtSignal(str)
    sync_finished = pyqtSignal(bool, str)

    def __init__(self, api: FrappeAPI):
        super().__init__()
        self.api = api

    def run(self):
        try:
            self.progress_update.emit("Ma'lumotlar bazasi tekshirilmoqda...")
            db.connect(reuse_if_open=True)

            self._sync_pending_invoices()
            
            logged_user = self._get_logged_user()
            self._sync_pos_profile(logged_user)
            self._sync_item_groups()
            self._sync_items()
            self._sync_customers()

            self.sync_finished.emit(True, "Sinxronizatsiya muvaffaqiyatli yakunlandi!")
        except Exception as e:
            logger.error("Sinxronizatsiya xatosi: %s", e)
            self.sync_finished.emit(False, str(e))
        finally:
            if not db.is_closed():
                db.close()

    def _sync_pending_invoices(self):
        self.progress_update.emit("Oflayn cheklar yuborilmoqda...")
        # Draft va legacy Failed holatlarni qayta yuboramiz.
        pending = SalesInvoice.select().where(
            (SalesInvoice.status == "Draft") | (SalesInvoice.status == "Failed")
        )
        if not pending.exists():
            return

        count = pending.count()
        for i, inv in enumerate(pending):
            self.progress_update.emit(f"Oflayn chek yuborilmoqda: {i + 1}/{count}")
            status, message = process_pending_invoice(self.api, inv)
            inv.status = status
            inv.sync_message = message
            inv.save()

    def _get_logged_user(self) -> str:
        self.progress_update.emit("Foydalanuvchi tekshirilmoqda...")
        success, user_data = self.api.call_method("frappe.auth.get_logged_user")
        return user_data if success else self.api.user

    def _sync_pos_profile(self, logged_user: str):
        self.progress_update.emit("POS Profile olinmoqda...")
        success, pos_profile_data = self.api.call_method("posawesome.posawesome.api.utils.get_active_pos_profile")
        
        # pos_profile_data string bo'lishi kerak, lekin ba'zida ro'yxat yoki dict kelishi mumkin
        pos_profile_name = ""
        if success:
            if isinstance(pos_profile_data, str):
                pos_profile_name = pos_profile_data
            elif isinstance(pos_profile_data, list) and len(pos_profile_data) > 0:
                pos_profile_name = pos_profile_data[0]
            elif isinstance(pos_profile_data, dict):
                pos_profile_name = pos_profile_data.get("name") or pos_profile_data.get("message")

        if not success or not pos_profile_name:
            raise Exception("Faol POS profili topilmadi. Iltimos, serverda POS profilini sozlang.")

        success_detail, profile_doc = self.api.call_method(
            "frappe.client.get", {"doctype": "POS Profile", "name": str(pos_profile_name)}
        )

        if success_detail and isinstance(profile_doc, dict):
            payments = profile_doc.get("payments", [])
            payment_methods = [p.get("mode_of_payment") for p in payments]
            default_customer = profile_doc.get("customer") or DEFAULT_CUSTOMER
            currency = profile_doc.get("currency", DEFAULT_CURRENCY)
            price_list = profile_doc.get("selling_price_list", "")
            
            save_config({
                "pos_profile": pos_profile_name,
                "cashier": logged_user,
                "company": profile_doc.get("company"),
                "currency": currency,
                "price_list": price_list,
                "payment_methods": payment_methods,
                "default_customer": default_customer,
                "posa_tax_inclusive": profile_doc.get("posa_tax_inclusive", 0),
                "warehouse": profile_doc.get("warehouse")
            })

    def _sync_item_groups(self):
        self.progress_update.emit("Mahsulot guruhlari yuklanmoqda...")
        success, groups = self.api.call_method(
            "frappe.client.get_list", {
                "doctype": "Item Group",
                "fields": ["name", "parent_item_group", "is_group"],
                "limit_page_length": 1000
            }
        )
        if success and isinstance(groups, list):
            with db.atomic():
                for g in groups:
                    ItemGroup.insert(
                        name=g["name"],
                        parent_item_group=g.get("parent_item_group"),
                        is_group=bool(g.get("is_group"))
                    ).on_conflict_replace().execute()

    def _sync_items(self):
        config = load_config()
        pos_profile = config.get("pos_profile")
        price_list = config.get("price_list")
        if not pos_profile:
            return
            
        self.progress_update.emit(f"'{pos_profile}' profilidagi tovarlar yuklanmoqda...")
        # PosAwesome'dan barcha kerakli fieldlarni olamiz
        success, items_data = self.api.call_method(
            "posawesome.posawesome.api.items.get_items", 
            {"pos_profile": pos_profile, "price_list": price_list}
        )

        if not success or not isinstance(items_data, list):
            logger.warning("Items ma'lumotlari olinmadi")
            return

        server_item_codes = set()
        with db.atomic():
            for it in items_data:
                item_code = it.get("item_code")
                if not item_code:
                    continue
                server_item_codes.add(item_code)

                # Soliqlarni JSON formatida saqlaymiz
                taxes = it.get("taxes")
                taxes_json = json.dumps(taxes) if taxes else None

                Item.insert(
                    item_code=item_code,
                    item_name=it.get("item_name", item_code),
                    item_group=it.get("item_group", ""),
                    description=it.get("description", ""),
                    barcode=it.get("barcode", ""),
                    custom_barcode=it.get("custom_barcode", ""),
                    image=it.get("image", ""),
                    uom=it.get("uom", DEFAULT_UOM),
                    has_batch_no=bool(it.get("has_batch_no", 0)),
                    has_serial_no=bool(it.get("has_serial_no", 0)),
                    is_stock_item=bool(it.get("is_stock_item", 1)),
                    allow_negative_stock=bool(it.get("allow_negative_stock", 0)),
                    actual_qty=float(it.get("actual_qty") or 0.0),
                    taxes=taxes_json
                ).on_conflict_replace().execute()

                rate = float(it.get("rate") or it.get("price_list_rate") or 0.0)
                ItemPrice.insert(
                    name=f"Price-{item_code}",
                    item_code=item_code,
                    price_list=price_list,
                    price_list_rate=rate,
                    currency=config.get("currency", DEFAULT_CURRENCY),
                ).on_conflict_replace().execute()

    def _sync_customers(self):
        self.progress_update.emit("Mijozlar ro'yxati yuklanmoqda...")
        config = load_config()
        pos_profile = config.get("pos_profile")
        if not pos_profile:
            return

        # customers API json.loads(pos_profile) kutadi.
        pos_profile_payload = json.dumps({
            "name": pos_profile,
            "posa_use_server_cache": 0,
            "posa_server_cache_duration": 30,
        })
            
        success, customers = self.api.call_method(
            "posawesome.posawesome.api.customers.get_customer_names", 
            {"pos_profile": pos_profile_payload, "limit": CUSTOMER_SYNC_LIMIT}
        )
        if not success or not isinstance(customers, list):
            return

        with db.atomic():
            for cust in customers:
                c_name = cust.get("name")
                if not c_name: continue
                Customer.insert(
                    name=c_name,
                    customer_name=cust.get("customer_name", c_name),
                    customer_group=cust.get("customer_group", ""),
                    phone=cust.get("mobile_no", ""),
                    email=cust.get("email_id", ""),
                    tax_id=cust.get("tax_id", "")
                ).on_conflict_replace().execute()
