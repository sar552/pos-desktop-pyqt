import json
import uuid
from core.api import FrappeAPI
from database.models import SalesInvoice, SalesInvoiceItem, SalesInvoicePayment
from core.logger import get_logger
from core.config import load_config

logger = get_logger(__name__)


def _is_probable_invoice_id(value: str) -> bool:
    if not value:
        return False
    clean = value.strip()
    if len(clean) > 140 or " " in clean:
        return False
    return any(ch.isdigit() for ch in clean)


def _extract_invoice_name(response) -> str:
    """Extract created Sales Invoice name from POSAwesome submit response."""
    if isinstance(response, str):
        candidate = response.strip()
        return candidate if _is_probable_invoice_id(candidate) else ""

    if not isinstance(response, dict):
        return ""

    message = response.get("message")
    if isinstance(message, str):
        candidate = message.strip()
        return candidate if _is_probable_invoice_id(candidate) else ""
    if isinstance(message, dict):
        candidate = str(message.get("name") or message.get("value") or "").strip()
        return candidate if _is_probable_invoice_id(candidate) else ""

    candidate = str(response.get("name") or "").strip()
    return candidate if _is_probable_invoice_id(candidate) else ""

def process_pending_invoice(api: FrappeAPI, inv: SalesInvoice) -> tuple[str, str]:
    """Bitta oflayn chekni serverga yuborish.
    Qaytaradi: (status_string, error_message)
    status_string: "Synced" yoki "Failed" yoki "Draft"
    """
    if not api.is_configured():
        return "Draft", "API sozlanmagan"

    try:
        config = load_config()
        currency = config.get("currency", "UZS")

        # Invoice ma'lumotlarini yig'ish (Frappe/PosAwesome formatida)
        items = []
        for it in inv.items:
            amount = float(it.amount or 0)
            items.append({
                "item_code": it.item_code,
                "item_name": it.item_name,
                "qty": it.qty,
                "rate": it.rate,
                "amount": amount,
                "base_amount": amount,
                "uom": it.uom,
                "batch_no": it.batch_no,
                "serial_no": it.serial_no
            })

        payments = []
        for p in inv.payments:
            amount = float(p.amount or 0)
            p_type = "Cash" if "cash" in (p.mode_of_payment or "").lower() else "Bank"
            payments.append({
                "mode_of_payment": p.mode_of_payment,
                "amount": amount,
                "base_amount": amount,
                "account": p.account,
                "type": p_type,
                "currency": currency,
            })

        effective_pos_profile = inv.pos_profile
        configured_profile = config.get("pos_profile")
        if configured_profile and effective_pos_profile and effective_pos_profile != configured_profile:
            logger.warning(
                "Invoice %s da pos_profile '%s' topildi, configured profile '%s' ishlatiladi.",
                inv.offline_id,
                effective_pos_profile,
                configured_profile,
            )
            effective_pos_profile = configured_profile

        invoice_payload = {
            "customer": inv.customer,
            "pos_profile": effective_pos_profile,
            "company": inv.company,
            "posting_date": inv.posting_date.strftime("%Y-%m-%d"),
            "items": items,
            "payments": payments,
            "is_pos": 1,
            "update_stock": 1,
            "total": float(inv.total or inv.net_total or inv.grand_total or 0),
            "net_total": float(inv.net_total or inv.total or inv.grand_total or 0),
            "grand_total": float(inv.grand_total or 0),
            "rounded_total": float(inv.grand_total or 0),
            "paid_amount": float(inv.paid_amount or 0),
            "base_grand_total": float(inv.grand_total or 0),
            "base_paid_amount": float(inv.paid_amount or 0),
            "currency": currency,
        }
        
        # PosAwesome asosan `submit_invoice` metodini kutadi
        # invoice: json_string, data: json_string
        
        success, response = api.call_method(
            "posawesome.posawesome.api.invoices.submit_invoice",
            {
                "invoice": json.dumps(invoice_payload),
                "data": json.dumps(
                    {
                        "is_credit_sale": int((inv.paid_amount or 0) < (inv.grand_total or 0)),
                        "paid_change": max(0, float(inv.paid_amount or 0) - float(inv.grand_total or 0)),
                        "write_off_amount": 0,
                    }
                ),
            }
        )

        if success:
            server_name = _extract_invoice_name(response)
            if not server_name:
                logger.error("submit_invoice javobida invoice nomi yo'q: %s", response)
                return "Draft", "Server invoice nomi qaytmadi"

            inv.name = server_name
            logger.info("Invoice serverga muvaffaqiyatli ketdi: %s (Server Name: %s)", inv.offline_id, server_name)
            return "Synced", ""
        else:
            logger.error("Invoice yuborishda xatolik: %s", response)
            return "Draft", str(response)

    except Exception as e:
        logger.error("Invoice yuborishda kutilmagan xatolik: %s", e)
        return "Draft", str(e)

def save_offline_invoice(invoice_data: dict) -> SalesInvoice:
    """Sotuv ma'lumotlarini lokal bazaga saqlash"""
    from database.models import db
    
    with db.atomic():
        offline_id = str(uuid.uuid4())
        
        inv = SalesInvoice.create(
            offline_id=offline_id,
            customer=invoice_data["customer"],
            pos_profile=invoice_data["pos_profile"],
            company=invoice_data["company"],
            total_qty=invoice_data["total_qty"],
            grand_total=invoice_data["grand_total"],
            net_total=invoice_data.get("net_total", 0),
            discount_amount=invoice_data.get("discount_amount", 0),
            paid_amount=invoice_data["paid_amount"],
            status="Draft"
        )
        
        for item in invoice_data["items"]:
            SalesInvoiceItem.create(
                invoice=inv,
                item_code=item["item_code"],
                item_name=item["item_name"],
                qty=item["qty"],
                uom=item["uom"],
                rate=item["rate"],
                amount=item["amount"],
                batch_no=item.get("batch_no"),
                serial_no=item.get("serial_no")
            )
            
        for p in invoice_data["payments"]:
            SalesInvoicePayment.create(
                invoice=inv,
                mode_of_payment=p["mode_of_payment"],
                amount=p["amount"],
                account=p.get("account")
            )
            
        return inv
