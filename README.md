# Crossref XML Generator

Download, edit, and convert metadata for DOI registration.

A web-based tool for metadata librarians to manage Crossref submissions without navigating complex XML schemas or APIs. Pull existing DOI metadata, modify it in a spreadsheet, and generate Crossref 5.3.1 XML for submission. Input is validated before any XML is produced, and output can be checked against the official Crossref 5.3.1 XSD.

<img src="docs/images/web-interface.png" alt="Web Interface" width="650">

## Use Cases

**Who uses this:**
- Metadata librarians managing institutional repositories
- Journal managers updating DOI records
- Repository administrators maintaining publisher metadata

**Common workflows:**
- **Bulk ORCID enrichment** — Download 500 article records, add author ORCIDs in Excel, resubmit to Crossref
- **ROR affiliation updates** — Pull existing metadata, append ROR identifiers to institutional affiliations, generate updated XML
- **Metadata corrections** — Fix author names, affiliations, or publication dates across multiple DOIs without manual XML editing
- **New DOI registration** — Create CSV from local records, add required Crossref fields, generate submission XML

**Why CSV as intermediate format:**
- Editable in Excel, Google Sheets, or any spreadsheet tool
- Supports bulk find-and-replace operations across hundreds of records
- No XML syntax knowledge required for metadata staff
- Version control friendly for tracking changes

> **Before resubmitting downloaded records:** this tool round-trips only the fields listed under [Supported and Omitted Metadata](#supported-and-omitted-metadata). Crossref [overwrites existing metadata](https://www.crossref.org/documentation/register-maintain-records/maintaining-your-metadata/updating-your-metadata/) with an update deposit and nulls fields that are not supplied. Bibliographic metadata the CSV does not carry, such as funding, editors and other contributor roles, subtitles, or separate print and online dates, can therefore be removed from Crossref when you redeposit. References, Crossmark, and relations follow their own update procedures. Check that section first.

## Requirements

- Python 3.10+ (the code uses PEP 604 `X | Y` type hints)
- Dependencies: see `requirements.txt`

### Tested environment

The test suite passes on Python 3.12.3 with the exact versions in `requirements-tested.txt` (Flask 3.1.3, pandas 3.0.5, lxml 6.1.3, requests 2.34.2). It also passes with pandas 2.3.3. `requirements.txt` stays unpinned so the tool installs alongside other packages; if something breaks after an upgrade, install `requirements-tested.txt` to get the known-good set.

## Setup

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

Open `http://localhost:5000` in your browser.

`python app.py` starts Flask's development server with debug mode on, for use on your own machine. Debug mode includes an interactive debugger that can run code, so never expose this server on a network. To host the tool for others, run `app:app` under a production WSGI server (for example gunicorn or waitress) with debug off, behind whatever authentication your environment requires.

### Running Tests

```bash
# One-time: download the Crossref 5.3.1 XSD used by schema-validation tests
python scripts/fetch_crossref_schema.py

pytest
```

Schema-validation tests are skipped, with a message saying so, until the XSD has been downloaded. The files are fetched from Crossref's [official schema repository](https://gitlab.com/crossref/schema) at a pinned commit rather than committed here, because that repository does not state a license. Set `CROSSREF_SCHEMA_DIR` to use a copy stored elsewhere.

## Usage

### Web Interface

1. **Download** — Enter a DOI prefix to pull existing metadata from Crossref
   - Choose to download all records or filter to most recent (100, 500, 1000, or custom limit up to 10,000)
   - The message reports any records that are not journal articles; remove those rows before converting
2. **Edit** — Open the CSV in Excel/Sheets, filter to records needing updates, add ORCIDs, fix affiliations
3. **Convert** — Upload edited CSV (at most 500 rows) to generate Crossref XML
   - If any row has a problem, nothing is generated and every problem is listed with its spreadsheet row number
4. **Submit** — Upload the XML to Crossref for DOI registration or updates

### Library

```python
from crossref_xml import download_prefix, generate_xml, validate_xml
import pandas as pd

# Download existing metadata
df = download_prefix('10.1234', email='you@example.org')
df.to_csv('my-dois.csv', index=False)

# Or download only most recent 500 records
df = download_prefix('10.1234', email='you@example.org', limit=500)
df.to_csv('my-dois.csv', index=False)

# After editing...
df = pd.read_csv('my-dois-edited.csv')
xml = generate_xml(
    data=df,
    depositor_name='Library Name',
    depositor_email='library@example.org',
    registrant='Library Name',
    include_references=True
)

# Optional: check against the Crossref XSD (run scripts/fetch_crossref_schema.py first)
errors = validate_xml(xml)
if errors:
    raise SystemExit('\n'.join(errors))

with open('crossref-update.xml', 'w') as f:
    f.write(xml)
```

## CSV Format

### Required Columns

| Column | Description |
|--------|-------------|
| `doi` | The DOI being registered, as a bare DOI (`10.1234/abc`, not `https://doi.org/...`) |
| `title` | Article title |
| `publication` | Journal or series name |
| `authors` | Semicolon-delimited author list (the column must exist; a cell may be blank) |
| `publication_date` | ISO format: `YYYY`, `YYYY-MM`, or `YYYY-MM-DD` |
| `resource_url` | Landing page URL (`http://` or `https://`) |

`publication_date` and `resource_url` are required because the Crossref 5.3.1 schema makes both mandatory for journal articles. Without them the XML would always be rejected.

### Optional Columns

| Column | Description |
|--------|-------------|
| `volume` | Volume number |
| `issue` | Issue number |
| `pages` | Page range (e.g., `1-45`) |
| `abstract` | Article abstract |
| `abbrev_title` | Journal title abbreviation (e.g., `J. Appl. Ecol.`); omitted from XML when blank |
| `issn_print` | Print ISSN |
| `issn_electronic` | Electronic ISSN |
| `pdf_url` | Direct PDF link (enables text mining) |
| `references` | JSON array of citations |
| `type` | Crossref work type from download; any value other than `journal-article` is rejected |

### Author Notation

Authors use `Surname, Given` format with optional bracketed metadata:

```
Chen, Maria ORCID[https://orcid.org/0000-0001-2345-6789] ORG[Riverside University] ROR[https://ror.org/abc123]
```

Multiple authors separated by semicolons:

```
Chen, Maria; Okonkwo, David ORG[Field Research Institute]
```

Multiple affiliations for one author:

```
Larsson, Erik ORG[Northern College; Marine Biology Center] ROR[https://ror.org/def456; https://ror.org/ghi789]
```

ORG and ROR entries pair by position. Leave a slot empty when only some affiliations have a ROR ID:

```
Larsson, Erik ORG[Northern College; Marine Biology Center] ROR[; https://ror.org/ghi789]
```

An organization as author (for example, a consortium), with no person name:

```
ORG[Pollinator Survey Consortium]
```

A person with only one name:

```
Plato,
```

The download function automatically formats author data from Crossref in this notation. An author entry that can't be converted without losing information is reported as an error instead of being skipped. Examples: a missing comma, an unknown bracket such as `ISNI[...]`, or a malformed ORCID.

### References Format

References stored as a JSON array:

```json
[
  {"key": "ref1", "DOI": "10.1234/cited.2020.001", "doi-asserted-by": "publisher"},
  {"key": "ref2", "unstructured": "Author, A. (2019). Title. Journal, 10(2), 45-67."}
]
```

See `docs/csv-guide.md` for detailed field documentation including transformation examples and edge cases.

## Supported and Omitted Metadata

This is not a lossless Crossref round trip. The CSV carries only the fields below. Everything else on an existing Crossref record is **not downloaded and not written back**.

| Area | Carried through download → CSV → XML | Omitted |
|------|--------------------------------------|---------|
| Record types | Journal articles | Book chapters, books, datasets, conference papers, posted content, peer reviews, components, and all other types (rejected at conversion) |
| Titles | First article title; journal full title and abbreviation | Subtitles, original-language titles, multiple journal titles |
| Contributors | Authors (people and organizations), in order; ORCID; affiliation names; one ROR per affiliation | Editors, translators, and other roles; suffixes; alternate names; ISNI/Wikidata affiliation IDs; extra RORs per affiliation; affiliations or IDs on organization authors |
| Dates | One publication date (from Crossref's `issued`), written as `media_type="online"` | Separate print/online dates; acceptance date |
| Numbering | Volume, issue, first/last page | Article numbers, other pages, special numbering |
| Identifiers & links | DOI, landing page, one PDF link (Similarity Check + text-mining collections), print/electronic ISSN | Other resource collections, multiple resolution, CODEN, archive locations |
| Abstract | Plain text (JATS `<p>` tags stripped) | Other JATS markup appears as literal text; multiple abstracts |
| References | Citation key, publisher-asserted DOI, unstructured citation | Structured citation fields (author, year, journal title, ...) and non-publisher-asserted DOIs |
| License | One content (version-of-record) license URL applied to every record in the file | Per-record licenses, AM/TDM licenses, free-to-read dates |
| Not modeled | — | Funding, Crossmark/updates, relations, clinical trials, component lists, language |

## API Reference

### download_prefix(prefix, email=None, limit=None, sort_by='deposited') → DataFrame

Download works for a DOI prefix from Crossref API.

- `prefix`: DOI prefix (e.g., '10.1234')
- `email`: Optional contact email for Crossref polite pool (faster rate limits)
- `limit`: Optional maximum number of records to download (None = all records, maximum 10,000)
- `sort_by`: Field to sort by when limit is specified ('deposited', 'updated', 'indexed', 'published'). Defaults to 'deposited' for most recent records.

Raises `ValueError` if a page in the middle of the download is invalid rather than returning partial data. HTTP and network errors propagate as `requests` exceptions. The result includes a `type` column; non-journal-article rows must be removed before conversion.

### generate_xml(data, depositor_name, depositor_email, registrant, include_references=False, license_url=None) → str

Generate Crossref 5.3.1 XML from DataFrame. Every row becomes exactly one record, or a `ValueError` lists what must be fixed; rows are never silently skipped or truncated.

- `data`: DataFrame with required columns (at most 500 rows)
- `depositor_name`: Organization registering the DOIs
- `depositor_email`: Contact email for registration issues
- `registrant`: Registrant identifier (usually same as depositor_name)
- `include_references`: Include citation list in output. Unparseable reference cells are then errors.
- `license_url`: Optional license URL for the **article content** (version of record), e.g. a Creative Commons license, emitted as `<ai:license_ref applies_to="vor">` on every record. It does not license the metadata. If None, no license element is added.

### validate_csv(df, include_references=False) → list

Check DataFrame for required columns and per-record validity (blank or whitespace-only required values, DOI format, duplicate DOIs, real calendar dates, URLs, ISSNs, author notation, record type). Returns a list of error messages with spreadsheet row numbers.

### validate_xml(xml, schema=None) → list

Validate XML against the Crossref 5.3.1 XSD without network access. Returns error messages with line numbers. Requires `scripts/fetch_crossref_schema.py` to have been run, or `CROSSREF_SCHEMA_DIR` to be set.

### parse_contributors(authors_str) → list

Parse author string with bracket notation into structured data. Raises `ValueError` for entries that cannot be represented.

## Validation

Validation happens at three levels, each catching things the one before cannot:

1. **Input validation** (`validate_csv`, run automatically by `generate_xml`) catches missing or malformed values before any XML is produced.
2. **Schema validation** (`validate_xml`) checks the XML against the official Crossref 5.3.1 XSD, including limits such as the 60-character name maximum. The test suite runs representative output through it.
3. **Crossref's deposit processing** applies rules no schema can express: prefix ownership, title and ISSN matching against existing journals, and so on. Schema-valid XML can still be rejected, so always read the submission log Crossref returns.

You can also check files with the [Crossref Metadata Parser](https://www.crossref.org/02publishers/parser.html) before submission.

Spot-check a few records manually against your source data—automated transformations can propagate errors silently across hundreds of records.

## Limitations

These limits come from different places:

- **This tool: 500 records per XML file.** An application limit, not a Crossref rule. Larger CSVs are rejected with an error; split them into files of 500 rows or fewer. The limit keeps typical files far below Crossref's size cap and makes errors easy to trace.
- **Crossref deposits: 10 MB per file.** Crossref's documented limit for XML uploads through the admin tool or HTTPS POST. Crossref does not document a per-file record count.
- **Crossref REST API (downloads).** At most 1,000 rows per request; this tool requests 500 per page. Sorted "most recent" downloads use offset paging, which the API allows only up to 10,000 records. Full downloads use cursor paging, which has no such cap.
- Journal articles only (no books, datasets, or conference papers); other types are refused rather than converted
- Generates XML for submission; does not submit directly to Crossref

## License

[CC0 1.0 Universal](LICENSE)
