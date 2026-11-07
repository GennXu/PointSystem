"""Preserve an optional runtime-provided certificate policy file in frozen builds."""
from pathlib import Path
from PyInstaller.utils.hooks import get_module_file_attribute

policy = Path(get_module_file_attribute('ssl')).with_name('codex-rejected-cas.pem')
datas = [(str(policy), '.')] if policy.is_file() else []
