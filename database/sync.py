import json
import datetime
import requests
from peewee import DatabaseError, IntegrityError
from PyQt6.QtCore import QThread, pyqtSignal
from core.api import FrappeAPI
from core.config import load_config, save_config
from core.logger import get_logger
from core.constants import CUSTOMER_SYNC_LIMIT
from database.models import Item, ItemPrice, Customer, PosProfile, PosShift, PendingInvoice, db
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
            pos_profile_data = self._sync_pos_profile(logged_user)
            if not pos_profile_data:
                self.sync_finished.emit(False, "POS Profil ochiq emas yoki topilmadi. Avval smena oching.")
                return

            self._sync_items(pos_profile_data)
            self._sync_item_prices(pos_profile_data)
            self._sync_customers(pos_profile_data)

            self.sync_finished.emit(True, "Sinxronizatsiya muvaffaqiyatli yakunlandi!")
        except requests.exceptions.ConnectionError as e:
            logger.error("Server bilan aloqa xatosi: %s", e)
            self.sync_finished.emit(False, "Server bilan aloqa o'rnatib bo'lmadi")
        except requests.exceptions.Timeout as e:
            logger.error("Server javob bermadi (timeout): %s", e)
            self.sync_finished.emit(False, "Server javob bermadi (timeout)")
        except (DatabaseError, IntegrityError) as e:
            logger.error("Database xatosi: %s", e)
            self.sync_finished.emit(False, f"Ma'lumotlar bazasi xatosi: {e}")
        except Exception as e:
            logger.error("Sinxronizatsiya xatosi: %s", e, exc_info=True)
            self.sync_finished.emit(False, str(e))
        finally:
            if not db.is_closed():
                db.close()

    def _sync_pending_invoices(self):
        self.progress_update.emit("Oflayn cheklar yuborilmoqda...")
        pending = PendingInvoice.select().where(PendingInvoice.status == "Pending")

        if not pending.exists():
            return

        count = pending.count()
        for i, inv in enumerate(pending):
            self.progress_update.emit(f"Oflayn chek yuborilmoqda: {i + 1}/{count}")
            status, message = process_pending_invoice(self.api, inv)
            inv.status = status
            inv.error_message = message
            inv.save()

    def _get_logged_user(self) -> str:
        self.progress_update.emit("Foydalanuvchi ma'lumotlari olinmoqda...")
        success, user_data = self.api.call_method("frappe.auth.get_logged_user")
        return user_data if success else "Administrator"

    def _sync_pos_profile(self, logged_user: str) -> dict:
        self.progress_update.emit("POS Smena tekshirilmoqda...")
        success, shift_data = self.api.call_method(
            "posawesome.posawesome.api.shifts.check_opening_shift", 
            {"user": logged_user}
        )

        if not success or not shift_data:
            logger.warning("No open shift found")
            return None

        # PosAwesome qaytargan ma'lumotlar
        pos_profile = shift_data.get("pos_profile", {})
        pos_opening_shift = shift_data.get("pos_opening_shift", {})
        company = shift_data.get("company", {})

        profile_name = pos_profile.get("name")
        if not profile_name:
            return None

        # Config'ga joriy profilni saqlash
        config = load_config()
        config["pos_profile"] = profile_name
        config["company"] = company.get("name")
        config["warehouse"] = pos_profile.get("warehouse")
        config["currency"] = pos_profile.get("currency")
        
        # Default customer ni POS Profile dan olish
        default_customer = pos_profile.get("customer")
        if default_customer:
            config["default_customer"] = default_customer
        
        # Payment methods ni POS Profile dan olish
        payments = pos_profile.get("payments", [])
        if payments:
            config["payment_methods"] = [p.get("mode_of_payment") for p in payments if p.get("mode_of_payment")]
        
        save_config(config)

        # Bazaga POS Profile'ni seriyali Json sifatida saqlash
        with db.atomic():
            PosProfile.insert(
                name=profile_name,
                company=company.get("name"),
                warehouse=pos_profile.get("warehouse"),
                currency=pos_profile.get("currency"),
                profile_data=json.dumps(pos_profile),
                last_sync=datetime.datetime.now()
            ).on_conflict(
                conflict_target=[PosProfile.name],
                preserve=[PosProfile.company, PosProfile.warehouse, PosProfile.currency, PosProfile.profile_data, PosProfile.last_sync],
            ).execute()

            # PosShift ni locally ochiq qilib belgilash
            shift_entry = pos_opening_shift.get("name")
            if shift_entry:
                PosShift.insert(
                    opening_entry=shift_entry,
                    pos_profile=profile_name,
                    company=company.get("name"),
                    user=logged_user,
                    status="Open",
                    opened_at=pos_opening_shift.get("period_start_date") or datetime.datetime.now()
                ).on_conflict_ignore().execute() # Agar bor bo'lsa ignore

        return pos_profile

    def _sync_items(self, pos_profile_data: dict):
        self.progress_update.emit("Tovarlar POSAwesome'dan yuklanmoqda...")
        profile_json = json.dumps(pos_profile_data)
        
        # Batch synchronization parameters
        limit = 500
        start_after = ""
        total_synced = 0
        has_more = True

        server_item_codes = set()

        while has_more:
            params = {
                "pos_profile": profile_json,
                "limit": limit,
            }
            if start_after:
                params["start_after"] = start_after

            success, items_response = self.api.call_method(
                "posawesome.posawesome.api.items.get_items", params
            )

            if not success or not items_response:
                break
            
            # items_response format list of dicts based on posawesome api
            if not isinstance(items_response, list):
                break

            with db.atomic():
                for itm in items_response:
                    item_code = itm.get("item_code")
                    if not item_code:
                        continue
                        
                    server_item_codes.add(item_code)
                    
                    Item.insert(
                        item_code=item_code,
                        item_name=itm.get("item_name") or item_code,
                        description=itm.get("description"),
                        item_group=itm.get("item_group"),
                        barcode=itm.get("barcode"),
                        uom=itm.get("uom") or itm.get("stock_uom"),
                        stock_uom=itm.get("stock_uom"),
                        image=itm.get("image"),
                        has_batch_no=bool(itm.get("has_batch_no")),
                        has_serial_no=bool(itm.get("has_serial_no")),
                        has_variants=bool(itm.get("has_variants")),
                        is_stock_item=bool(itm.get("is_stock_item")),
                        standard_rate=float(itm.get("price_list_rate") or 0.0),
                        posawesome_data=json.dumps(itm),
                        last_sync=datetime.datetime.now()
                    ).on_conflict(
                        conflict_target=[Item.item_code],
                        update={
                            "item_name": itm.get("item_name") or item_code,
                            "description": itm.get("description"),
                            "item_group": itm.get("item_group"),
                            "barcode": itm.get("barcode"),
                            "uom": itm.get("uom") or itm.get("stock_uom"),
                            "stock_uom": itm.get("stock_uom"),
                            "image": itm.get("image"),
                            "has_batch_no": bool(itm.get("has_batch_no")),
                            "has_serial_no": bool(itm.get("has_serial_no")),
                            "has_variants": bool(itm.get("has_variants")),
                            "is_stock_item": bool(itm.get("is_stock_item")),
                            "standard_rate": float(itm.get("price_list_rate") or 0.0),
                            "posawesome_data": json.dumps(itm),
                            "last_sync": datetime.datetime.now()
                        }
                    ).execute()
                    
                    # Update start_after hook for keyset pagination
                    start_after = item_code

            total_synced += len(items_response)
            self.progress_update.emit(f"Tovarlar POSAwesome dan yuklandi: {total_synced}")
            
            if len(items_response) < limit:
                has_more = False

        if server_item_codes:
            # Optionally remove items not in server_item_codes if you want pure sync
            pass


    def _sync_item_prices(self, pos_profile_data: dict):
        self.progress_update.emit("Narxlar ro'yxati (Price Lists) yuklanmoqda...")
        
        # 1. Barcha ruxsat etilgan Price Listlarni olish
        success, response = self.api.call_method("posawesome.posawesome.api.utilities.get_selling_price_lists", {})
        if not success or not response:
            logger.error("Narxlar ro'yxatini olib bo'lmadi.")
            return
            
        price_lists = [pl.get("name") for pl in response if pl.get("name")]
        profile_json = json.dumps(pos_profile_data)
        
        # 2. Har bir price list uchun narxlarni yuklash
        for price_list in price_lists:
            self.progress_update.emit(f"'{price_list}' narxlari yuklanmoqda...")
            limit = 500
            start_after = ""
            total_for_pl = 0
            has_more = True
            
            while has_more:
                params = {
                    "pos_profile": profile_json,
                    "price_list": price_list,
                    "limit": limit,
                }
                if start_after:
                    params["start_after"] = start_after

                succ, items_res = self.api.call_method("posawesome.posawesome.api.items.get_items", params)

                if not succ or not items_res or not isinstance(items_res, list):
                    break

                with db.atomic():
                    for itm in items_res:
                        item_code = itm.get("item_code")
                        rate = float(itm.get("price_list_rate") or itm.get("rate") or 0.0)
                        currency = itm.get("price_list_currency") or itm.get("currency") or "UZS"
                        
                        if not item_code:
                            continue
                            
                        # Composite name: ItemCode-PriceList
                        idx_name = f"{item_code}-{price_list}"
                        
                        ItemPrice.insert(
                            name=idx_name,
                            item_code=item_code,
                            price_list=price_list,
                            price_list_rate=rate,
                            currency=currency,
                            last_sync=datetime.datetime.now()
                        ).on_conflict(
                            conflict_target=[ItemPrice.name],
                            update={
                                "price_list": price_list,
                                "price_list_rate": rate,
                                "currency": currency,
                                "last_sync": datetime.datetime.now()
                            }
                        ).execute()
                        
                        start_after = item_code

                total_for_pl += len(items_res)
                self.progress_update.emit(f"'{price_list}' dan {total_for_pl} tasi yuklandi")
                
                if len(items_res) < limit:
                    has_more = False

    def _sync_customers(self, pos_profile_data: dict):
        self.progress_update.emit("Mijozlar POSAwesome'dan yuklanmoqda...")
        profile_json = json.dumps(pos_profile_data)
        
        limit = CUSTOMER_SYNC_LIMIT
        start_after = ""
        total_synced = 0
        has_more = True

        while has_more:
            params = {
                "pos_profile": profile_json,
                "limit": limit,
            }
            if start_after:
                params["start_after"] = start_after

            success, customer_response = self.api.call_method(
                "posawesome.posawesome.api.customers.get_customer_names", params
            )

            if not success or not customer_response:
                break
                
            if not isinstance(customer_response, list):
                break

            with db.atomic():
                for cust in customer_response:
                    # customer returns object with name, customer_name, customer_group, mobile_no
                    name = cust.get("name")
                    if not name:
                        continue
                        
                    Customer.insert(
                        name=name,
                        customer_name=cust.get("customer_name") or name,
                        customer_group=cust.get("customer_group"),
                        phone=cust.get("mobile_no") or cust.get("phone"),
                        email=cust.get("email_id"),
                        address=cust.get("customer_primary_address"),
                        posawesome_data=json.dumps(cust),
                        last_sync=datetime.datetime.now()
                    ).on_conflict(
                        conflict_target=[Customer.name],
                        update={
                            "customer_name": cust.get("customer_name") or name,
                            "customer_group": cust.get("customer_group"),
                            "phone": cust.get("mobile_no") or cust.get("phone"),
                            "email": cust.get("email_id"),
                            "address": cust.get("customer_primary_address"),
                            "posawesome_data": json.dumps(cust),
                            "last_sync": datetime.datetime.now()
                        }
                    ).execute()
                    
                    start_after = name

            total_synced += len(customer_response)
            self.progress_update.emit(f"Mijozlar POSAwesome dan yuklandi: {total_synced}")
            
            if len(customer_response) < limit:
                has_more = False
        
        # Agar default_customer configda yo'q bo'lsa, birinchi customerni default qilish
        config = load_config()
        if not config.get("default_customer"):
            first_customer = Customer.select().first()
            if first_customer:
                config["default_customer"] = first_customer.name
                save_config(config)
                self.progress_update.emit(f"Default mijoz: {first_customer.name}")
