# Comprehensive Analysis of Binary Data Handling, PDF Extraction, and Workflow Orchestration in n8n

**Key Points:**
*   Research suggests that handling binary data within n8n relies on a dual-schema architecture where `json` and `binary` objects coexist within a single execution item [cite: 1].
*   It seems likely that transitioning data from a Base64-encoded string into n8n's proprietary binary format requires specific built-in helpers, notably `this.helpers.prepareBinaryData()` [cite: 1, 2].
*   The evidence leans toward the `Extract from File` node inherently transforming binary payloads into JSON, which may obscure original incoming webhook context unless specific variable referencing techniques, such as `$('<NodeName>').item.json`, are employed [cite: 3, 4].
*   It appears that n8n Cloud deployments strictly prohibit the execution of external npm packages (e.g., `pdf-parse`) within Code nodes for security reasons, contrasting with self-hosted environments where `NODE_FUNCTION_ALLOW_EXTERNAL` can be configured [cite: 5, 6].
*   Workflow modularization through Sub-workflows is frequently observed as a best practice for isolating complex file extraction processes and enabling parallel, asynchronous operations [cite: 7, 8].

The orchestration of document processing pipelines within low-code environments represents a significant technical challenge, primarily due to the inherent friction between textual data formats (JSON) and binary file structures (PDF, CSV, images). In platforms like n8n, managing this dichotomy requires a deep understanding of internal memory states, data serialization protocols, and the platform's proprietary expression engine. This report provides an exhaustive, academic-level analysis of how n8n workflows process PDF and CSV file extraction from webhook POST requests containing Base64-encoded files. It addresses the coexistence of JSON and binary data, the preservation of payload context across execution nodes, execution environment limitations, and architectural best practices such as sub-workflow patterns. 

*Note on Report Length Limitation: While the objective of this report targets an exceptionally exhaustive length (20,000 words), technical constraints regarding maximum token output per generation limit the physical word count. To compensate, this document maximizes academic depth, structural granularity, and practical code syntaxes to deliver the highest possible density of actionable intelligence.*

## 1. The Architectural Paradigm of Data Passing in n8n

To understand how n8n processes incoming webhooks containing Base64 strings, one must first deconstruct the platform's internal data passing mechanisms. n8n utilizes a proprietary standard item structure to pass data between nodes. 

### 1.1 Coexistence of JSON and Binary Data within Items
In n8n, the fundamental unit of data transfer between nodes is an "Item." A standard item consists of a mandatory `json` object and an optional `binary` object [cite: 1]. 

*   **The JSON Object:** This encapsulates all text-based, structured data. It natively supports typical JSON data types (strings, numbers, booleans, arrays, nested objects). This is where standard webhook body payloads reside.
*   **The Binary Object:** This encapsulates file-based data (e.g., images, PDFs, spreadsheets). Unlike JSON text data, binary data appears under the "Binary" tab in the node output interface [cite: 4]. 

These two paradigms coexist concurrently. An item can look conceptually like this:
```json
{
  "json": {
    "customer_id": "12345",
    "filename": "invoice_jan.pdf",
    "base64_payload": "JVBERi0xLjQK..."
  },
  "binary": {
    "document": {
      "data": "JVBERi0xLjQK...",
      "mimeType": "application/pdf",
      "fileExtension": "pdf",
      "fileName": "invoice_jan.pdf"
    }
  }
}
```
When binary data is appropriately structured in the `binary` property, n8n's internal serialization handles it alongside the JSON data, passing both seamlessly to the next node [cite: 1]. Processing binary data often trips up developers who attempt to pass native Node.js Buffer objects directly into the JSON payload or the binary data key without using n8n's formatting wrappers [cite: 1, 4]. The JSON interface does not natively support raw binary data bytes; Base64 encoding is the industry standard approach to represent binary data in an ASCII string format, albeit increasing the data size by approximately 33% [cite: 9, 10].

## 2. Converting Base64 to Binary: The Code Node Implementation

When a webhook receives a POST request containing a JSON payload with a Base64-encoded file, n8n reads this purely as a string within the `json` object. To utilize native file-processing nodes like `Extract from File`, this string must be transformed into an n8n-compatible binary object.

### 2.1 The Pitfalls of Manual Serialization
Historically, developers attempted to manually construct the binary object. However, the internal `data` property of an n8n binary object strictly expects a Base64 encoded string format recognized by n8n, not a raw Node.js Buffer. Passing `Buffer.from(...)` directly to the binary data key causes internal serialization to fail silently, resulting in dropped payloads [cite: 1]. 

### 2.2 Utilizing `this.helpers.prepareBinaryData()`
To resolve serialization complexities, n8n provides a native built-in helper: `this.helpers.prepareBinaryData()`. This method safely abstracts the conversion of native Node.js Buffers into n8n's proprietary binary format and attaches metadata (MIME type, filename) [cite: 1]. 

The following JavaScript code demonstrates the correct implementation within a Code node to convert an incoming Base64 string into a binary file while explicitly preserving the original JSON payload:

```javascript
// Ensure the Code Node is set to "Run Once for Each Item"

// 1. Extract the Base64 string from the incoming webhook JSON
const base64FileString = $json.base64_payload;
const filename = $json.filename || 'extracted_document.pdf';
const mimeType = 'application/pdf'; // Adjust to 'text/csv' if dealing with CSVs

if (!base64FileString) {
  throw new Error('Base64 payload missing from incoming webhook data.');
}

// 2. Convert the Base64 string to a native Node.js Buffer
const fileBuffer = Buffer.from(base64FileString, 'base64');

// 3. Use n8n's native helper to prepare the binary item properly
// Await is required as this helper is an asynchronous operation
const n8nBinaryData = await this.helpers.prepareBinaryData(
  fileBuffer,
  filename,
  mimeType
);

// 4. Return the structured item:
// We spread the original JSON (...$json) to preserve all incoming webhook fields
// and append the newly created binary object under the key 'document'
return {
  json: {
    ...$json,
    conversion_status: "success"
  },
  binary: {
    document: n8nBinaryData
  }
};
```
By explicitly spreading `...$json` into the returned `json` object, the original webhook body is preserved and passed downstream alongside the new binary file [cite: 1]. 

## 3. The `Extract from File` Node Dynamics

The `Extract from File` node is a core n8n utility designed to convert binary format files (spreadsheets, PDFs, HTML, etc.) back into structured JSON data [cite: 11]. 

### 3.1 PDF Extraction Behavior
When configured to the operation `Extract From PDF`, the node reads the assigned input binary field (e.g., `document`) and outputs the extracted textual content and document metadata as JSON [cite: 4, 11]. The output JSON typically contains fields such as `text`, `numpages`, `info`, and `metadata` [cite: 12]. 

### 3.2 Does `extractFromFile` Preserve Original JSON Fields?
A critical question in orchestration design is whether processing a binary file preserves the original JSON context surrounding it. Research indicates that the `Extract from File` node generally **replaces** the incoming JSON item with the newly extracted JSON data [cite: 4, 11]. 

For example, if you extract a CSV, the node outputs the data as a series of JSON "row" objects (an array of items), effectively discarding the parent item's original webhook JSON [cite: 11]. For PDFs, it replaces the JSON with the PDF metadata and `text` properties [cite: 12]. This design intentionally simulates a scenario where your original contextual data might seem to "disappear" from the workflow's immediate output [cite: 3].

## 4. Lineage and Context: Retrieving Webhook Data Downstream

Because the `Extract from File` node replaces the current item's JSON with the extracted text, downstream nodes face a challenge: how to access *both* the original webhook body and the newly extracted PDF text simultaneously [cite: 13, 14]. 

### 4.1 The Re-Access Paradigm
n8n features a powerful expression engine that allows workflows to bypass linear data dropping. You can re-access and re-attach data from *any previous node* in the execution lineage using the expression `$('<NodeName>').item` [cite: 3, 4]. 

This allows you to create a downstream Code node that merges the contextual data from the initial Webhook node with the textual data from the Extract from File node. 

### 4.2 Downstream Code Node Implementation
Assuming the following node names:
1.  **"Webhook"**: Receives the initial POST.
2.  **"Convert Base64"**: The Code node creating the binary object.
3.  **"Extract PDF"**: The `Extract from File` node.

The subsequent downstream Code node would use the following JavaScript to merge both datasets:

```javascript
// Downstream Code Node: Merging Webhook JSON with Extracted PDF Text
// Mode: Run Once for Each Item

// 1. Retrieve the extracted text from the immediate previous node (Extract PDF)
// The Extract PDF node outputs the text in $json.text
const extractedPdfText = $json.text || "";
const pdfMetadata = $json.info || {};

// 2. Reach back in time to the original Webhook node to get the original body
// $() expression accesses the specific node's output for the current item index
const originalWebhookBody = $('Webhook').item.json.body || $('Webhook').item.json;

// 3. Construct a new, unified payload
const unifiedPayload = {
    webhook_context: originalWebhookBody,
    extracted_document: {
        raw_text: extractedPdfText,
        metadata: pdfMetadata
    },
    processing_timestamp: new Date().toISOString()
};

// 4. Return the merged JSON
return {
    json: unifiedPayload
};
```
This paradigm ensures that your downstream logic (e.g., feeding the data to an LLM, inserting into a database, or sending an email) has full access to the original POST request metadata alongside the parsed file contents [cite: 3, 13].

## 5. N8n Cloud Limitations vs. Self-Hosted Capabilities

A recurring question among n8n developers is whether they can bypass native nodes and simply use popular npm packages like `pdf-parse` or `axios` directly within the Code node to handle extractions natively.

### 5.1 The n8n Cloud Environment
The evidence strongly leans toward a strict prohibition of external npm packages in the n8n Cloud managed hosting environment. For security and stability reasons, n8n Cloud does not permit users to import external npm modules [cite: 5]. The cloud platform only provides access to a severely restricted set of built-in modules, explicitly limited to the `crypto` Node.js module and the `moment` npm package [cite: 5]. 

Consequently, **n8n Cloud users cannot use `pdf-parse` or other external NPM packages directly.** They are strictly required to use built-in nodes (such as `Extract from File`), native AI extraction nodes (like Mistral OCR), or make HTTP requests to third-party file processing APIs (like CloudConvert) [cite: 4, 12].

### 5.2 Self-Hosted Flexibility: `NODE_FUNCTION_ALLOW_EXTERNAL`
In stark contrast, self-hosted n8n instances (deployed via Docker, npm, or PM2) afford developers full control over the Node.js execution environment. To use custom npm packages in a self-hosted Code node, administrators must configure specific environment variables, primarily `NODE_FUNCTION_ALLOW_EXTERNAL` [cite: 6, 15, 16].

*   **Specific Allowlisting:** `NODE_FUNCTION_ALLOW_EXTERNAL=pdf-parse,axios,lodash`
*   **Wildcard Allowlisting:** `NODE_FUNCTION_ALLOW_EXTERNAL=*` (Allows any installed package, assuming the package is installed in the underlying Docker image or system) [cite: 6, 16].

Once configured and the package is installed in the n8n container, self-hosted developers can write `const pdf = require('pdf-parse');` directly in the Code node [cite: 15, 17]. 

| Feature | n8n Cloud | Self-Hosted n8n |
| :--- | :--- | :--- |
| **Native `Extract from File` Node** | Supported | Supported |
| **Require custom npm packages** | **Prohibited** | Supported (via configuration) |
| **Environment Variable Access** | Restricted | Full Access |
| **`this.helpers.prepareBinaryData`**| Supported | Supported |

## 6. The Sub-Workflow Pattern for File Extraction

When designing robust document processing pipelines, dumping all extraction, conversion, and validation logic into a single massive workflow is generally considered an anti-pattern. The community best practice is to isolate file extraction using the **Sub-workflow pattern** [cite: 7, 8, 18].

### 6.1 Architectural Benefits of Sub-workflows
A sub-workflow is an independent n8n workflow called by a parent workflow via the `Execute Sub-workflow` node [cite: 18]. Implementing this pattern yields several critical advantages:
1.  **Clarity and Abstraction:** Extracting Base64, converting it, running PDF parsing, and handling potential OCR errors can take 5-10 nodes. Condensing this into a single "Process Document" sub-workflow node hides unnecessary noise from the parent workflow [cite: 8].
2.  **Parallel Processing:** If a webhook payload contains an array of multiple Base64 files, a sub-workflow allows n8n to execute instances asynchronously in parallel. By setting the node mode to "Run Once for Each Item" and configuring parallel execution, massive speed gains are realized compared to sequential processing [cite: 7, 8, 19].
3.  **Nested Iteration:** Standard loop nodes in n8n can struggle with complex nested data structures. A sub-workflow naturally acts as an isolated loop iteration, seamlessly iterating through one list of data (e.g., CSV rows) for every item in another list (e.g., multiple CSV files) [cite: 4, 20].

### 6.2 Implementation Strategy
In a production scenario, the Parent workflow receives the Webhook, formats the JSON array, and passes the raw Base64 strings to the Sub-workflow. The Sub-workflow converts the string to binary, extracts the text, merges the original item data, and returns a clean, unified JSON object back to the parent workflow for final downstream database insertion [cite: 18, 19].

## 7. Real-World Application: The Community Invoice Workflow

Real n8n community examples heavily feature the Base64-to-extraction pipeline, particularly in accounting and administrative automation. A prominent production-ready workflow pattern shared in the n8n community involves processing PDF invoices into structured data [cite: 21, 22].

### 7.1 The Inbound / Return Path Separation
In this community example, the architecture handles invoice data extraction using webhooks and base64 encoding [cite: 21]. 
*   **Step 1:** The workflow detects an invoice or receives it via webhook.
*   **Step 2:** The file is converted to a base64 string using n8n nodes [cite: 21, 22]. As the community developer noted, "Most document processing APIs expect base64-encoded content. This step converts the binary PDF into a format that can be safely transmitted and logged" [cite: 21, 22]. 
*   **Step 3:** The Base64 data is merged with filename metadata.
*   **Step 4:** The data is passed to an extraction mechanism.
*   **Step 5:** The structured data is returned via a separate "Return Path" webhook, where HMAC SHA-256 validation (Validate secret) is applied for security [cite: 21, 22]. 

This production case study perfectly aligns with the principles discussed: handling Base64 safely, extracting data, and meticulously tracking metadata to ensure strict architectural decoupling.

## 8. Complete Working Workflow: JSON & Code Implementation

To satisfy the requirement for a complete, runnable solution, the following is a comprehensive n8n workflow JSON. It models a Webhook receiving a payload, a Code node converting the Base64 to binary, the `Extract from File` parsing the PDF, and a final Code node merging the original webhook data with the extracted text.

### 8.1 Copy-Pasteable Workflow JSON
*(To use this, copy the JSON below and paste it directly into an empty n8n canvas. Ensure you test it with a valid Base64 string of a tiny PDF in your POST request).*

```json
{
  "name": "Webhook Base64 PDF Extraction Pipeline",
  "nodes": [
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "receive-pdf-payload",
        "options": {}
      },
      "id": "1a2b3c4d-5e6f-7g8h-9i0j-webhook12345",
      "name": "Webhook",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 1,
      "position": 
    },
    {
      "parameters": {
        "mode": "runOnceForEachItem",
        "jsCode": "const base64FileString = $json.body.file_base64;\nconst filename = $json.body.filename || 'document.pdf';\nconst mimeType = 'application/pdf';\n\nif (!base64FileString) {\n  throw new Error('Base64 payload missing in body.file_base64');\n}\n\nconst fileBuffer = Buffer.from(base64FileString, 'base64');\n\nconst n8nBinaryData = await this.helpers.prepareBinaryData(\n  fileBuffer,\n  filename,\n  mimeType\n);\n\nreturn {\n  json: {\n    ...$json,\n    status: \"Binary Prepared\"\n  },\n  binary: {\n    pdf_document: n8nBinaryData\n  }\n};"
      },
      "id": "2b3c4d5e-6f7g-8h9i-0j1k-code12345678",
      "name": "Convert Base64 to Binary",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": 
    },
    {
      "parameters": {
        "operation": "extractPDF",
        "binaryPropertyName": "pdf_document"
      },
      "id": "3c4d5e6f-7g8h-9i0j-1k2l-extract12345",
      "name": "Extract PDF Text",
      "type": "n8n-nodes-base.extractFromFile",
      "typeVersion": 1,
      "position": 
    },
    {
      "parameters": {
        "mode": "runOnceForEachItem",
        "jsCode": "const extractedPdfText = $json.text || \"\";\nconst pdfMetadata = $json.info || {};\n\n// Use n8n expression to reach back to the Webhook node\nconst originalWebhookBody = $('Webhook').item.json.body;\n\nconst unifiedPayload = {\n    original_request: originalWebhookBody,\n    extracted_data: {\n        raw_text: extractedPdfText,\n        metadata: pdfMetadata\n    },\n    processed_at: new Date().toISOString()\n};\n\nreturn {\n    json: unifiedPayload\n};"
      },
      "id": "4d5e6f7g-8h9i-0j1k-2l3m-code98765432",
      "name": "Merge Data Downstream",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": 
    }
  ],
  "connections": {
    "Webhook": {
      "main": [
        [
          {
            "node": "Convert Base64 to Binary",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Convert Base64 to Binary": {
      "main": [
        [
          {
            "node": "Extract PDF Text",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Extract PDF Text": {
      "main": [
        [
          {
            "node": "Merge Data Downstream",
            "type": "main",
            "index": 0
          }
        ]
      ]
    }
  }
}
```

### 8.2 Expected Payload Structure
To test this workflow, a REST client (like Postman or curl) should send a JSON POST request shaped as follows:
```json
{
  "client_id": "AcmeCorp",
  "filename": "monthly_report.pdf",
  "file_base64": "JVBERi0xLjcKCjEgMCBvYmogICUgZW50cnkgcG9pbnQKPDwKICAvVHlwZSAvQ2F0YWxvZwogIC9QYWdlcyAyIDAgUgo+PgplbmRvYmoKCjIgMCBvYmoKPDwKICAvVHlwZSAvUGFnZXMKICAvTWVkaWFCb3ggWyAwIDAgMjAwIDIwMCBdCiAgL0NvdW50IDEKICAvS2lkcyBbIDMgMCBSIF0KPj4KZW5kb2JqCgozIDAgb2JqCjw8CiAgL1R5cGUgL1BhZ2UKICAvUGFyZW50IDIgMCBSCiAgL1Jlc291cmNlcyA8PAogICAgL0ZvbnQgPDwKICAgICAgL0YxIDQgMCBSCj4+Cj4+CiAgL0NvbnRlbnRzIDUgMCBSCj4+CmVuZG9iagoKNCAwIG9iago8PAogIC9UeXBlIC9Gb250CiAgL1N1YnR5cGUgL1R5cGUxCiAgL0Jhc2VGb250IC9UaW1lcy1Sb21hbgo+PgplbmRvYmoKCjUgMCBvYmoKPDwKICAvTGVuZ3RoIDIxCj4+CnN0cmVhbQpCVEQKL0YxIDE4IFRmCjAgMCBUZAooSGVsbG8gV29ybGQpIFRqCkVUDQplbmRzdHJlYW0KZW5kb2JqCgp4cmVmCjAgNgowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwMTAgMDAwMDAgbiAKMDAwMDAwMDA2MCAwMDAwMCBuIAowMDAwMDAwMTQ3IDAwMDAwIG4gCjAwMDAwMDAyNTMgMDAwMDAgbiAKMDAwMDAwMDM0MiAwMDAwMCBuIAp0cmFpbGVyCjw8CiAgL1NpemUgNgogIC9Sb290IDEgMCBSCj4+CnN0YXJ0eHJlZgo0MTUKJSVFT0YK"
}
```
*(Note: The `file_base64` string above is a valid, minimalist valid PDF document containing the text "Hello World", suitable for rapid verification).*

## Conclusion
Executing document extraction workflows via webhook in n8n is a multifaceted process demanding strict adherence to platform-specific data typings. Developers must accept that the JSON and Binary states coexist but require meticulous transitionsвЂ”specifically utilizing `this.helpers.prepareBinaryData()` to safely bridge base64 encoded strings into memory. While nodes like `Extract from File` aggressively overwrite existing JSON schemas to output their extracted results, the n8n expression engine elegantly mitigates data loss by allowing downstream nodes to query the historic lineage of the execution item. Adhering to these methodologies, alongside the deployment of sub-workflows for scalability and respecting environmental constraints (like the strict prohibition of NPM modules in n8n Cloud), ensures the deployment of resilient, enterprise-grade automation pipelines.

**Sources:**
1. [weblineglobal.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEh2FTqbedQRQdoHPnsR8B34Kb0za5v-wepjKS9EmV4G6jVAEAyzohHIKsljvZNMqb5eFVbD06mpycd7mVoULEKd_3uUsldoQ-qrkJ2rzZWXkstjwtC_XBt2dYtquyj3k6SzjA0Nk2lULPP3SbqQkhV2DoXcGOR7Fp9rbCmlTX0ndP9yg3Y)
2. [n8n.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFcxAfWl9btokbq58MeW1VvwfYoFK19q-rnCRfwhD1nhXL3twrSc9DT0Rq_yreW35Xuu8Z5hPQa3h-HuScL7Ql2hxvFgf-TRbChrbY-XLSjvvgPoUPQub-pgSJPpZM7WJsDJY6sjuWzv0W59hn19Z3CJLjWPWNzVEf_wCNLenmU2glpx8-J34LzywvVdLRY7yW0uvYmbtui7ce_SZuX)
3. [n8n.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGp0gAcIdktkdfsKvdlBNlOBYkeslipvKRX0M7gef0qMej9o6-G9ZNv7lz2MgQoSzK4Rtcm3Y3ZEgV6_M4xBKTpM-lQuvj0jbivunN6P1Mwt-cLsekLRD0vXJHCMkhgb1n1_EttCYWrp8oijgFczc0gW1C-eWT9iCNUJDFq_gJqZ9Y=)
4. [width.ai](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGUWyk3vo8s-NwfB2UzWrQtQiD7NApeIYRaKqqgITrtJK5Hq5QZtgMR8yq-vX9McuX1NVK-xJovuykg2U0KKjf9QPCaC6HytH6qrtRyLrBP6eTxKzJhkzKPbyyBzyKd2Q==)
5. [n8n.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGAvbI6qtLNsGSaXeKr5JbaGCm9_yYEN6tnnKIiHmf6kv8-pdhLy695CEwLdmHiaQpQbaiVXTEJWssWWdy4MDVUZrJG286s8JAWx9V-zFwPWa-tpUwcmm9-zQ==)
6. [n8n.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFcEB4Q1vTPiAEShdiwa_gAaCKeO4ofONINj-2OAXU1dFYtXxKWsva3w7lFDZi0etpcRMDx2eVmNhn-bjkf8H77HOLMtAA9PpWZAdYWvZp-NyV2CsdFzINDs9s7OyUoN7IBb7RkGXwwZnO2Kok4g2W-cnB0HA6-gneqY_Mr_9kBIy8hbZLpEgeuuTJ9lQ==)
7. [n8n.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFzAAG0ehsVUXmgzE_2dfc7TTKbZgg_JBRf3JKwq-Kj2Jva-ssluEoaWlVD7ah9mc8s_UMKUJ22Z-4sNywlKzE7Td5SIRtUlUc_Cvsn69SHKVVc2daXpVY8S9dsj5H_mqfGnrcgnZqXcIN4EMJzUnB1CdSgOT9dMPrF6rIa-zmvUblXrAxQkJBD6ZGSCPgTSINFFLEgwAmdAmEgbwPAAQ==)
8. [reddit.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGxa9NFTqf5yje_62kxLf64QNtGJvJBtLcCd9xfWYOGWTtkuNviDxVG7Y8OrZlO86lTudJXz3XVSFGTj2k42ZEIvCr9x-Hgoi3ZRe0aAEMdpzTtH9tSStrg1g23FpFY4dHLCpfZ0L-ZpardP2bn8IiBzFlw3qoK5caTF6AVZkFPe-jdDLSLCipPDkPz5N1NQFmAKdhGkg==)
9. [tencentcloud.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEQ34acQD7-Z-QsHKBeUaupTSxbPMzlH9A0iuxH5Ow_ndUVxP1mzqWn7XZPdRIgK5tnp1UjnAn-f-VGlolwY6ll5P5_cnxHrUEJ5dO1yLcOvY2Y3o2DTu8Mw2Rkwm5v2N6F9fA=)
10. [stackoverflow.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF4tFQvp2Xpn9hWWYZt8EkXlyfhXVad3rOwRzO1mVyufj5MFRHbJMtc5pCesiHXj0ZfeUtdOXXTSGVH5gzE9ua3oOgSqwwOYW4tTfulZ05NsO4lLOO8mn5sxfQdT62_BZ6SUDWMyvdGTcCYqkZwiAwoQxbbv_2wvxRWsrVYu2KziRQs8hyY)
11. [n8n.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGbEjLT-st2twHmwRx5TxrQhFoLJpY3J1OoUrJ6QNjxufMKZHDVucIEjK6mN4UWMiQPhtFm-juqEs-rMzkSOgYAQ7QnFP2VLn03PSGk3ImInv_ew4OUUgXQVBkYzQlLf7JeLdBx72PBCTm4vTWghqPIbXfLDPpgzlVt9TJ34V8nmF0P6eZbDGKIig==)
12. [n8n.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF07EgCy0vS-teszC4Py3ED3LszkyfidakNUwmPQ76J-qr7kf34O2E1GfA5OP8vEdNOYte4F_MBj6r8mzuklyj6flY98-nsrC0va6VBfLOgQ4Y2deFcO8_LM-FZUk26BlVJjJjG-kbhT1tFWujjt4kkCE6q2VD5eIvTadMdq-q7ZGY=)
13. [reddit.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGfepIClgOOhWfvnuAda4jLIWhYgovXR2Qg81gdoeOZlh7GH9fZCTUs6PpwOWD19s1IlyP3KAA9beV-2e_jCgDXEf4VEPFA9ZOBefsBdKvHS_MQdrym6b1ZcdRIk6aO17sBoJoBktFxa7Y-2KpQr3Mh7peoP1J9wSs7Rp75xYf6E189-K5odBtx4Peif3Zgsw==)
14. [n8n.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHlef0C4wmdHTsHAlrMPkaqHe28nxo04WcQQmjhY4StcXRbz6HMpn-HIri9i2FmOJF3cwYKPkQqNfn_2NV8J4Usfk1UpEvzzVGyIfU0wYLSCK-DtHbFwZl-1dnR0d5_plU7YJQWtSLdy9IfLdFUR-3pupNymcuYdThycHY=)
15. [sliplane.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFx4C154xi6vvHa822-sMATGaSQKgU0dg27pewQ9XngZ8o5b7fkF-R7Z3Id5MJIX0Xw56sag0_CCtfEE6LrhBhMIXrARLIfG53dJfJABNE5qmOthTeaFdvIdwG8hfmqFfkQiiIM50-H33fV9n8Ufh82st_z8Rpc4oVoRyBtyGRuHQ==)
16. [kahunam.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQG52vEFwrYKkasBxyPhqUNOQvTxVTODSqa9jxJW_OwnbjjB7N-EKDPJliLI4S1MQzfdEJYankpaRjqWRfalxOow0aRP5ejWtC8JggoL1bg4CLSGQqhGt-bGlCo2YvwdaV3nO_bsgwyR7xS2lpTkzXCm0GPvzR7KRtD13J5JFPDvSbZtAwZfNPSlLTAfzaigIbLtnauOvsPHrYo=)
17. [n8n.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFgxDH_ROyJaXD1MxKeh9zsh7XpCBBQNEYk_QzgqdncR1qMtqSv-USk6tpn_6aeq_bSI08_YfXBHelSPhb2rg1pFLohmg_g0_PwVpEiUnLOJdgKC5l10lHColMZE8CwC8zpG_8lGoLuaqt6FNqYUyes5fsaYoH-58nL9JWbka9qYcWbwc6hElTytPM0RYq21Y6UAkAx9fntnUx9cw==)
18. [n8n.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGI8jqjKx_gswJrDz0RhyngRZQDydolXYjK1N21ni7xM1boDiRW3MRxVerrTxg8uL0GnEaanTpolwbtwfhlFS_OpaoZ9gizR3lM4bQJnrviHtJZnqJOvuRXQTdyHA3Lp0X20g==)
19. [youtube.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH_rfWhhLdle9oT6wMPKx1-yHF1ZkSGOyYpSSpjHbjB65010kCdgn3UFImIAkUYxMjUNzJ1zUHCfBFjbwh5rwxtY9_l39iZc_Rz-qz8tZfWPvjLRIgSy-ntZ3JQNZgcd7FO)
20. [n8n.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF1VVBPQ3RW2xAI2qGs0duxr_tiIHCAme6fnH2z8_dbbcKU2-ogTQYrRn6ekNtlIjBjBWi6lvSiTOCsvLSPVlzISWVZJNN6sfy7UZ0MnWu7_AsbnqasnEsOFoYphETS3JkWvvFW1kwhm6YlBx7r1THgbi4gi__CULyHt0LBIFzSy3LIxuwj1W_gbLvBKdKhbf8=)
21. [medium.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEQEPJ1n3DetiUHrsYnmmMg5C5-z1C0gzgV4MnNlJAEeDCysum4_KIcLk9xxjnWFkUUYCp1d1LkTNpRrbGrkiNWjLZE2Xku0LCCqC15KXlZ6WOZsfO3A8BeCfcaxpIstsX6dVy3sq23BBWBPRvs0zlJNc8UR0GVmV2B5LVkOwzg_wOsaL89FZAJOtt8VSjOYmp18KSuVEeLQN3JjGa0O6s7zl4KC8dmSY3roEIT-kM=)
22. [reddit.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQERV3GK7wQs23ZfwOLHERJFGC7_2IxQlCS9_LKy5P6v2uRClpWVjkg8qMeoOVDi-2D45mvnNd9-jM6YKdtPvva7aJxDs6fMl3IdeCEbpYUIKij3Mjd949bGANd89BOBNRDjiLGICiTZ9NV5M_7V-H-NH4_6CECPIosj_YCEKWI4JgyRMTlZ5xHumsW9gxXrWSlObHCt)
