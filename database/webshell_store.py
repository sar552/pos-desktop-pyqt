import datetime
import json
import os
import uuid
from urllib.parse import urlparse

import requests
from peewee import fn

from core.api import FrappeAPI
from core.config import clear_credentials, load_config, save_config
from core.logger import get_logger
from database.models import (
    AppSetting,
    Customer,
    Item,
    ItemPrice,
    PosShift,
    SalesInvoice,
    SalesInvoicePayment,
    SyncLog,
    db,
)
from database.invoice_processor import process_pending_invoice

logger = get_logger(__name__)


def normalize_server_url(raw_url: str) -> str:
    if not raw_url or not isinstance(raw_url, str):
        return ""

    value = raw_url.strip()
    if not value:
        return ""

    if "://" not in value:
        value = f"https://{value}"

    try:
        parsed = urlparse(value)
    except Exception:
        return ""

    if not parsed.scheme or not parsed.netloc:
        return ""

    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path or ''}"
    return normalized.rstrip("/")


def _parse_json(raw, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _parse_datetime(date_value: str | None, time_value: str | None = None) -> datetime.datetime:
    if not date_value:
        return datetime.datetime.now()

    normalized_time = time_value or "00:00:00"
    payload = f"{date_value} {normalized_time}".strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m-%d %H:%M"):
        try:
            return datetime.datetime.strptime(payload, fmt)
        except ValueError:
            continue

    try:
        return datetime.datetime.fromisoformat(payload)
    except Exception:
        return datetime.datetime.now()


def _model_to_item_payload(item: Item) -> dict:
    extra = _parse_json(item.extra, {})
    payload = {
        **extra,
        "item_code": item.item_code,
        "item_name": item.item_name,
        "item_group": item.item_group or "",
        "description": item.description or "",
        "image": item.image or "",
        "local_image_path": item.local_image_path or "",
        "stock_uom": item.stock_uom or item.uom or "Nos",
        "uom": item.uom or item.stock_uom or "Nos",
        "has_batch_no": bool(item.has_batch_no),
        "has_serial_no": bool(item.has_serial_no),
        "is_stock_item": bool(item.is_stock_item),
        "allow_negative_stock": bool(item.allow_negative_stock),
        "actual_qty": float(item.actual_qty or 0),
        "rate": float(item.rate or item.price_list_rate or 0),
        "price_list_rate": float(item.price_list_rate or item.rate or 0),
        "currency": item.currency or "UZS",
        "barcode": item.barcode or "",
        "taxes": _parse_json(item.taxes, []),
        "custom_barcode": item.custom_barcode or "",
    }
    return payload


def _model_to_customer_payload(customer: Customer) -> dict:
    extra = _parse_json(customer.extra, {})
    payload = {
        **extra,
        "name": customer.name,
        "customer_name": customer.customer_name,
        "customer_group": customer.customer_group or "",
        "territory": customer.territory or "",
        "mobile_no": extra.get("mobile_no") or customer.phone or "",
        "phone": customer.phone or "",
        "email_id": extra.get("email_id") or customer.email or "",
        "email": customer.email or "",
        "tax_id": customer.tax_id or "",
    }
    return payload


class WebShellStore:
    def __init__(self, api: FrappeAPI):
        self.api = api

    def get_config(self) -> dict:
        config = load_config()
        return {
            "serverUrl": config.get("serverUrl", ""),
            "apiKey": config.get("apiKey", ""),
            "apiSecret": config.get("apiSecret", ""),
            "posProfile": config.get("pos_profile", ""),
            "priceList": config.get("price_list", ""),
            "site": config.get("site", ""),
            "user": config.get("user", ""),
        }

    def save_config(self, payload: dict) -> dict:
        current = load_config()
        updated = {
            "serverUrl": normalize_server_url(payload.get("serverUrl", current.get("serverUrl", ""))),
            "apiKey": payload.get("apiKey", current.get("apiKey", "")),
            "apiSecret": payload.get("apiSecret", current.get("apiSecret", "")),
            "pos_profile": payload.get("posProfile", current.get("pos_profile", "")),
            "price_list": payload.get("priceList", current.get("price_list", "")),
            "site": payload.get("site", current.get("site", "")),
            "user": payload.get("user", current.get("user", "")),
            "password": payload.get("password", current.get("password", "")),
        }
        save_config(updated)
        self.api.reload_config()
        return {"saved": True, "config": self.get_config()}

    def get_server_url(self) -> str:
        return normalize_server_url(self.get_config().get("serverUrl", ""))

    def set_server_url(self, value: str) -> dict:
        config = load_config()
        config["serverUrl"] = normalize_server_url(value)
        save_config(config)
        self.api.reload_config()
        return {"saved": True, "serverUrl": config["serverUrl"]}

    def reset_server(self) -> dict:
        clear_credentials()
        save_config({"serverUrl": "", "pos_profile": "", "price_list": ""})
        self.api.reload_config()
        return {"reset": True}

    def probe_server(self) -> dict:
        url = self.get_server_url()
        if not url:
            return {"reachable": False, "message": "No server URL configured"}

        try:
            response = requests.get(f"{url}/api/method/ping", timeout=10)
            return {"reachable": response.ok, "status": response.status_code, "url": url}
        except requests.RequestException as exc:
            return {"reachable": False, "message": str(exc)}

    def validate_connection(self) -> dict:
        config = self.get_config()
        if not config.get("serverUrl"):
            return {"ok": False, "message": "Server URL kiritilmagan"}

        if not config.get("apiKey") or not config.get("apiSecret"):
            return {"ok": False, "message": "API Key va API Secret kiriting"}

        probe = self.probe_server()
        if not probe.get("reachable"):
            return {
                "ok": False,
                "offline": True,
                "message": probe.get("message") or "Server bilan aloqa yo'q",
            }

        success, user = self.api.call_method("frappe.auth.get_logged_user")
        if not success or not user:
            return {"ok": False, "message": str(user) if user else "Login muvaffaqiyatsiz"}

        profile = self._sync_pos_profile()
        if not profile:
            fallback_profile = config.get("posProfile") or config.get("pos_profile")
            if not fallback_profile:
                return {"ok": False, "message": "POS Profile topilmadi yoki ruxsat yo'q"}
            profile = {"name": fallback_profile}

        latest = self.get_config()
        return {
            "ok": True,
            "message": "Connection confirmed",
            "user": user,
            "posProfile": latest.get("posProfile") or profile.get("name", ""),
            "priceList": latest.get("priceList") or profile.get("selling_price_list", ""),
        }

    def log_sync(self, log_type: str, status: str, message: str = ""):
        SyncLog.create(type=log_type, status=status, message=(message or "")[:4000])

    def get_setting(self, key: str):
        row = AppSetting.get_or_none(AppSetting.key == key)
        return row.value if row else None

    def set_setting(self, key: str, value):
        payload = value if isinstance(value, str) else json.dumps(value)
        row = AppSetting.get_or_none(AppSetting.key == key)
        if row:
            row.value = payload
            row.updated_at = datetime.datetime.now()
            row.save()
        else:
            AppSetting.create(key=key, value=payload, updated_at=datetime.datetime.now())
        return {"saved": True}

    def save_items_bulk(self, items: list[dict]) -> int:
        count = 0
        with db.atomic():
            for raw in items or []:
                item_code = raw.get("item_code")
                if not item_code:
                    continue
                Item.insert(
                    item_code=item_code,
                    item_name=raw.get("item_name") or item_code,
                    item_group=raw.get("item_group", ""),
                    description=raw.get("description", ""),
                    barcode=raw.get("barcode", ""),
                    uom=raw.get("uom") or raw.get("stock_uom") or "Nos",
                    stock_uom=raw.get("stock_uom") or raw.get("uom") or "Nos",
                    image=raw.get("image", ""),
                    local_image_path=raw.get("local_image_path", ""),
                    has_batch_no=bool(raw.get("has_batch_no")),
                    has_serial_no=bool(raw.get("has_serial_no")),
                    is_stock_item=bool(raw.get("is_stock_item", 1)),
                    allow_negative_stock=bool(raw.get("allow_negative_stock", 0)),
                    actual_qty=float(raw.get("actual_qty") or 0),
                    rate=float(raw.get("rate") or raw.get("price_list_rate") or 0),
                    price_list_rate=float(raw.get("price_list_rate") or raw.get("rate") or 0),
                    currency=raw.get("currency") or "UZS",
                    taxes=json.dumps(raw.get("taxes") or []),
                    custom_barcode=raw.get("custom_barcode", ""),
                    extra=json.dumps(raw),
                    last_sync=datetime.datetime.now(),
                ).on_conflict_replace().execute()

                price_list = load_config().get("price_list") or raw.get("price_list") or ""
                ItemPrice.insert(
                    name=f"Price-{item_code}-{price_list or 'default'}",
                    item_code=item_code,
                    price_list=price_list,
                    price_list_rate=float(raw.get("price_list_rate") or raw.get("rate") or 0),
                    currency=raw.get("currency") or "UZS",
                    last_sync=datetime.datetime.now(),
                ).on_conflict_replace().execute()
                count += 1

        self.log_sync("save_items_bulk", "success", f"Stored {count} items")
        return count

    def get_items(self, opts: dict | None = None) -> list[dict]:
        opts = opts or {}
        search = (opts.get("search") or "").lower()
        item_group = opts.get("item_group") or ""
        limit = int(opts.get("limit") or 200)
        offset = int(opts.get("offset") or 0)

        query = Item.select().order_by(Item.item_name).offset(offset).limit(limit)
        if item_group and item_group != "ALL":
            query = query.where(Item.item_group == item_group)

        rows = []
        for item in query:
            payload = _model_to_item_payload(item)
            if search:
                haystack = " ".join(
                    [
                        str(payload.get("item_name", "")).lower(),
                        str(payload.get("item_code", "")).lower(),
                        str(payload.get("barcode", "")).lower(),
                    ]
                )
                if search not in haystack:
                    continue
            rows.append(payload)
        return rows

    def get_item_by_code(self, item_code: str):
        item = Item.get_or_none(Item.item_code == item_code)
        return _model_to_item_payload(item) if item else None

    def get_item_by_barcode(self, barcode: str):
        item = Item.get_or_none(Item.barcode == barcode)
        return _model_to_item_payload(item) if item else None

    def get_items_count(self) -> int:
        return Item.select().count()

    def get_item_image_path(self, item_code: str) -> str:
        item = Item.get_or_none(Item.item_code == item_code)
        return item.local_image_path if item and item.local_image_path else ""

    def clear_all_items(self):
        Item.delete().execute()
        return {"cleared": True}

    def save_customers(self, customers: list[dict]) -> int:
        count = 0
        with db.atomic():
            for raw in customers or []:
                name = raw.get("name")
                if not name:
                    continue
                Customer.insert(
                    name=name,
                    customer_name=raw.get("customer_name") or name,
                    customer_group=raw.get("customer_group", ""),
                    territory=raw.get("territory", ""),
                    phone=raw.get("mobile_no") or raw.get("phone") or "",
                    email=raw.get("email_id") or raw.get("email") or "",
                    tax_id=raw.get("tax_id", ""),
                    extra=json.dumps(raw),
                    last_sync=datetime.datetime.now(),
                ).on_conflict_replace().execute()
                count += 1

        self.log_sync("save_customers", "success", f"Stored {count} customers")
        return count

    def get_customers(self, opts: dict | None = None) -> list[dict]:
        opts = opts or {}
        search = (opts.get("search") or "").lower()
        limit = int(opts.get("limit") or 100)
        offset = int(opts.get("offset") or 0)

        query = Customer.select().order_by(Customer.customer_name).offset(offset).limit(limit)
        rows = []
        for customer in query:
            payload = _model_to_customer_payload(customer)
            if search:
                haystack = " ".join(
                    [
                        str(payload.get("name", "")).lower(),
                        str(payload.get("customer_name", "")).lower(),
                        str(payload.get("mobile_no", "")).lower(),
                        str(payload.get("email_id", "")).lower(),
                    ]
                )
                if search not in haystack:
                    continue
            rows.append(payload)
        return rows

    def get_customers_count(self) -> int:
        return Customer.select().count()

    def clear_all_customers(self):
        Customer.delete().execute()
        return {"cleared": True}

    def _deduct_local_stock(self, items: list[dict]):
        with db.atomic():
            for row in items or []:
                item_code = row.get("item_code")
                if not item_code:
                    continue
                qty = abs(float(row.get("qty") or 0))
                if not qty:
                    continue
                item = Item.get_or_none(Item.item_code == item_code)
                if not item:
                    continue
                item.actual_qty = max(0.0, float(item.actual_qty or 0) - qty)
                item.save()

    def save_invoice(self, invoice_payload: dict) -> dict:
        if not invoice_payload or not invoice_payload.get("items"):
            raise ValueError("Cart is empty. Add items before saving.")

        posting_date = invoice_payload.get("posting_date")
        posting_time = invoice_payload.get("posting_time")
        invoice_dt = _parse_datetime(posting_date, posting_time)
        offline_id = f"offline-{int(datetime.datetime.now().timestamp() * 1000)}-{uuid.uuid4().hex[:6]}"

        with db.atomic():
            invoice = SalesInvoice.create(
                offline_id=offline_id,
                customer=invoice_payload.get("customer") or "",
                customer_name=invoice_payload.get("customer_name") or invoice_payload.get("customer") or "",
                posting_date=invoice_dt,
                posting_time=posting_time or invoice_dt.strftime("%H:%M:%S"),
                total_qty=float(invoice_payload.get("total_qty") or 0),
                total=float(invoice_payload.get("total") or invoice_payload.get("net_total") or 0),
                net_total=float(invoice_payload.get("net_total") or 0),
                total_taxes_and_charges=float(invoice_payload.get("total_taxes_and_charges") or 0),
                discount_amount=float(invoice_payload.get("discount_amount") or 0),
                grand_total=float(invoice_payload.get("grand_total") or 0),
                paid_amount=float(invoice_payload.get("paid_amount") or 0),
                pos_profile=invoice_payload.get("pos_profile") or load_config().get("pos_profile") or "",
                company=invoice_payload.get("company") or load_config().get("company") or "",
                status="Draft",
                sync_message="",
                sync_error="",
                invoice_data=json.dumps(invoice_payload),
            )

            for payment in invoice_payload.get("payments") or []:
                SalesInvoicePayment.create(
                    invoice=invoice,
                    mode_of_payment=payment.get("mode_of_payment") or "",
                    amount=float(payment.get("amount") or 0),
                    account=payment.get("account"),
                    extra=json.dumps(payment),
                )

        self._deduct_local_stock(invoice_payload.get("items") or [])
        self.log_sync("save_invoice", "success", f"Saved offline invoice {offline_id}")
        return {"id": invoice.id, "local_name": offline_id}

    def get_pending_invoices(self) -> list[dict]:
        query = SalesInvoice.select().where(SalesInvoice.status.in_(("Draft", "Failed"))).order_by(SalesInvoice.created_at)
        return [
            {
                "id": row.id,
                "local_name": row.offline_id,
                "server_name": row.name or "",
                "customer": row.customer,
                "customer_name": row.customer_name or "",
                "grand_total": float(row.grand_total or 0),
                "net_total": float(row.net_total or 0),
                "total_qty": float(row.total_qty or 0),
                "posting_date": row.posting_date.strftime("%Y-%m-%d") if row.posting_date else "",
                "posting_time": row.posting_time or "",
                "status": row.status,
                "sync_error": row.sync_error or row.sync_message or "",
                "invoice_data": row.invoice_data or "{}",
                "created_at": row.created_at.isoformat() if row.created_at else "",
                "synced_at": row.synced_at.isoformat() if row.synced_at else "",
            }
            for row in query
        ]

    def get_pending_count(self) -> int:
        return SalesInvoice.select().where(SalesInvoice.status.in_(("Draft", "Failed"))).count()

    def get_all_invoices(self, opts: dict | None = None) -> list[dict]:
        opts = opts or {}
        status = opts.get("status") or ""
        limit = int(opts.get("limit") or 100)
        offset = int(opts.get("offset") or 0)

        query = SalesInvoice.select().order_by(SalesInvoice.created_at.desc()).offset(offset).limit(limit)
        if status:
            query = query.where(SalesInvoice.status == status)

        return [
            {
                "id": row.id,
                "local_name": row.offline_id,
                "server_name": row.name or "",
                "customer": row.customer,
                "customer_name": row.customer_name or "",
                "grand_total": float(row.grand_total or 0),
                "net_total": float(row.net_total or 0),
                "status": row.status,
                "sync_error": row.sync_error or row.sync_message or "",
                "created_at": row.created_at.isoformat() if row.created_at else "",
                "synced_at": row.synced_at.isoformat() if row.synced_at else "",
            }
            for row in query
        ]

    def delete_invoice(self, invoice_id: int):
        SalesInvoice.delete_by_id(invoice_id)
        return {"deleted": True}

    def get_local_stock(self, item_code: str) -> float:
        item = Item.get_or_none(Item.item_code == item_code)
        return float(item.actual_qty or 0) if item else 0.0

    def get_sync_logs(self, limit: int = 50) -> list[dict]:
        query = SyncLog.select().order_by(SyncLog.created_at.desc()).limit(limit)
        return [
            {
                "id": row.id,
                "type": row.type,
                "status": row.status,
                "message": row.message,
                "created_at": row.created_at.isoformat() if row.created_at else "",
            }
            for row in query
        ]

    def get_db_stats(self) -> dict:
        db_path = db.database if hasattr(db, "database") else ""
        return {
            "dbPath": db_path,
            "itemsCount": self.get_items_count(),
            "customersCount": self.get_customers_count(),
            "pendingInvoices": self.get_pending_count(),
        }

    def get_images_dir(self) -> str:
        images_dir = os.path.join(os.path.dirname(db.database), "images")
        os.makedirs(images_dir, exist_ok=True)
        return images_dir

    def frappe_call(self, method: str, args=None):
        success, result = self.api.call_method_raw(method, args or {})
        if not success:
            raise RuntimeError(str(result))
        return result

    def _sync_pos_profile(self) -> dict | None:
        success, profile = self.api.call_method("posawesome.posawesome.api.utils.get_active_pos_profile")
        if not success or not isinstance(profile, dict):
            return None

        save_config(
            {
                "pos_profile": profile.get("name", ""),
                "company": profile.get("company", ""),
                "currency": profile.get("currency", "UZS"),
                "price_list": profile.get("selling_price_list", ""),
                "payment_methods": [row.get("mode_of_payment") for row in profile.get("payments", [])],
                "default_customer": profile.get("customer", "Walk-in Customer"),
                "warehouse": profile.get("warehouse", ""),
            }
        )
        self.api.reload_config()
        return profile

    def full_sync(self) -> dict:
        if not self.api.is_configured():
            return {"error": "Missing server credentials"}

        results = {"items": 0, "customers": 0, "invoices": {"pending": 0, "synced": 0, "failed": 0}}
        profile = self._sync_pos_profile() or {}

        pending = SalesInvoice.select().where(SalesInvoice.status.in_(("Draft", "Failed")))
        results["invoices"]["pending"] = pending.count()
        for invoice in pending:
            status, message = process_pending_invoice(self.api, invoice)
            invoice.status = status
            invoice.sync_message = message
            invoice.sync_error = message
            if status == "Synced":
                invoice.synced_at = datetime.datetime.now()
                results["invoices"]["synced"] += 1
            else:
                results["invoices"]["failed"] += 1
            invoice.save()

        pos_profile_name = profile.get("name") or load_config().get("pos_profile")
        price_list = profile.get("selling_price_list") or load_config().get("price_list")
        if pos_profile_name:
            success, items = self.api.call_method(
                "posawesome.posawesome.api.items.get_items",
                {"pos_profile": pos_profile_name, "price_list": price_list, "include_image": 1},
            )
            if success and isinstance(items, list):
                results["items"] = self.save_items_bulk(items)

            customer_profile = json.dumps(
                {
                    "name": pos_profile_name,
                    "posa_use_server_cache": 0,
                    "posa_server_cache_duration": 30,
                }
            )
            success, customers = self.api.call_method(
                "posawesome.posawesome.api.customers.get_customer_names",
                {"pos_profile": customer_profile, "limit": 5000},
            )
            if success and isinstance(customers, list):
                results["customers"] = self.save_customers(customers)

        self.log_sync("full_sync", "success", json.dumps(results))
        return results

    def get_boot_config(self) -> dict:
        config = load_config()
        boot = {
            "serverUrl": config.get("serverUrl", ""),
            "user": config.get("user", ""),
            "user_fullname": config.get("user", ""),
            "pos_profile": None,
            "sysdefaults": {
                "company": config.get("company", ""),
                "currency": config.get("currency", "UZS"),
            },
            "lang": "en",
            "use_western_numerals": True,
            "website_settings": {},
            "translations": {},
            "user_defaults": {},
        }

        if not self.api.is_configured():
            pos_profile_name = config.get("pos_profile")
            if pos_profile_name:
                boot["pos_profile"] = {"name": pos_profile_name}
            return boot

        success, user = self.api.call_method("frappe.auth.get_logged_user")
        if success and isinstance(user, str):
            boot["user"] = user
            boot["user_fullname"] = user

        success, profile = self.api.call_method("posawesome.posawesome.api.utils.get_active_pos_profile")
        if success and isinstance(profile, dict):
            boot["pos_profile"] = profile
            boot["sysdefaults"]["company"] = profile.get("company", boot["sysdefaults"]["company"])
            boot["sysdefaults"]["currency"] = profile.get("currency", boot["sysdefaults"]["currency"])

        lang = "en"
        success, user_doc = self.api.call_method("frappe.client.get", {"doctype": "User", "name": boot["user"]})
        if success and isinstance(user_doc, dict):
            boot["user_fullname"] = user_doc.get("full_name") or boot["user"]
            lang = user_doc.get("language") or lang
        boot["lang"] = lang

        try:
            success, translations = self.api.call_method("posawesome.posawesome.api.utils.get_translations", {"lang": lang})
            if success and isinstance(translations, dict):
                boot["translations"] = translations
        except Exception:
            logger.debug("Translations preload skipped", exc_info=True)

        return boot
