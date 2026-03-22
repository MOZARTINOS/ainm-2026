// Parse native Google Gemini response + keyword fallback + routing
const items = $input.all();
const d = items[0].json;

// Get original data from Extract Body
let orig;
try { orig = $('Extract Body').first().json; } catch(e) { orig = d; }

// Parse Gemini response (native node returns text/output, or candidates array)
let plan = {};
try {
  let raw = '';
  try {
    const gc = $('Gemini Classify').first().json;
    raw = gc.text || gc.output || gc.response || '';
    // Native Gemini node may return candidates array
    if (!raw && gc.candidates) {
      const part = gc.candidates[0]?.content?.parts?.find(p => p.text);
      if (part) raw = part.text;
    }
  } catch(e) {}
  if (!raw) raw = d.text || d.output || d.response || '';
  if (typeof raw === 'object') raw = JSON.stringify(raw);

  try { plan = JSON.parse(raw); } catch(e) {
    const m = raw.match(/```(?:json)?\s*([\s\S]*?)```/);
    if (m) try { plan = JSON.parse(m[1].trim()); } catch(_) {}
    if (!plan.task_type) {
      const idx = raw.search(/\{/);
      if (idx >= 0) {
        const end = raw.lastIndexOf('}');
        if (end > idx) try { plan = JSON.parse(raw.substring(idx, end + 1)); } catch(_) {}
      }
    }
  }
} catch(e) {}

// Keyword fallback if Gemini failed
if (!plan.task_type || plan.task_type === 'unknown') {
  const t = (orig.task || '').toLowerCase();
  if ((t.includes('supplier') || t.includes('leverandor') || t.includes('leverandør') || t.includes('lieferant') || t.includes('fournisseur')) && (t.includes('invoice') || t.includes('faktura') || t.includes('rechnung'))) plan.task_type = 'supplier_invoice';
  else if (t.includes('payroll') || t.includes('salary') || t.includes('lonn') || t.includes('lønn') || t.includes('gehalt')) plan.task_type = 'payroll_voucher';
  else if ((t.includes('project') || t.includes('projekt') || t.includes('prosjekt')) && (t.includes('invoice') || t.includes('hours') || t.includes('stunden') || t.includes('rechnung') || t.includes('cycle') || t.includes('zyklus'))) plan.task_type = 'project_invoice';
  else if (t.includes('reconcil') || t.includes('kontoauszug') || t.includes('abgleich') || t.includes('avstem') || t.includes('kontoutskrift') || t.includes('bankutskrift') || t.includes('rapprochez')) plan.task_type = 'bank_reconciliation';
  else if (t.includes('closing') || t.includes('encerramento') || t.includes('avslutning') || t.includes('abschluss') || t.includes('year-end') || t.includes('arsavslutning') || t.includes('årsavslutning')) plan.task_type = 'monthly_closing';
  else if (t.includes('analyze') || t.includes('analyse') || t.includes('analice') || t.includes('analysiere') || t.includes('analyser')) plan.task_type = 'ledger_analysis';
  else if (t.includes('reminder') || t.includes('purring') || t.includes('mahnung') || t.includes('rappel')) plan.task_type = 'reminder_fee';
  else if (t.includes('reverse') || t.includes('stornieren') || t.includes('stornere')) plan.task_type = 'reverse_payment';
  else if (t.includes('credit') || t.includes('kredit')) plan.task_type = 'credit_note';
  else if (t.includes('order') && t.includes('invoice') && t.includes('payment')) plan.task_type = 'register_payment';
  else if (t.includes('employee') || t.includes('ansatt') || t.includes('tilsette') || t.includes('mitarbeiter') || t.includes('employe') || t.includes('employé')) plan.task_type = 'create_employee';
  else if (t.includes('travel') || t.includes('reise') || t.includes('viaje') || t.includes('voyage') || t.includes('receipt') || t.includes('kvittering') || t.includes('expense')) plan.task_type = 'create_travel_expense';
  else if (t.includes('customer') || t.includes('kunde') || t.includes('client') || t.includes('cliente')) plan.task_type = 'create_customer';
  else if (t.includes('supplier') || t.includes('leverandor') || t.includes('leverandør') || t.includes('lieferant')) plan.task_type = 'create_supplier';
  else if (t.includes('product') || t.includes('produkt')) plan.task_type = 'create_product';
  else if (t.includes('department') || t.includes('avdeling') || t.includes('abteilung')) plan.task_type = 'create_department';
  else if (t.includes('project') || t.includes('prosjekt') || t.includes('projekt')) plan.task_type = 'create_project';
  else if (t.includes('invoice') || t.includes('faktura') || t.includes('rechnung') || t.includes('factura')) plan.task_type = 'create_invoice';
  else if (t.includes('voucher') || t.includes('bilag') || t.includes('journal') || t.includes('depreci') || t.includes('avskriv')) plan.task_type = 'create_voucher';
  else if (t.includes('delete') || t.includes('slett') || t.includes('loschen') || t.includes('löschen')) { plan.task_type = t.includes('travel') ? 'delete_travel_expense' : t.includes('customer') ? 'delete_customer' : 'delete_employee'; }
  else if (t.includes('update') || t.includes('oppdater') || t.includes('endre') || t.includes('andern') || t.includes('ändern')) { plan.task_type = t.includes('customer') ? 'update_customer' : 'update_employee'; }
}

// Overrides
const t = (orig.task || '').toLowerCase();
if (plan.task_type === 'create_invoice' && (t.includes('fixed price') || t.includes('festpreis') || t.includes('fastpris'))) plan.task_type = 'project_invoice';
if (plan.task_type === 'create_project' && (t.includes('analyze') || t.includes('analyse') || t.includes('reconcil') || t.includes('closing'))) plan.task_type = 'ledger_analysis';
if (t.includes('projektzyklus') || t.includes('project cycle') || t.includes('prosjektsyklus') || t.includes('ciclo del proyecto')) plan.task_type = 'project_invoice';
if ((t.includes('kontoauszug') || t.includes('bank statement') || t.includes('kontoutskrift') || t.includes('bankutskrift')) && (t.includes('csv') || t.includes('abgleich') || t.includes('reconcil') || t.includes('avstem'))) plan.task_type = 'bank_reconciliation';

// Routing
const R = { create_customer:1, create_supplier:1, create_product:1, create_department:1, create_project:1, delete_employee:1, delete_customer:1, delete_product:1, delete_travel_expense:1, update_employee:1, update_customer:1, create_employee:2, create_invoice:3, credit_note:3, register_payment:3, reverse_payment:3, project_invoice:4, create_travel_expense:5, payroll_voucher:5, create_voucher:6, supplier_invoice:6, dimension_voucher:6, ledger_analysis:6, monthly_closing:6, bank_reconciliation:6, reminder_fee:6 };

const ep = plan.extracted_params || {};
return [{ json: { ...orig, task_type: plan.task_type || 'unknown', extracted_params: ep, entities: plan.entities || null, routing_group: R[plan.task_type] || 7, confidence: plan.confidence, fileContext: d.fileContext || orig.fileContext || '' } }];
