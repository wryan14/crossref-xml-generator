"""Crossref XML Generator - Download, edit, and convert Crossref metadata.

This module provides tools for:
1. Downloading metadata from Crossref Works API by DOI prefix
2. Converting CSV metadata to Crossref 5.3.1 XML for DOI registration/updates
"""

import ast
import os
import re
import json
import math
import datetime
import logging
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests
from lxml import etree

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ['doi', 'title', 'publication', 'authors', 'publication_date', 'resource_url']
CROSSREF_API_BASE = 'https://api.crossref.org'
CROSSREF_ROWS_PER_PAGE = 500
# REST API rule: offset + rows may not exceed 10,000; only cursors page further
CROSSREF_MAX_OFFSET_WINDOW = 10000

# Application limit, not a Crossref rule: Crossref caps deposit files at 10 MB.
# 500 records keeps a typical file well under that and failures easy to trace.
MAX_RECORDS_PER_FILE = 500

# Crossref REST API work type this tool can convert to XML
SUPPORTED_RECORD_TYPE = 'journal-article'

SCHEMA_VERSION = '5.3.1'
# Crossref does not publish its XSDs under an explicit license, so they are not
# bundled here. Run scripts/fetch_crossref_schema.py to download them.
DEFAULT_SCHEMA_DIR = Path(__file__).resolve().parent / 'schemas' / 'crossref'


# =============================================================================
# Download Functions
# =============================================================================

def download_prefix(prefix: str, email: str | None = None, limit: int | None = None,
                   sort_by: str = 'deposited') -> pd.DataFrame:
    """Download works for a DOI prefix from Crossref API.

    Args:
        prefix: DOI prefix (e.g., '10.1234')
        email: Contact email for polite pool access (recommended for large requests)
        limit: Maximum number of records to download (None = all records)
        sort_by: Field to sort by when limit is specified ('deposited', 'updated',
                'indexed', 'published'). Defaults to 'deposited' for most recent.

    Returns:
        DataFrame with columns matching the CSV schema expected by generate_xml

    Raises:
        ValueError: If API returns invalid response, no data, or invalid parameters
        requests.RequestException: If API requests fail
    """
    # Validate parameters
    if limit is not None and limit <= 0:
        raise ValueError("Limit must be greater than 0")
    if limit is not None and limit > CROSSREF_MAX_OFFSET_WINDOW:
        raise ValueError(
            f"Limit cannot exceed {CROSSREF_MAX_OFFSET_WINDOW:,} records: sorted downloads use "
            "offset paging, which the Crossref REST API caps there. Omit the limit to download "
            "all records."
        )

    valid_sort_fields = ['deposited', 'updated', 'indexed', 'published',
                        'published-print', 'published-online', 'issued']
    if sort_by not in valid_sort_fields:
        raise ValueError(f"Invalid sort_by value: {sort_by}. Must be one of {valid_sort_fields}")

    headers = {'User-Agent': f'CrossrefXMLGenerator/1.0 (mailto:{email})' if email else 'CrossrefXMLGenerator/1.0'}
    all_items = []

    # /prefixes endpoint doesn't support sorting; /works with filter enables sort_by parameter
    if limit is not None:
        # Use /works endpoint with filter for sorting support
        works_url = f'{CROSSREF_API_BASE}/works'
        params = {
            'filter': f'prefix:{prefix}',
            'rows': CROSSREF_ROWS_PER_PAGE,
            'sort': sort_by,
            'order': 'desc',
            'offset': 0
        }
        use_cursor = False
    else:
        # Use /prefixes endpoint with cursor pagination for full downloads
        works_url = f'{CROSSREF_API_BASE}/prefixes/{prefix}/works'
        params = {'rows': CROSSREF_ROWS_PER_PAGE, 'cursor': '*'}
        use_cursor = True

    try:
        if limit is not None:
            logger.info(f"Fetching most recent {limit} records for prefix {prefix} (sorted by {sort_by})")
        else:
            logger.info(f"Fetching all Crossref metadata for prefix {prefix}")

        resp = requests.get(works_url, params=params, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data.get('message'), dict) or 'items' not in data['message']:
            raise ValueError("Invalid Crossref API response format")

        all_items.extend(data['message']['items'])
        total = data['message'].get('total-results', 0)

        # Calculate pages needed based on limit
        if limit is not None:
            pages_needed = math.ceil(limit / CROSSREF_ROWS_PER_PAGE)
            pages = min(math.ceil(total / CROSSREF_ROWS_PER_PAGE), pages_needed)
        else:
            pages = math.ceil(total / CROSSREF_ROWS_PER_PAGE)

        logger.info(f"Found {total} total records, fetching {pages} pages")

        # Pagination loop
        for page in range(1, pages):
            # Check if we've reached limit
            if limit and len(all_items) >= limit:
                logger.info(f"Reached limit of {limit} records")
                break

            if page % 5 == 0:
                logger.info(f"Progress: page {page}/{pages}")

            if use_cursor:
                # Cursor-based pagination
                cursor = data['message'].get('next-cursor')
                if not cursor:
                    break
                params['cursor'] = cursor
            else:
                # Offset-based pagination
                params['offset'] = page * CROSSREF_ROWS_PER_PAGE

            resp = requests.get(works_url, params=params, headers=headers, timeout=60)
            resp.raise_for_status()
            data = resp.json()

            if not isinstance(data.get('message'), dict) or 'items' not in data['message']:
                raise ValueError(
                    f"Download incomplete: Crossref returned an invalid response for page "
                    f"{page + 1} of {pages} after {len(all_items)} of {total} records. "
                    "Try again later."
                )
            if not data['message']['items']:
                break

            all_items.extend(data['message']['items'])

        expected = min(total, limit) if limit else total
        if len(all_items) < expected:
            logger.warning(f"Downloaded {len(all_items)} records for prefix {prefix}, expected {expected}; "
                           "Crossref results may have changed during the download")

        # Truncate to exact limit if specified
        if limit and len(all_items) > limit:
            all_items = all_items[:limit]

        if not all_items:
            raise ValueError(f"No records found for prefix {prefix}")

        logger.info(f"Downloaded {len(all_items)} records")
        return _normalize_crossref_data(pd.DataFrame(all_items))

    except requests.RequestException as e:
        logger.error(f"API request failed: {e}")
        raise


def _join_list(value: list | str | None) -> str:
    """Join list to semicolon-separated string."""
    if isinstance(value, list):
        return '; '.join(str(v) for v in value)
    return str(value) if pd.notna(value) else ''


def _extract_date(date_field: dict | None) -> str:
    """Extract date from Crossref date-parts structure."""
    if not date_field or not isinstance(date_field, dict):
        return ''
    date_parts = date_field.get('date-parts', [[]])
    if date_parts and date_parts[0]:
        parts = [str(p) for p in date_parts[0] if p]
        if len(parts) >= 1:
            if len(parts) >= 2:
                parts[1] = parts[1].zfill(2)
            if len(parts) >= 3:
                parts[2] = parts[2].zfill(2)
            return '-'.join(parts)
    return ''


def _notation_safe(value: str, context: str) -> str:
    """Replace characters that would break bracket notation, logging any change."""
    safe = value.replace(';', ',').replace('[', '(').replace(']', ')')
    if safe != value:
        logger.warning(f"{context}: replaced ';' or brackets in '{value}' to keep author notation parseable")
    return safe


def _extract_authors(author_list: list[dict] | None) -> str:
    """Format authors with ORCID, ORG, and ROR bracket notation.

    ORG[] and ROR[] are positional: when only some affiliations have a ROR
    ID, empty slots keep each ID attached to the right institution.
    """
    if not author_list or not isinstance(author_list, list):
        return ''

    formatted = []
    for auth in author_list:
        if auth.get('family'):
            family = _notation_safe(auth['family'], 'author')
            given = _notation_safe(auth.get('given') or '', 'author')
            name = f"{family}, {given}".strip()

            if auth.get('ORCID'):
                name += f" ORCID[{auth['ORCID']}]"

            affiliations = []
            ror_ids = []
            for aff in auth.get('affiliation', []):
                aff_name = _notation_safe(aff.get('name') or '', f'affiliation of {family}')
                ror_id = next((id_obj.get('id', '') for id_obj in aff.get('id', [])
                               if id_obj.get('id-type', '').upper() == 'ROR'), '')
                if aff_name or ror_id:
                    affiliations.append(aff_name)
                    ror_ids.append(ror_id)

            if any(affiliations):
                name += f" ORG[{'; '.join(affiliations)}]"
            if any(ror_ids):
                name += f" ROR[{'; '.join(ror_ids)}]"

            formatted.append(name)
        elif auth.get('name'):
            if auth.get('affiliation') or auth.get('ORCID'):
                logger.warning(f"Organization author '{auth['name']}': affiliations/ORCID "
                               "omitted (not supported for organizations in schema 5.3.1)")
            formatted.append(f"ORG[{_notation_safe(auth['name'], 'organization author')}]")
        else:
            logger.warning(f"Author without family name or organization name omitted: {auth}")

    return '; '.join(formatted)


def _extract_issn(issn_type_list: list[dict] | None, media_type: str) -> str:
    """Extract ISSN by media type (print or electronic)."""
    if not issn_type_list or not isinstance(issn_type_list, list):
        return ''
    for issn in issn_type_list:
        if issn.get('type') == media_type:
            return issn.get('value', '')
    return ''


def _extract_link(links: list[dict] | None, intended_application: str) -> str:
    """Extract URL by intended application type."""
    if not links or not isinstance(links, list):
        return ''
    for link in links:
        if link.get('intended-application') == intended_application:
            return link.get('URL', '')
    return ''


def _extract_resource_url(resource: dict | None) -> str:
    """Extract primary resource URL."""
    if isinstance(resource, dict) and 'primary' in resource:
        return resource['primary'].get('URL', '')
    return ''


def _normalize_crossref_data(df: pd.DataFrame) -> pd.DataFrame:
    """Transform raw Crossref API data to CSV schema format."""
    df = df.fillna('')

    result = pd.DataFrame()

    result['doi'] = df['DOI']
    result['title'] = df['title'].apply(_join_list)
    result['publication'] = df.get('container-title', pd.Series([''] * len(df))).apply(_join_list)
    result['authors'] = df.get('author', pd.Series([''] * len(df))).apply(_extract_authors)

    result['publication_date'] = df.get('issued', pd.Series([''] * len(df))).apply(_extract_date)
    result['volume'] = df.get('volume', '')
    result['issue'] = df.get('issue', '')
    result['pages'] = df.get('page', '')

    if 'abstract' in df.columns:
        result['abstract'] = df['abstract'].astype(str).str.replace(r'</?jats:p>', '', regex=True)
    else:
        result['abstract'] = ''

    result['issn_print'] = df.get('issn-type', pd.Series([''] * len(df))).apply(lambda x: _extract_issn(x, 'print'))
    result['issn_electronic'] = df.get('issn-type', pd.Series([''] * len(df))).apply(lambda x: _extract_issn(x, 'electronic'))

    result['resource_url'] = df.get('resource', pd.Series([''] * len(df))).apply(_extract_resource_url)
    result['pdf_url'] = df.get('link', pd.Series([''] * len(df))).apply(lambda x: _extract_link(x, 'text-mining'))

    if 'reference' in df.columns:
        result['references'] = df['reference'].apply(lambda x: json.dumps(x) if isinstance(x, list) else '')
    else:
        result['references'] = ''

    # Prefixes often mix record types; keep the type so conversion can refuse
    # anything that is not a journal article instead of mislabeling it.
    result['type'] = df['type'] if 'type' in df.columns else ''

    result['abbrev_title'] = df.get('short-container-title', pd.Series([''] * len(df))).apply(_join_list)

    return result


# =============================================================================
# Validation Functions
# =============================================================================

DOI_PATTERN = re.compile(r'10\.[0-9]{4,9}/.{1,200}')
DATE_PATTERN = re.compile(r'(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?')
ISSN_PATTERN = re.compile(r'\d{4}-?\d{3}[\dXx]')
MAX_REPORTED_ERRORS = 25


def _clean(value) -> str:
    """Normalize a CSV cell to a stripped string ('' for missing values).

    pandas reads numeric columns containing blanks as float, so 2024 arrives
    as 2024.0; integer-valued floats are rendered without the decimal part.
    """
    if value is None:
        return ''
    if isinstance(value, float):
        if math.isnan(value):
            return ''
        if value.is_integer():
            return str(int(value))
    return str(value).strip()


def _cell(row: pd.Series, column: str) -> str:
    """Return a normalized cell value, or '' when the column is absent."""
    return _clean(row[column]) if column in row else ''


def _is_url(value: str) -> bool:
    """Check for an absolute http(s)/ftp URL, as the Crossref schema requires."""
    if re.search(r'\s', value):
        return False
    parsed = urlparse(value)
    return parsed.scheme.lower() in ('http', 'https', 'ftp') and bool(parsed.netloc)


def _parse_date(value: str) -> tuple[str, str | None, str | None]:
    """Split YYYY, YYYY-MM, or YYYY-MM-DD into zero-padded (year, month, day).

    Raises:
        ValueError: If the value is not a real calendar date in that format
    """
    match = DATE_PATTERN.fullmatch(value)
    if not match:
        raise ValueError(f"publication_date '{value}' must be YYYY, YYYY-MM, or YYYY-MM-DD")
    year, month, day = match.groups()
    if not 1400 <= int(year) <= 2200:
        raise ValueError(f"publication_date '{value}' has a year outside 1400-2200")
    try:
        datetime.date(int(year), int(month or 1), int(day or 1))
    except ValueError:
        raise ValueError(f"publication_date '{value}' is not a valid calendar date") from None
    return year, month.zfill(2) if month else None, day.zfill(2) if day else None


def _row_errors(row: pd.Series, include_references: bool = False) -> list:
    """Return problems with a single record that would produce a bad deposit."""
    errors = []

    doi = _cell(row, 'doi')
    if not doi:
        errors.append('doi is empty')
    elif not DOI_PATTERN.fullmatch(doi):
        errors.append(f"doi '{doi}' must be a bare DOI like 10.1234/abc "
                      "(no https://doi.org/ prefix)")

    if not _cell(row, 'title'):
        errors.append('title is empty')

    record_type = _cell(row, 'type')
    if record_type and record_type != SUPPORTED_RECORD_TYPE:
        errors.append(f"type '{record_type}' is not supported; only {SUPPORTED_RECORD_TYPE} "
                      "records can be converted")

    publication = _cell(row, 'publication')
    if not publication:
        errors.append('publication is empty')
    elif len(publication) > 255:
        errors.append('publication is longer than 255 characters')

    if len(_cell(row, 'abbrev_title')) > 150:
        errors.append('abbrev_title is longer than 150 characters')

    publication_date = _cell(row, 'publication_date')
    if not publication_date:
        errors.append('publication_date is empty (Crossref requires one for journal articles)')
    else:
        try:
            _parse_date(publication_date)
        except ValueError as e:
            errors.append(str(e))

    resource_url = _cell(row, 'resource_url')
    if not resource_url:
        errors.append('resource_url is empty (Crossref requires a landing page URL)')
    elif not _is_url(resource_url):
        errors.append(f"resource_url '{resource_url}' is not an absolute http(s) URL")

    pdf_url = _cell(row, 'pdf_url')
    if pdf_url and not _is_url(pdf_url):
        errors.append(f"pdf_url '{pdf_url}' is not an absolute http(s) URL")

    for column in ('issn_print', 'issn_electronic'):
        issn = _cell(row, column)
        if issn and not ISSN_PATTERN.fullmatch(issn):
            errors.append(f"{column} '{issn}' is not a valid ISSN (NNNN-NNNN)")

    pages = _cell(row, 'pages')
    if pages and not pages.partition('-')[0].strip():
        errors.append(f"pages '{pages}' must start with a first page")

    try:
        parse_contributors(_cell(row, 'authors'))
    except ValueError as e:
        errors.append(str(e))

    references = _cell(row, 'references') if include_references else ''
    if references:
        try:
            for ref in _load_references(references):
                if len(str(ref.get('key') or '')) > 128:
                    errors.append(f"reference key '{ref['key']}' is longer than 128 characters")
        except ValueError as e:
            errors.append(str(e))

    return errors


def validate_csv(df: pd.DataFrame, include_references: bool = False) -> list:
    """Check DataFrame for required columns and per-record data validity.

    Row numbers in messages match spreadsheet rows (header is row 1).

    Args:
        df: DataFrame to validate
        include_references: Also require the references column to be parseable

    Returns:
        List of error messages, empty if valid
    """
    errors = []

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        errors.append(f"Missing required columns: {', '.join(missing)}")
        return errors

    first_seen = {}
    for position, (_, row) in enumerate(df.iterrows()):
        line = position + 2
        doi = _cell(row, 'doi')
        label = f"Row {line} ({doi})" if doi else f"Row {line}"
        errors.extend(f"{label}: {message}" for message in _row_errors(row, include_references))

        if doi:
            key = doi.lower()  # DOIs are case-insensitive
            if key in first_seen:
                errors.append(f"{label}: duplicate DOI (first used in row {first_seen[key]})")
            else:
                first_seen[key] = line

    return errors


def schema_dir() -> Path:
    """Return the directory holding Crossref XSD files (CROSSREF_SCHEMA_DIR overrides)."""
    return Path(os.environ.get('CROSSREF_SCHEMA_DIR') or DEFAULT_SCHEMA_DIR)


def load_schema(directory: str | Path | None = None) -> etree.XMLSchema:
    """Load the Crossref 5.3.1 XSD from a local directory without network access.

    Raises:
        FileNotFoundError: If the schema files have not been downloaded
    """
    directory = Path(directory) if directory else schema_dir()
    xsd_path = directory / f'crossref{SCHEMA_VERSION}.xsd'
    if not xsd_path.is_file():
        raise FileNotFoundError(
            f"Crossref schema not found at {xsd_path}. "
            "Run: python scripts/fetch_crossref_schema.py"
        )
    parser = etree.XMLParser(no_network=True)
    return etree.XMLSchema(etree.parse(str(xsd_path), parser))


def validate_xml(xml: str | bytes, schema: etree.XMLSchema | None = None) -> list:
    """Validate generated XML against the Crossref 5.3.1 XSD.

    Schema validity is necessary but not sufficient for a successful deposit:
    Crossref also applies business rules (prefix ownership, title matching,
    etc.) that no XSD can check.

    Args:
        xml: XML document as produced by generate_xml
        schema: Preloaded schema; loaded from schema_dir() when omitted

    Returns:
        List of error messages (with line numbers), empty if valid
    """
    schema = schema or load_schema()
    if isinstance(xml, str):
        xml = xml.encode('utf-8')
    doc = etree.fromstring(xml, etree.XMLParser(no_network=True))
    if schema.validate(doc):
        return []
    return [f"line {err.line}: {err.message}" for err in schema.error_log]


# =============================================================================
# Contributor Parsing
# =============================================================================

ORCID_PATTERN = re.compile(r'(?:(?:https?://)?orcid\.org/)?(\d{4}-\d{4}-\d{4}-\d{3}[\dX])', re.IGNORECASE)
BRACKET_PATTERN = re.compile(r'(ORCID|ORG|ROR)\[([^\]]*)\]')


def _normalize_ror(value: str) -> str:
    """Expand 'abc123' or 'ror.org/abc123' to 'https://ror.org/abc123'."""
    value = re.sub(r'^https?://', '', value)
    if value.startswith('ror.org/'):
        value = value[len('ror.org/'):]
    return f'https://ror.org/{value}'


def parse_contributors(authors_str: str) -> list:
    """Parse author string with bracket notation into structured contributor data.

    Each semicolon-delimited entry is one of:
    - a person: ``Surname, Given`` (or ``Surname,`` when there is no given
      name) with optional ORCID[], ORG[], and ROR[] brackets
    - an organization: ``ORG[Name]`` with no person name

    ORG[] and ROR[] lists pair by position; leave a slot empty to skip one,
    e.g. ``ORG[Dept A; Dept B] ROR[; https://ror.org/xyz]``.

    Args:
        authors_str: Semicolon-delimited author string with optional ORCID[], ORG[], ROR[] brackets

    Returns:
        List of contributor dicts with keys: surname, given_name, orcid,
        affiliations, rors, organization (None for people)

    Raises:
        ValueError: If an entry cannot be represented without losing data
    """
    if authors_str is None or (not isinstance(authors_str, str) and pd.isna(authors_str)):
        return []

    contributors = []
    author_parts = re.split(r';(?![^\[]*\])', str(authors_str))

    for part in author_parts:
        part = part.strip()
        if not part:
            continue

        brackets = {'ORCID': [], 'ORG': [], 'ROR': []}
        for tag, content in BRACKET_PATTERN.findall(part):
            brackets[tag].append(content)
        name = BRACKET_PATTERN.sub('', part).strip()

        if '[' in name or ']' in name:
            raise ValueError(f"author '{part}' has unrecognized bracket notation "
                             "(supported: ORCID[], ORG[], ROR[])")

        contributor = {
            'surname': None,
            'given_name': None,
            'orcid': None,
            'affiliations': [],
            'rors': [],
            'organization': None,
        }

        if not name:
            if len(brackets['ORG']) == 1 and not brackets['ORCID'] and not brackets['ROR']:
                organization = brackets['ORG'][0].strip()
                if organization:
                    contributor['organization'] = organization
                    contributors.append(contributor)
                    continue
            raise ValueError(f"author '{part}' has no person name; use 'Surname, Given' for a "
                             "person or ORG[Name] alone for an organization (Crossref 5.3.1 "
                             "organization contributors cannot carry ORCID or ROR)")

        if ',' not in name:
            raise ValueError(f"author '{name}' must be 'Surname, Given' "
                             "(or 'Surname,' when there is no given name)")
        surname, _, given_name = name.partition(',')
        if not surname.strip():
            raise ValueError(f"author '{part}' has an empty surname")
        contributor['surname'] = surname.strip()
        contributor['given_name'] = given_name.strip() or None
        for label, value in (('surname', contributor['surname']), ('given name', contributor['given_name'])):
            if value and len(value) > 60:
                raise ValueError(f"author '{name}' {label} is longer than Crossref's 60-character limit")

        if len(brackets['ORCID']) > 1:
            raise ValueError(f"author '{name}' has more than one ORCID")
        if brackets['ORCID']:
            orcid_match = ORCID_PATTERN.fullmatch(brackets['ORCID'][0].strip())
            if not orcid_match:
                raise ValueError(f"author '{name}' has an invalid ORCID "
                                 f"'{brackets['ORCID'][0]}' (expected https://orcid.org/0000-0000-0000-0000)")
            contributor['orcid'] = 'https://orcid.org/' + orcid_match.group(1).upper()

        # Keep empty slots so ORG and ROR entries stay aligned by position
        contributor['affiliations'] = [o.strip() for group in brackets['ORG'] for o in group.split(';')]
        contributor['rors'] = [r.strip() for group in brackets['ROR'] for r in group.split(';')]
        for ror in contributor['rors']:
            if re.search(r'\s', ror):
                raise ValueError(f"author '{name}' has an invalid ROR '{ror}'")
        if not any(contributor['affiliations']):
            contributor['affiliations'] = []
        if not any(contributor['rors']):
            contributor['rors'] = []

        contributors.append(contributor)

    return contributors


def contributors_to_xml(authors_str: str) -> etree.Element:
    """Convert author string to Crossref contributors XML element.

    Args:
        authors_str: Semicolon-delimited author string with optional bracket notation

    Returns:
        Crossref <contributors> element, or None if no contributors

    Raises:
        ValueError: If an entry cannot be parsed (see parse_contributors)
    """
    contributors = parse_contributors(authors_str)
    if not contributors:
        return None

    contributors_elem = etree.Element('contributors')

    for i, contrib in enumerate(contributors):
        sequence = 'first' if i == 0 else 'additional'

        if contrib['organization']:
            org_elem = etree.SubElement(contributors_elem, 'organization')
            org_elem.set('contributor_role', 'author')
            org_elem.set('sequence', sequence)
            org_elem.text = contrib['organization']
            continue

        person_elem = etree.SubElement(contributors_elem, 'person_name')
        person_elem.set('contributor_role', 'author')
        person_elem.set('sequence', sequence)

        if contrib['given_name']:
            given_elem = etree.SubElement(person_elem, 'given_name')
            given_elem.text = contrib['given_name']

        surname_elem = etree.SubElement(person_elem, 'surname')
        surname_elem.text = contrib['surname']

        slots = max(len(contrib['affiliations']), len(contrib['rors']))
        institutions = []
        for idx in range(slots):
            affiliation = contrib['affiliations'][idx] if idx < len(contrib['affiliations']) else ''
            ror_id = contrib['rors'][idx] if idx < len(contrib['rors']) else ''
            if affiliation or ror_id:
                institutions.append((affiliation, ror_id))

        if institutions:
            affiliations_elem = etree.SubElement(person_elem, 'affiliations')

            for affiliation, ror_id in institutions:
                institution_elem = etree.SubElement(affiliations_elem, 'institution')

                if affiliation:
                    inst_name_elem = etree.SubElement(institution_elem, 'institution_name')
                    inst_name_elem.text = affiliation

                if ror_id:
                    inst_id_elem = etree.SubElement(institution_elem, 'institution_id', type='ror')
                    inst_id_elem.text = _normalize_ror(ror_id)

        if contrib['orcid']:
            orcid_elem = etree.SubElement(person_elem, 'ORCID')
            orcid_elem.text = contrib['orcid']

    return contributors_elem


# =============================================================================
# Reference Parsing
# =============================================================================

def _load_references(references_str: str) -> list:
    """Strictly parse a references cell into a list of dicts.

    Raises:
        ValueError: If the value is not a JSON (or Python literal) list of objects
    """
    for loader in (json.loads, ast.literal_eval):
        try:
            references = loader(references_str)
        except (ValueError, SyntaxError, TypeError, RecursionError, MemoryError):
            continue
        if isinstance(references, list) and all(isinstance(ref, dict) for ref in references):
            return references
    raise ValueError(f"references could not be parsed as a JSON array of objects: "
                     f"{str(references_str)[:60]}")


def parse_references(references_str: str) -> list:
    """Parse references from JSON or Python literal format.

    Args:
        references_str: JSON array or Python literal containing reference dictionaries

    Returns:
        List of reference dictionaries, or empty list if parsing fails
    """
    if references_str is None or (not isinstance(references_str, str) and pd.isna(references_str)):
        return []
    if not str(references_str).strip():
        return []

    try:
        return _load_references(references_str)
    except ValueError:
        logger.warning(f"Failed to parse references: {str(references_str)[:100]}")
        return []


def references_to_xml(references_str: str) -> etree.Element:
    """Convert references to Crossref citation_list XML element.

    Args:
        references_str: JSON or Python literal with reference dictionaries

    Returns:
        Crossref <citation_list> element, or None if no valid references
    """
    references = parse_references(references_str)

    if not references:
        return None

    citation_list = etree.Element('citation_list')

    for position, ref in enumerate(references, start=1):
        if not isinstance(ref, dict):
            continue

        # Crossref requires a non-empty key; number unkeyed references by position
        key = str(ref.get('key') or f'ref{position}')
        citation = etree.SubElement(citation_list, 'citation', key=key)

        doi = ref.get('DOI')
        doi_asserted = ref.get('doi-asserted-by')
        if doi and doi_asserted == 'publisher':
            doi_elem = etree.SubElement(citation, 'doi')
            doi_elem.text = doi

        unstructured = ref.get('unstructured')
        if unstructured:
            unstructured_elem = etree.SubElement(citation, 'unstructured_citation')
            unstructured_elem.text = unstructured

    return citation_list if len(citation_list) > 0 else None


# =============================================================================
# XML Generation
# =============================================================================

def _add_publication_date(parent: etree.Element, value: str) -> None:
    """Append a <publication_date> built from a validated date string."""
    year, month, day = _parse_date(value)
    publication_date = etree.SubElement(parent, 'publication_date', media_type='online')
    if month:
        etree.SubElement(publication_date, 'month').text = month
    if day:
        etree.SubElement(publication_date, 'day').text = day
    etree.SubElement(publication_date, 'year').text = year


def _journal_element(row: pd.Series, include_references: bool,
                     license_url: str | None) -> etree.Element:
    """Build one <journal> element from a validated CSV row."""
    journal = etree.Element('journal')

    journal_metadata = etree.SubElement(journal, 'journal_metadata')

    publication = _cell(row, 'publication')
    full_title = etree.SubElement(journal_metadata, 'full_title')
    full_title.text = publication

    abbrev = _cell(row, 'abbrev_title')
    if abbrev:
        abbrev_title = etree.SubElement(journal_metadata, 'abbrev_title')
        abbrev_title.text = abbrev

    for column, media_type in (('issn_print', 'print'), ('issn_electronic', 'electronic')):
        issn = _cell(row, column).replace('-', '').upper()
        if issn:
            issn_elem = etree.SubElement(journal_metadata, 'issn', media_type=media_type)
            issn_elem.text = f'{issn[:4]}-{issn[4:]}'

    publication_date = _cell(row, 'publication_date')

    journal_issue = etree.SubElement(journal, 'journal_issue')
    _add_publication_date(journal_issue, publication_date)

    volume = _cell(row, 'volume')
    if volume:
        volume_elem = etree.SubElement(journal_issue, 'journal_volume')
        volume_number = etree.SubElement(volume_elem, 'volume')
        volume_number.text = volume

    issue = _cell(row, 'issue')
    if issue:
        issue_elem = etree.SubElement(journal_issue, 'issue')
        issue_elem.text = issue

    journal_article = etree.SubElement(journal, 'journal_article', publication_type='full_text')

    titles = etree.SubElement(journal_article, 'titles')
    title = etree.SubElement(titles, 'title')
    title.text = _cell(row, 'title')

    contributors_elem = contributors_to_xml(row.get('authors', ''))
    if contributors_elem is not None:
        journal_article.append(contributors_elem)

    abstract_text = re.sub(r'</?jats:p>', '', _cell(row, 'abstract'))
    if abstract_text:
        abstract = etree.SubElement(journal_article, '{http://www.ncbi.nlm.nih.gov/JATS1}abstract')
        abstract_p = etree.SubElement(abstract, '{http://www.ncbi.nlm.nih.gov/JATS1}p')
        abstract_p.text = abstract_text

    _add_publication_date(journal_article, publication_date)

    pages = _cell(row, 'pages')
    if pages:
        pages_elem = etree.SubElement(journal_article, 'pages')
        first, _, last = pages.partition('-')
        first_page = etree.SubElement(pages_elem, 'first_page')
        first_page.text = first.strip()
        if last.strip():
            last_page = etree.SubElement(pages_elem, 'last_page')
            last_page.text = last.strip()

    if license_url:
        ai_program = etree.SubElement(
            journal_article,
            '{http://www.crossref.org/AccessIndicators.xsd}program',
            name='AccessIndicators'
        )
        license_ref = etree.SubElement(
            ai_program,
            '{http://www.crossref.org/AccessIndicators.xsd}license_ref',
            applies_to='vor'
        )
        license_ref.text = license_url

    doi_data = etree.SubElement(journal_article, 'doi_data')

    doi_elem = etree.SubElement(doi_data, 'doi')
    doi_elem.text = _cell(row, 'doi')

    resource = etree.SubElement(doi_data, 'resource')
    resource.text = _cell(row, 'resource_url')

    pdf_url = _cell(row, 'pdf_url')
    if pdf_url:
        crawler_collection = etree.SubElement(doi_data, 'collection', property='crawler-based')
        tdm_item = etree.SubElement(crawler_collection, 'item', crawler='iParadigms')
        tdm_resource = etree.SubElement(tdm_item, 'resource')
        tdm_resource.text = pdf_url

        text_mining_collection = etree.SubElement(doi_data, 'collection', property='text-mining')
        text_mining_item = etree.SubElement(text_mining_collection, 'item')
        text_mining_resource = etree.SubElement(
            text_mining_item, 'resource',
            content_version='vor',
            mime_type='application/pdf'
        )
        text_mining_resource.text = pdf_url

    if include_references and 'references' in row:
        citation_list = references_to_xml(row.get('references'))
        if citation_list is not None:
            journal_article.append(citation_list)

    return journal


def generate_xml(data: pd.DataFrame, depositor_name: str, depositor_email: str,
                 registrant: str, include_references: bool = False,
                 license_url: str | None = None) -> str:
    """Generate Crossref 5.3.1 XML from DataFrame.

    Every row becomes exactly one record, or the whole call fails: rows are
    never silently skipped or truncated. Passing validation here does not
    guarantee Crossref will accept the deposit; see validate_xml.

    Args:
        data: DataFrame with the columns listed in REQUIRED_COLUMNS
        depositor_name: Name of the depositing organization
        depositor_email: Contact email for the depositor
        registrant: Registrant identifier
        include_references: When True, includes references column as citations
        license_url: Optional license URL for the article content (version of
            record), emitted as <ai:license_ref applies_to="vor">. If None or
            empty, no license element is added.

    Returns:
        Crossref 5.3.1 XML document as string

    Raises:
        ValueError: When required columns or values are missing or invalid, or
            when data has more than MAX_RECORDS_PER_FILE rows
    """
    if len(data) > MAX_RECORDS_PER_FILE:
        raise ValueError(
            f"CSV contains {len(data)} records; this tool generates at most "
            f"{MAX_RECORDS_PER_FILE} records per XML file. Split the CSV into "
            f"files of {MAX_RECORDS_PER_FILE} rows or fewer and convert each one."
        )

    for name, value in (('depositor_name', depositor_name),
                        ('depositor_email', depositor_email),
                        ('registrant', registrant)):
        if not _clean(value):
            raise ValueError(f"{name} is required")

    license_url = _clean(license_url) or None
    if license_url and not _is_url(license_url):
        raise ValueError(f"license_url '{license_url}' is not an absolute http(s) URL")

    errors = validate_csv(data, include_references=include_references)
    if errors:
        shown = errors[:MAX_REPORTED_ERRORS]
        message = '; '.join(shown)
        if len(errors) > len(shown):
            message += f'; ... and {len(errors) - len(shown)} more'
        raise ValueError(message)

    root = etree.Element(
        '{http://www.crossref.org/schema/5.3.1}doi_batch',
        nsmap={
            None: 'http://www.crossref.org/schema/5.3.1',
            'ai': 'http://www.crossref.org/AccessIndicators.xsd',
            'jats': 'http://www.ncbi.nlm.nih.gov/JATS1',
            'fr': 'http://www.crossref.org/fundref.xsd',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
        }
    )
    root.set('{http://www.w3.org/2001/XMLSchema-instance}schemaLocation',
             'http://www.crossref.org/schema/5.3.1 https://www.crossref.org/schemas/crossref5.3.1.xsd')
    root.set('version', '5.3.1')

    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')[:-3]

    head = etree.SubElement(root, 'head')

    doi_batch_id = etree.SubElement(head, 'doi_batch_id')
    doi_batch_id.text = f'batch_{timestamp}'

    timestamp_elem = etree.SubElement(head, 'timestamp')
    timestamp_elem.text = timestamp

    depositor_elem = etree.SubElement(head, 'depositor')
    depositor_name_elem = etree.SubElement(depositor_elem, 'depositor_name')
    depositor_name_elem.text = depositor_name.strip()
    email_elem = etree.SubElement(depositor_elem, 'email_address')
    email_elem.text = depositor_email.strip()

    registrant_elem = etree.SubElement(head, 'registrant')
    registrant_elem.text = registrant.strip()

    body = etree.SubElement(root, 'body')

    for position, (_, row) in enumerate(data.iterrows()):
        try:
            body.append(_journal_element(row, include_references, license_url))
        except ValueError as e:
            raise ValueError(f"Row {position + 2}: {e}") from e

    xml_bytes = etree.tostring(root, pretty_print=True, encoding='UTF-8', xml_declaration=True)
    xml_str = xml_bytes.decode('utf-8')

    xml_str = xml_str.replace(
        '<jats:abstract>',
        '<jats:abstract xmlns:jats="http://www.ncbi.nlm.nih.gov/JATS1">'
    )
    xml_str = xml_str.replace(
        '<ai:program name="AccessIndicators">',
        '<ai:program xmlns:ai="http://www.crossref.org/AccessIndicators.xsd" name="AccessIndicators">'
    )

    return xml_str
