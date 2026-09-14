"""Download and pagination behavior, with the Crossref API mocked."""

import pandas as pd
import pytest
import requests

import app as app_module
import crossref_xml
from crossref_xml import download_prefix, generate_xml, validate_xml


def api_item(n: int, **overrides) -> dict:
    item = {
        'DOI': f'10.1234/item.{n}',
        'type': 'journal-article',
        'title': [f'Title {n}'],
        'container-title': ['Journal of Examples'],
        'author': [{'family': 'Chen', 'given': 'Maria'}],
        'issued': {'date-parts': [[2024, 3, 15]]},
        'resource': {'primary': {'URL': f'https://example.org/{n}'}},
    }
    item.update(overrides)
    return item


class FakeResponse:
    def __init__(self, payload=None, status=200):
        self.payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f'{self.status_code} Client Error', response=self)

    def json(self):
        return self.payload


def page(items, total, next_cursor=None) -> FakeResponse:
    message = {'items': items, 'total-results': total}
    if next_cursor:
        message['next-cursor'] = next_cursor
    return FakeResponse({'status': 'ok', 'message': message})


@pytest.fixture
def api(monkeypatch):
    """Queue fake responses and record each request's URL and params."""
    monkeypatch.setattr(crossref_xml, 'CROSSREF_ROWS_PER_PAGE', 2)
    state = {'responses': [], 'calls': []}

    def fake_get(url, params=None, headers=None, timeout=None):
        state['calls'].append((url, dict(params or {})))
        response = state['responses'].pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(crossref_xml.requests, 'get', fake_get)
    return state


class TestFullDownload:

    def test_follows_cursor_until_all_pages_fetched(self, api):
        api['responses'] = [
            page([api_item(1), api_item(2)], total=5, next_cursor='c1'),
            page([api_item(3), api_item(4)], total=5, next_cursor='c2'),
            page([api_item(5)], total=5, next_cursor='c3'),
        ]
        df = download_prefix('10.1234')
        assert list(df['doi']) == [f'10.1234/item.{n}' for n in range(1, 6)]
        assert [params['cursor'] for _, params in api['calls']] == ['*', 'c1', 'c2']
        assert all(url.endswith('/prefixes/10.1234/works') for url, _ in api['calls'])

    def test_invalid_response_mid_download_raises_instead_of_returning_partial_data(self, api):
        api['responses'] = [
            page([api_item(1), api_item(2)], total=4, next_cursor='c1'),
            FakeResponse({'status': 'error', 'message': 'backend unavailable'}),
        ]
        with pytest.raises(ValueError, match='incomplete'):
            download_prefix('10.1234')

    def test_http_error_mid_download_propagates(self, api):
        api['responses'] = [
            page([api_item(1), api_item(2)], total=4, next_cursor='c1'),
            FakeResponse(status=503),
        ]
        with pytest.raises(requests.HTTPError):
            download_prefix('10.1234')

    def test_timeout_propagates(self, api):
        api['responses'] = [requests.Timeout('timed out')]
        with pytest.raises(requests.Timeout):
            download_prefix('10.1234')

    def test_invalid_first_response_raises(self, api):
        api['responses'] = [FakeResponse({'status': 'ok'})]
        with pytest.raises(ValueError, match='Invalid Crossref API response'):
            download_prefix('10.1234')

    def test_empty_prefix_raises(self, api):
        api['responses'] = [page([], total=0)]
        with pytest.raises(ValueError, match='No records found'):
            download_prefix('10.1234')

    def test_fewer_records_than_reported_is_logged(self, api, caplog):
        api['responses'] = [
            page([api_item(1), api_item(2)], total=4, next_cursor='c1'),
            page([], total=4),
        ]
        df = download_prefix('10.1234')
        assert len(df) == 2
        assert 'expected 4' in caplog.text


class TestLimitedDownload:

    def test_uses_sorted_offset_pages_and_trims_to_limit(self, api):
        api['responses'] = [
            page([api_item(1), api_item(2)], total=10),
            page([api_item(3), api_item(4)], total=10),
        ]
        df = download_prefix('10.1234', limit=3, sort_by='updated')
        assert len(df) == 3
        assert [params['offset'] for _, params in api['calls']] == [0, 2]
        assert api['calls'][0][1]['filter'] == 'prefix:10.1234'
        assert api['calls'][0][1]['sort'] == 'updated'

    def test_limit_beyond_offset_window_is_rejected_before_any_request(self, api):
        with pytest.raises(ValueError, match='10,000'):
            download_prefix('10.1234', limit=10_001)
        assert api['calls'] == []

    @pytest.mark.parametrize('limit', [0, -1])
    def test_non_positive_limit_is_rejected(self, api, limit):
        with pytest.raises(ValueError, match='greater than 0'):
            download_prefix('10.1234', limit=limit)


def test_downloaded_records_convert_to_schema_valid_xml(api, crossref_schema):
    api['responses'] = [page([
        api_item(1, author=[{'name': 'Study Group'}, {'family': 'Plato'}]),
        api_item(2, author=[{'family': 'Chen', 'given': 'Maria', 'ORCID': 'http://orcid.org/0000-0002-1825-0097',
                             'affiliation': [{'name': 'Dept A'},
                                             {'id': [{'id': 'https://ror.org/03wmf1y16', 'id-type': 'ROR'}]}]}],
                 volume='12', issue='3', page='101-110',
                 **{'issn-type': [{'type': 'electronic', 'value': '1234-5678'}]}),
    ], total=2)]
    df = download_prefix('10.1234')
    csv_round_trip = pd.read_csv(pd.io.common.StringIO(df.to_csv(index=False)))
    xml = generate_xml(csv_round_trip, 'Lib', 'lib@example.org', 'Lib')
    assert xml.count('<journal_article ') == 2
    assert validate_xml(xml, crossref_schema) == []


class TestDownloadRoute:

    @pytest.fixture
    def client(self):
        app_module.app.config['TESTING'] = True
        return app_module.app.test_client()

    def test_http_error_reports_status(self, client, monkeypatch):
        def fail(*args, **kwargs):
            raise requests.HTTPError('429 Too Many Requests', response=FakeResponse(status=429))
        monkeypatch.setattr(app_module, 'download_prefix', fail)
        result = client.get('/download?prefix=10.1234').get_json()
        assert result['success'] is False
        assert '429' in result['message']

    def test_value_error_message_is_shown(self, client, monkeypatch):
        def fail(*args, **kwargs):
            raise ValueError('Download incomplete: example')
        monkeypatch.setattr(app_module, 'download_prefix', fail)
        result = client.get('/download?prefix=10.1234').get_json()
        assert result == {'success': False, 'message': 'Download incomplete: example'}

    @pytest.mark.parametrize('query, message', [
        ('prefix=', 'DOI prefix is required'),
        ('prefix=11.1234', 'must start with 10.'),
        ('prefix=10.1234&download_mode=custom&custom_limit=abc', 'must be a number'),
        ('prefix=10.1234&download_mode=custom&custom_limit=10001', 'cannot exceed 10,000'),
    ])
    def test_invalid_parameters(self, client, query, message):
        result = client.get(f'/download?{query}').get_json()
        assert result['success'] is False
        assert message in result['message']
