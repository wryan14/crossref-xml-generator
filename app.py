"""Crossref XML Generator - Web interface for downloading and converting Crossref metadata."""

import logging

import pandas as pd
from flask import Flask, render_template_string, request, jsonify

from crossref_xml import generate_xml, download_prefix

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Crossref XML Generator</title>
    <style>
        :root {
            --primary: #64748b;
            --text-primary: #111827;
            --text-secondary: #6b7280;
            --bg-primary: #ffffff;
            --bg-subtle: #f3f4f6;
            --border: #e5e7eb;
            --error: #dc2626;
            --success: #059669;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            font-size: 16px;
            line-height: 1.5;
            color: var(--text-primary);
            background: var(--bg-primary);
            padding: 16px;
        }

        .container {
            max-width: 800px;
            margin: 0 auto;
        }

        h1 {
            font-size: 28px;
            font-weight: 600;
            line-height: 1.2;
            margin-bottom: 8px;
        }

        h2 {
            font-size: 20px;
            font-weight: 600;
            margin-bottom: 16px;
        }

        .subtitle {
            color: var(--text-secondary);
            margin-bottom: 32px;
        }

        .section {
            background: var(--bg-subtle);
            padding: 24px;
            margin-bottom: 24px;
        }

        .tabs {
            display: flex;
            gap: 0;
            margin-bottom: 24px;
            border-bottom: 2px solid var(--border);
        }

        .tab {
            padding: 12px 24px;
            background: none;
            border: none;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            color: var(--text-secondary);
            border-bottom: 2px solid transparent;
            margin-bottom: -2px;
        }

        .tab:hover {
            color: var(--text-primary);
        }

        .tab.active {
            color: var(--text-primary);
            border-bottom-color: var(--primary);
        }

        .tab-content {
            display: none;
        }

        .tab-content.active {
            display: block;
        }

        fieldset {
            border: none;
            margin-bottom: 24px;
        }

        legend {
            font-weight: 600;
            margin-bottom: 16px;
        }

        label {
            display: block;
            font-weight: 600;
            margin-bottom: 8px;
        }

        input[type="text"],
        input[type="email"] {
            display: block;
            width: 100%;
            padding: 12px;
            background: var(--bg-primary);
            border: 1px solid var(--border);
            margin-bottom: 16px;
            font-size: 16px;
            font-family: inherit;
        }

        input[type="file"] {
            display: block;
            width: 100%;
            padding: 12px;
            background: var(--bg-primary);
            border: 1px solid var(--border);
            margin-bottom: 16px;
            font-size: 14px;
        }

        input[type="checkbox"] {
            width: 20px;
            height: 20px;
            margin: 0;
        }

        .field-hint {
            font-size: 14px;
            color: var(--text-secondary);
            margin-top: -12px;
            margin-bottom: 16px;
        }

        .checkbox-group {
            padding: 16px;
            background: var(--bg-primary);
            border: 1px solid var(--border);
        }

        .checkbox-label {
            display: flex;
            align-items: center;
            cursor: pointer;
            gap: 8px;
        }

        button {
            background: var(--primary);
            color: white;
            border: none;
            padding: 12px 24px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            min-height: 44px;
        }

        button:hover {
            opacity: 0.9;
        }

        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .status {
            margin-top: 24px;
            padding: 16px;
            background: var(--bg-subtle);
            display: none;
        }

        .status.show {
            display: block;
        }

        .status.error {
            border-left: 4px solid var(--error);
            color: var(--error);
        }

        .status.success {
            border-left: 4px solid var(--success);
            color: var(--success);
        }

        .processing {
            padding: 12px 16px;
            background: var(--bg-primary);
            border: 1px solid var(--border);
            color: var(--text-secondary);
            font-size: 14px;
            display: none;
            margin-top: 24px;
        }

        .processing.show {
            display: block;
        }

        .download-section {
            margin-top: 24px;
            padding: 24px;
            background: var(--bg-subtle);
            display: none;
        }

        .download-section.show {
            display: block;
        }

        .download-btn {
            background: var(--success);
        }

        .workflow {
            background: var(--bg-primary);
            padding: 16px;
            margin-bottom: 24px;
            border: 1px solid var(--border);
        }

        .workflow h3 {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 12px;
        }

        .workflow ol {
            margin-left: 24px;
            font-size: 14px;
        }

        .workflow li {
            margin-bottom: 8px;
        }

        footer {
            margin-top: 48px;
            padding-top: 24px;
            border-top: 1px solid var(--border);
            font-size: 14px;
            color: var(--text-secondary);
        }

        footer a {
            color: var(--text-secondary);
        }

        @media (min-width: 768px) {
            body {
                padding: 32px;
            }

            h1 {
                font-size: 32px;
            }

            .section {
                padding: 32px;
            }

            .input-row {
                display: flex;
                gap: 16px;
            }

            .input-row > div {
                flex: 1;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Crossref XML Generator</h1>
        <p class="subtitle">Download, edit, and convert metadata for DOI registration</p>

        <div class="workflow">
            <h3>Workflow</h3>
            <ol>
                <li><strong>Download</strong> - Pull existing metadata from Crossref by DOI prefix</li>
                <li><strong>Edit</strong> - Filter and modify records in your spreadsheet (add ORCIDs, fix affiliations)</li>
                <li><strong>Convert</strong> - Generate Crossref XML from your edited CSV for submission</li>
            </ol>
        </div>

        <div class="tabs">
            <button class="tab active" data-tab="download">Download from Crossref</button>
            <button class="tab" data-tab="convert">Convert CSV to XML</button>
        </div>

        <!-- Download Tab -->
        <div id="download-tab" class="tab-content active">
            <div class="section">
                <h2>Download Metadata by DOI Prefix</h2>
                <form id="download-form">
                    <label for="doi-prefix">DOI Prefix</label>
                    <input type="text" id="doi-prefix" name="prefix" placeholder="10.1234" required>
                    <div class="field-hint">Your organization's DOI prefix (e.g., 10.1234)</div>

                    <label for="contact-email">Contact Email (optional)</label>
                    <input type="email" id="contact-email" name="email" placeholder="you@example.org">
                    <div class="field-hint">Providing an email enables faster API access via Crossref's polite pool</div>

                    <button type="submit">Download Metadata</button>
                </form>

                <div id="download-processing" class="processing"></div>
                <div id="download-status" class="status"></div>
                <div id="download-result" class="download-section">
                    <p style="margin-bottom: 16px; font-weight: 600;">Download Complete</p>
                    <a id="csv-download-link" href="#" download="crossref-metadata.csv">
                        <button type="button" class="download-btn">Download CSV</button>
                    </a>
                </div>
            </div>
        </div>

        <!-- Convert Tab -->
        <div id="convert-tab" class="tab-content">
            <div class="section">
                <h2>Convert CSV to Crossref XML</h2>
                <form id="convert-form" enctype="multipart/form-data">
                    <fieldset>
                        <legend>Depositor Information</legend>
                        <div class="input-row">
                            <div>
                                <label for="depositor-name">Depositor Name</label>
                                <input type="text" id="depositor-name" name="depositor_name" required>
                                <div class="field-hint">Organization registering the DOIs</div>
                            </div>
                            <div>
                                <label for="depositor-email">Depositor Email</label>
                                <input type="email" id="depositor-email" name="depositor_email" required>
                                <div class="field-hint">Contact email for registration issues</div>
                            </div>
                        </div>
                        <label for="registrant">Registrant</label>
                        <input type="text" id="registrant" name="registrant" required>
                        <div class="field-hint">Usually same as depositor name</div>
                    </fieldset>

                    <fieldset>
                        <legend>CSV Upload</legend>
                        <label for="csv-file">Metadata CSV File</label>
                        <input type="file" id="csv-file" name="csv_file" accept=".csv" required>
                        <div class="field-hint">Required columns: doi, title, publication, authors</div>

                        <div class="checkbox-group">
                            <label class="checkbox-label">
                                <input type="checkbox" id="include-references" name="include_references">
                                <span>Include references in XML output</span>
                            </label>
                        </div>
                    </fieldset>

                    <button type="submit">Generate XML</button>
                </form>

                <div id="convert-processing" class="processing"></div>
                <div id="convert-status" class="status"></div>
                <div id="convert-result" class="download-section">
                    <p style="margin-bottom: 16px; font-weight: 600;">XML Generation Complete</p>
                    <a id="xml-download-link" href="#" download="crossref.xml">
                        <button type="button" class="download-btn">Download XML</button>
                    </a>
                </div>
            </div>
        </div>

        <footer>
            <a href="https://github.com/wryan14/crossref-xml-generator" target="_blank">Source on GitHub</a> ·
            <a href="https://creativecommons.org/publicdomain/zero/1.0/" target="_blank">CC0 1.0</a>
        </footer>
    </div>

    <script>
        // Tab switching
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

                tab.classList.add('active');
                document.getElementById(tab.dataset.tab + '-tab').classList.add('active');
            });
        });

        // Load saved depositor info
        const savedDepositorName = localStorage.getItem('crossref_depositor_name');
        const savedDepositorEmail = localStorage.getItem('crossref_depositor_email');
        const savedRegistrant = localStorage.getItem('crossref_registrant');
        const savedContactEmail = localStorage.getItem('crossref_contact_email');

        if (savedDepositorName) document.getElementById('depositor-name').value = savedDepositorName;
        if (savedDepositorEmail) document.getElementById('depositor-email').value = savedDepositorEmail;
        if (savedRegistrant) document.getElementById('registrant').value = savedRegistrant;
        if (savedContactEmail) document.getElementById('contact-email').value = savedContactEmail;

        // Download form
        const downloadForm = document.getElementById('download-form');
        const downloadProcessing = document.getElementById('download-processing');
        const downloadStatus = document.getElementById('download-status');
        const downloadResult = document.getElementById('download-result');
        const csvDownloadLink = document.getElementById('csv-download-link');

        downloadForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const prefix = document.getElementById('doi-prefix').value.trim();
            const email = document.getElementById('contact-email').value.trim();

            if (email) {
                localStorage.setItem('crossref_contact_email', email);
            }

            downloadProcessing.textContent = 'Fetching metadata from Crossref API (this may take a minute for large collections)...';
            downloadProcessing.className = 'processing show';
            downloadStatus.className = 'status';
            downloadResult.className = 'download-section';
            downloadForm.querySelector('button').disabled = true;

            try {
                const params = new URLSearchParams({ prefix });
                if (email) params.append('email', email);

                const response = await fetch('/download?' + params.toString());
                const result = await response.json();

                downloadProcessing.className = 'processing';
                downloadForm.querySelector('button').disabled = false;

                if (result.success) {
                    downloadStatus.className = 'status success show';
                    downloadStatus.textContent = result.message;

                    const blob = new Blob([result.csv], { type: 'text/csv' });
                    const url = URL.createObjectURL(blob);
                    csvDownloadLink.href = url;
                    csvDownloadLink.download = prefix.replace('/', '-') + '-metadata.csv';
                    downloadResult.className = 'download-section show';
                } else {
                    downloadStatus.className = 'status error show';
                    downloadStatus.textContent = 'Error: ' + result.message;
                }
            } catch (error) {
                downloadProcessing.className = 'processing';
                downloadForm.querySelector('button').disabled = false;
                downloadStatus.className = 'status error show';
                downloadStatus.textContent = 'Error: Failed to fetch data. Please try again.';
            }
        });

        // Convert form
        const convertForm = document.getElementById('convert-form');
        const convertProcessing = document.getElementById('convert-processing');
        const convertStatus = document.getElementById('convert-status');
        const convertResult = document.getElementById('convert-result');
        const xmlDownloadLink = document.getElementById('xml-download-link');

        convertForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            // Save depositor info
            const depositorName = document.getElementById('depositor-name').value;
            const depositorEmail = document.getElementById('depositor-email').value;
            const registrant = document.getElementById('registrant').value;

            localStorage.setItem('crossref_depositor_name', depositorName);
            localStorage.setItem('crossref_depositor_email', depositorEmail);
            localStorage.setItem('crossref_registrant', registrant);

            const formData = new FormData(convertForm);
            const includeReferences = document.getElementById('include-references').checked;
            formData.set('include_references', includeReferences);

            convertProcessing.textContent = 'Converting CSV to Crossref XML...';
            convertProcessing.className = 'processing show';
            convertStatus.className = 'status';
            convertResult.className = 'download-section';
            convertForm.querySelector('button[type="submit"]').disabled = true;

            try {
                const response = await fetch('/convert', {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();

                convertProcessing.className = 'processing';
                convertForm.querySelector('button[type="submit"]').disabled = false;

                if (result.success) {
                    convertStatus.className = 'status success show';
                    convertStatus.textContent = result.message;

                    const blob = new Blob([result.xml], { type: 'text/xml' });
                    const url = URL.createObjectURL(blob);
                    xmlDownloadLink.href = url;

                    const timestamp = new Date().toISOString().slice(0, 10);
                    xmlDownloadLink.download = timestamp + '-crossref.xml';

                    convertResult.className = 'download-section show';
                } else {
                    convertStatus.className = 'status error show';
                    convertStatus.textContent = 'Error: ' + result.message;
                }
            } catch (error) {
                convertProcessing.className = 'processing';
                convertForm.querySelector('button[type="submit"]').disabled = false;
                convertStatus.className = 'status error show';
                convertStatus.textContent = 'Error: Failed to convert file. Please try again.';
            }
        });
    </script>
</body>
</html>
"""


@app.route('/')
def home():
    """Serve the main interface."""
    return render_template_string(HTML_TEMPLATE)


@app.route('/download')
def download():
    """Download metadata from Crossref API by DOI prefix.

    Query params:
        prefix: DOI prefix (required)
        email: Contact email for polite pool (optional)

    Returns:
        JSON with keys: success (bool), message (str), csv (str on success)
    """
    prefix = request.args.get('prefix', '').strip()
    email = request.args.get('email', '').strip()

    if not prefix:
        return jsonify({'success': False, 'message': 'DOI prefix is required'})

    if not prefix.startswith('10.'):
        return jsonify({'success': False, 'message': 'DOI prefix must start with 10.'})

    try:
        logger.info(f"Downloading metadata for prefix {prefix}")
        df = download_prefix(prefix, email if email else None)

        csv_buffer = df.to_csv(index=False)
        record_count = len(df)

        logger.info(f"Downloaded {record_count} records for prefix {prefix}")
        return jsonify({
            'success': True,
            'message': f'Downloaded {record_count} records',
            'csv': csv_buffer
        })

    except ValueError as e:
        logger.warning(f"Download failed for {prefix}: {e}")
        return jsonify({'success': False, 'message': str(e)})
    except Exception as e:
        logger.error(f"Unexpected error downloading {prefix}: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Failed to download metadata. Check the DOI prefix and try again.'})


@app.route('/convert', methods=['POST'])
def convert():
    """Convert uploaded CSV to Crossref XML.

    Returns:
        JSON with keys: success (bool), message (str), xml (str on success)
    """
    try:
        csv_file = request.files.get('csv_file')
        depositor_name = request.form.get('depositor_name', '').strip()
        depositor_email = request.form.get('depositor_email', '').strip()
        registrant = request.form.get('registrant', '').strip()
        include_references = request.form.get('include_references', 'false').lower() == 'true'

        if not csv_file or not csv_file.filename:
            return jsonify({'success': False, 'message': 'CSV file is required'})

        if not csv_file.filename.endswith('.csv'):
            return jsonify({'success': False, 'message': 'File must be a CSV'})

        if not depositor_name:
            return jsonify({'success': False, 'message': 'Depositor name is required'})

        if not depositor_email:
            return jsonify({'success': False, 'message': 'Depositor email is required'})

        if not registrant:
            return jsonify({'success': False, 'message': 'Registrant is required'})

        try:
            data = pd.read_csv(csv_file)
        except pd.errors.EmptyDataError:
            return jsonify({'success': False, 'message': 'CSV file is empty'})
        except pd.errors.ParserError as e:
            logger.error(f"CSV parse error: {e}")
            return jsonify({'success': False, 'message': 'Invalid CSV format'})

        logger.info(f"Processing {len(data)} records, include_references={include_references}")

        try:
            xml_content = generate_xml(
                data=data,
                depositor_name=depositor_name,
                depositor_email=depositor_email,
                registrant=registrant,
                include_references=include_references
            )
        except ValueError as e:
            return jsonify({'success': False, 'message': str(e)})

        record_count = min(len(data), 500)
        message = f'Generated XML for {record_count} records'
        if include_references:
            message += ' with references'

        logger.info(message)
        return jsonify({
            'success': True,
            'message': message,
            'xml': xml_content
        })

    except Exception as e:
        logger.error(f"Unexpected error: {type(e).__name__} - {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'An unexpected error occurred'})


if __name__ == '__main__':
    app.run(debug=True)
