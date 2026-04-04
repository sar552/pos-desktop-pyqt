import os
import platform
import shutil
import subprocess
import threading
from html import escape
from datetime import datetime
from PyQt6.QtGui import QTextDocument, QPageLayout, QPageSize
from PyQt6.QtCore import QSizeF, QMarginsF
from PyQt6.QtPrintSupport import QPrinter, QPrinterInfo
from core.logger import get_logger
from core.config import load_config
from database.models import Item, db

logger = get_logger(__name__)

# ESC/POS buyruqlari
ESC = b'\x1b'
GS = b'\x1d'

CMD_INIT = ESC + b'\x40'
CMD_ALIGN_CENTER = ESC + b'\x61\x01'
CMD_ALIGN_LEFT = ESC + b'\x61\x00'
CMD_BOLD_ON = ESC + b'\x45\x01'
CMD_BOLD_OFF = ESC + b'\x45\x00'
CMD_DOUBLE_ON = GS + b'\x21\x11'
CMD_DOUBLE_OFF = GS + b'\x21\x00'
CMD_FONT_B = ESC + b'\x4d\x01'
CMD_FONT_A = ESC + b'\x4d\x00'
CMD_CUT = GS + b'\x56\x41\x03'
CMD_FEED = ESC + b'\x64\x04'
CMD_OPEN_DRAWER = ESC + b'\x70\x00\x19\xfa'

CHARS_PER_LINE = 48
CHARS_DOUBLE = 24  # CMD_DOUBLE_ON da 2x kenglik → yarmi sig'adi
PRINTER_TIMEOUT = 3.0

ORDER_TYPE_LABELS = {
    "Shu yerda": "Xarid cheki",
    "Saboy": "Olib ketish cheki",
    "Dastavka": "Dastavka cheki",
    "Dastavka Saboy": "Dastavka cheki",
}


# ──────────────────────────────────────────────────
#  Printer ro'yxatini config'dan yuklash
# ──────────────────────────────────────────────────
def get_printers() -> list[dict]:
    config = load_config()
    printers = config.get("printers", None)

    if not printers:
        device = config.get("printer_device", "/dev/usb/lp0")
        win_name = config.get("printer_name", "XP-365B")
        return [{"name": "Mijoz", "device": device, "type": "customer", "win_name": win_name, "mode": "auto"}]

    return printers


def get_printers_by_type(printer_type: str) -> list[dict]:
    return [p for p in get_printers() if p.get("type") == printer_type]


def _get_named_printer(printer_config: dict) -> str:
    if platform.system() == "Windows":
        return (printer_config.get("win_name") or printer_config.get("name") or "").strip()
    return (printer_config.get("cups_name") or "").strip()


def _get_printer_mode(printer_config: dict) -> str:
    mode = (printer_config.get("mode") or "auto").strip().lower()
    if mode not in {"auto", "thermal", "office"}:
        return "auto"
    return mode


def list_linux_printers() -> list[dict]:
    """Linux'da CUPS queue'lari va raw USB device'larni qaytaradi."""
    printers = []
    seen = set()

    if platform.system() != "Linux":
        return printers

    if shutil.which("lpstat"):
        try:
            result = subprocess.run(
                ["lpstat", "-p"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line.startswith("printer "):
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                printer_name = parts[1].strip()
                if printer_name and printer_name not in seen:
                    printers.append({
                        "label": f"{printer_name} (CUPS)",
                        "device": "",
                        "win_name": "",
                        "cups_name": printer_name,
                    })
                    seen.add(printer_name)
        except Exception as e:
            logger.warning("CUPS printerlarni o'qib bo'lmadi: %s", e)

    for index in range(10):
        device = f"/dev/usb/lp{index}"
        if os.path.exists(device) and device not in seen:
            printers.append({
                "label": device,
                "device": device,
                "win_name": "",
                "cups_name": "",
            })
            seen.add(device)

    return printers


def is_printer_available(device: str) -> bool:
    if platform.system() == "Windows":
        try:
            import win32print
            printers = [p[2] for p in win32print.EnumPrinters(2)]
            return device in printers
        except ImportError:
            return False
    else:
        return os.path.exists(device)


def get_printer_issue(printer_config: dict) -> str:
    """Printer yuborishdan oldin aniq muammoni aniqlash."""
    printer_name = _get_named_printer(printer_config)
    if printer_name:
        available = {info.printerName() for info in QPrinterInfo.availablePrinters()}
        if available and printer_name not in available:
            return f"Printer topilmadi: {printer_name}"
        return ""

    if platform.system() == "Windows":
        printer_name = printer_config.get("win_name", printer_config.get("name", "")).strip()
        if not printer_name:
            return "Printer tanlanmagan."
        if not is_printer_available(printer_name):
            return f"Windows printer topilmadi: {printer_name}"
        return ""

    device = printer_config.get("device", "").strip()
    if not device:
        return "Printer qurilmasi tanlanmagan."
    if not os.path.exists(device):
        return f"Printer qurilmasi topilmadi: {device}"
    if not os.access(device, os.W_OK):
        return (
            f"Printerga yozish ruxsati yo'q: {device}\n"
            "Linux'da foydalanuvchini 'lp' guruhiga qo'shing va sessiyani qayta oching:\n"
            "sudo usermod -aG lp $USER"
        )
    return ""


# ──────────────────────────────────────────────────
#  Matn formatlash
# ──────────────────────────────────────────────────
def _encode(text: str) -> bytes:
    try:
        return text.encode("cp866")
    except UnicodeEncodeError:
        return text.encode("utf-8", errors="replace")


def _line(left: str, right: str = "", fill: str = " ", width: int = CHARS_PER_LINE) -> bytes:
    if not right:
        return _encode(left[:width] + "\n")
    space = width - len(left) - len(right)
    if space < 1:
        space = 1
    return _encode(left + fill * space + right + "\n")


def _center_text(text: str) -> bytes:
    return CMD_ALIGN_CENTER + _encode(text + "\n") + CMD_ALIGN_LEFT


def _separator(char: str = "-", width: int = CHARS_PER_LINE) -> bytes:
    return _encode(char * width + "\n")


def _format_amount(amount) -> str:
    return f"{float(amount):,.0f}"


def _order_type_label(order_type: str) -> str:
    return ORDER_TYPE_LABELS.get(order_type, "Chek")


# ──────────────────────────────────────────────────
#  Chek ma'lumotlarini yaratish
# ──────────────────────────────────────────────────
def _build_customer_receipt(order_data: dict, payments_list: list, config: dict) -> bytes:
    """Mijoz uchun to'liq chek — turiga qarab sarlavha o'zgaradi"""
    items_list = order_data.get("items", [])
    total_amount = order_data.get("total_amount", 0.0)
    order_type = order_data.get("order_type", "")
    ticket_number = order_data.get("ticket_number", "")
    comment = order_data.get("comment", "")
    customer = order_data.get("customer", "")

    company = config.get("company", "POKIZA POS")

    total_paid = sum(float(p.get("amount", 0)) for p in payments_list)
    change = max(0, total_paid - total_amount)
    date_str = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")

    data = bytearray()
    data += CMD_INIT

    # Sarlavha — turiga qarab
    data += CMD_ALIGN_CENTER
    data += CMD_BOLD_ON + CMD_DOUBLE_ON
    data += _encode(company + "\n")
    data += CMD_DOUBLE_OFF + CMD_BOLD_OFF
    data += _encode(_order_type_label(order_type) + "\n")
    data += _encode(date_str + "\n")
    data += CMD_ALIGN_LEFT

    # Dastavka → mijoz nomi
    if order_type in ("Dastavka", "Dastavka Saboy") and customer and customer != "guest":
        data += _separator()
        data += CMD_BOLD_ON
        data += _line("Mijoz:", customer)
        data += CMD_BOLD_OFF

    # Stiker raqami
    if ticket_number:
        data += _encode("\n")
        data += _separator("=")
        data += CMD_ALIGN_CENTER + CMD_BOLD_ON + CMD_DOUBLE_ON
        data += _encode(f"STIKER: {ticket_number}\n")
        data += CMD_DOUBLE_OFF + CMD_BOLD_OFF + CMD_ALIGN_LEFT
        data += _separator("=")

    # Tovarlar
    data += _encode("\n")
    data += CMD_BOLD_ON
    data += _line("Nomi", "Soni   Summa")
    data += CMD_BOLD_OFF
    data += _separator()

    for item in items_list:
        name = item.get("name", item.get("item_name", ""))
        qty = int(item.get("qty", 0))
        price = float(item.get("price", item.get("rate", 0)))
        line_total = qty * price
        qty_str = str(qty)
        total_str = _format_amount(line_total)
        right_part = f"{qty_str:>4}  {total_str:>10}"

        if len(name) + len(right_part) + 1 > CHARS_PER_LINE:
            data += _encode(name[:CHARS_PER_LINE] + "\n")
            data += _encode(right_part.rjust(CHARS_PER_LINE) + "\n")
        else:
            data += _line(name, right_part)

    # Jami
    data += _separator("=")
    data += CMD_BOLD_ON + CMD_DOUBLE_ON
    data += _line("JAMI:", f"{_format_amount(total_amount)} UZS", width=CHARS_DOUBLE)
    data += CMD_DOUBLE_OFF + CMD_BOLD_OFF
    data += _separator("=")

    # To'lovlar
    data += _encode("\n")
    data += CMD_BOLD_ON
    data += _encode("TO'LOVLAR:\n")
    data += CMD_BOLD_OFF
    for p in payments_list:
        if float(p.get("amount", 0)) > 0:
            data += _line(f"  {p['mode_of_payment']}:", f"{_format_amount(p['amount'])} UZS")

    # Qaytim
    if change > 0:
        data += _separator()
        data += CMD_BOLD_ON
        data += _line("QAYTIM:", f"{_format_amount(change)} UZS")
        data += CMD_BOLD_OFF

    # Izoh
    if comment:
        data += _encode(f"\nIzoh: {comment}\n")

    # Pastki qism
    data += _encode("\n")
    data += _center_text("Xaridingiz uchun rahmat!")
    data += CMD_FEED
    data += CMD_CUT

    return bytes(data)


def _build_production_receipt(order_data: dict, unit_items: list, unit_name: str) -> bytes:
    """Production unit uchun chek — turiga qarab format o'zgaradi"""
    order_type = order_data.get("order_type", "")
    ticket_number = order_data.get("ticket_number", "")
    comment = order_data.get("comment", "")
    customer = order_data.get("customer", "")
    date_str = datetime.now().strftime("%H:%M:%S")

    data = bytearray()
    data += CMD_INIT

    # Sarlavha — unit nomi katta
    data += CMD_ALIGN_CENTER + CMD_BOLD_ON + CMD_DOUBLE_ON
    data += _encode(f"--- {unit_name} ---\n")
    data += CMD_DOUBLE_OFF + CMD_BOLD_OFF

    # Buyurtma turi + vaqt
    data += CMD_ALIGN_CENTER
    data += CMD_BOLD_ON + CMD_DOUBLE_ON
    data += _encode(f"{order_type}\n")
    data += CMD_DOUBLE_OFF + CMD_BOLD_OFF
    data += _encode(date_str + "\n")

    # Stiker — eng muhim qism
    if ticket_number:
        data += _encode("\n")
        data += CMD_BOLD_ON + CMD_DOUBLE_ON
        data += _encode(f"# {ticket_number}\n")
        data += CMD_DOUBLE_OFF + CMD_BOLD_OFF

    # Dastavka → mijoz nomi
    if order_type in ("Dastavka", "Dastavka Saboy") and customer and customer != "guest":
        data += CMD_BOLD_ON
        data += _encode(f"Mijoz: {customer}\n")
        data += CMD_BOLD_OFF

    data += CMD_ALIGN_LEFT
    data += _separator("=")

    # Tovarlar — katta shrift, faqat nom va miqdor
    data += CMD_BOLD_ON + CMD_DOUBLE_ON
    for item in unit_items:
        name = item.get("name", item.get("item_name", ""))
        qty = int(item.get("qty", 0))
        right = f"x{qty}"
        # DOUBLE_ON = 24 belgi sig'adi
        if len(name) + len(right) + 1 > CHARS_DOUBLE:
            name = name[:CHARS_DOUBLE - len(right) - 1]
        data += _line(name, right, width=CHARS_DOUBLE)
    data += CMD_DOUBLE_OFF + CMD_BOLD_OFF

    data += _separator("=")

    # Izoh
    if comment:
        data += CMD_BOLD_ON
        data += _encode(f"IZOH: {comment}\n")
        data += CMD_BOLD_OFF

    data += CMD_FEED
    data += CMD_CUT

    return bytes(data)


def _get_item_groups_map(items: list) -> dict:
    """Lokal DB dan itemlarning item_group ini oladi."""
    item_codes = [
        item.get("item_code", item.get("item", ""))
        for item in items
        if item.get("item_code") or item.get("item")
    ]
    if not item_codes:
        return {}

    try:
        db.connect(reuse_if_open=True)
        rows = Item.select(Item.item_code, Item.item_group).where(
            Item.item_code.in_(item_codes)
        )
        return {row.item_code: row.item_group or "" for row in rows}
    except Exception as e:
        logger.error("Item group olishda xatolik: %s", e)
        return {}
    finally:
        if not db.is_closed():
            db.close()


# ──────────────────────────────────────────────────
#  Printerga yuborish (timeout bilan)
# ──────────────────────────────────────────────────
def _send_to_device(data: bytes, device: str) -> bool:
    """Ma'lumotni printerga yuborish (Linux USB) — timeout bilan"""
    if not os.path.exists(device):
        logger.warning("Printer topilmadi: %s", device)
        return False

    result = [False]
    error = [None]

    def _write():
        try:
            with open(device, "wb") as printer:
                printer.write(data)
                printer.flush()
            result[0] = True
        except Exception as e:
            error[0] = e

    t = threading.Thread(target=_write, daemon=True)
    t.start()
    t.join(timeout=PRINTER_TIMEOUT)

    if t.is_alive():
        logger.error("Printer timeout (%.0f sek): %s", PRINTER_TIMEOUT, device)
        return False

    if error[0]:
        if isinstance(error[0], PermissionError):
            logger.error("Printer ruxsati yo'q: %s (sudo usermod -aG lp $USER)", device)
        else:
            logger.error("Printer xatosi (%s): %s", device, error[0])
        return False

    return result[0]


def _send_win32(data: bytes, printer_name: str) -> bool:
    """Windows'da win32print orqali yuborish"""
    try:
        import win32print
        hPrinter = win32print.OpenPrinter(printer_name)
        try:
            hJob = win32print.StartDocPrinter(hPrinter, 1, ("POS Receipt", None, "RAW"))
            try:
                win32print.StartPagePrinter(hPrinter)
                win32print.WritePrinter(hPrinter, data)
                win32print.EndPagePrinter(hPrinter)
            finally:
                win32print.EndDocPrinter(hPrinter)
        finally:
            win32print.ClosePrinter(hPrinter)
        return True
    except ImportError:
        logger.error("win32print topilmadi. 'pip install pywin32' qiling.")
        return False
    except Exception as e:
        logger.error("Windows print xatosi (%s): %s", printer_name, e)
        return False


def _looks_like_thermal(printer_name: str) -> bool:
    name = (printer_name or "").lower()
    keywords = ("xp-", "xprinter", "thermal", "receipt", "pos", "80mm", "58mm")
    return any(word in name for word in keywords)


def _is_thermal_printer(printer_config: dict) -> bool:
    mode = _get_printer_mode(printer_config)
    if mode == "thermal":
        return True
    if mode == "office":
        return False

    named = _get_named_printer(printer_config)
    if named:
        return _looks_like_thermal(named)

    device = (printer_config.get("device") or "").strip()
    return bool(device)


def _build_customer_receipt_html(order_data: dict, payments_list: list, config: dict) -> str:
    items_list = order_data.get("items", [])
    total_amount = float(order_data.get("total_amount", 0.0) or 0)
    order_type = order_data.get("order_type", "")
    ticket_number = order_data.get("ticket_number", "")
    comment = order_data.get("comment", "")
    customer = order_data.get("customer", "")
    company = config.get("company", "POKIZA POS")
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_paid = sum(float(p.get("amount", 0) or 0) for p in payments_list)
    change = max(0, total_paid - total_amount)

    rows = []
    for item in items_list:
        name = escape(str(item.get("name", item.get("item_name", ""))))
        qty = float(item.get("qty", 0) or 0)
        price = float(item.get("price", item.get("rate", 0)) or 0)
        amount = float(item.get("amount", qty * price) or 0)
        rows.append(
            f"<tr><td>{name}</td><td class='num'>{qty:,.0f}</td>"
            f"<td class='num'>{_format_amount(price)}</td><td class='num'>{_format_amount(amount)}</td></tr>"
        )

    payment_rows = []
    for payment in payments_list:
        amount = float(payment.get("amount", 0) or 0)
        if amount <= 0:
            continue
        payment_rows.append(
            f"<tr><td>{escape(str(payment.get('mode_of_payment', '')))}</td>"
            f"<td class='num'>{_format_amount(amount)}</td></tr>"
        )

    meta_rows = [
        f"<div><strong>Sana:</strong> {escape(date_str)}</div>",
        f"<div><strong>Turi:</strong> {escape(_order_type_label(order_type))}</div>",
    ]
    if ticket_number:
        meta_rows.append(f"<div><strong>Stiker:</strong> {escape(str(ticket_number))}</div>")
    if customer and customer != "guest":
        meta_rows.append(f"<div><strong>Mijoz:</strong> {escape(str(customer))}</div>")
    if comment:
        meta_rows.append(f"<div><strong>Izoh:</strong> {escape(str(comment))}</div>")

    return f"""
    <html>
    <head>
      <style>
        body {{ font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 10pt; color: #000; margin: 0; }}
        .wrap {{ width: 100%; }}
        .center {{ text-align: center; }}
        .title {{ font-size: 16pt; font-weight: 700; margin-bottom: 4px; }}
        .subtitle {{ font-size: 11pt; margin-bottom: 8px; }}
        .meta {{ margin: 12px 0; line-height: 1.5; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
        th, td {{ border-bottom: 1px solid #ddd; padding: 6px 4px; }}
        th {{ text-align: left; font-weight: 700; }}
        .num {{ text-align: right; white-space: nowrap; }}
        .totals {{ margin-top: 14px; width: 100%; }}
        .totals div {{ display: block; margin: 4px 0; text-align: right; }}
        .grand {{ font-size: 12pt; font-weight: 700; }}
        .note {{ margin-top: 18px; text-align: center; font-weight: 600; }}
      </style>
    </head>
    <body>
      <div class="wrap">
        <div class="center">
          <div class="title">{escape(str(company))}</div>
          <div class="subtitle">{escape(_order_type_label(order_type))}</div>
        </div>
        <div class="meta">{''.join(meta_rows)}</div>
        <table>
          <thead>
            <tr><th>Nomi</th><th class="num">Soni</th><th class="num">Narx</th><th class="num">Summa</th></tr>
          </thead>
          <tbody>{''.join(rows) or '<tr><td colspan="4">Item yo&apos;q</td></tr>'}</tbody>
        </table>
        <table>
          <thead><tr><th>To&apos;lov</th><th class="num">Summa</th></tr></thead>
          <tbody>{''.join(payment_rows) or '<tr><td colspan="2">To&apos;lov ma&apos;lumoti yo&apos;q</td></tr>'}</tbody>
        </table>
        <div class="totals">
          <div class="grand">Jami: {_format_amount(total_amount)} UZS</div>
          <div>To&apos;langan: {_format_amount(total_paid)} UZS</div>
          <div>Qaytim: {_format_amount(change)} UZS</div>
        </div>
        <div class="note">Xaridingiz uchun rahmat!</div>
      </div>
    </body>
    </html>
    """


def _build_production_receipt_html(order_data: dict, unit_items: list, unit_name: str) -> str:
    order_type = order_data.get("order_type", "")
    ticket_number = order_data.get("ticket_number", "")
    comment = order_data.get("comment", "")
    customer = order_data.get("customer", "")
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows = []
    for item in unit_items:
        name = escape(str(item.get("name", item.get("item_name", ""))))
        qty = float(item.get("qty", 0) or 0)
        rows.append(f"<tr><td>{name}</td><td class='num'>{qty:,.0f}</td></tr>")

    meta_rows = [
        f"<div><strong>Sana:</strong> {escape(date_str)}</div>",
        f"<div><strong>Turi:</strong> {escape(str(order_type))}</div>",
    ]
    if ticket_number:
        meta_rows.append(f"<div><strong>Stiker:</strong> {escape(str(ticket_number))}</div>")
    if customer and customer != "guest":
        meta_rows.append(f"<div><strong>Mijoz:</strong> {escape(str(customer))}</div>")
    if comment:
        meta_rows.append(f"<div><strong>Izoh:</strong> {escape(str(comment))}</div>")

    return f"""
    <html>
    <head>
      <style>
        body {{ font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 10pt; color: #000; margin: 0; }}
        .center {{ text-align: center; }}
        .title {{ font-size: 16pt; font-weight: 700; margin-bottom: 8px; }}
        .meta {{ margin: 12px 0; line-height: 1.5; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
        th, td {{ border-bottom: 1px solid #ddd; padding: 6px 4px; }}
        th {{ text-align: left; font-weight: 700; }}
        .num {{ text-align: right; white-space: nowrap; }}
      </style>
    </head>
    <body>
      <div class="center"><div class="title">{escape(str(unit_name))}</div></div>
      <div class="meta">{''.join(meta_rows)}</div>
      <table>
        <thead><tr><th>Nomi</th><th class="num">Soni</th></tr></thead>
        <tbody>{''.join(rows) or '<tr><td colspan="2">Item yo&apos;q</td></tr>'}</tbody>
      </table>
    </body>
    </html>
    """


def _send_native_printer_html(html: str, printer_name: str) -> bool:
    try:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPrinterName(printer_name)
        if not printer.isValid():
            logger.error("Native printer topilmadi: %s", printer_name)
            return False

        if _looks_like_thermal(printer_name):
            printer.setPageSize(QPageSize(QSizeF(80, 200), QPageSize.Unit.Millimeter, "POS80"))
            printer.setPageMargins(QMarginsF(2, 4, 2, 4), QPageLayout.Unit.Millimeter)
        else:
            printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
            printer.setPageMargins(QMarginsF(8, 10, 8, 10), QPageLayout.Unit.Millimeter)

        document = QTextDocument()
        document.setHtml(html)
        page_rect = printer.pageRect(QPrinter.Unit.Point)
        document.setPageSize(page_rect.size())
        document.print(printer)
        logger.info("Native printerga yuborildi: %s", printer_name)
        return True
    except Exception as e:
        logger.error("Native print xatosi (%s): %s", printer_name, e)
        return False


def _send_cups(data: bytes, cups_name: str) -> bool:
    """Linux'da CUPS queue orqali RAW yuborish."""
    try:
        result = subprocess.run(
            ["lp", "-d", cups_name, "-o", "raw"],
            input=data,
            capture_output=True,
            timeout=max(PRINTER_TIMEOUT, 10),
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or b"").decode("utf-8", errors="replace").strip()
            logger.error("CUPS print xatosi (%s): %s", cups_name, stderr or result.returncode)
            return False
        return True
    except Exception as e:
        logger.error("CUPS print xatosi (%s): %s", cups_name, e)
        return False


def _send_data(data: bytes, printer_config: dict) -> bool:
    """Platformaga mos tarzda printerga yuborish"""
    printer_name = _get_named_printer(printer_config)
    if printer_name:
        html = printer_config.get("_html")
        if html and not _is_thermal_printer(printer_config):
            return _send_native_printer_html(html, printer_name)
        if platform.system() == "Windows":
            return _send_win32(data, printer_name)
        return _send_cups(data, printer_name)

    device = printer_config.get("device", "/dev/usb/lp0")
    return _send_to_device(data, device)


# ──────────────────────────────────────────────────
#  Umumiy API
# ──────────────────────────────────────────────────
def print_receipt(parent_widget, order_data: dict, payments_list: list) -> dict:
    """Barcha sozlangan printerlarga chek yuborish.

    1. Mijoz cheki — barcha itemlar + narxlar (customer printer)
    2. Production unit cheklari — har bir unit uchun faqat o'z item_group itemlari

    Qaytaradi: {"customer": True/False, "Unit nomi": True/False, ...}
    """
    results = {}
    config = load_config()

    # 1. Mijoz cheki (customer printer) — doim
    customer_printers = get_printers_by_type("customer")
    if customer_printers:
        try:
            receipt_data = _build_customer_receipt(order_data, payments_list, config)
            printer_config = dict(customer_printers[0])
            if _get_named_printer(printer_config) and not _is_thermal_printer(printer_config):
                printer_config["_html"] = _build_customer_receipt_html(order_data, payments_list, config)
            success = _send_data(receipt_data, printer_config)
            results["customer"] = success
            if success:
                logger.info("Mijoz cheki chop etildi")
            else:
                logger.warning("Mijoz cheki chop etilmadi")
        except Exception as e:
            logger.error("Mijoz printer xatosi: %s", e)
            results["customer"] = False
    else:
        logger.warning("Mijoz printeri sozlanmagan")

    # 2. Production unit cheklari
    prod_units = config.get("production_units", [])
    if not prod_units:
        return results

    # Item → item_group mapping (lokal DB) — 1 marta query
    items_list = order_data.get("items", [])
    item_groups_map = _get_item_groups_map(items_list)

    for unit in prod_units:
        unit_name = unit.get("name", "")
        device = unit.get("printer_device", "")
        win_name = unit.get("printer_win_name", "")
        cups_name = unit.get("printer_cups_name", "")

        # Platformaga qarab printer sozlanganligini tekshirish
        if not win_name and not cups_name and not device:
            logger.info("'%s' uchun printer sozlanmagan, o'tkazib yuborildi", unit_name)
            continue
        if not win_name and not cups_name and platform.system() != "Windows":
            if not device:
                logger.info("'%s' uchun printer_device sozlanmagan, o'tkazib yuborildi", unit_name)
                continue

        # Faqat shu unitga tegishli itemlarni filtrlash
        unit_item_groups = set(unit.get("item_groups", []))
        unit_items = [
            item for item in items_list
            if item_groups_map.get(
                item.get("item_code", item.get("item", ""))
            ) in unit_item_groups
        ]

        if not unit_items:
            continue

        try:
            receipt_data = _build_production_receipt(order_data, unit_items, unit_name)
            printer_config = {
                "device": device,
                "win_name": win_name,
                "cups_name": cups_name,
                "mode": unit.get("printer_mode", "auto"),
            }
            if _get_named_printer(printer_config) and not _is_thermal_printer(printer_config):
                printer_config["_html"] = _build_production_receipt_html(order_data, unit_items, unit_name)
            success = _send_data(receipt_data, printer_config)
            results[unit_name] = success

            if success:
                logger.info("Production chek chop etildi: %s", unit_name)
            else:
                logger.warning("Production chek chop etilmadi: %s", unit_name)
        except Exception as e:
            logger.error("Production printer xatosi (%s): %s", unit_name, e)
            results[unit_name] = False

    return results


def open_cash_drawer() -> bool:
    """Cash drawer ochish (birinchi customer printerga)"""
    customer_printers = get_printers_by_type("customer")
    if not customer_printers:
        logger.warning("Mijoz printeri topilmadi — cash drawer ochib bo'lmaydi")
        return False

    p = customer_printers[0]
    if not _is_thermal_printer(p):
        logger.warning("Cash drawer faqat thermal printer bilan ishlaydi")
        return False
    data = CMD_INIT + CMD_OPEN_DRAWER
    return _send_data(data, p)


def send_test_print(printer_config: dict) -> bool:
    """Sinov cheki — printer ishlayotganligini tekshirish."""
    issue = get_printer_issue(printer_config)
    if issue:
        logger.warning("Sinov chop etish bloklandi: %s", issue.replace("\n", " | "))
        return False

    data = bytearray()
    data += CMD_INIT
    data += CMD_ALIGN_CENTER
    data += CMD_BOLD_ON + CMD_DOUBLE_ON
    data += _encode("SINOV CHEKI\n")
    data += CMD_DOUBLE_OFF + CMD_BOLD_OFF
    data += _encode(f"Printer: {printer_config.get('name', 'Test')}\n")
    data += _encode(datetime.now().strftime("%Y-%m-%d  %H:%M:%S") + "\n")
    data += _separator()
    data += _center_text("Printer ishlayapti!")
    data += CMD_FEED
    data += CMD_CUT
    printer_payload = dict(printer_config)
    if _get_named_printer(printer_payload) and not _is_thermal_printer(printer_payload):
        printer_payload["_html"] = f"""
        <html>
        <head>
          <style>
            body {{ font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 12pt; color: #000; }}
            .wrap {{ text-align: center; margin-top: 40px; }}
            .title {{ font-size: 20pt; font-weight: 700; margin-bottom: 12px; }}
            .line {{ margin: 8px 0; }}
          </style>
        </head>
        <body>
          <div class="wrap">
            <div class="title">SINOV CHEKI</div>
            <div class="line">Printer: {escape(str(printer_config.get('name', 'Test')))}</div>
            <div class="line">{escape(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}</div>
            <div class="line">Printer ishlayapti!</div>
          </div>
        </body>
        </html>
        """
    return _send_data(bytes(data), printer_payload)


def reprint_receipt(order_data: dict, payments_list: list) -> bool:
    """Faqat mijoz printeriga qayta chop etish"""
    customer_printers = get_printers_by_type("customer")
    if not customer_printers:
        logger.warning("Mijoz printeri topilmadi — qayta chop etib bo'lmaydi")
        return False

    config = load_config()
    receipt_data = _build_customer_receipt(order_data, payments_list, config)
    printer_config = dict(customer_printers[0])
    if _get_named_printer(printer_config) and not _is_thermal_printer(printer_config):
        printer_config["_html"] = _build_customer_receipt_html(order_data, payments_list, config)
    return _send_data(receipt_data, printer_config)


def print_closing_shift_receipt(closing_data: dict) -> bool:
    """Kassa yopish cheki — kunlik hisobot.
    
    closing_data strukturasi:
    {
        "shift_name": "POS-CLOSE-2026-00001",
        "opening_entry": "POS-OPEN-2026-00001",
        "user": "kassir@company.com",
        "pos_profile": "Main POS",
        "company": "My Company",
        "period_start": "2026-04-04 09:00:00",
        "period_end": "2026-04-04 18:00:00",
        "total_invoices": 25,
        "grand_total": 15000000,
        "net_total": 12500000,
        "total_quantity": 150,
        "payment_reconciliation": [
            {"mode_of_payment": "Cash", "opening_amount": 500000, "expected_amount": 5000000, "closing_amount": 5000000},
            {"mode_of_payment": "Card", "opening_amount": 0, "expected_amount": 10000000, "closing_amount": 10000000},
        ]
    }
    """
    customer_printers = get_printers_by_type("customer")
    if not customer_printers:
        logger.warning("Mijoz printeri topilmadi — kassa yopish cheki chop etib bo'lmaydi")
        return False

    config = load_config()
    company = config.get("company", "POKIZA POS")
    
    # ESC/POS chek yaratish
    data = bytearray()
    data += CMD_INIT
    data += CMD_ALIGN_CENTER
    
    # Sarlavha
    data += CMD_BOLD_ON + CMD_DOUBLE_ON
    data += _encode("KASSA YOPISH\n")
    data += CMD_DOUBLE_OFF
    data += _encode("KUNLIK HISOBOT\n")
    data += CMD_BOLD_OFF
    data += _separator("=")
    
    # Shift ma'lumotlari
    data += CMD_ALIGN_LEFT
    data += _line("Kompaniya:", company)
    data += _line("POS Profil:", str(closing_data.get("pos_profile", "")))
    data += _line("Kassir:", str(closing_data.get("user", "")))
    data += _separator("-")
    
    # Vaqt
    period_start = closing_data.get("period_start", "")
    period_end = closing_data.get("period_end", "")
    if period_start:
        data += _line("Ochilgan:", str(period_start)[:19])
    if period_end:
        data += _line("Yopilgan:", str(period_end)[:19])
    data += _separator("-")
    
    # Umumiy statistika
    data += CMD_BOLD_ON
    data += _center_text("SAVDO STATISTIKASI")
    data += CMD_BOLD_OFF
    data += _line("Cheklar soni:", str(closing_data.get("total_invoices", 0)))
    data += _line("Jami miqdor:", str(closing_data.get("total_quantity", 0)))
    data += _separator("-")
    
    # Moliyaviy ma'lumotlar
    data += CMD_BOLD_ON
    data += _line("Sof savdo:", _format_amount(closing_data.get("net_total", 0)))
    data += _line("Jami savdo:", _format_amount(closing_data.get("grand_total", 0)))
    data += CMD_BOLD_OFF
    data += _separator("=")
    
    # To'lov turlari bo'yicha
    data += CMD_BOLD_ON
    data += _center_text("TO'LOV TURLARI")
    data += CMD_BOLD_OFF
    
    payment_rows = closing_data.get("payment_reconciliation", [])
    for rec in payment_rows:
        mode = rec.get("mode_of_payment", "")
        opening = float(rec.get("opening_amount", 0) or 0)
        expected = float(rec.get("expected_amount", 0) or 0)
        closing = float(rec.get("closing_amount", 0) or 0)
        diff = closing - expected
        
        data += _separator("-")
        data += CMD_BOLD_ON
        data += _encode(f"{mode}\n")
        data += CMD_BOLD_OFF
        data += _line("  Ochilish:", _format_amount(opening))
        data += _line("  Kutilgan:", _format_amount(expected))
        data += _line("  Yopilish:", _format_amount(closing))
        if diff != 0:
            diff_sign = "+" if diff > 0 else ""
            data += _line("  Farq:", f"{diff_sign}{_format_amount(diff)}")
    
    data += _separator("=")
    
    # Umumiy farq
    total_diff = 0
    for rec in payment_rows:
        expected = float(rec.get("expected_amount", 0) or 0)
        closing = float(rec.get("closing_amount", 0) or 0)
        total_diff += (closing - expected)
    
    if total_diff == 0:
        data += CMD_BOLD_ON
        data += _center_text("FARQ YO'Q")
        data += CMD_BOLD_OFF
    else:
        diff_sign = "+" if total_diff > 0 else ""
        data += CMD_BOLD_ON
        data += _line("UMUMIY FARQ:", f"{diff_sign}{_format_amount(total_diff)}")
        data += CMD_BOLD_OFF
    
    data += _separator("=")
    data += CMD_ALIGN_CENTER
    data += _encode(datetime.now().strftime("%Y-%m-%d  %H:%M:%S") + "\n")
    data += _encode("\n")
    data += CMD_FEED
    data += CMD_CUT
    
    # HTML versiya (A4 printer uchun)
    printer_config = dict(customer_printers[0])
    if _get_named_printer(printer_config) and not _is_thermal_printer(printer_config):
        printer_config["_html"] = _build_closing_shift_html(closing_data, config)
    
    success = _send_data(bytes(data), printer_config)
    if success:
        logger.info("Kassa yopish cheki chop etildi")
    else:
        logger.warning("Kassa yopish cheki chop etilmadi")
    return success


def _build_closing_shift_html(closing_data: dict, config: dict) -> str:
    """Kassa yopish cheki uchun HTML (A4 printer)"""
    company = escape(config.get("company", "POKIZA POS"))
    pos_profile = escape(str(closing_data.get("pos_profile", "")))
    user = escape(str(closing_data.get("user", "")))
    period_start = escape(str(closing_data.get("period_start", ""))[:19])
    period_end = escape(str(closing_data.get("period_end", ""))[:19])
    
    payment_rows_html = ""
    payment_rows = closing_data.get("payment_reconciliation", [])
    total_diff = 0
    
    for rec in payment_rows:
        mode = escape(str(rec.get("mode_of_payment", "")))
        opening = float(rec.get("opening_amount", 0) or 0)
        expected = float(rec.get("expected_amount", 0) or 0)
        closing = float(rec.get("closing_amount", 0) or 0)
        diff = closing - expected
        total_diff += diff
        diff_str = f"+{_format_amount(diff)}" if diff > 0 else _format_amount(diff)
        diff_color = "#16a34a" if diff == 0 else ("#dc2626" if diff < 0 else "#f59e0b")
        
        payment_rows_html += f"""
        <tr>
            <td style="font-weight:600;">{mode}</td>
            <td style="text-align:right;">{_format_amount(opening)}</td>
            <td style="text-align:right;">{_format_amount(expected)}</td>
            <td style="text-align:right;">{_format_amount(closing)}</td>
            <td style="text-align:right;color:{diff_color};font-weight:600;">{diff_str}</td>
        </tr>
        """
    
    total_diff_str = f"+{_format_amount(total_diff)}" if total_diff > 0 else _format_amount(total_diff)
    total_diff_color = "#16a34a" if total_diff == 0 else ("#dc2626" if total_diff < 0 else "#f59e0b")
    
    return f"""
    <html>
    <head>
      <style>
        body {{ font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 11pt; color: #000; padding: 20px; }}
        .header {{ text-align: center; margin-bottom: 20px; }}
        .title {{ font-size: 18pt; font-weight: 700; margin-bottom: 5px; }}
        .subtitle {{ font-size: 12pt; color: #666; }}
        .info {{ margin: 15px 0; }}
        .info-row {{ display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid #eee; }}
        .stats {{ background: #f5f5f5; padding: 15px; border-radius: 8px; margin: 15px 0; }}
        .stats-title {{ font-weight: 600; margin-bottom: 10px; }}
        .stats-row {{ display: flex; justify-content: space-between; padding: 3px 0; }}
        .stats-value {{ font-weight: 700; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th {{ background: #333; color: white; padding: 8px; text-align: left; }}
        td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
        .total-row {{ background: #f0f0f0; font-weight: 700; }}
        .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 10pt; }}
      </style>
    </head>
    <body>
      <div class="header">
        <div class="title">KASSA YOPISH HISOBOTI</div>
        <div class="subtitle">{company}</div>
      </div>
      
      <div class="info">
        <div class="info-row"><span>POS Profil:</span><span>{pos_profile}</span></div>
        <div class="info-row"><span>Kassir:</span><span>{user}</span></div>
        <div class="info-row"><span>Ochilgan:</span><span>{period_start}</span></div>
        <div class="info-row"><span>Yopilgan:</span><span>{period_end}</span></div>
      </div>
      
      <div class="stats">
        <div class="stats-title">SAVDO STATISTIKASI</div>
        <div class="stats-row"><span>Cheklar soni:</span><span class="stats-value">{closing_data.get("total_invoices", 0)}</span></div>
        <div class="stats-row"><span>Jami miqdor:</span><span class="stats-value">{closing_data.get("total_quantity", 0)}</span></div>
        <div class="stats-row"><span>Sof savdo:</span><span class="stats-value">{_format_amount(closing_data.get("net_total", 0))}</span></div>
        <div class="stats-row"><span>Jami savdo:</span><span class="stats-value">{_format_amount(closing_data.get("grand_total", 0))}</span></div>
      </div>
      
      <table>
        <tr>
          <th>To'lov turi</th>
          <th style="text-align:right;">Ochilish</th>
          <th style="text-align:right;">Kutilgan</th>
          <th style="text-align:right;">Yopilish</th>
          <th style="text-align:right;">Farq</th>
        </tr>
        {payment_rows_html}
        <tr class="total-row">
          <td colspan="4">UMUMIY FARQ</td>
          <td style="text-align:right;color:{total_diff_color};">{total_diff_str}</td>
        </tr>
      </table>
      
      <div class="footer">
        {escape(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}
      </div>
    </body>
    </html>
    """
