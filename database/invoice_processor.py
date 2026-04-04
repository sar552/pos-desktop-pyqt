import json
import sched
import time
from threading import Thread
from database.models import PendingInvoice, db
from core.api import FrappeAPI
from core.logger import get_logger

logger = get_logger(__name__)

# ──────────────────────────────────────────────────
#  Permanent error detection
# ──────────────────────────────────────────────────
PERMANENT_KEYWORDS = [
    "validationerror",
    "permissionerror",
    "doesnotexisterror",
    "mandatoryerror",
    "invalidcolumnname",
    "server xatosi (417)",
    "server xatosi (403)",
    "server xatosi (404)",
    "does not exist",
    "not found",
]


def is_permanent_error(error_msg: str) -> bool:
    msg_lower = error_msg.lower()
    return any(kw in msg_lower for kw in PERMANENT_KEYWORDS)


def process_pending_invoice(api: FrappeAPI, invoice: PendingInvoice) -> tuple[str, str]:
    """Oflayn invoiceni POSAwesome orqali serverga yuborish."""
    logger.info(f"Oflayn chek sinxronlanmoqda: {invoice.offline_id}")
    
    try:
        data = json.loads(invoice.invoice_data)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Invoice JSON parse xatosi: {e}")
        return 'Failed', f"Noto'g'ri invoice ma'lumotlari: {e}"
    
    payload = dict(data)
    
    # Payments ni ajratib olish
    payments = payload.pop("_payments", None) or payload.get("payments", [])
    
    # Config'dan kerakli maydonlar
    from core.config import load_config
    config = load_config()
    
    # Customer tekshiruvi - bo'sh bo'lsa default customer
    customer = payload.get("customer", "").strip()
    if not customer:
        payload["customer"] = config.get("default_customer", "Guest")
    
    # POSAwesome uchun kerakli maydonlar
    payload["doctype"] = "Sales Invoice"
    payload["is_pos"] = 1
    payload["update_stock"] = 1
    
    # Currency - POSAwesome uchun majburiy
    if not payload.get("currency"):
        payload["currency"] = config.get("currency", "UZS")

    if not payload.get("selling_price_list"):
        payload["selling_price_list"] = config.get("price_list")
    
    # Items formatting
    items = payload.get("items", [])
    formatted_items = []
    for item in items:
        formatted_items.append({
            "item_code": item.get("item_code"),
            "qty": item.get("qty", 1),
            "rate": item.get("rate", 0),
            "amount": item.get("amount", item.get("rate", 0) * item.get("qty", 1)),
        })
    payload["items"] = formatted_items
    
    # Payments formatting
    formatted_payments = []
    for p in payments:
        formatted_payments.append({
            "mode_of_payment": p.get("mode_of_payment"),
            "amount": p.get("amount", 0),
        })
    payload["payments"] = formatted_payments
    
    # POSAwesome submit_invoice API chaqirish
    # invoice va data JSON string bo'lishi kerak
    data_payload = {
        "payments": formatted_payments,
    }
    
    try:
        success, response = api.call_method(
            "posawesome.posawesome.api.invoices.submit_invoice",
            {
                "invoice": json.dumps(payload),
                "data": json.dumps(data_payload),
                "submit_in_background": 0
            }
        )
        
        if success and isinstance(response, dict):
            doc_name = response.get("name", "")
            logger.info(f"Oflayn chek muvaffaqiyatli sinxronlandi: {invoice.offline_id} -> {doc_name}")
            return 'Synced', doc_name
        else:
            error_str = str(response)
            logger.error(f"Sinxronlashda xato: {error_str}")
            
            if is_permanent_error(error_str):
                return 'Failed', error_str
            return 'Pending', error_str
            
    except Exception as e:
        logger.error(f"Invoice sinxronizatsiya exception: {e}")
        return 'Pending', str(e)

class InvoiceProcessor:
    def __init__(self, api: FrappeAPI):
        self.api = api
        self.scheduler = sched.scheduler(time.time, time.sleep)
        self.running = False
        
    def start(self):
        if not self.running:
            self.running = True
            logger.info("Invoice processor is starting in background...")
            t = Thread(target=self._run_loop, daemon=True)
            t.start()
            
    def stop(self):
        self.running = False
        
    def _run_loop(self):
        while self.running:
            try:
                self.process_pending_invoices()
            except Exception as e:
                logger.error(f"Error in processor loop: {e}")
            time.sleep(15)  # Har 15 soniyada urunib ko'rish
            
    def process_pending_invoices(self):
        db.connect(reuse_if_open=True)
        try:
            pending = PendingInvoice.select().where(PendingInvoice.status == 'Pending')
            
            for invoice in pending:
                status, message = process_pending_invoice(self.api, invoice)
                invoice.status = status
                invoice.error_message = message
                invoice.save()
                    
        finally:
            if not db.is_closed():
                db.close()
