"""Reject a release tag that does not match the installer version."""
import os
import re
from pathlib import Path

root = Path(__file__).resolve().parent.parent
version = re.search(r"^AppVersion=(.+)$", (root / 'installer/setup.iss').read_text(encoding='utf8'), re.M).group(1).strip()
tag = os.environ['RELEASE_TAG']
if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', tag) or tag != 'v' + version:
    raise SystemExit(f'Tag {tag!r} must equal installer version v{version}')
print(f'Release version verified: {tag}')
