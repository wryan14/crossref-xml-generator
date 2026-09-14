"""Download the Crossref 5.3.1 deposit schema (and its imports) for local validation.

The files come from Crossref's official schema repository, pinned to a specific
commit so validation results are reproducible:
https://gitlab.com/crossref/schema

Usage:
    python scripts/fetch_crossref_schema.py [destination]

The destination defaults to schemas/crossref/ (git-ignored). Point
CROSSREF_SCHEMA_DIR at a different directory to use it instead.
"""

import sys
import urllib.request
from pathlib import Path

SCHEMA_COMMIT = '0dfa3bde531b43107b5f7e899c1a65047e22155b'
BASE_URL = f'https://gitlab.com/crossref/schema/-/raw/{SCHEMA_COMMIT}/schemas/'

# Every file crossref5.3.1.xsd pulls in through xsd:include / xsd:import.
FILES = [
    'crossref5.3.1.xsd',
    'common5.3.1.xsd',
    'AccessIndicators.xsd',
    'clinicaltrials.xsd',
    'fundref.xsd',
    'relations.xsd',
    'JATS-journalpublishing1-3d2-mathml3.xsd',
    'JATS-journalpublishing1-3d2-mathml3-elements.xsd',
    'standard-modules/module-ali.xsd',
    'standard-modules/xlink.xsd',
    'standard-modules/xml.xsd',
    'standard-modules/mathml3/mathml3.xsd',
    'standard-modules/mathml3/mathml3-common.xsd',
    'standard-modules/mathml3/mathml3-content.xsd',
    'standard-modules/mathml3/mathml3-presentation.xsd',
    'standard-modules/mathml3/mathml3-strict-content.xsd',
]


def fetch(destination: Path) -> None:
    for name in FILES:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(BASE_URL + name, timeout=60) as resp:
            target.write_bytes(resp.read())
        print(f'  {name}')


if __name__ == '__main__':
    default = Path(__file__).resolve().parent.parent / 'schemas' / 'crossref'
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    print(f'Downloading Crossref schema @ {SCHEMA_COMMIT[:10]} to {dest}')
    fetch(dest)
    print('Done.')
