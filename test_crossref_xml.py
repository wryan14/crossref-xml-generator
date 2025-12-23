"""Tests for crossref_xml parsing and validation logic."""

import pandas as pd
import pytest

from crossref_xml import (
    parse_contributors,
    parse_references,
    validate_csv,
    _extract_date,
    _extract_authors,
)


class TestParseContributors:
    """Test bracket notation parsing for author metadata."""

    def test_single_author_basic(self):
        result = parse_contributors("Chen, Maria")
        assert len(result) == 1
        assert result[0]['surname'] == 'Chen'
        assert result[0]['given_name'] == 'Maria'
        assert result[0]['orcid'] is None
        assert result[0]['affiliations'] == []

    def test_single_author_with_orcid(self):
        result = parse_contributors("Chen, Maria ORCID[https://orcid.org/0000-0001-2345-6789]")
        assert result[0]['orcid'] == 'https://orcid.org/0000-0001-2345-6789'

    def test_single_author_with_affiliation(self):
        result = parse_contributors("Chen, Maria ORG[Riverside University]")
        assert result[0]['affiliations'] == ['Riverside University']

    def test_single_author_with_ror(self):
        result = parse_contributors("Chen, Maria ROR[https://ror.org/abc123]")
        assert result[0]['rors'] == ['https://ror.org/abc123']

    def test_multiple_affiliations_with_rors(self):
        result = parse_contributors(
            "Larsson, Erik ORG[Northern College; Marine Biology Center] "
            "ROR[https://ror.org/def456; https://ror.org/ghi789]"
        )
        assert result[0]['affiliations'] == ['Northern College', 'Marine Biology Center']
        assert result[0]['rors'] == ['https://ror.org/def456', 'https://ror.org/ghi789']

    def test_multiple_authors(self):
        result = parse_contributors("Chen, Maria; Okonkwo, David; Larsson, Erik")
        assert len(result) == 3
        assert result[0]['surname'] == 'Chen'
        assert result[1]['surname'] == 'Okonkwo'
        assert result[2]['surname'] == 'Larsson'

    def test_semicolon_inside_brackets_preserved(self):
        result = parse_contributors("Author, Test ORG[Dept A; Dept B]")
        assert result[0]['affiliations'] == ['Dept A', 'Dept B']

    def test_empty_string(self):
        assert parse_contributors("") == []
        assert parse_contributors(None) == []


class TestParseReferences:
    """Test reference parsing from JSON and Python literal formats."""

    def test_valid_json_array(self):
        refs_str = '[{"key": "ref1", "DOI": "10.1234/test", "doi-asserted-by": "publisher"}]'
        result = parse_references(refs_str)
        assert len(result) == 1
        assert result[0]['key'] == 'ref1'
        assert result[0]['DOI'] == '10.1234/test'

    def test_python_literal_format(self):
        refs_str = "[{'key': 'ref1', 'unstructured': 'Author (2020). Title.'}]"
        result = parse_references(refs_str)
        assert len(result) == 1
        assert result[0]['unstructured'] == 'Author (2020). Title.'

    def test_malformed_json_returns_empty_list(self):
        assert parse_references('not valid json') == []
        assert parse_references('[{broken}]') == []

    def test_empty_or_none_input(self):
        assert parse_references('') == []
        assert parse_references(None) == []
        assert parse_references('[]') == []


class TestExtractDate:
    """Test Crossref date-parts extraction."""

    def test_full_date(self):
        date_field = {'date-parts': [[2024, 3, 15]]}
        assert _extract_date(date_field) == '2024-03-15'

    def test_year_month_only(self):
        date_field = {'date-parts': [[2024, 3]]}
        assert _extract_date(date_field) == '2024-03'

    def test_year_only(self):
        date_field = {'date-parts': [[2024]]}
        assert _extract_date(date_field) == '2024'

    def test_single_digit_month_and_day_padded(self):
        date_field = {'date-parts': [[2024, 1, 5]]}
        assert _extract_date(date_field) == '2024-01-05'

    def test_empty_or_invalid_input(self):
        assert _extract_date(None) == ''
        assert _extract_date({}) == ''
        assert _extract_date({'date-parts': []}) == ''
        assert _extract_date({'date-parts': [[]]}) == ''


class TestExtractAuthors:
    """Test Crossref API author format to bracket notation conversion."""

    def test_basic_author_with_family_and_given(self):
        author_list = [{'family': 'Chen', 'given': 'Maria'}]
        result = _extract_authors(author_list)
        assert result == 'Chen, Maria'

    def test_author_with_orcid(self):
        author_list = [{
            'family': 'Chen',
            'given': 'Maria',
            'ORCID': 'https://orcid.org/0000-0001-2345-6789'
        }]
        result = _extract_authors(author_list)
        assert 'ORCID[https://orcid.org/0000-0001-2345-6789]' in result

    def test_author_with_affiliation(self):
        author_list = [{
            'family': 'Chen',
            'given': 'Maria',
            'affiliation': [{'name': 'Riverside University'}]
        }]
        result = _extract_authors(author_list)
        assert 'ORG[Riverside University]' in result

    def test_author_with_ror(self):
        author_list = [{
            'family': 'Chen',
            'given': 'Maria',
            'affiliation': [{
                'name': 'Riverside University',
                'id': [{'id-type': 'ROR', 'id': 'https://ror.org/abc123'}]
            }]
        }]
        result = _extract_authors(author_list)
        assert 'ROR[https://ror.org/abc123]' in result

    def test_multiple_authors(self):
        author_list = [
            {'family': 'Chen', 'given': 'Maria'},
            {'family': 'Okonkwo', 'given': 'David'}
        ]
        result = _extract_authors(author_list)
        assert result == 'Chen, Maria; Okonkwo, David'

    def test_empty_or_invalid_input(self):
        assert _extract_authors(None) == ''
        assert _extract_authors([]) == ''
        assert _extract_authors([{'name': 'Some Org'}]) == 'ORG[Some Org]'


class TestValidateCsv:
    """Test CSV validation for required columns."""

    def test_valid_csv_with_all_required_columns(self):
        df = pd.DataFrame({
            'doi': ['10.1234/test'],
            'title': ['Test Title'],
            'publication': ['Test Journal'],
            'authors': ['Chen, Maria']
        })
        errors = validate_csv(df)
        assert errors == []

    def test_missing_required_column(self):
        df = pd.DataFrame({
            'doi': ['10.1234/test'],
            'title': ['Test Title'],
            'authors': ['Chen, Maria']
        })
        errors = validate_csv(df)
        assert len(errors) == 1
        assert 'publication' in errors[0]

    def test_missing_multiple_required_columns(self):
        df = pd.DataFrame({'doi': ['10.1234/test']})
        errors = validate_csv(df)
        assert len(errors) == 1
        assert 'title' in errors[0]
        assert 'publication' in errors[0]
        assert 'authors' in errors[0]

    def test_empty_doi_values(self):
        df = pd.DataFrame({
            'doi': ['10.1234/test', None, ''],
            'title': ['Title 1', 'Title 2', 'Title 3'],
            'publication': ['Pub', 'Pub', 'Pub'],
            'authors': ['Author', 'Author', 'Author']
        })
        errors = validate_csv(df)
        assert any('doi' in error.lower() for error in errors)

    def test_empty_title_values(self):
        df = pd.DataFrame({
            'doi': ['10.1234/test', '10.1234/test2'],
            'title': ['Title 1', None],
            'publication': ['Pub', 'Pub'],
            'authors': ['Author', 'Author']
        })
        errors = validate_csv(df)
        assert any('title' in error.lower() for error in errors)
