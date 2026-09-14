"""Shared pytest fixtures."""

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from crossref_xml import generate_xml, load_schema, schema_dir


def load_fetch_script():
    """Import scripts/fetch_crossref_schema.py (scripts/ is not a package)."""
    path = Path(__file__).resolve().parent / 'scripts' / 'fetch_crossref_schema.py'
    spec = importlib.util.spec_from_file_location('fetch_crossref_schema', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='session')
def crossref_schema():
    """Crossref 5.3.1 XSD, verified against pinned checksums.

    Schema-validation tests fail (rather than skip) when the schema is missing
    or altered, so a green run always means output was checked against it.
    """
    directory = schema_dir()
    problems = load_fetch_script().verify(directory)
    if problems:
        pytest.fail(
            f"Crossref schema at {directory} is unavailable or unverified "
            f"({'; '.join(problems[:3])}). "
            "Run: python scripts/fetch_crossref_schema.py",
            pytrace=False,
        )
    return load_schema(directory)


def make_row(**overrides) -> dict:
    """A minimal record that satisfies every requirement for a journal article."""
    row = {
        'doi': '10.1234/example.001',
        'title': 'Example Title',
        'publication': 'Example Journal',
        'authors': 'Chen, Maria',
        'publication_date': '2024-03-15',
        'resource_url': 'https://example.org/articles/001',
    }
    row.update(overrides)
    return row


def generate(rows: list[dict], **kwargs) -> str:
    """Run generate_xml over dict rows with placeholder depositor details."""
    return generate_xml(
        pd.DataFrame(rows),
        depositor_name='Test Library',
        depositor_email='test@example.org',
        registrant='Test Library',
        **kwargs,
    )
