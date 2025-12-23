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
      <collection property="text-mining">
        <item><resource mime_type="application/pdf">https://example.org/papers/001.pdf</resource></item>
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

| Field | Behavior if Empty |
|-------|-------------------|
| `doi` | Row skipped entirely |
| `title` | Row skipped entirely |
| `publication` | Empty `<full_title>` element (may cause Crossref validation errors) |
| `authors` | No `<contributors>` element generated |

### Publication Date

Accepts three formats:

| Format | Example | XML Output |
|--------|---------|------------|
| Year only | `2024` | `<year>2024</year>` |
| Year-month | `2024-03` | `<month>03</month><year>2024</year>` |
| Full date | `2024-03-15` | `<month>03</month><day>15</day><year>2024</year>` |

The date appears twice in the XML: once in `<journal_issue>` and once in `<journal_article>`. Both are set from this single field.

### ISSNs

Either format works—dashes are normalized automatically:

- `1234-5678` → `1234-5678`
- `12345678` → `1234-5678`

Both print and electronic ISSNs are optional. If only one exists, only that one appears in the XML.

### Pages

| Input | Output |
|-------|--------|
| `1-45` | `<first_page>1</first_page><last_page>45</last_page>` |
| `112` | `<first_page>112</first_page>` |
| Empty | No `<pages>` element |

### Volume and Issue

Both optional. Float values like `12.0` are converted to integers (`12`). If `publication_date` is empty, the entire `<journal_issue>` element is omitted regardless of volume/issue values.

### PDF URL

When provided, enables two features:

1. **Crawler access** for plagiarism detection services (iParadigms/Turnitin)
2. **Text mining** collection for research tools

If you don't want these features, leave the field empty.

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

### Unstructured Citations

For references without DOIs, use the `unstructured` field:

```json
{"key": "ref5", "unstructured": "Author, A. (2019). Title of work. Journal Name, 10(2), 45-67."}
```

### Enabling References

References are only included when you check "Include references in XML output" during conversion. The download function captures references from Crossref, but they're excluded from XML by default.

## Processing Notes

### Record Limits

- Maximum 500 records per XML batch (Crossref API limit)
- Records beyond 500 are silently dropped

### Silent Filtering

Rows are excluded without warning when:

- `doi` is empty or null
- `title` is empty or null

### License Element

License metadata is optional and can be configured during XML generation. The web interface provides a dropdown with common Creative Commons licenses:

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

The license applies to the metadata only, not the article content.

### Abstract Cleanup

JATS paragraph tags (`<jats:p>`, `</jats:p>`) are stripped from abstracts automatically. The Crossref download sometimes includes these; they're removed before XML generation.

## Common Issues

**Empty contributors element**: If your author string doesn't follow `Surname, Given` format, no contributors are generated. Check for missing commas.

**Missing journal issue**: The `<journal_issue>` element only appears when `publication_date` has a value. Volume and issue alone won't create it.

**References not appearing**: Ensure "Include references" is checked, and that DOI references include `"doi-asserted-by": "publisher"`.

**ISSN validation failures**: ISSNs must be exactly 8 digits. Values like `1234-567` (7 digits) are silently dropped.
