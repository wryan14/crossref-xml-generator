# Crossref XML Generator

Download, edit, and convert metadata for DOI registration.

A web-based tool for metadata librarians to manage Crossref submissions without navigating complex XML schemas or APIs. Pull your existing DOI metadata, modify it in a spreadsheet, and generate valid Crossref 5.3.1 XML for submission.

## Features

- **Download** metadata from Crossref by DOI prefix
- **Edit** in your preferred spreadsheet application
- **Convert** CSV back to schema-compliant Crossref XML
- Supports ORCID, ROR, and affiliation metadata
- Optional reference/citation inclusion
- No accounts or server-side storage
- Also usable as a Python library

## Quick Start

```bash
pip install flask pandas lxml requests
python app.py
```

Open `http://localhost:5000` in your browser.

## Workflow

1. **Download** - Enter your DOI prefix to pull all existing metadata from Crossref
2. **Edit** - Open the CSV in Excel/Sheets, filter to records you want to update, add ORCIDs, fix affiliations
3. **Convert** - Upload your edited CSV to generate Crossref XML
4. **Submit** - Upload the XML to Crossref for DOI registration or updates

## CSV Format

The download produces (and convert expects) these columns:

### Required Columns

| Column | Description |
|--------|-------------|
| `doi` | The DOI being registered |
| `title` | Article title |
| `publication` | Journal or series name |
| `authors` | Semicolon-delimited author list |

### Optional Columns

| Column | Description |
|--------|-------------|
| `resource_url` | Landing page URL |
| `publication_date` | ISO format: `YYYY`, `YYYY-MM`, or `YYYY-MM-DD` |
| `volume` | Volume number |
| `issue` | Issue number |
| `pages` | Page range (e.g., `1-45`) |
| `abstract` | Article abstract |
| `issn_print` | Print ISSN |
| `issn_electronic` | Electronic ISSN |
| `pdf_url` | Direct PDF link (enables text mining) |
| `references` | JSON array of citations |

### Author Notation

Authors use `Surname, Given` format with optional bracketed metadata:

```
Smith, Jane ORCID[https://orcid.org/0000-0001-2345-6789] ORG[University of Example] ROR[https://ror.org/abc123]
```

Multiple authors separated by semicolons:

```
Smith, Jane; Johnson, Robert ORG[Research Institute]
```

Multiple affiliations for one author:

```
Smith, Jane ORG[University of Example; Research Center] ROR[https://ror.org/abc123; https://ror.org/def456]
```

The download function automatically formats author data from Crossref in this notation.

### References Format

References stored as a JSON array:

```json
[
  {"key": "ref1", "DOI": "10.1234/cited.2020.001", "doi-asserted-by": "publisher"},
  {"key": "ref2", "unstructured": "Author, A. (2019). Title. Journal, 10(2), 45-67."}
]
```

## Library Usage

```python
from crossref_xml import download_prefix, generate_xml

# Download existing metadata
df = download_prefix('10.1234', email='you@example.org')
df.to_csv('my-dois.csv', index=False)

# ... edit CSV in spreadsheet ...

# Generate XML from edited data
import pandas as pd
df = pd.read_csv('my-dois-edited.csv')

xml = generate_xml(
    data=df,
    depositor_name='Library Name',
    depositor_email='library@example.org',
    registrant='Library Name',
    include_references=True
)

with open('crossref-update.xml', 'w') as f:
    f.write(xml)
```

## API Reference

### download_prefix(prefix, email=None) -> DataFrame

Download all works for a DOI prefix from Crossref API.

- `prefix`: DOI prefix (e.g., '10.1234')
- `email`: Optional contact email for Crossref polite pool (faster rate limits)

### generate_xml(data, depositor_name, depositor_email, registrant, include_references=False) -> str

Generate Crossref 5.3.1 XML from DataFrame.

- `data`: DataFrame with required columns
- `depositor_name`: Organization registering the DOIs
- `depositor_email`: Contact email for registration issues
- `registrant`: Registrant identifier (usually same as depositor_name)
- `include_references`: Include citation list in output

### validate_csv(df) -> list

Check DataFrame for required columns. Returns list of error messages.

### parse_contributors(authors_str) -> list

Parse author string with bracket notation into structured data.

## Limitations

- Maximum 500 records per XML batch (Crossref API limit)
- Journal articles only (no books, datasets, or conference papers)
- Generates XML for submission; does not submit directly to Crossref

## License

[CC0 1.0 Universal](LICENSE) - Public Domain
