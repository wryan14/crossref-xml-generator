"""Tests for record validation: required fields, identifiers, dates, and URLs."""

import io

import pandas as pd
import pytest

from conftest import generate, make_row
from crossref_xml import generate_xml, validate_csv, validate_xml


def errors_for(**overrides) -> list:
    return validate_csv(pd.DataFrame([make_row(**overrides)]))


def test_minimal_row_is_valid():
    assert errors_for() == []


class TestRequiredFields:

    @pytest.mark.parametrize('field', ['doi', 'title', 'publication', 'publication_date', 'resource_url'])
    @pytest.mark.parametrize('blank', ['', '   ', '\t', None])
    def test_blank_required_value_is_rejected(self, field, blank):
        errors = errors_for(**{field: blank})
        assert any(f'{field} is empty' in e for e in errors), errors

    @pytest.mark.parametrize('field', ['publication_date', 'resource_url'])
    def test_missing_required_column_is_reported(self, field):
        row = make_row()
        del row[field]
        errors = validate_csv(pd.DataFrame([row]))
        assert errors == [f'Missing required columns: {field}']

    def test_empty_title_row_is_rejected_not_silently_dropped(self):
        with pytest.raises(ValueError, match='title is empty'):
            generate([make_row(), make_row(doi='10.1234/example.002', title='  ')])

    def test_empty_doi_row_is_rejected_not_silently_dropped(self):
        with pytest.raises(ValueError, match='doi is empty'):
            generate([make_row(), make_row(doi='')])

    def test_messages_use_spreadsheet_row_numbers(self):
        df = pd.DataFrame([make_row(), make_row(doi='10.1234/example.002', title='')])
        assert validate_csv(df) == ['Row 3 (10.1234/example.002): title is empty']

    def test_long_error_lists_are_capped(self):
        rows = [make_row(doi=f'10.1234/example.{i}', title='') for i in range(40)]
        with pytest.raises(ValueError, match='and 15 more'):
            generate(rows)


class TestDoi:

    @pytest.mark.parametrize('doi', ['10.1234/abc', '10.123456789/a(b)c-1', '10.1234/A.B/C'])
    def test_valid_dois(self, doi):
        assert errors_for(doi=doi) == []

    @pytest.mark.parametrize('doi', [
        'https://doi.org/10.1234/abc', 'doi:10.1234/abc', '10.123/abc',
        '10.1234/', '10.1234', '11.1234/abc',
    ])
    def test_invalid_dois(self, doi):
        assert any('must be a bare DOI' in e for e in errors_for(doi=doi))

    def test_duplicate_dois_are_rejected_case_insensitively(self):
        df = pd.DataFrame([make_row(doi='10.1234/ABC'), make_row(doi='10.1234/abc')])
        assert validate_csv(df) == ['Row 3 (10.1234/abc): duplicate DOI (first used in row 2)']


class TestPublicationDate:

    @pytest.mark.parametrize('value', ['2024', '2024-03', '2024-3', '2024-03-15', '2024-02-29', '1400', '2200'])
    def test_valid_dates(self, value):
        assert errors_for(publication_date=value) == []

    @pytest.mark.parametrize('value', [
        '2024-13', '2024-00', '2023-02-29', '2024-04-31', '24', 'March 2024',
        '2024/03/15', '15-03-2024', '1399', '2201',
    ])
    def test_invalid_dates(self, value):
        assert any('publication_date' in e for e in errors_for(publication_date=value))

    def test_single_digit_month_is_zero_padded(self):
        xml = generate([make_row(publication_date='2024-3-5')])
        assert '<month>03</month>' in xml
        assert '<day>05</day>' in xml

    def test_year_only_column_read_as_float_emits_integer_year(self, crossref_schema):
        # A blank date elsewhere in the column makes pandas parse years as floats
        csv = (
            'doi,title,publication,authors,publication_date,resource_url,pages\n'
            '10.1234/a,T,J,"Chen, M",2024,https://example.org/a,12\n'
            '10.1234/b,T,J,"Chen, M",2023,https://example.org/b,\n'
        )
        data = pd.read_csv(io.StringIO(csv))
        assert data['publication_date'].dtype.kind in 'if'
        xml = generate_xml(data, 'Lib', 'lib@example.org', 'Lib')
        assert '<year>2024</year>' in xml
        assert '<first_page>12</first_page>' in xml
        assert '.0<' not in xml
        assert validate_xml(xml, crossref_schema) == []


class TestUrls:

    @pytest.mark.parametrize('url', ['https://example.org/a', 'http://example.org', 'HTTPS://EXAMPLE.ORG/a?b=1'])
    def test_valid_resource_urls(self, url):
        assert errors_for(resource_url=url) == []

    @pytest.mark.parametrize('url', [
        'example.org/a', 'www.example.org', 'https://', 'javascript:alert(1)',
        'https://exa mple.org', '/articles/1',
    ])
    def test_invalid_resource_urls(self, url):
        assert any('resource_url' in e for e in errors_for(resource_url=url))

    def test_invalid_pdf_url_is_rejected(self):
        assert any('pdf_url' in e for e in errors_for(pdf_url='files/001.pdf'))

    def test_blank_pdf_url_is_allowed(self):
        assert errors_for(pdf_url='  ') == []

    def test_invalid_license_url_is_rejected(self):
        with pytest.raises(ValueError, match='license_url'):
            generate([make_row()], license_url='CC BY 4.0')

    def test_blank_license_url_means_no_license(self):
        assert 'license_ref' not in generate([make_row()], license_url='')


class TestIssn:

    @pytest.mark.parametrize('value, expected', [
        ('1234-5678', '1234-5678'), ('12345678', '1234-5678'), ('1234-567x', '1234-567X'),
    ])
    def test_valid_issns_are_normalized(self, value, expected):
        assert f'<issn media_type="print">{expected}</issn>' in generate([make_row(issn_print=value)])

    @pytest.mark.parametrize('value', ['1234-567', 'ABCD-EFGH', '1234-56789'])
    def test_invalid_issns_are_rejected_not_silently_dropped(self, value):
        assert any('issn_electronic' in e for e in errors_for(issn_electronic=value))


class TestDepositorFields:

    @pytest.mark.parametrize('field', ['depositor_name', 'depositor_email', 'registrant'])
    def test_blank_depositor_field_is_rejected(self, field):
        kwargs = {'depositor_name': 'Lib', 'depositor_email': 'lib@example.org', 'registrant': 'Lib'}
        kwargs[field] = '  '
        with pytest.raises(ValueError, match=field):
            generate_xml(pd.DataFrame([make_row()]), **kwargs)


def test_unencodable_characters_report_the_row():
    with pytest.raises(ValueError, match='Row 3'):
        generate([make_row(), make_row(doi='10.1234/example.002', abstract='bad \x0b char')])


def test_edge_values_produce_schema_valid_xml(crossref_schema):
    rows = [
        make_row(doi='10.1234/a', publication_date='2024', pages='e1234'),
        make_row(doi='10.1234/b', publication_date='2024-3', issn_print='1234567x'),
        make_row(doi='10.1234/c', publication_date='2024-02-29', pages='12-', title='  Padded  '),
    ]
    assert validate_xml(generate(rows), crossref_schema) == []
