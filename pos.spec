# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — POKIZA POS (Windows .exe). PyInstaller 6.x uchun.

Build (Windows mashinasida):
    pyinstaller --noconfirm pos.spec
Natija:
    dist\\POKIZA-POS\\POKIZA-POS.exe

Eslatma: config.json, .env, pos_data.db, logs/ — RUNTIME fayllar.
Ular .exe yoniga (dist\\POKIZA-POS\\) avtomatik yoziladi (core/paths.py).
Shu sababli ular bundle ICHIGA qo'shilmaydi (har do'kon/kassada o'ziniki).
"""

import os

# Ixtiyoriy dastur ikonasi — pos-desktop-pyqt/app.ico mavjud bo'lsa ishlatiladi.
ICON = "app.ico" if os.path.exists("app.ico") else None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # Windows printer (pywin32)
        "win32print",
        "win32timezone",
        "pywintypes",
        # Serial skanerlar
        "serial",
        "serial.tools.list_ports",
        # ORM / config
        "peewee",
        "dotenv",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtMultimedia",
        "PyQt6.QtBluetooth",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="POKIZA-POS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI ilova — konsol oynasi chiqmaydi
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="POKIZA-POS",
)
