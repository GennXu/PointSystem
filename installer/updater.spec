# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH).parent
payload = root / 'work' / 'updater-payload'
a = Analysis(
    [str(root / 'updater' / 'gui.py')], pathex=[str(root)],
    binaries=[], datas=[(str(payload / 'payload.zip'), '.'), (str(payload / 'manifest.json'), '.')],
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [], name='PointSystemUpdate',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False, uac_admin=True,
)
