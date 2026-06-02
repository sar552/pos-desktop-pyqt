# POSAwesome — Windows uchun build qilish

Bu hujjat PyQt6 POS dasturini **Windows .exe** ga aylantirish va tarqatish bo'yicha qo'llanma.

> **Muhim:** PyInstaller cross-compile qilmaydi. Windows `.exe` ni **albatta Windows
> kompyuterida** build qilish kerak (Linux'da build qilsangiz Linux dasturi chiqadi).

---

## 1. Talablar (build kompyuteri — Windows)

- Windows 10/11
- **Python 3.10+** (python.org dan, o'rnatishda "Add Python to PATH" ni belgilang)
- Internet (kutubxonalar yuklash uchun)

## 2. Build qilish

Loyiha papkasini (`pos-desktop-pyqt`) Windows kompyuteriga ko'chiring, so'ng:

**Oson yo'l** — `build_windows.bat` faylini ikki marta bosing. U o'zi:
1. `venv` yaratadi
2. `requirements.txt` dagi kutubxonalarni o'rnatadi (PyQt6, pywin32, peewee, ...)
3. PyInstaller bilan build qiladi

**Qo'lda** (PowerShell/CMD):
```bat
py -3 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pyinstaller --noconfirm pos.spec
```

**Natija:** `dist\POSAwesome\POSAwesome.exe`

## 3. Tarqatish (kassaga o'rnatish)

- Butun **`dist\POSAwesome\`** papkasini kassa kompyuteriga ko'chiring
  (faqat .exe emas — yonidagi DLL/kutubxonalar ham kerak).
- `POSAwesome.exe` ni ishga tushiring.
- Yorliq (shortcut) yasab, ish stoliga / autostart'ga qo'ying.

## 4. Birinchi ishga tushirish

1. Login oynasi chiqadi → **Server manzili** (ERPNext URL), **Login**, **Parol** kiriting.
2. Til tanlang (🌐 — O'zbekcha / Русский / English).
3. Kirgach dastur serverdan mahsulot, mijoz, narx, POS Profile ma'lumotlarini sinxronlaydi.

## 5. Runtime fayllar (qayerda saqlanadi)

Dastur quyidagi fayllarni **`.exe` yonidagi papkada** yaratadi/saqlaydi
(`core/paths.py` "frozen" rejimni shunday boshqaradi):

| Fayl | Vazifasi |
|------|----------|
| `.env` | Server manzili, login/parol (kirgandan keyin) |
| `config.json` | Sozlamalar: til, mavzu, to'lov turlari, printerlar |
| `pos_data.db` | **Offline baza** (SQLite) — mahsulot, mijoz, kutilayotgan cheklar |
| `logs\` | Log fayllar (xatolarni tekshirish uchun) |
| `.cache\branding\` | Kompaniya logosi (yuklab olingan) |

> Bu fayllar har kassada **o'ziniki** bo'ladi — bundle ichiga kirmaydi.
> Yangilanish (yangi versiya) chiqsa, `dist\POSAwesome\` ni almashtiring,
> lekin yuqoridagi fayllarni **saqlab qoling** (sozlama va offline baza yo'qolmasin).

## 6. Offline / Online hamohanglik

Dasturda allaqachon ishlaydi (qo'shimcha sozlash shart emas):

- **Online:** har bir chek darhol serverga (ERPNext) yuboriladi.
- **Internet uzilsa:** chek lokal bazaga (`pos_data.db` → `PendingInvoice`) saqlanadi,
  dastur ishlashda davom etadi.
- **Internet tiklanganda:** `OfflineSyncWorker` kutilayotgan cheklarni avtomatik
  serverga yuboradi. "Offline: N" tugmasidan navbatni ko'rish mumkin.
- **Sinxronlash** tugmasi — mahsulot/mijoz/narxlarni serverdan qayta yuklaydi.
- Server bilan aloqa `ConnectivityCheckWorker` orqali doimiy tekshiriladi
  (ONLINE/OFFLINE holati yuqorida ko'rinadi).

## 7. Printer (Windows)

- Windows'da chek **native printer** orqali chop etiladi (`win32print`, `pywin32`).
- Printerni **Printer** sozlamalaridan tanlang (mijoz cheki + production unitlar).
- Termal yoki oddiy A4 printer ishlaydi.

## 8. Muammolar va yechimlar

- **Antivirus .exe ni bloklaydi:** PyInstaller build'lari ba'zan "false positive"
  beradi. Istisno (exception) qo'shing yoki imzolangan (code-signed) build qiling.
- **Dastur ochilmaydi / darrov yopiladi:** xatoni ko'rish uchun `pos.spec` da
  `console=False` ni vaqtincha `console=True` qiling va qayta build qiling —
  konsol oynasida xato chiqadi. Yoki `logs\` ichidagi log faylga qarang.
- **Printer topilmadi:** printer Windows'da o'rnatilganmi va nomi to'g'rimi tekshiring.
- **Dastur ikonasi:** `pos-desktop-pyqt\app.ico` faylini qo'ysangiz, build avtomatik
  o'shani ishlatadi.

## 9. (Ixtiyoriy) Bitta faylli (.exe) build

Hozirgi spec **papkali** (onedir) build qiladi — POS uchun tavsiya etiladi
(tez ochiladi, antivirus kamroq shubhalanadi). Agar **bitta .exe** kerak bo'lsa,
`pos.spec` da `EXE(...)` ga `exclude_binaries=True` o'rniga barcha binaries qo'shib,
`COLLECT` ni olib tashlash kerak — lekin onedir afzal.
