"""Avto-yangilanish — GitHub Releases'dan yangi versiyani tekshiradi va o'rnatadi.

Ishlash:
1. `check_for_update()` — GitHub'dagi eng so'nggi release tegini joriy
   __version__ bilan solishtiradi. Yangi bo'lsa {version, url, notes} qaytaradi.
2. `perform_update(url)` — yangi zipni yuklab oladi, vaqtinchalik papkaga ochadi,
   `_update.bat` yozadi va uni ishga tushiradi, so'ng dastur yopilishi kerak.
   .bat dastur yopilishini kutib, fayllarni almashtiradi (DATA fayllarga
   tegmasdan) va dasturni qayta ishga tushiradi.

Faqat "frozen" (.exe) holatda to'liq ishlaydi; dev rejimda o'tkazib yuboriladi.
"""

import os
import sys
import zipfile
import shutil
import subprocess

import requests

from core.version import __version__, GITHUB_REPO
from core.logger import get_logger

logger = get_logger(__name__)

API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

# Almashtirishda saqlanadigan (tegilmaydigan) runtime fayl/papkalar
_KEEP_FILES = [".env", "config.json", "pos_data.db"]
_KEEP_DIRS = ["logs", ".cache"]


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _parse_version(v: str) -> tuple:
    """'v1.2.3' yoki '1.2.3' -> (1, 2, 3). Solishtirish uchun."""
    v = (v or "").strip().lstrip("vV")
    parts = []
    for chunk in v.split("."):
        num = ""
        for ch in chunk:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    return tuple(parts) if parts else (0,)


def check_for_update(timeout: int = 8) -> dict | None:
    """Yangi release bo'lsa {version, url, notes}, aks holda None."""
    try:
        resp = requests.get(
            API_LATEST,
            timeout=timeout,
            headers={"Accept": "application/vnd.github+json"},
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        tag = data.get("tag_name") or ""
        if _parse_version(tag) <= _parse_version(__version__):
            return None  # yangi emas

        # Windows zip asset'ini topamiz
        asset_url = ""
        for asset in data.get("assets", []):
            name = (asset.get("name") or "").lower()
            if name.endswith(".zip") and ("windows" in name or "win" in name):
                asset_url = asset.get("browser_download_url") or ""
                break
        if not asset_url:
            logger.debug("Releaseda Windows zip asset topilmadi")
            return None
        return {"version": tag, "url": asset_url, "notes": data.get("body", "")}
    except Exception as e:
        logger.debug("Yangilanishni tekshirish xatosi: %s", e)
        return None


def perform_update(asset_url: str) -> bool:
    """Yangi versiyani yuklab olib, o'rnatish jarayonini boshlaydi.

    True qaytarsa — chaqiruvchi dasturni darhol yopishi kerak (.bat almashtiradi).
    """
    if not is_frozen():
        logger.info("Dev rejim — auto-update o'tkazib yuborildi")
        return False

    install_dir = os.path.dirname(sys.executable)
    exe_path = sys.executable
    staging = os.path.join(install_dir, "_update_staging")
    zip_path = os.path.join(install_dir, "_update.zip")
    bat_path = os.path.join(install_dir, "_update.bat")

    # 1) Yuklab olish
    logger.info("Yangi versiya yuklanmoqda: %s", asset_url)
    with requests.get(asset_url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)

    # 2) Vaqtinchalik papkaga ochish
    if os.path.exists(staging):
        shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(staging)

    # 3) Almashtiruvchi .bat — dastur yopilishini kutadi, fayllarni ko'chiradi,
    #    DATA fayllarga tegmaydi, so'ng dasturni qayta ishga tushiradi.
    xf = " ".join(_KEEP_FILES)
    xd = " ".join(_KEEP_DIRS)
    bat = f"""@echo off
chcp 65001 >nul
REM Dastur to'liq yopilishini kutamiz
timeout /t 2 /nobreak >nul
REM Yangi fayllarni o'rnatamiz (data fayllar saqlanadi)
robocopy "{staging}" "{install_dir}" /E /IS /IT /R:3 /W:1 /NFL /NDL /NJH /NJS /XF {xf} /XD {xd}
REM Tozalash
del "{zip_path}" >nul 2>&1
rmdir /s /q "{staging}" >nul 2>&1
REM Dasturni qayta ishga tushirish
start "" "{exe_path}"
del "%~f0" >nul 2>&1
"""
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat)

    # 4) .bat ni alohida (detached) ishga tushiramiz — dastur yopilsa ham ishlaydi
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    subprocess.Popen(
        ["cmd", "/c", bat_path],
        cwd=install_dir,
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    logger.info("Yangilash jarayoni boshlandi — dastur yopilmoqda")
    return True
