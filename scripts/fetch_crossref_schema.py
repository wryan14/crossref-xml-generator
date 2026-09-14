"""Download and verify the Crossref 5.3.1 deposit schema for local validation.

Source: Crossref's official schema repository, https://gitlab.com/crossref/schema,
pinned to SCHEMA_COMMIT. Every file is checked against a pinned SHA-256
checksum, so a changed or corrupted download is refused rather than used.

The files are not committed to this repository because Crossref's schema
repository does not state a license.

Usage:
    python scripts/fetch_crossref_schema.py [destination]           # download + verify
    python scripts/fetch_crossref_schema.py --verify [destination]  # verify only

The destination defaults to schemas/crossref/ (git-ignored). Point
CROSSREF_SCHEMA_DIR at a different directory to use it instead.
"""

import hashlib
import sys
import urllib.request
from pathlib import Path

SCHEMA_REPOSITORY = 'https://gitlab.com/crossref/schema'
SCHEMA_VERSION = '5.3.1'
SCHEMA_COMMIT = '0dfa3bde531b43107b5f7e899c1a65047e22155b'
BASE_URL = f'{SCHEMA_REPOSITORY}/-/raw/{SCHEMA_COMMIT}/schemas/'
DEFAULT_DESTINATION = Path(__file__).resolve().parent.parent / 'schemas' / 'crossref'

# Every file crossref5.3.1.xsd pulls in through xsd:include / xsd:import,
# with its SHA-256 at SCHEMA_COMMIT.
FILES = {
    'crossref5.3.1.xsd': '0465eb615d97708f031854db62e276c947046bace4e4a0237924e1933d62f4fa',
    'common5.3.1.xsd': '92e60aa3fcf5632fa4db21cc45c2ebd7ea7a3194cdb2daaa23d81c7592cc3af0',
    'AccessIndicators.xsd': '6c07de1d6ae77da26f72d3c251eea1a35acd253df12439f6be94553a4f1ff300',
    'clinicaltrials.xsd': 'cc540947ab933a3df373d7a711bccffb5778185b245da73ff136c73ec22cb899',
    'fundref.xsd': 'bcd58527b2c43639201deac4fd5e6664a7ccb3a0e48b227327b753d72acd0905',
    'relations.xsd': '8845e28b8d77d20d8742ac54d15fc6cfe3cece13e38e5a80689d79bf7c5e01d4',
    'JATS-journalpublishing1-3d2-mathml3.xsd': '8283b67249b5d9f176fa4185642fc569305d8b804add8091c1bfc44aeafc75f6',
    'JATS-journalpublishing1-3d2-mathml3-elements.xsd': '9798c93059b8c71d3d6dabc7d8673712a21dafed0f4dfe8cf5805336951a6616',
    'standard-modules/module-ali.xsd': '73fba5884602b101d198a3c0bf6c53491b08ecb54940f1109c46a12f1fdd5234',
    'standard-modules/xlink.xsd': '84b3ca0fba2b6226af5936c13ecd9701a2c7d44c9397ae0c35e4889f98d80f40',
    'standard-modules/xml.xsd': '61960fb3131e38022caad5360e2f33a3382578ab3c80cd58bd74320ede61b20c',
    'standard-modules/mathml3/mathml3.xsd': 'f7e03c16ac50574e724802cc67e42300b404d7976306d56a38091115630e2d9e',
    'standard-modules/mathml3/mathml3-common.xsd': '3f0ba889b16dbb2ec39eeeb799e777227c51d3129697316610f2b1d185ad1db6',
    'standard-modules/mathml3/mathml3-content.xsd': '7f2c679f8ac223cd59835af62dfb063b18f5b8ec2919e0a1841f8f0225455a3d',
    'standard-modules/mathml3/mathml3-presentation.xsd': '4919906381bff160d08186b28e0a355cd2bb3cea1ab2d4139580f635fda545f6',
    'standard-modules/mathml3/mathml3-strict-content.xsd': 'e088d44535a774c343dea51b8cb5f2057b79af04b2adfebb95ea438728f76765',
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify(destination: Path) -> list[str]:
    """Return a problem for each schema file that is missing or does not match its checksum."""
    problems = []
    for name, expected in FILES.items():
        path = destination / name
        if not path.is_file():
            problems.append(f'missing: {name}')
        elif sha256(path.read_bytes()) != expected:
            problems.append(f'checksum mismatch: {name}')
    return problems


def fetch(destination: Path) -> None:
    """Download every schema file, refusing any whose checksum does not match."""
    for name, expected in FILES.items():
        with urllib.request.urlopen(BASE_URL + name, timeout=60) as resp:
            data = resp.read()
        if sha256(data) != expected:
            raise SystemExit(f'Checksum mismatch for {name}; refusing to write it.')
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        print(f'  {name}')
    (destination / 'SOURCE.txt').write_text(
        f'Crossref deposit schema {SCHEMA_VERSION}\n'
        f'Repository: {SCHEMA_REPOSITORY}\n'
        f'Commit: {SCHEMA_COMMIT}\n'
        'Fetched and verified by scripts/fetch_crossref_schema.py\n'
    )


def main(argv: list[str]) -> int:
    verify_only = '--verify' in argv
    args = [a for a in argv if a != '--verify']
    dest = Path(args[0]) if args else DEFAULT_DESTINATION

    if not verify_only:
        print(f'Downloading Crossref schema {SCHEMA_VERSION} @ {SCHEMA_COMMIT[:10]} to {dest}')
        fetch(dest)

    problems = verify(dest)
    if problems:
        print(f'Schema at {dest} failed verification:')
        for problem in problems:
            print(f'  {problem}')
        return 1
    print(f'Verified {len(FILES)} files against pinned checksums (commit {SCHEMA_COMMIT[:10]}).')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
