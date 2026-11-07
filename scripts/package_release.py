"""Package public release files only; never include runtime data."""
import hashlib
import re
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
dist = root / 'dist'
version = re.search(r'^AppVersion=(.+)$', (root / 'installer/setup.iss').read_text(encoding='utf8'), re.M).group(1).strip()
setup = dist / 'Setup.exe'
if not setup.is_file():
    raise SystemExit('Build Setup.exe first')
manual = root / '操作手冊.pdf'
if not manual.is_file():
    raise SystemExit('Missing operation manual')
archive = dist / f'QRPointSystem-{version}.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
    release_files = [(setup, 'Setup.exe'), (manual, '操作手冊.pdf'), (root / 'docs/QUICK_START.txt', '開始使用.txt'), (root / 'docs/GITHUB_UPDATES.md', 'GITHUB_UPDATES.md'), (root / 'docs/RELEASE_1.1.0.md', '版本更新說明.md')]
    checksums = ''
    for file, name in release_files:
        z.write(file, name)
        checksums += hashlib.sha256(file.read_bytes()).hexdigest() + '  ' + name + '\n'
    z.writestr('SHA256SUMS.txt', checksums)
(dist / 'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in [setup, archive]), encoding='utf8')
print(archive)
