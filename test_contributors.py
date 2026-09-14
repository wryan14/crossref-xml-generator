"""Contributor handling: bracket notation, organizations, and download round trips."""

import logging

import pytest
from lxml import etree

from conftest import generate, make_row
from crossref_xml import _extract_authors, contributors_to_xml, parse_contributors, validate_xml


def contributors_as_data(authors_str: str) -> list[dict]:
    """Read a <contributors> element back into plain data for comparison."""
    elem = contributors_to_xml(authors_str)
    result = []
    for child in elem:
        entry = {'kind': child.tag, 'sequence': child.get('sequence')}
        if child.tag == 'organization':
            entry['name'] = child.text
        else:
            entry['given'] = child.findtext('given_name')
            entry['family'] = child.findtext('surname')
            entry['orcid'] = child.findtext('ORCID')
            entry['affiliations'] = [
                (inst.findtext('institution_name'), inst.findtext('institution_id'))
                for inst in child.iterfind('affiliations/institution')
            ]
        result.append(entry)
    return result


class TestOrganizationContributors:

    def test_org_only_entry_is_an_organization(self):
        result = parse_contributors('ORG[Crossref Working Group]')
        assert len(result) == 1
        assert result[0]['organization'] == 'Crossref Working Group'
        assert result[0]['surname'] is None

    def test_org_only_entry_emits_organization_element(self):
        assert contributors_as_data('ORG[Crossref Working Group]') == [
            {'kind': 'organization', 'sequence': 'first', 'name': 'Crossref Working Group'}
        ]

    def test_org_name_may_contain_semicolons(self):
        assert parse_contributors('ORG[Lab A; Lab B consortium]')[0]['organization'] == 'Lab A; Lab B consortium'

    def test_people_and_organizations_keep_order_and_sequence(self):
        data = contributors_as_data('ORG[Study Group]; Chen, Maria; ORG[Second Group]')
        assert [(d['kind'], d['sequence']) for d in data] == [
            ('organization', 'first'), ('person_name', 'additional'), ('organization', 'additional'),
        ]

    @pytest.mark.parametrize('entry', ['ROR[https://ror.org/abc123]', 'ORG[Group] ROR[https://ror.org/abc123]',
                                       'ORCID[https://orcid.org/0000-0001-2345-6789]', 'ORG[A] ORG[B]'])
    def test_nameless_entries_that_are_not_plain_organizations_are_rejected(self, entry):
        with pytest.raises(ValueError, match='no person name'):
            parse_contributors(entry)


class TestPersonNames:

    def test_surname_only_is_kept_without_given_name(self):
        assert contributors_as_data('Plato,') == [{
            'kind': 'person_name', 'sequence': 'first', 'given': None, 'family': 'Plato',
            'orcid': None, 'affiliations': [],
        }]

    @pytest.mark.parametrize('entry', ['Maria Chen', 'Plato'])
    def test_entry_without_comma_is_rejected_not_dropped(self, entry):
        with pytest.raises(ValueError, match="must be 'Surname, Given'"):
            parse_contributors(entry)

    def test_empty_surname_is_rejected(self):
        with pytest.raises(ValueError, match='empty surname'):
            parse_contributors(', Maria')

    def test_unknown_bracket_is_rejected(self):
        with pytest.raises(ValueError, match='unrecognized bracket'):
            parse_contributors('Chen, Maria ISNI[0000000121032683]')

    def test_overlong_surname_is_rejected(self):
        with pytest.raises(ValueError, match='60-character'):
            parse_contributors('X' * 61 + ', Maria')

    def test_invalid_author_fails_generation_with_row_number(self):
        with pytest.raises(ValueError, match=r"Row 3 \(10.1234/b\): author 'Maria Chen'"):
            generate([make_row(), make_row(doi='10.1234/b', authors='Maria Chen')])

    def test_blank_authors_emit_no_contributors(self):
        assert '<contributors' not in generate([make_row(authors='  ')])


class TestOrcid:

    @pytest.mark.parametrize('value', [
        'https://orcid.org/0000-0002-1825-009X', 'http://orcid.org/0000-0002-1825-009X',
        'orcid.org/0000-0002-1825-009X', '0000-0002-1825-009x',
    ])
    def test_orcid_forms_normalize_to_https(self, value):
        assert parse_contributors(f'Chen, Maria ORCID[{value}]')[0]['orcid'] == 'https://orcid.org/0000-0002-1825-009X'

    @pytest.mark.parametrize('value', ['0000-0002-1825', 'https://example.org/0000-0002-1825-0097', ''])
    def test_invalid_orcid_is_rejected_not_merged_into_name(self, value):
        with pytest.raises(ValueError, match='invalid ORCID'):
            parse_contributors(f'Chen, Maria ORCID[{value}]')

    def test_multiple_orcids_are_rejected(self):
        with pytest.raises(ValueError, match='more than one ORCID'):
            parse_contributors('Chen, Maria ORCID[0000-0002-1825-0097] ORCID[0000-0001-2345-6789]')


class TestAffiliationsAndRor:

    def test_positional_empty_slot_keeps_ror_on_correct_institution(self):
        data = contributors_as_data('Chen, Maria ORG[Dept A; Dept B] ROR[; https://ror.org/0b]')
        assert data[0]['affiliations'] == [('Dept A', None), ('Dept B', 'https://ror.org/0b')]

    def test_fewer_rors_than_orgs_pair_from_the_start(self):
        data = contributors_as_data('Chen, Maria ORG[Dept A; Dept B] ROR[https://ror.org/0a]')
        assert data[0]['affiliations'] == [('Dept A', 'https://ror.org/0a'), ('Dept B', None)]

    def test_ror_without_org_name_emits_identifier_only_institution(self):
        data = contributors_as_data('Chen, Maria ROR[https://ror.org/abc123]')
        assert data[0]['affiliations'] == [(None, 'https://ror.org/abc123')]

    def test_extra_rors_are_kept_not_dropped(self):
        data = contributors_as_data('Chen, Maria ORG[Dept A] ROR[ror.org/0a; 0b]')
        assert data[0]['affiliations'] == [('Dept A', 'https://ror.org/0a'), (None, 'https://ror.org/0b')]

    def test_repeated_org_brackets_are_merged_not_dropped(self):
        assert parse_contributors('Chen, Maria ORG[Dept A] ORG[Dept B]')[0]['affiliations'] == ['Dept A', 'Dept B']


class TestDownloadRoundTrip:
    """Crossref API author JSON -> CSV notation -> XML must preserve every supported field."""

    CASES = {
        'person_with_everything': [{
            'given': 'Maria', 'family': 'Chen', 'ORCID': 'http://orcid.org/0000-0002-1825-0097',
            'affiliation': [{'name': 'Riverside University',
                             'id': [{'id': 'https://ror.org/abc123', 'id-type': 'ROR', 'asserted-by': 'publisher'}]}],
        }],
        'organization_author': [{'name': 'Consortium for Open Metadata', 'sequence': 'first'}],
        'surname_only': [{'family': 'Plato', 'sequence': 'first'}],
        'mixed_affiliation_ror': [{
            'given': 'Maria', 'family': 'Chen',
            'affiliation': [{'name': 'Dept A'},
                            {'name': 'Dept B', 'id': [{'id': 'https://ror.org/0b', 'id-type': 'ROR'}]}],
        }],
        'ror_only_affiliation': [{
            'given': 'Nicole', 'family': 'Case',
            'affiliation': [{'id': [{'id': 'https://ror.org/03wmf1y16', 'id-type': 'ROR'}]}],
        }],
        'people_and_org': [
            {'given': 'Maria', 'family': 'Chen'},
            {'name': 'Study Group'},
            {'given': 'David', 'family': 'Okonkwo', 'affiliation': [{'name': 'Field Institute'}]},
        ],
    }

    @staticmethod
    def expected(api_authors: list[dict]) -> list[dict]:
        result = []
        for i, auth in enumerate(api_authors):
            sequence = 'first' if i == 0 else 'additional'
            if 'family' not in auth:
                result.append({'kind': 'organization', 'sequence': sequence, 'name': auth['name']})
                continue
            orcid = auth.get('ORCID')
            result.append({
                'kind': 'person_name', 'sequence': sequence,
                'given': auth.get('given'), 'family': auth['family'],
                'orcid': orcid.replace('http://', 'https://') if orcid else None,
                'affiliations': [
                    (aff.get('name'), next((i['id'] for i in aff.get('id', [])), None))
                    for aff in auth.get('affiliation', [])
                ],
            })
        return result

    @pytest.mark.parametrize('case', CASES)
    def test_round_trip_preserves_contributors(self, case):
        api_authors = self.CASES[case]
        assert contributors_as_data(_extract_authors(api_authors)) == self.expected(api_authors)

    @pytest.mark.parametrize('case', CASES)
    def test_round_trip_output_is_schema_valid(self, case, crossref_schema):
        xml = generate([make_row(authors=_extract_authors(self.CASES[case]))])
        assert validate_xml(xml, crossref_schema) == []

    def test_notation_characters_in_names_are_replaced_and_logged(self, caplog):
        api_authors = [{'family': 'Chen', 'given': 'Maria', 'affiliation': [{'name': 'Dept A; Lab [North]'}]}]
        with caplog.at_level(logging.WARNING):
            authors = _extract_authors(api_authors)
        assert contributors_as_data(authors)[0]['affiliations'] == [('Dept A, Lab (North)', None)]
        assert 'replaced' in caplog.text

    def test_unrepresentable_authors_are_logged(self, caplog):
        api_authors = [{'given': 'Anonymous'}, {'name': 'Group', 'affiliation': [{'name': 'Somewhere'}]}]
        with caplog.at_level(logging.WARNING):
            assert _extract_authors(api_authors) == 'ORG[Group]'
        assert 'without family name' in caplog.text
        assert 'affiliations/ORCID omitted' in caplog.text
