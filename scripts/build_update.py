"""Build a single double-click Windows updater from a tested onedir app bundle."""
import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--app-bundle', type=Path, default=ROOT / 'output/windows/QRPointServer')
    args = parser.parse_args()
    app = args.app_bundle.resolve()
    if not (app / 'QRPointServer.exe').is_file() or not (app / '_internal/frontend/dist/index.html').is_file():
        raise SystemExit('Build and test the complete onedir application first')
    stage = ROOT / 'work/updater-payload'
    stage.mkdir(parents=True, exist_ok=True)
    archive, files = stage / 'payload.zip', {}
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
        members = [app / 'QRPointServer.exe', *sorted((app / '_internal').rglob('*'))]
        for file in members:
            if not file.is_file():
                continue
            if file.is_symlink() or file.suffix.lower() in ('.key', '.pem', '.cer', '.db', '.bak') or file.name in ('config.json', 'secret.key'):
                raise SystemExit('Unexpected runtime data in app bundle: ' + str(file))
            relative = file.relative_to(app).as_posix()
            files[relative] = hashlib.sha256(file.read_bytes()).hexdigest()
            output.write(file, relative)
    manifest = {'version': '2026.11.28', 'files': files,
                'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
    (stage / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    '--distpath', str(ROOT / 'output/updater'), '--workpath', str(ROOT / 'work/pyinstaller-updater'),
                    str(ROOT / 'installer/updater.spec')], cwd=ROOT, check=True)
    exe = ROOT / 'output/updater/PointSystemUpdate.exe'
    checksum = hashlib.sha256(exe.read_bytes()).hexdigest()
    exe.with_suffix('.sha256').write_text(checksum + '  ' + exe.name + '\n', encoding='ascii')
    print(exe)
    print('SHA256:', checksum)


if __name__ == '__main__':
    main()
