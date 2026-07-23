import os
import shutil
import sys

# Base directory adjustment for PyInstaller bundles.
#
# MUHIM (Windows): .exe odatda "Program Files" kabi YOZIB BO'LMAYDIGAN
# papkaga o'rnatiladi. config.json, .env, pos_data.db va loglarni exe yoniga
# yozishga urinish PermissionError bilan dasturni ochilmasdan o'ldirardi.
# Shuning uchun frozen rejimda ma'lumotlar %LOCALAPPDATA%\POSAwesome ga
# yoziladi (birinchi ishga tushishda exe yonidagi eski fayllar ko'chiriladi).

_EXE_DIR = None
if getattr(sys, "frozen", False):
    _EXE_DIR = os.path.dirname(sys.executable)
    _data_root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if _data_root:
        BASE_DIR = os.path.join(_data_root, "POSAwesome")
    else:
        BASE_DIR = _EXE_DIR
    try:
        os.makedirs(BASE_DIR, exist_ok=True)
        # Bir martalik migratsiya: eski o'rnatishlarda exe yonida qolgan
        # ma'lumot fayllarini yangi joyga ko'chiramiz.
        if _EXE_DIR and os.path.abspath(_EXE_DIR) != os.path.abspath(BASE_DIR):
            for fname in ("config.json", ".env", "pos_data.db",
                          "pos_data.db-wal", "pos_data.db-shm"):
                src = os.path.join(_EXE_DIR, fname)
                dst = os.path.join(BASE_DIR, fname)
                if os.path.exists(src) and not os.path.exists(dst):
                    try:
                        shutil.copy2(src, dst)
                    except OSError:
                        pass
    except OSError:
        # LOCALAPPDATA yozib bo'lmasa — oxirgi chora sifatida exe yoni.
        BASE_DIR = _EXE_DIR
else:
    # Running in normal Python environment
    # core/paths.py is at project_root/core/paths.py, so we go up two levels
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ensure logs directory exists at project root
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
