# PyInstaller spec — one-file Mesea Operator build.
#
# Run from the repo root:  pyinstaller packaging/mesea_operator.spec --noconfirm
# All paths are repo-root-relative (PyInstaller resolves Analysis paths from CWD).
#
# Bundles the sv-ttk Tcl theme data (its .tcl files are package data and must be
# collected explicitly) and keyring's dynamically-imported platform backends
# (hidden imports), which PyInstaller's static analysis misses.
#
# Output: dist/mesea-operator(.exe)

import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# PyInstaller resolves Analysis paths relative to the spec's directory, not the
# CWD — so anchor everything to the repo root via SPECPATH.
ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))

datas = collect_data_files("sv_ttk")
hiddenimports = collect_submodules("keyring.backends") + [
    "keyring.backends.Windows",
    "keyring.backends.macOS",
    "keyring.backends.SecretService",
]

a = Analysis(
    [os.path.join(ROOT, "app.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="mesea-operator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,  # GUI app — no console window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# On macOS, also emit a proper .app bundle so it can be packaged into a .dmg
# and double-clicked from Finder (the bare unix binary can't).
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="Mesea Operator.app",
        icon=None,
        bundle_identifier="ro.mesea.operator",
        info_plist={"CFBundleShortVersionString": "0.3.0", "NSHighResolutionCapable": True},
    )
