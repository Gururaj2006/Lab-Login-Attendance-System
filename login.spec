# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys


python_base = Path(sys.base_prefix)
dll_dir = python_base / "DLLs"
tcl_dir = python_base / "tcl"
hook_dir = str((Path.cwd() / "pyinstaller_hooks").resolve())

extra_datas = [('lab.db', '.')]

for source_name, target_name in (("tcl8.6", "_tcl_data"), ("tk8.6", "_tk_data")):
    folder_path = tcl_dir / source_name
    if folder_path.exists():
        extra_datas.append((str(folder_path), target_name))

extra_binaries = []
for binary_name in ("_tkinter.pyd", "tcl86t.dll", "tk86t.dll"):
    binary_path = dll_dir / binary_name
    if binary_path.exists():
        extra_binaries.append((str(binary_path), "."))


a = Analysis(
    ['login.py'],
    pathex=[],
    binaries=extra_binaries,
    datas=extra_datas,
    hiddenimports=['tkinter', 'tkinter.ttk', '_tkinter'],
    hookspath=[hook_dir],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='login',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
