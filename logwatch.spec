# -*- mode: python ; coding: utf-8 -*-
# PyInstaller-Spezifikation für LogWatch.
# Erzeugt eine einzelne .exe (onefile), ohne Konsolenfenster (GUI-App).
#
# Bauen (auf Windows):  pyinstaller logwatch.spec --noconfirm
# Ergebnis:             dist\LogWatch.exe

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Nicht benötigte Qt-Module ausschließen, um die .exe klein zu halten.
        'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.Qt3DCore',
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
        'PySide6.QtMultimedia', 'PySide6.QtCharts', 'PySide6.QtNetwork',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='LogWatch',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # GUI-App, kein Konsolenfenster
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='logwatch.ico',  # optional: eigenes Icon hinterlegen
)
