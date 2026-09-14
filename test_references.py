"""Reference handling when include_references is enabled."""

import json

import pytest

from conftest import generate, make_row
from crossref_xml import parse_references, validate_xml


def refs(*items) -> str:
    return json.dumps(list(items))


class TestUnparseableReferences:

    @pytest.mark.parametrize('value', ['[{broken', 'not json', '{"key": "ref1"}', '["just a string"]'])
    def test_rejected_when_references_are_included(self, value):
        with pytest.raises(ValueError, match=r'Row 2 \(10.1234/example.001\): references could not be parsed'):
            generate([make_row(references=value)], include_references=True)

    def test_ignored_when_references_are_excluded(self):
        xml = generate([make_row(references='[{broken')], include_references=False)
        assert '<citation_list' not in xml

    def test_parse_references_stays_lenient(self):
        assert parse_references('["just a string"]') == []
        assert parse_references('   ') == []


class TestCitationKeys:

    def test_missing_keys_are_numbered_by_position(self, crossref_schema):
        value = refs({'key': 'a1', 'unstructured': 'First.'}, {'unstructured': 'Second.'}, {'key': '', 'unstructured': 'Third.'})
        xml = generate([make_row(references=value)], include_references=True)
        assert '<citation key="a1">' in xml
        assert '<citation key="ref2">' in xml
        assert '<citation key="ref3">' in xml
        assert validate_xml(xml, crossref_schema) == []

    def test_overlong_key_is_rejected(self):
        with pytest.raises(ValueError, match='longer than 128'):
            generate([make_row(references=refs({'key': 'k' * 129, 'unstructured': 'x'}))], include_references=True)


def test_blank_references_cell_emits_no_citation_list():
    assert '<citation_list' not in generate([make_row(references='')], include_references=True)


def test_references_output_is_schema_valid(crossref_schema):
    value = refs(
        {'key': 'r1', 'DOI': '10.1000/cited.1', 'doi-asserted-by': 'publisher'},
        {'key': 'r2', 'DOI': '10.1000/cited.2', 'doi-asserted-by': 'crossref', 'unstructured': 'Cited work.'},
    )
    xml = generate([make_row(references=value)], include_references=True)
    assert '<doi>10.1000/cited.1</doi>' in xml
    assert '10.1000/cited.2' not in xml
    assert validate_xml(xml, crossref_schema) == []
