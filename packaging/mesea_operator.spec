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

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files("sv_ttk")
hiddenimports = collect_submodules("keyring.backends") + [
    "keyring.backends.Windows",
    "keyring.backends.macOS",
    "keyring.backends.SecretService",
]

a = Analysis(
    ["mesea_operator/__main__.py"],
    pathex=["."],
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
