"""Record types: only journal articles may be converted."""

import pandas as pd
import pytest

import app as app_module
from conftest import generate, make_row
from crossref_xml import _normalize_crossref_data, validate_csv


def test_normalized_download_keeps_record_type():
    raw = pd.DataFrame([
        {'DOI': '10.1234/a', 'title': ['A'], 'type': 'journal-article'},
        {'DOI': '10.1234/b', 'title': ['B'], 'type': 'book-chapter'},
    ])
    assert list(_normalize_crossref_data(raw)['type']) == ['journal-article', 'book-chapter']


def test_journal_article_type_is_accepted():
    assert validate_csv(pd.DataFrame([make_row(type='journal-article')])) == []


@pytest.mark.parametrize('record_type', ['book-chapter', 'dataset', 'posted-content', 'component', 'Journal-Article'])
def test_other_types_are_rejected_not_mislabeled_as_articles(record_type):
    with pytest.raises(ValueError, match=f"type '{record_type}' is not supported"):
        generate([make_row(type=record_type)])


def test_csv_without_type_column_is_treated_as_journal_articles():
    assert validate_csv(pd.DataFrame([make_row()])) == []


def test_blank_type_is_treated_as_journal_article():
    assert validate_csv(pd.DataFrame([make_row(type='')])) == []


def test_download_message_reports_unsupported_types(monkeypatch):
    frame = pd.DataFrame({
        'doi': ['10.1234/a', '10.1234/b', '10.1234/c', '10.1234/d'],
        'type': ['journal-article', 'book-chapter', 'book-chapter', 'dataset'],
    })
    monkeypatch.setattr(app_module, 'download_prefix', lambda *args, **kwargs: frame)
    app_module.app.config['TESTING'] = True
    result = app_module.app.test_client().get('/download?prefix=10.1234').get_json()
    assert result['success'] is True
    assert '3 are not journal articles (2 book-chapter, 1 dataset)' in result['message']
