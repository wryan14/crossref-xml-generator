"""Tests for the Flask routes."""

import io

import pandas as pd
import pytest

from app import app
from conftest import make_row
from crossref_xml import MAX_RECORDS_PER_FILE


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def post_csv(client, rows: list[dict], **form):
    csv_bytes = pd.DataFrame(rows).to_csv(index=False).encode('utf-8')
    data = {
        'depositor_name': 'Test Library',
        'depositor_email': 'test@example.org',
        'registrant': 'Test Library',
        'csv_file': (io.BytesIO(csv_bytes), 'records.csv'),
    }
    data.update(form)
    return client.post('/convert', data=data, content_type='multipart/form-data').get_json()


class TestLicenseLabel:
    """license_ref applies_to="vor" licenses the article content, not the metadata."""

    def test_license_is_emitted_for_version_of_record(self, client):
        result = post_csv(client, [make_row()], license_url='https://creativecommons.org/licenses/by/4.0/')
        assert 'applies_to="vor">https://creativecommons.org/licenses/by/4.0/</ai:license_ref>' in result['xml']

    def test_ui_does_not_describe_it_as_a_metadata_license(self, client):
        page = client.get('/').get_data(as_text=True)
        assert 'Metadata License' not in page
        assert 'Applies to metadata only' not in page
        assert 'Article Content License' in page
        assert 'version of record' in page


class TestConvertRecordCounts:

    def test_reports_emitted_and_requested_counts(self, client):
        rows = [make_row(doi=f'10.1234/example.{i}') for i in range(3)]
        result = post_csv(client, rows)
        assert result['success'] is True
        assert result['message'].startswith('Generated XML for 3 of 3 records')

    def test_oversized_csv_is_rejected_not_truncated(self, client):
        rows = [make_row(doi=f'10.1234/example.{i}') for i in range(MAX_RECORDS_PER_FILE + 1)]
        result = post_csv(client, rows)
        assert result['success'] is False
        assert f'{MAX_RECORDS_PER_FILE + 1} records' in result['message']
        assert 'xml' not in result
