// Classify — Gemini classification + keyword fallback + routing
const items = $input.all();
const d = items[0].json;
const task = d.task || '';
const fileContext = d.fileContext || '';
const pdfFiles = d.pdfFiles || [];
const GEMINI_KEY = 'AIzaSyC_ya1fW-hpajZyb8osz35Y4znS9cx_h4g';

const _helpers = this.helpers;
const callGemini = async (prompt, pdfs) => {
  try {
    const parts = [{ text: prompt }];
    if (pdfs && pdfs.length > 0) {
      for (const f of pdfs) {
        if (f.content_base64) parts.push({ inline_data: { mime_type: 'application/pdf', data: f.content_base64 } });
      }
    }
    const r = await _helpers.httpRequest({
      method: 'POST',
      url: 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=' + GEMINI_KEY,
      body: {
        contents: [{ parts }],
        generationConfig: { temperature: 0, topK: 1, topP: 0.1, maxOutputTokens: 4096, responseMimeType: 'application/json' },
        safetySettings: [
          { category: 'HARM_CATEGORY_HARASSMENT', threshold: 'BLOCK_NONE' },
          { category: 'HARM_CATEGORY_HATE_SPEECH', threshold: 'BLOCK_NONE' },
          { category: 'HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold: 'BLOCK_NONE' },
          { category: 'HARM_CATEGORY_DANGEROUS_CONTENT', threshold: 'BLOCK_NONE' }
        ]
      },
      headers: { 'Content-Type': 'application/json' }, json: true
    });
    const raw = r.candidates[0].content.parts.find(p => p.text)?.text || '{}';
    try { return JSON.parse(raw); } catch(e) {
      const m = raw.match(/```(?:json)?\s*([\s\S]*?)```/);
      if (m) try { return JSON.parse(m[1].trim()); } catch(_) {}
      const idx = raw.search(/[{[]/);
      if (idx >= 0) try { return JSON.parse(raw.substring(idx)); } catch(_) {}
      return {};
    }
  } catch(e) { return {}; }
}

// === CLASSIFY PROMPT ===
const classifyPrompt = `You are a Tripletex accounting API expert. Analyze this task and return a structured plan.

RULES:
- Task may be in Norwegian, English, Spanish, Portuguese, German, French, Italian.
- Norwegian: ansatt=employee, kunde=customer, leverandør=supplier, produkt=product, faktura=invoice, betaling=payment, reiseregning=travel_expense, avdeling=department, prosjekt=project, kreditnota=credit_note, bilag/voucher=voucher, slett=delete, oppdater/endre=update
- "slett reiseregning"/"delete travel expense" → delete_travel_expense
- CLASSIFICATION PRIORITY: If task mentions reversing/cancelling a PAYMENT → reverse_payment. credit_note = create new credit invoice.
- "leverandør/supplier" → create_supplier. "kunde/customer" → create_customer
- Extract ALL parameters. Dates: YYYY-MM-DD. If only day/month, assume 2026.
- For employees: firstName, lastName, email, phoneNumberMobile, dateOfBirth, startDate, department, nationalIdentityNumber (11-digit), occupationCode (STYRK 4-digit), salary (annual), employmentPercentage (0-100), employmentType (FAST/MIDLERTIDIG)
- PDF EMPLOYEE EXTRACTION CHECKLIST — extract ALL of these from document text if present:
  * firstName, lastName, email, phoneNumberMobile, dateOfBirth (YYYY-MM-DD)
  * nationalIdentityNumber — 11-digit fødselsnummer
  * startDate, department, salary (annual number), employmentPercentage (0-100)
  * occupationCode (4-digit STYRK), employmentType (FAST=permanent, MIDLERTIDIG=temporary)
- For customers: name, email, phoneNumber, organizationNumber, address, postalCode, city, isPrivateIndividual
- For suppliers: name, email, phoneNumber, organizationNumber, address, postalCode, city
- For products: name, number, priceExcludingVat, vatPercentage (default 25)
- For invoices: customerName, customerOrgNumber, invoiceDate, dueDate, lines[{description, quantity, unitPrice, vatPercentage}], shouldSend
- For payments: invoiceNumber, amount, paymentDate, customerName, customerOrgNumber, productDescription, productPrice, products[{name, number, unitPrice}], currency, exchangeRateInvoice, exchangeRatePayment
- For projects: name, customerName, customerOrgNumber, projectManagerFirstName, projectManagerLastName, startDate, endDate, isInternal
- For project_invoice: customerName, customerOrgNumber, projectName, employeeFirstName, employeeLastName, employeeEmail, activityName, hours, hourlyRate, fixedPrice, description
- For payroll_voucher: employeeFirstName, employeeLastName, employeeEmail, salaryItems[{description, amount, accountNumber}]
- For supplier_invoice: supplierName, supplierOrgNumber, invoiceNumber, amountIncludingVat, accountNumber, description
- For travel expenses: employeeName, employeeEmail, title, departureDate, returnDate, destination, costs[{description, amount}], perDiem:{days, accommodation, location, dailyRate}
- For credit notes: invoiceNumber, customerName, customerOrgNumber, productDescription, amount
- For vouchers: date, description, postings[{accountNumber, amount, isDebit, description}]
- For dimension_voucher: dimensionName, dimensionValues, linkedValue, voucherAccountNumber, voucherAmount, voucherDescription
- CRITICAL: If "Extracted document text:" section is present, extract ALL field values from it.
- For MULTIPLE entities: return "entities" array with one object per entity.

Task: ${task}${fileContext}

Return: {"task_type": "create_employee|create_customer|create_supplier|create_product|create_invoice|register_payment|reverse_payment|project_invoice|payroll_voucher|supplier_invoice|dimension_voucher|create_travel_expense|delete_travel_expense|update_employee|update_customer|delete_employee|delete_customer|credit_note|create_department|create_project|create_voucher|ledger_analysis|monthly_closing|bank_reconciliation|reminder_fee|unknown", "confidence": 0.0, "extracted_params": {}, "entities": null, "reasoning": ""}`;

const plan = await callGemini(classifyPrompt, pdfFiles);

// SAFEGUARD: keyword fallback if Gemini fails
if (!plan.task_type || plan.task_type === 'unknown' || plan.task_type === 'null') {
  const t = task.toLowerCase();
  if ((t.includes('stornieren') || t.includes('reverse') || t.includes('cancel') || t.includes('stornere')) && (t.includes('payment') || t.includes('zahlung') || t.includes('betaling'))) plan.task_type = 'reverse_payment';
  else if (t.includes('order') && t.includes('invoice') && t.includes('payment')) plan.task_type = 'register_payment';
  else if ((t.includes('supplier') || t.includes('leverandør') || t.includes('fournisseur') || t.includes('lieferant')) && (t.includes('invoice') || t.includes('faktura') || t.includes('rechnung'))) plan.task_type = 'supplier_invoice';
  else if (t.includes('payroll') || t.includes('salary') || t.includes('lønn') || t.includes('gehalt') || t.includes('salaire')) plan.task_type = 'payroll_voucher';
  else if (t.includes('order') && t.includes('invoice')) plan.task_type = 'create_invoice';
  else if ((t.includes('project') || t.includes('projekt') || t.includes('prosjekt')) && (t.includes('invoice') || t.includes('hours') || t.includes('stunden') || t.includes('faktura') || t.includes('rechnung') || t.includes('cycle') || t.includes('zyklus'))) plan.task_type = 'project_invoice';
  else if ((t.includes('dimension') || t.includes('kostsenter') || t.includes('kostenstelle')) && (t.includes('voucher') || t.includes('bilag') || t.includes('journal'))) plan.task_type = 'dimension_voucher';
  else if (t.includes('analyze') || t.includes('analyse') || t.includes('analice') || t.includes('analysiere')) plan.task_type = 'ledger_analysis';
  else if (t.includes('reconcil') || t.includes('concilia') || t.includes('avstem') || t.includes('kontoauszug') || t.includes('abgleich') || t.includes('rapprochez') || t.includes('kontoutskrift') || t.includes('bankutskrift')) plan.task_type = 'bank_reconciliation';
  else if (t.includes('closing') || t.includes('encerramento') || t.includes('avslutning') || t.includes('abschluss') || t.includes('clôture')) plan.task_type = 'monthly_closing';
  else if (t.includes('reminder') || t.includes('purring') || t.includes('overdue') || t.includes('mahnung') || t.includes('rappel')) plan.task_type = 'reminder_fee';
  else if (t.includes('employee') || t.includes('ansatt') || t.includes('tilsette') || t.includes('employé') || t.includes('mitarbeiter')) plan.task_type = 'create_employee';
  else if (t.includes('customer') || t.includes('kunde') || t.includes('client')) plan.task_type = 'create_customer';
  else if (t.includes('supplier') || t.includes('leverandør') || t.includes('lieferant')) plan.task_type = 'create_supplier';
  else if (t.includes('product') || t.includes('produkt')) plan.task_type = 'create_product';
  else if (t.includes('department') || t.includes('avdeling') || t.includes('abteilung')) plan.task_type = 'create_department';
  else if (t.includes('invoice') || t.includes('faktura') || t.includes('rechnung')) plan.task_type = 'create_invoice';
  else if (t.includes('voucher') || t.includes('bilag') || t.includes('journal')) plan.task_type = 'create_voucher';
  else if (t.includes('travel') || t.includes('reise') || t.includes('viaje') || t.includes('voyage')) plan.task_type = 'create_travel_expense';
  else if (t.includes('project') || t.includes('prosjekt') || t.includes('projekt')) plan.task_type = 'create_project';
  else if (t.includes('delete') || t.includes('slett') || t.includes('löschen') || t.includes('supprimer')) {
    if (t.includes('employee') || t.includes('ansatt')) plan.task_type = 'delete_employee';
    else if (t.includes('customer') || t.includes('kunde')) plan.task_type = 'delete_customer';
    else plan.task_type = 'delete_employee';
  }
  else if (t.includes('update') || t.includes('oppdater') || t.includes('endre') || t.includes('ändern') || t.includes('modifier')) {
    if (t.includes('employee') || t.includes('ansatt')) plan.task_type = 'update_employee';
    else plan.task_type = 'update_customer';
  }
}

// OVERRIDES
const t = task.toLowerCase();
// fixed price → project_invoice
if (plan.task_type === 'create_invoice' && (t.includes('fixed price') || t.includes('festpreis') || t.includes('fastpris'))) plan.task_type = 'project_invoice';
// analyze/reconcile → NOT create_project
if (plan.task_type === 'create_project' && (t.includes('analyze') || t.includes('analyse') || t.includes('reconcil') || t.includes('closing'))) plan.task_type = 'ledger_analysis';
// project cycle → project_invoice
if (t.includes('projektzyklus') || t.includes('project cycle') || t.includes('prosjektsyklus') || t.includes('ciclo del proyecto')) plan.task_type = 'project_invoice';
// CSV bank statement → bank_reconciliation
if ((t.includes('kontoauszug') || t.includes('bank statement') || t.includes('kontoutskrift') || t.includes('bankutskrift')) && (t.includes('csv') || t.includes('abgleich') || t.includes('reconcil') || t.includes('avstem') || t.includes('rapproch'))) plan.task_type = 'bank_reconciliation';

// MAP TO ROUTING GROUP
const ROUTING = {
  'create_customer': 1, 'create_supplier': 1, 'create_product': 1, 'create_department': 1,
  'delete_employee': 1, 'delete_customer': 1, 'delete_product': 1, 'delete_travel_expense': 1,
  'update_employee': 1, 'update_customer': 1,
  'create_employee': 2,
  'create_invoice': 3, 'credit_note': 3, 'register_payment': 3, 'reverse_payment': 3,
  'project_invoice': 4, 'create_project': 4,
  'create_travel_expense': 5, 'payroll_voucher': 5,
  'create_voucher': 6, 'supplier_invoice': 6, 'dimension_voucher': 6,
  'ledger_analysis': 6, 'monthly_closing': 6, 'bank_reconciliation': 6, 'reminder_fee': 6
};
const routing_group = ROUTING[plan.task_type] || 7;

return [{
  json: {
    ...d,
    task_type: plan.task_type,
    extracted_params: plan.extracted_params || {},
    entities: plan.entities || null,
    routing_group,
    confidence: plan.confidence,
    reasoning: plan.reasoning
  }
}];
