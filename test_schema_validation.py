"""XSD-backed tests: generated XML must validate against the Crossref 5.3.1 schema."""

import shutil
from pathlib import Path

import pandas as pd
import pytest

from conftest import generate, load_fetch_script, make_row
from crossref_xml import generate_xml, load_schema, schema_dir, validate_xml

SAMPLE_DIR = Path(__file__).resolve().parent / 'sample_data'


def test_sample_csv_output_is_schema_valid(crossref_schema):
    data = pd.read_csv(SAMPLE_DIR / 'example.csv')
    xml = generate_xml(
        data, 'Test Library', 'test@example.org', 'Test Library',
        include_references=True,
        license_url='https://creativecommons.org/licenses/by/4.0/',
    )
    assert validate_xml(xml, crossref_schema) == []


def test_checked_in_sample_output_is_schema_valid(crossref_schema):
    xml = (SAMPLE_DIR / 'example_output.xml').read_bytes()
    assert validate_xml(xml, crossref_schema) == []


def test_minimal_record_is_schema_valid(crossref_schema):
    assert validate_xml(generate([make_row()]), crossref_schema) == []


def test_optional_fields_are_schema_valid(crossref_schema):
    row = make_row(
        authors=(
            'Chen, Maria ORCID[https://orcid.org/0000-0001-2345-6789] '
            'ORG[Riverside University] ROR[https://ror.org/abc123]; Okonkwo, David'
        ),
        volume='12', issue='1', pages='1-45', abstract='An abstract.',
        issn_print='1234-5678', issn_electronic='87654321',
        pdf_url='https://example.org/articles/001.pdf',
    )
    xml = generate([row], license_url='https://creativecommons.org/licenses/by/4.0/')
    assert validate_xml(xml, crossref_schema) == []


def test_validate_xml_reports_schema_errors(crossref_schema):
    xml = generate([make_row()]).replace(
        '<doi>10.1234/example.001</doi>', '<doi>not-a-doi</doi>'
    )
    errors = validate_xml(xml, crossref_schema)
    assert errors
    assert any('doi' in e for e in errors)


def test_load_schema_missing_directory_explains_fix(tmp_path):
    with pytest.raises(FileNotFoundError, match='fetch_crossref_schema.py'):
        load_schema(tmp_path)


class TestSchemaVerification:

    def test_fetched_schema_matches_pinned_checksums(self, crossref_schema):
        fetch_script = load_fetch_script()
        assert fetch_script.verify(schema_dir()) == []

    def test_missing_files_are_reported(self, tmp_path):
        problems = load_fetch_script().verify(tmp_path)
        assert 'missing: crossref5.3.1.xsd' in problems

    def test_altered_file_is_reported(self, tmp_path, crossref_schema):
        fetch_script = load_fetch_script()
        copy = tmp_path / 'schema'
        shutil.copytree(schema_dir(), copy)
        with open(copy / 'common5.3.1.xsd', 'a') as f:
            f.write('<!-- modified -->')
        assert fetch_script.verify(copy) == ['checksum mismatch: common5.3.1.xsd']
