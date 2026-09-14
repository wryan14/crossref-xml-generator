"""Journal title abbreviations must come from data, never be invented."""

import pandas as pd

from conftest import generate, make_row
from crossref_xml import _normalize_crossref_data, validate_csv, validate_xml


def test_no_abbrev_title_is_fabricated():
    xml = generate([make_row(publication='Journal of Applied Ecology')])
    assert '<abbrev_title' not in xml


def test_abbrev_title_column_is_emitted_verbatim(crossref_schema):
    xml = generate([make_row(publication='Journal of Applied Ecology', abbrev_title='J. Appl. Ecol.')])
    assert '<abbrev_title>J. Appl. Ecol.</abbrev_title>' in xml
    assert validate_xml(xml, crossref_schema) == []


def test_blank_abbrev_title_is_omitted():
    assert '<abbrev_title' not in generate([make_row(abbrev_title='  ')])


def test_overlong_abbrev_title_is_rejected():
    errors = validate_csv(pd.DataFrame([make_row(abbrev_title='x' * 151)]))
    assert any('abbrev_title is longer than 150' in e for e in errors)


def test_download_keeps_short_container_title():
    raw = pd.DataFrame([{'DOI': '10.1234/a', 'title': ['A'], 'short-container-title': ['J. Appl. Ecol.']}])
    assert _normalize_crossref_data(raw)['abbrev_title'].tolist() == ['J. Appl. Ecol.']
