# PyInstaller spec for the DataCharter desktop app.
# macOS: onedir -> DataCharter.app (BUNDLE). Windows: onefile DataCharter.exe.
# Build (from repo root):  pyinstaller desktop/datacharter.spec \
#     --workpath desktop/build --distpath desktop/dist -y
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

HERE = Path(SPECPATH)  # noqa: F821 - provided by PyInstaller

# The bundle must carry the real version (About box reads Info.plist).
_init = (HERE.parent / "src" / "datacharter" / "__init__.py").read_text()
VERSION = next(
    line.split('"')[1] for line in _init.splitlines() if line.startswith("__version__")
)

# pytz: DuckDB's client imports it DYNAMICALLY for TIMESTAMP WITH TIME ZONE
# results, so PyInstaller's static trace misses it — without the explicit
# entries every tz-aware query fails only in the frozen builds.
datas = collect_data_files("datacharter") + collect_data_files("pytz")
hiddenimports = (
    collect_submodules("uvicorn")
    + [
        "pytz",
        "keyring.backends.macOS",
        "keyring.backends.Windows",
        "keyring.backends.SecretService",
        "keyring.backends.fail",
    ]
)

a = Analysis(
    [str(HERE / "launcher.py")],
    pathex=[],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

icon_icns = HERE / "icon.icns"
icon_ico = HERE / "icon.ico"

if sys.platform == "win32":
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        name="DataCharter",
        console=False,
        icon=str(icon_ico) if icon_ico.exists() else None,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        exclude_binaries=True,
        name="DataCharter",
        console=False,
    )
    coll = COLLECT(exe, a.binaries, a.datas, name="DataCharter")
    app = BUNDLE(
        coll,
        name="DataCharter.app",
        icon=str(icon_icns) if icon_icns.exists() else None,
        bundle_identifier="dev.datacharter.desktop",
        info_plist={
            "CFBundleName": "DataCharter",
            "CFBundleDisplayName": "DataCharter",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
