# CSV Field Guide

A detailed walkthrough of how CSV fields translate to Crossref XML, with examples and edge cases.

## Complete Record Example

**CSV row:**
```
doi,title,publication,authors,publication_date,volume,issue,pages,abstract,resource_url,pdf_url,issn_print,issn_electronic,references
10.1234/example.2024.001,Pollinator Diversity in Urban Garden Ecosystems,Journal of Applied Ecology,"Chen, Maria ORCID[https://orcid.org/0000-0001-2345-6789] ORG[Riverside University] ROR[https://ror.org/abc123]; Okonkwo, David ORG[Field Research Institute]",2024-03,12,1,1-45,This study surveys bee and butterfly populations across 47 urban gardens to assess biodiversity indicators.,https://example.org/papers/001,https://example.org/papers/001.pdf,1234-5678,8765-4321,"[{""key"": ""ref1"", ""DOI"": ""10.1000/cited.2020.001"", ""doi-asserted-by"": ""publisher""}]"
```

**Resulting XML (abbreviated):**
```xml
<journal>
  <journal_metadata>
    <full_title>Journal of Applied Ecology</full_title>
    <issn media_type="print">1234-5678</issn>
    <issn media_type="electronic">8765-4321</issn>
  </journal_metadata>
  <journal_issue>
    <publication_date media_type="online">
      <month>03</month>
      <year>2024</year>
    </publication_date>
    <journal_volume><volume>12</volume></journal_volume>
    <issue>1</issue>
  </journal_issue>
  <journal_article publication_type="full_text">
    <titles><title>Pollinator Diversity in Urban Garden Ecosystems</title></titles>
    <contributors>
      <person_name contributor_role="author" sequence="first">
        <given_name>Maria</given_name>
        <surname>Chen</surname>
        <affiliations>
          <institution>
            <institution_name>Riverside University</institution_name>
            <institution_id type="ror">https://ror.org/abc123</institution_id>
          </institution>
        </affiliations>
        <ORCID>https://orcid.org/0000-0001-2345-6789</ORCID>
      </person_name>
      <person_name contributor_role="author" sequence="additional">
        <given_name>David</given_name>
        <surname>Okonkwo</surname>
        <affiliations>
          <institution><institution_name>Field Research Institute</institution_name></institution>
        </affiliations>
      </person_name>
    </contributors>
    <jats:abstract><jats:p>This study surveys bee and butterfly populations...</jats:p></jats:abstract>
    <publication_date media_type="online">
      <month>03</month>
      <year>2024</year>
    </publication_date>
    <pages>
      <first_page>1</first_page>
      <last_page>45</last_page>
    </pages>
    <doi_data>
      <doi>10.1234/example.2024.001</doi>
      <resource>https://example.org/papers/001</resource>
      <collection property="crawler-based">
        <item crawler="iParadigms"><resource>https://example.org/papers/001.pdf</resource></item>
      </collection>
      <collection property="text-mining">
        <item><resource content_version="vor" mime_type="application/pdf">https://example.org/papers/001.pdf</resource></item>
      </collection>
    </doi_data>
    <citation_list>
      <citation key="ref1"><doi>10.1000/cited.2020.001</doi></citation>
    </citation_list>
  </journal_article>
</journal>
```

## Field Reference

### Required Fields

Conversion is all-or-nothing: if any row has a problem, no XML is produced and every problem is listed as `Row N (doi): message`. Row numbers match your spreadsheet, with the header in row 1. Blank and whitespace-only values count as empty.

| Field | Rule |
|-------|------|
| `doi` | Bare DOI matching `10.NNNN/suffix` (4–9 digit registrant code). `https://doi.org/` prefixes are rejected. Duplicate DOIs in one file are rejected (case-insensitive) |
| `title` | Must not be empty |
| `publication` | Must not be empty; at most 255 characters |
| `authors` | Column must exist; a blank cell produces no `<contributors>` element. Non-blank cells must parse (see Author Notation) |
| `publication_date` | Must be a real date in one of the formats below. Required by the Crossref schema |
| `resource_url` | Absolute `http://` or `https://` URL. Required by the Crossref schema |

### Publication Date

Accepts three formats:

| Format | Example | XML Output |
|--------|---------|------------|
| Year only | `2024` | `<year>2024</year>` |
| Year-month | `2024-03` | `<month>03</month><year>2024</year>` |
| Full date | `2024-03-15` | `<month>03</month><day>15</day><year>2024</year>` |

Single-digit months and days (`2024-3-5`) are zero-padded. Impossible dates (`2024-13`, `2023-02-29`) and years outside 1400–2200 are rejected. If a spreadsheet saves years as numbers (`2024.0`), they are written as `2024`.

The date appears twice in the XML: once in `<journal_issue>` and once in `<journal_article>`. Both are set from this single field and are marked `media_type="online"`. Downloaded dates come from Crossref's `issued` date, which may actually be a print date.

### ISSNs

Either format works—dashes are normalized automatically:

- `1234-5678` → `1234-5678`
- `12345678` → `1234-5678`
- `1234-567x` → `1234-567X`

Both print and electronic ISSNs are optional. If only one exists, only that one appears in the XML. A value that is not 8 characters (7 digits plus a digit or `X`) is an error. Check digits are not verified.

### Journal Abbreviation

`abbrev_title` is optional and written as-is, up to 150 characters. When the column is missing or blank, no `<abbrev_title>` is emitted; the tool never makes one up. Downloads fill it from Crossref's `short-container-title`.

### Pages

| Input | Output |
|-------|--------|
| `1-45` | `<first_page>1</first_page><last_page>45</last_page>` |
| `112` | `<first_page>112</first_page>` |
| `e1234` | `<first_page>e1234</first_page>` |
| Empty | No `<pages>` element |

### Volume and Issue

Both optional. Float values like `12.0` are converted to integers (`12`).

### PDF URL

When provided, enables two features:

1. **Crawler access** for plagiarism detection services (iParadigms/Turnitin)
2. **Text mining** collection for research tools

If you don't want these features, leave the field empty. A non-empty value must be an absolute `http(s)` URL.

### Record Type

Downloads include a `type` column with the Crossref work type. Only `journal-article` rows can be converted, because every record is written as `<journal_article>`. Other types (`book-chapter`, `dataset`, `posted-content`, ...) are errors, so remove those rows before converting. CSVs without a `type` column, or with blank types, are treated as journal articles.

## Author Notation

### Basic Format

```
Surname, Given
```

Multiple authors separated by semicolons:

```
Chen, Maria; Okonkwo, David; Larsson, Erik
```

The first author gets `sequence="first"`, all others get `sequence="additional"`.

For a person with a single name, keep the comma and leave the given name empty. No `<given_name>` element is written:

```
Plato,
```

### Adding Metadata

Bracket notation appends structured data:

| Notation | Purpose | Example |
|----------|---------|---------|
| `ORCID[url]` | Researcher identifier | `ORCID[https://orcid.org/0000-0001-2345-6789]` |
| `ORG[name]` | Institutional affiliation | `ORG[Riverside University]` |
| `ROR[url]` | Organization identifier | `ROR[https://ror.org/abc123]` |

Full example:

```
Chen, Maria ORCID[https://orcid.org/0000-0001-2345-6789] ORG[Riverside University] ROR[https://ror.org/abc123]
```

ORCIDs may be written as `https://orcid.org/…`, `http://orcid.org/…`, `orcid.org/…`, or the bare `0000-0000-0000-0000` form; all are written as `https://orcid.org/…`. A malformed ORCID is an error. Check digits are not verified.

### Organizations as Authors

An entry with no person name and a single `ORG[...]` bracket is an organization author, written as `<organization>`:

```
Chen, Maria; ORG[Pollinator Survey Consortium]
```

Semicolons inside the brackets are part of the organization name. Crossref 5.3.1 organization contributors cannot carry ORCID, ROR, or affiliations, so combining them with a nameless entry is an error.

### Multiple Affiliations

Separate with semicolons inside the brackets. ROR IDs are matched to affiliations by position:

```
Larsson, Erik ORG[Northern College; Marine Biology Center] ROR[https://ror.org/def456; https://ror.org/ghi789]
```

This produces:

```xml
<affiliations>
  <institution>
    <institution_name>Northern College</institution_name>
    <institution_id type="ror">https://ror.org/def456</institution_id>
  </institution>
  <institution>
    <institution_name>Marine Biology Center</institution_name>
    <institution_id type="ror">https://ror.org/ghi789</institution_id>
  </institution>
</affiliations>
```

When only some affiliations have a ROR, leave the other slots empty so each ID stays with its institution:

```
Larsson, Erik ORG[Northern College; Marine Biology Center] ROR[; https://ror.org/ghi789]
```

Without the empty slot, `ROR[https://ror.org/ghi789]` would be paired with Northern College, the first affiliation. Downloads always write the empty slots for you.

A ROR with no matching name produces an institution with only the identifier, which Crossref 5.3.1 allows:

```
Case, Nicole ROR[https://ror.org/03wmf1y16]
```

### Affiliation Without ROR

If you have an organization name but no ROR ID, just omit the ROR bracket:

```
Okonkwo, David ORG[Field Research Institute]
```

### ROR URL Formats

All of these normalize to `https://ror.org/abc123`:

- `https://ror.org/abc123`
- `ror.org/abc123`
- `abc123`

### Errors Instead of Dropped Authors

These entries are reported as errors rather than skipped:

- A person name without a comma (`Maria Chen`)
- Unrecognized brackets (`ISNI[...]`) or more than one `ORCID[...]`
- Nameless entries that are not a single `ORG[...]`
- Surnames or given names longer than 60 characters (Crossref's limit)

When downloading, Crossref authors this format cannot represent are logged as warnings. Examples: an author with only a given name, or an organization author with affiliations. Semicolons and square brackets inside downloaded names are replaced with commas and parentheses so the notation stays parseable, and a warning is logged.

## References

### Format

JSON array of citation objects:

```json
[
  {"key": "ref1", "DOI": "10.1000/cited.2020.001", "doi-asserted-by": "publisher"},
  {"key": "ref2", "unstructured": "Author, A. (2019). Title. Journal, 10(2), 45-67."}
]
```

### Important: doi-asserted-by

DOIs are only included in XML when `"doi-asserted-by": "publisher"` is present. This is a Crossref convention indicating the DOI was verified by the citing publisher.

| Reference | XML Output |
|-----------|------------|
| `{"key": "ref1", "DOI": "10.1000/x", "doi-asserted-by": "publisher"}` | `<citation key="ref1"><doi>10.1000/x</doi></citation>` |
| `{"key": "ref2", "DOI": "10.1000/x", "doi-asserted-by": "crossref"}` | `<citation key="ref2"></citation>` (DOI omitted) |
| `{"key": "ref3", "DOI": "10.1000/x"}` | `<citation key="ref3"></citation>` (DOI omitted) |

If you're adding references manually and want the DOI included, add `"doi-asserted-by": "publisher"`.

Structured fields from downloaded references (`author`, `year`, `journal-title`, `volume`, `first-page`, ...) are not written to XML. A downloaded reference with neither a publisher-asserted DOI nor an `unstructured` value becomes an empty `<citation>`.

### Citation Keys

Crossref requires every citation to have a key of 1–128 characters. References without a `key` are numbered by position (`ref1`, `ref2`, ...). Keys longer than 128 characters are an error.

### Unstructured Citations

For references without DOIs, use the `unstructured` field:

```json
{"key": "ref5", "unstructured": "Author, A. (2019). Title of work. Journal Name, 10(2), 45-67."}
```

### Enabling References

References are only included when you check "Include references in XML output" during conversion. The download function captures references from Crossref, but they're excluded from XML by default. When references are included, a cell that is not a JSON array of objects is an error. When they are excluded, the column is ignored.

## Processing Notes

### Record Limits

- Maximum 500 records per XML file. This is this tool's limit, not Crossref's.
- A CSV with more rows is rejected with an error. Nothing is truncated. Split the CSV into files of 500 rows or fewer.
- Crossref's own constraint for XML deposits is a 10 MB file size.

### No Silent Filtering

Earlier versions skipped rows with an empty `doi` or `title` without warning. Those rows are now errors, so the number of records in the XML always equals the number of rows in the CSV.

### License Element

A content license is optional and can be configured during XML generation. The web interface provides a dropdown with common Creative Commons licenses:

- None (no license element)
- CC0 1.0 Universal (Public Domain)
- CC BY 4.0 (Attribution)
- CC BY-SA 4.0 (Attribution-ShareAlike)
- CC BY-NC 4.0 (Attribution-NonCommercial)
- CC BY-ND 4.0 (Attribution-NoDerivatives)

When using the library directly, pass the `license_url` parameter:

```python
xml = generate_xml(data, ..., license_url='https://creativecommons.org/licenses/by/4.0/')
```

The license is written as `<ai:license_ref applies_to="vor">`, which Crossref defines as the license for the **version of record of the article content**. It does not license the metadata. The same URL is applied to every record in the file, so only choose one if it is true for all of those articles.

### Abstract Cleanup

JATS paragraph tags (`<jats:p>`, `</jats:p>`) are stripped from abstracts automatically. The Crossref download sometimes includes these; they're removed before XML generation. Other JATS markup (for example `<jats:italic>`) is not converted and will appear as literal text.

## Common Issues

**"must be 'Surname, Given'" error**: The author entry has no comma. Use `Surname, Given`, `Surname,` for a single name, or `ORG[Name]` for an organization.

**"publication_date is empty" or "resource_url is empty"**: Crossref requires both for every journal article. Downloaded CSVs include them; fill them in for new records.

**"type 'book-chapter' is not supported"**: The prefix contains non-article works. Filter the CSV to `journal-article` rows.

**Missing journal abbreviation**: `<abbrev_title>` only appears when the `abbrev_title` column has a value.

**References not appearing**: Ensure "Include references" is checked, and that DOI references include `"doi-asserted-by": "publisher"`.

**ISSN errors**: ISSNs must be exactly 8 characters once dashes are removed. Values like `1234-567` (7 digits) are reported as errors.

**Schema-valid but rejected by Crossref**: The XSD cannot check prefix ownership or journal title/ISSN matching. Read the submission log Crossref sends after each deposit.
