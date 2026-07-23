import json

from core.api import FrappeAPI
from core.logger import get_logger
from database.models import PendingInvoice, PosShift, db

logger = get_logger(__name__)

# ──────────────────────────────────────────────────
#  Permanent error detection
# ──────────────────────────────────────────────────
# HTTP status codes that mean the invoice will never succeed on retry.
PERMANENT_STATUS_CODES = {400, 403, 404, 417, 422}

# Backstop string-based detection (legacy) — kept for non-HTTP exceptions.
PERMANENT_KEYWORDS = (
    "validationerror",
    "permissionerror",
    "doesnotexisterror",
    "mandatoryerror",
    "invalidcolumnname",
    "does not exist",
    "not found",
)


def is_permanent_error(error_msg: str, status_code: int = 0) -> bool:
    if status_code and status_code in PERMANENT_STATUS_CODES:
        return True
    msg_lower = (error_msg or "").lower()
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
    # ("Guest" emas — online oqim bilan bir xil nom, aks holda server
    # "Guest" degan yangi soxta mijoz yaratib yuborardi)
    customer = payload.get("customer", "").strip()
    if not customer:
        payload["customer"] = config.get("default_customer") or "Guest Customer"

    # Idempotency: server shu id li chekni qayta yaratmaydi.
    if invoice.offline_id:
        payload["posa_offline_id"] = invoice.offline_id
    
    # POSAwesome uchun kerakli maydonlar
    payload["doctype"] = "Sales Invoice"
    payload["is_pos"] = 1
    payload["update_stock"] = 1

    # MUHIM: chek saqlangan paytdagi smena sinxron vaqtiga kelib YOPILGAN
    # bo'lishi mumkin — server yopiq smenali chekni qabul qilmaydi va chek
    # butunlay yo'qolardi. Shu sababli har urinishda JORIY ochiq smena bilan
    # qayta muhrlaymiz; ochiq smena bo'lmasa maydonni olib tashlaymiz.
    try:
        shift = (
            PosShift.select()
            .where(PosShift.status == "Open")
            .order_by(PosShift.id.desc())
            .first()
        )
        if shift and shift.opening_entry:
            payload["posa_pos_opening_shift"] = shift.opening_entry
        else:
            payload.pop("posa_pos_opening_shift", None)
    except Exception as e:
        logger.debug("Pending invoice uchun opening shift olinmadi: %s", e)
    
    # Currency - POSAwesome uchun majburiy
    if not payload.get("currency"):
        payload["currency"] = config.get("currency", "UZS")

    if not payload.get("selling_price_list"):
        payload["selling_price_list"] = config.get("price_list")
    
    # Items formatting
    items = payload.get("items", [])
    formatted_items = []
    for item in items:
        rate = item.get("rate", 0)
        qty = item.get("qty", 1)
        discount_amount = item.get("discount_amount", 0)
        price_list_rate = item.get("price_list_rate", rate)
        formatted_items.append({
            "item_code": item.get("item_code"),
            "item_name": item.get("item_name") or item.get("name") or item.get("item_code"),
            "qty": qty,
            "uom": item.get("uom"),
            "conversion_factor": item.get("conversion_factor", 1),
            "warehouse": item.get("warehouse") or payload.get("set_warehouse"),
            "rate": rate,
            "base_rate": item.get("base_rate", rate),
            "amount": item.get("amount", rate * qty),
            "base_amount": item.get("base_amount", rate * qty),
            "price_list_rate": price_list_rate,
            "base_price_list_rate": item.get("base_price_list_rate", price_list_rate),
            "discount_amount": discount_amount,
            "base_discount_amount": item.get("base_discount_amount", discount_amount),
            "discount_percentage": item.get("discount_percentage", 0),
            "is_stock_item": item.get("is_stock_item", 1),
        })
    payload["items"] = formatted_items
    
    # Payments formatting
    formatted_payments = []
    for p in payments:
        formatted_payments.append({
            "mode_of_payment": p.get("mode_of_payment"),
            "amount": p.get("amount", 0),
            "type": p.get("type", "Cash"),
        })
    payload["payments"] = formatted_payments
    
    # POSAwesome submit_invoice API chaqirish
    # invoice va data JSON string bo'lishi kerak
    data_payload = {
        "payments": formatted_payments,
    }
    if payload.get("due_date"):
        data_payload["due_date"] = payload.get("due_date")
    if payload.get("is_credit_sale"):
        data_payload["is_credit_sale"] = 1
    if payload.get("is_partly_paid"):
        data_payload["is_partly_paid"] = 1
    
    try:
        result = api.call_method(
            "posawesome.posawesome.api.invoices.submit_invoice",
            {
                "invoice": json.dumps(payload),
                "data": json.dumps(data_payload),
                "submit_in_background": 0,
            },
        )
        # ApiResponse: (success, payload, status_code).  Legacy 2-tuple unpack
        # would lose the status code, so we index directly.
        success = bool(result[0])
        response = result[1]
        status_code = result[2] if len(result) > 2 else 0

        if success:
            # 200 OK, lekin javob dict bo'lmasligi (bo'sh message) ham mumkin —
            # server chekni qabul qilgan. "Pending"da qoldirsak, har 30
            # sekundda qayta yuborilib, cheksiz dublikat chek yaratiladi.
            doc_name = response.get("name", "") if isinstance(response, dict) else ""
            logger.info(
                "Oflayn chek muvaffaqiyatli sinxronlandi: %s -> %s",
                invoice.offline_id, doc_name or "(nomsiz javob)",
            )
            return "Synced", doc_name

        error_str = str(response)
        logger.error("Sinxronlashda xato (HTTP %s): %s", status_code, error_str)
        # Smena bilan bog'liq rad — sotuvni yo'qotmaymiz: keyingi urinishda
        # joriy ochiq smena bilan (yoki smenasiz) qayta yuboriladi.
        if "shift" in error_str.lower() and "not open" in error_str.lower():
            return "Pending", error_str
        if is_permanent_error(error_str, status_code):
            return "Failed", error_str
        return "Pending", error_str
    except Exception as e:
        logger.error("Invoice sinxronizatsiya exception: %s", e)
        return "Pending", str(e)
