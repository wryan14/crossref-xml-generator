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

import pandas as pd
import requests
from lxml import etree

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ['doi', 'title', 'publication', 'authors']
CROSSREF_API_BASE = 'https://api.crossref.org'
CROSSREF_ROWS_PER_PAGE = 500

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

        if 'message' not in data or 'items' not in data['message']:
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

            if 'message' not in data or 'items' not in data['message']:
                logger.warning(f"Invalid response at page {page}, stopping")
                break

            all_items.extend(data['message']['items'])

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


def _extract_authors(author_list: list[dict] | None) -> str:
    """Format authors with ORCID, ORG, and ROR bracket notation."""
    if not author_list or not isinstance(author_list, list):
        return ''

    formatted = []
    for auth in author_list:
        if 'family' in auth:
            name = f"{auth['family']}, {auth.get('given', '')}"

            if auth.get('ORCID'):
                name += f" ORCID[{auth['ORCID']}]"

            affiliations = []
            ror_ids = []
            for aff in auth.get('affiliation', []):
                if aff.get('name'):
                    affiliations.append(aff['name'])
                for id_obj in aff.get('id', []):
                    if id_obj.get('id-type', '').upper() == 'ROR':
                        ror_ids.append(id_obj['id'])

            if affiliations:
                name += f" ORG[{'; '.join(affiliations)}]"
            if ror_ids:
                name += f" ROR[{'; '.join(ror_ids)}]"

            formatted.append(name)
        elif auth.get('name'):
            formatted.append(f"ORG[{auth['name']}]")

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

    return result


# =============================================================================
# Validation Functions
# =============================================================================

def validate_csv(df: pd.DataFrame) -> list:
    """Check DataFrame for required columns and basic data validity.

    Args:
        df: DataFrame to validate

    Returns:
        List of error messages, empty if valid
    """
    errors = []

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        errors.append(f"Missing required columns: {', '.join(missing)}")
        return errors

    empty_dois = df['doi'].isna().sum()
    if empty_dois > 0:
        errors.append(f"{empty_dois} rows have empty DOI values")

    empty_titles = df['title'].isna().sum()
    if empty_titles > 0:
        errors.append(f"{empty_titles} rows have empty title values")

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

def parse_contributors(authors_str: str) -> list:
    """Parse author string with bracket notation into structured contributor data.

    Args:
        authors_str: Semicolon-delimited author string with optional ORCID[], ORG[], ROR[] brackets

    Returns:
        List of contributor dicts with keys: surname, given_name, orcid, affiliations, rors
    """
    if not authors_str or pd.isna(authors_str):
        return []

    contributors = []
    author_parts = re.split(r';(?![^\[]*\])', authors_str)

    for part in author_parts:
        part = part.strip()
        if not part:
            continue

        contributor = {
            'surname': None,
            'given_name': None,
            'orcid': None,
            'affiliations': [],
            'rors': []
        }

        orcid_match = re.search(r'ORCID\[https?://([^\]]+)\]', part)
        if orcid_match:
            contributor['orcid'] = 'https://' + orcid_match.group(1)
            part = re.sub(r'ORCID\[[^\]]+\]', '', part)

        org_match = re.search(r'ORG\[([^\]]+)\]', part)
        if org_match:
            orgs = org_match.group(1).split('; ')
            contributor['affiliations'] = [o.strip() for o in orgs if o.strip()]
            part = re.sub(r'ORG\[[^\]]+\]', '', part)

        ror_match = re.search(r'ROR\[([^\]]+)\]', part)
        if ror_match:
            rors = ror_match.group(1).split('; ')
            contributor['rors'] = [r.strip() for r in rors if r.strip()]
            part = re.sub(r'ROR\[[^\]]+\]', '', part)

        name_match = re.match(r'([^,]+),\s*(.+)', part.strip())
        if name_match:
            contributor['surname'] = name_match.group(1).strip()
            contributor['given_name'] = name_match.group(2).strip()
            contributors.append(contributor)

    return contributors


def contributors_to_xml(authors_str: str) -> etree.Element:
    """Convert author string to Crossref contributors XML element.

    Args:
        authors_str: Semicolon-delimited author string with optional bracket notation

    Returns:
        Crossref <contributors> element, or None if no valid contributors
    """
    contributors = parse_contributors(authors_str)
    if not contributors:
        return None

    contributors_elem = etree.Element('contributors')

    for i, contrib in enumerate(contributors):
        if not contrib['surname']:
            continue

        sequence = 'first' if i == 0 else 'additional'

        person_elem = etree.SubElement(contributors_elem, 'person_name')
        person_elem.set('contributor_role', 'author')
        person_elem.set('sequence', sequence)

        given_elem = etree.SubElement(person_elem, 'given_name')
        given_elem.text = contrib['given_name']

        surname_elem = etree.SubElement(person_elem, 'surname')
        surname_elem.text = contrib['surname']

        if contrib['affiliations']:
            affiliations_elem = etree.SubElement(person_elem, 'affiliations')

            for aff_idx, affiliation in enumerate(contrib['affiliations']):
                institution_elem = etree.SubElement(affiliations_elem, 'institution')

                inst_name_elem = etree.SubElement(institution_elem, 'institution_name')
                inst_name_elem.text = affiliation

                if aff_idx < len(contrib['rors']) and contrib['rors'][aff_idx]:
                    ror_id = contrib['rors'][aff_idx]
                    if not ror_id.startswith('https://ror.org/'):
                        if ror_id.startswith('ror.org/'):
                            ror_id = 'https://' + ror_id
                        else:
                            ror_id = 'https://ror.org/' + ror_id
                    inst_id_elem = etree.SubElement(institution_elem, 'institution_id', type='ror')
                    inst_id_elem.text = ror_id

        if contrib['orcid']:
            orcid_elem = etree.SubElement(person_elem, 'ORCID')
            orcid_elem.text = contrib['orcid']

    return contributors_elem if len(contributors_elem) > 0 else None


# =============================================================================
# Reference Parsing
# =============================================================================

def parse_references(references_str: str) -> list:
    """Parse references from JSON or Python literal format.

    Args:
        references_str: JSON array or Python literal containing reference dictionaries

    Returns:
        List of reference dictionaries, or empty list if parsing fails
    """
    if not references_str or pd.isna(references_str):
        return []

    try:
        references = json.loads(references_str)
        if isinstance(references, list):
            return references
    except (json.JSONDecodeError, TypeError):
        pass

    try:
        references = ast.literal_eval(references_str)
        if isinstance(references, list):
            return references
    except (ValueError, SyntaxError, TypeError):
        pass

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

    for ref in references:
        if not isinstance(ref, dict):
            continue

        key = ref.get('key', '')
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

def generate_xml(data: pd.DataFrame, depositor_name: str, depositor_email: str,
                 registrant: str, include_references: bool = False,
                 license_url: str | None = None) -> str:
    """Generate Crossref 5.3.1 XML from DataFrame.

    Args:
        data: DataFrame with required columns: doi, title, publication, authors
        depositor_name: Name of the depositing organization
        depositor_email: Contact email for the depositor
        registrant: Registrant identifier
        include_references: When True, includes references column as citations
        license_url: Optional license URL for metadata. If None, no license element is added.

    Returns:
        Crossref 5.3.1 XML document as string

    Raises:
        ValueError: When required columns are missing
    """
    errors = validate_csv(data)
    if errors:
        raise ValueError('; '.join(errors))

    data = data[data['doi'].notna() & (data['doi'] != '')]
    data = data[data['title'].notna() & (data['title'] != '')]
    data = data.head(500)

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
    depositor_name_elem.text = depositor_name
    email_elem = etree.SubElement(depositor_elem, 'email_address')
    email_elem.text = depositor_email

    registrant_elem = etree.SubElement(head, 'registrant')
    registrant_elem.text = registrant

    body = etree.SubElement(root, 'body')

    for _, row in data.iterrows():
        journal = etree.SubElement(body, 'journal')

        journal_metadata = etree.SubElement(journal, 'journal_metadata')

        full_title = etree.SubElement(journal_metadata, 'full_title')
        full_title.text = str(row['publication']) if not pd.isna(row['publication']) else ''

        abbrev_title = etree.SubElement(journal_metadata, 'abbrev_title')
        pub_title = str(row['publication']) if not pd.isna(row['publication']) else ''
        abbrev_title.text = pub_title.replace(' ', '')[:20].lower()

        if 'issn_print' in row and not pd.isna(row.get('issn_print')) and row.get('issn_print'):
            issn_print = str(row['issn_print']).replace('-', '').strip()
            if len(issn_print) == 8:
                issn_elem = etree.SubElement(journal_metadata, 'issn', media_type='print')
                issn_elem.text = f'{issn_print[:4]}-{issn_print[4:]}'

        if 'issn_electronic' in row and not pd.isna(row.get('issn_electronic')) and row.get('issn_electronic'):
            issn_electronic = str(row['issn_electronic']).replace('-', '').strip()
            if len(issn_electronic) == 8:
                issn_elem = etree.SubElement(journal_metadata, 'issn', media_type='electronic')
                issn_elem.text = f'{issn_electronic[:4]}-{issn_electronic[4:]}'

        if 'publication_date' in row and not pd.isna(row.get('publication_date')) and row.get('publication_date'):
            journal_issue = etree.SubElement(journal, 'journal_issue')

            pub_date = str(row['publication_date'])
            date_parts = pub_date.split('-')

            publication_date = etree.SubElement(journal_issue, 'publication_date', media_type='online')
            if len(date_parts) >= 2 and date_parts[1]:
                month = etree.SubElement(publication_date, 'month')
                month.text = date_parts[1]
            if len(date_parts) >= 3 and date_parts[2]:
                day = etree.SubElement(publication_date, 'day')
                day.text = date_parts[2]
            if date_parts[0]:
                year = etree.SubElement(publication_date, 'year')
                year.text = date_parts[0]

            if 'volume' in row and not pd.isna(row.get('volume')) and row['volume']:
                volume_elem = etree.SubElement(journal_issue, 'journal_volume')
                volume_number = etree.SubElement(volume_elem, 'volume')
                vol_val = row['volume']
                if isinstance(vol_val, float) and vol_val.is_integer():
                    vol_val = int(vol_val)
                volume_number.text = str(vol_val)

            if 'issue' in row and not pd.isna(row.get('issue')) and row['issue']:
                issue_elem = etree.SubElement(journal_issue, 'issue')
                issue_val = row['issue']
                if isinstance(issue_val, float) and issue_val.is_integer():
                    issue_val = int(issue_val)
                issue_elem.text = str(issue_val)

        journal_article = etree.SubElement(journal, 'journal_article', publication_type='full_text')

        titles = etree.SubElement(journal_article, 'titles')
        title = etree.SubElement(titles, 'title')
        title.text = str(row['title']) if not pd.isna(row['title']) else ''

        contributors_elem = contributors_to_xml(row.get('authors', ''))
        if contributors_elem is not None:
            journal_article.append(contributors_elem)

        if 'abstract' in row and not pd.isna(row.get('abstract')) and row.get('abstract'):
            abstract_text = str(row['abstract'])
            abstract_text = re.sub(r'</?jats:p>', '', abstract_text)

            abstract = etree.SubElement(journal_article, '{http://www.ncbi.nlm.nih.gov/JATS1}abstract')
            abstract_p = etree.SubElement(abstract, '{http://www.ncbi.nlm.nih.gov/JATS1}p')
            abstract_p.text = abstract_text

        if 'publication_date' in row and not pd.isna(row.get('publication_date')) and row.get('publication_date'):
            pub_date = str(row['publication_date'])
            date_parts = pub_date.split('-')

            publication_date = etree.SubElement(journal_article, 'publication_date', media_type='online')
            if len(date_parts) >= 2 and date_parts[1]:
                month = etree.SubElement(publication_date, 'month')
                month.text = date_parts[1]
            if len(date_parts) >= 3 and date_parts[2]:
                day = etree.SubElement(publication_date, 'day')
                day.text = date_parts[2]
            if date_parts[0]:
                year = etree.SubElement(publication_date, 'year')
                year.text = date_parts[0]

        if 'pages' in row and not pd.isna(row.get('pages')) and row['pages']:
            pages_elem = etree.SubElement(journal_article, 'pages')
            page_str = str(row['pages'])
            if '-' in page_str:
                first_page = etree.SubElement(pages_elem, 'first_page')
                first_page.text = page_str.split('-')[0]
                last_page = etree.SubElement(pages_elem, 'last_page')
                last_page.text = page_str.split('-')[1]
            else:
                first_page = etree.SubElement(pages_elem, 'first_page')
                first_page.text = page_str

        # Add license element if provided
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
        doi_elem.text = str(row['doi']) if not pd.isna(row['doi']) else ''

        resource = etree.SubElement(doi_data, 'resource')
        resource.text = str(row['resource_url']) if 'resource_url' in row and not pd.isna(row.get('resource_url')) else ''

        if 'pdf_url' in row and not pd.isna(row.get('pdf_url')) and row.get('pdf_url'):
            crawler_collection = etree.SubElement(doi_data, 'collection', property='crawler-based')
            tdm_item = etree.SubElement(crawler_collection, 'item', crawler='iParadigms')
            tdm_resource = etree.SubElement(tdm_item, 'resource')
            tdm_resource.text = str(row['pdf_url'])

            text_mining_collection = etree.SubElement(doi_data, 'collection', property='text-mining')
            text_mining_item = etree.SubElement(text_mining_collection, 'item')
            text_mining_resource = etree.SubElement(
                text_mining_item, 'resource',
                content_version='vor',
                mime_type='application/pdf'
            )
            text_mining_resource.text = str(row['pdf_url'])

        if include_references and 'references' in row:
            citation_list = references_to_xml(row.get('references'))
            if citation_list is not None:
                journal_article.append(citation_list)

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
