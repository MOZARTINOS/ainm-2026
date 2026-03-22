// Merge Text — combine original body with extracted PDF text
const items = $input.all();
const original = $('Parse Input').first().json;
const extractedText = items[0].json.data || items[0].json.text || '';

let fileContext = original.fileContext || '';
let pdfFiles = original.pdfFiles || [];

if (extractedText) {
  fileContext += '\nExtracted document text:\n' + extractedText.substring(0, 12000) + '\n';
  pdfFiles = []; // don't send via Gemini vision if already extracted
}

return [{
  json: {
    task: original.task,
    base_url: original.base_url,
    session_token: original.session_token,
    files: original.files,
    fileContext,
    pdfFiles,
    hasPdf: original.hasPdf
  }
}];
