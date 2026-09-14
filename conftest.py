"""Shared pytest fixtures."""

import pandas as pd
import pytest

from crossref_xml import generate_xml, load_schema


@pytest.fixture(scope='session')
def crossref_schema():
    """Crossref 5.3.1 XSD; tests using it skip when the schema is not downloaded."""
    try:
        return load_schema()
    except FileNotFoundError as e:
        pytest.skip(str(e))


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
