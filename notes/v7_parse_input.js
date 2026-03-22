// Parse Input — extract task, credentials, files, create binary for PDF
const _helpers = _helpers;
const items = $input.all();
const body = items[0].json.body || items[0].json;
const task = body.prompt || body.task || '';
const base_url = (body.tripletex_credentials || {}).base_url || body.base_url || '';
const session_token = (body.tripletex_credentials || {}).session_token || body.session_token || '';
const files = body.files || body.attached_files || [];

if (!task || !base_url || !session_token) return [{ json: { status: 'completed' } }];

let fileContext = '';
const pdfFiles = [];
if (files.length > 0) {
  fileContext = '\nAttached files:\n';
  for (const f of files) {
    fileContext += '- ' + (f.filename || 'file') + ' (' + (f.mime_type || '?') + ')\n';
    if (f.mime_type === 'application/pdf') {
      pdfFiles.push(f);
      fileContext += '[PDF]\n';
    } else if (f.content_base64 && f.mime_type && (f.mime_type.includes('text') || f.mime_type.includes('csv'))) {
      try { fileContext += 'Content: ' + Buffer.from(f.content_base64, 'base64').toString('utf-8').substring(0, 5000) + '\n'; } catch(e) {}
    }
  }
}

// Create binary for PDF extraction if needed
const out = [];
if (pdfFiles.length > 0 && pdfFiles[0].content_base64) {
  const buf = Buffer.from(pdfFiles[0].content_base64, 'base64');
  out.push({
    json: { task, base_url, session_token, files, fileContext, pdfFiles, hasPdf: true },
    binary: { data: await _helpers.prepareBinaryData(buf, pdfFiles[0].filename || 'doc.pdf', 'application/pdf') }
  });
} else {
  out.push({ json: { task, base_url, session_token, files, fileContext, pdfFiles: [], hasPdf: false } });
}
return out;
