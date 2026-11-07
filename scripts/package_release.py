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
    for file in [setup, manual, root / 'docs/GITHUB_UPDATES.md']:
        z.write(file, file.name)
(dist / 'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in [setup, archive]), encoding='utf8')
print(archive)
