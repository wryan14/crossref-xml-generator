"""Tests for generate_xml output and its input guarantees."""

import pytest

from conftest import generate, make_row
from crossref_xml import MAX_RECORDS_PER_FILE, validate_xml


def rows(n: int) -> list[dict]:
    return [make_row(doi=f'10.1234/example.{i:04d}') for i in range(n)]


class TestRecordLimit:
    """Oversized input must be rejected, never truncated."""

    @pytest.mark.parametrize('count', [1, MAX_RECORDS_PER_FILE - 1, MAX_RECORDS_PER_FILE])
    def test_at_or_below_limit_emits_every_record(self, count):
        xml = generate(rows(count))
        assert xml.count('<journal_article ') == count

    @pytest.mark.parametrize('count', [MAX_RECORDS_PER_FILE + 1, MAX_RECORDS_PER_FILE * 2])
    def test_above_limit_is_rejected(self, count):
        with pytest.raises(ValueError, match=f'{count} records'):
            generate(rows(count))

    def test_limit_boundary_output_is_schema_valid(self, crossref_schema):
        xml = generate(rows(MAX_RECORDS_PER_FILE))
        assert validate_xml(xml, crossref_schema) == []
