// NM i AI 2026 - Tripletex Agent v2 (FIXED)
const items = $input.all();
const body = items[0].json.body || items[0].json;

// FIXED: Use correct field names from competition format
const task = body.prompt || '';
const base_url = (body.tripletex_credentials || {}).base_url || '';
const session_token = (body.tripletex_credentials || {}).session_token || '';
const files = body.files || [];

if (!task || !base_url || !session_token) {
  return [{ json: { status: 'completed', error: 'Missing required fields', _debug: { received_keys: Object.keys(body), has_prompt: !!body.prompt, has_creds: !!body.tripletex_credentials } } }];
}

const authHeader = 'Basic ' + Buffer.from('0:' + session_token).toString('base64');

async function tripletexCall(method, endpoint, reqBody) {
  const url = base_url.replace(/\/+$/, '') + endpoint;
  try {
    const opts = {
      method,
      url,
      headers: { 'Authorization': authHeader, 'Content-Type': 'application/json' },
      returnFullResponse: true,
      ignoreHttpStatusErrors: true,
      json: true
    };
    if (reqBody && method !== 'GET') {
      opts.body = typeof reqBody === 'string' ? JSON.parse(reqBody) : reqBody;
    }
    const r = await this.helpers.httpRequest(opts);
    return { ok: r.statusCode >= 200 && r.statusCode < 300, status: r.statusCode, data: r.body };
  } catch(e) { return { ok: false, error: e.message }; }
}

async function callGemini(prompt) {
  const r = await this.helpers.httpRequest({
    method: 'POST',
    url: 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=AIzaSyC_ya1fW-hpajZyb8osz35Y4znS9cx_h4g',
    body: {
      contents: [{ parts: [{ text: prompt }] }],
      generationConfig: { temperature: 0.0, responseMimeType: 'application/json' }
    },
    headers: { 'Content-Type': 'application/json' },
    json: true
  });
  const text = r.candidates[0].content.parts[0].text;
  return JSON.parse(text);
}

let fileContext = '';
if (files.length > 0) {
  fileContext = '\nAttached files:\n';
  for (const f of files) {
    fileContext += '- ' + f.filename + ' (' + f.mime_type + ')\n';
    if (f.mime_type && (f.mime_type.includes('text') || f.mime_type.includes('csv') || f.mime_type.includes('json'))) {
      try { fileContext += 'Content: ' + Buffer.from(f.content_base64, 'base64').toString('utf-8').substring(0, 2000) + '\n'; } catch(e){}
    }
  }
}

const classifyPrompt = `You are a Tripletex accounting API expert. Analyze this task and return a structured plan.

IMPORTANT RULES:
- The task may be in Norwegian or English
- Extract parameter VALUES as they appear in the task
- For date fields use YYYY-MM-DD format
- ansatt=employee, kunde=customer, produkt=product, faktura=invoice, betaling=payment, reiseregning=travel_expense, avdeling=department, prosjekt=project

Task: ${task}${fileContext}

Return JSON: {"task_type": "create_employee|create_customer|create_product|create_invoice|register_payment|create_travel_expense|update_employee|update_customer|delete_employee|delete_customer|delete_product|create_department|create_project|unknown", "confidence": 0.0-1.0, "extracted_params": {}, "reasoning": "..."}`;

const plan = await callGemini(classifyPrompt);
let results = []; let success = false;

try {
  switch (plan.task_type) {
    case 'create_employee': {
      const p = plan.extracted_params;
      const b = { firstName: p.firstName || '', lastName: p.lastName || '' };
      if (p.email) b.email = p.email;
      if (p.phoneNumberMobile || p.phoneNumber) b.phoneNumberMobile = p.phoneNumberMobile || p.phoneNumber;
      if (p.dateOfBirth) b.dateOfBirth = p.dateOfBirth;
      if (p.startDate) b.startDate = p.startDate;
      const r = await tripletexCall('POST', '/employee', b);
      results.push(r); success = r.ok;
      break;
    }
    case 'create_customer': {
      const p = plan.extracted_params;
      const b = { name: p.name || '', isCustomer: p.isCustomer !== false };
      if (p.email) b.email = p.email;
      if (p.phoneNumber) b.phoneNumber = p.phoneNumber;
      if (p.isSupplier) b.isSupplier = true;
      if (p.postalCode || p.city || p.address) {
        b.postalAddress = {};
        if (p.address) b.postalAddress.addressLine1 = p.address;
        if (p.postalCode) b.postalAddress.postalCode = p.postalCode;
        if (p.city) b.postalAddress.city = p.city;
      }
      const r = await tripletexCall('POST', '/customer', b);
      results.push(r); success = r.ok;
      break;
    }
    case 'create_product': {
      const p = plan.extracted_params;
      const b = { name: p.name || '' };
      if (p.number) b.number = p.number;
      if (p.priceExcludingVatCurrency !== undefined) b.priceExcludingVatCurrency = p.priceExcludingVatCurrency;
      if (p.unitPrice !== undefined) b.priceExcludingVatCurrency = p.unitPrice;
      const vt = await tripletexCall('GET', '/ledger/vatType?from=0&count=100');
      let vtId = 3;
      if (vt.ok && vt.data && vt.data.values) { const found = vt.data.values.find(v => v.percentage === (p.vatPercentage || 25)); if (found) vtId = found.id; }
      b.vatType = { id: vtId };
      const r = await tripletexCall('POST', '/product', b);
      results.push(r); success = r.ok;
      break;
    }
    case 'create_invoice': {
      const p = plan.extracted_params;
      let customerId;
      if (p.customerName) {
        const cs = await tripletexCall('GET', '/customer?name=' + encodeURIComponent(p.customerName) + '&from=0&count=5');
        if (cs.ok && cs.data && cs.data.values && cs.data.values.length > 0) { customerId = cs.data.values[0].id; }
        else { const nc = await tripletexCall('POST', '/customer', { name: p.customerName, isCustomer: true }); if (nc.ok) customerId = nc.data.value.id; }
      }
      results.push({ step: 'customer', customerId });
      const iDate = p.invoiceDate || new Date().toISOString().split('T')[0];
      const dDate = p.dueDate || new Date(Date.now()+30*86400000).toISOString().split('T')[0];
      const oLines = (p.lines || [{ description: 'Service', quantity: 1, unitPrice: 1000 }]).map(l => ({
        description: l.description || l.product || 'Item', count: l.quantity || 1, unitCostCurrency: l.unitPrice || 0, vatType: { id: 3 }
      }));
      const order = await tripletexCall('POST', '/order', { customer: { id: customerId }, deliveryDate: iDate, orderDate: iDate, orderLines: oLines });
      results.push({ step: 'order', data: order });
      if (order.ok) {
        const oId = order.data.value.id;
        const inv = await tripletexCall('POST', '/invoice', { invoiceDate: iDate, invoiceDueDate: dDate, customer: { id: customerId }, orders: [{ id: oId }] });
        results.push({ step: 'invoice', data: inv }); success = inv.ok;
        if (!inv.ok) {
          const inv2 = await tripletexCall('PUT', '/invoice/' + oId + '/:createInvoice?invoiceDate=' + iDate + '&sendToCustomer=false', {});
          results.push({ step: 'invoice_fallback', data: inv2 }); success = inv2.ok;
        }
      }
      break;
    }
    case 'register_payment': {
      const p = plan.extracted_params;
      const invs = await tripletexCall('GET', '/invoice?from=0&count=10');
      let iId = p.invoiceId;
      if (!iId && invs.ok && invs.data && invs.data.values) { const found = invs.data.values.find(i => (p.invoiceNumber && i.invoiceNumber === p.invoiceNumber) || i.amountOutstanding > 0); if (found) iId = found.id; }
      if (iId) { const r = await tripletexCall('POST', '/payment', { invoice: { id: iId }, amount: p.amount || 0, paymentDate: p.paymentDate || new Date().toISOString().split('T')[0] }); results.push(r); success = r.ok; }
      break;
    }
    case 'create_travel_expense': {
      const p = plan.extracted_params;
      const emps = await tripletexCall('GET', '/employee?from=0&count=1');
      let eId = 0;
      if (emps.ok && emps.data && emps.data.values && emps.data.values.length > 0) eId = emps.data.values[0].id;
      const r = await tripletexCall('POST', '/travelExpense', { employee: { id: eId }, title: p.title || p.description || 'Travel Expense', travelDetails: { departureDate: p.departureDate || p.startDate || new Date().toISOString().split('T')[0], returnDate: p.returnDate || p.endDate || new Date().toISOString().split('T')[0], destination: p.destination || '' } });
      results.push(r); success = r.ok;
      break;
    }
    case 'create_department': {
      const p = plan.extracted_params;
      const b = { name: p.name || '' }; if (p.departmentNumber) b.departmentNumber = p.departmentNumber;
      const r = await tripletexCall('POST', '/department', b); results.push(r); success = r.ok;
      break;
    }
    case 'create_project': {
      const p = plan.extracted_params;
      const b = { name: p.name || '', isInternal: p.isInternal !== false };
      if (p.number) b.number = p.number; if (p.startDate) b.startDate = p.startDate; if (p.endDate) b.endDate = p.endDate;
      const r = await tripletexCall('POST', '/project', b); results.push(r); success = r.ok;
      break;
    }
    case 'delete_employee': case 'delete_customer': case 'delete_product': {
      const p = plan.extracted_params; const et = plan.task_type.replace('delete_', ''); let eId = p.id;
      if (!eId) {
        let ep; if (et === 'employee') ep = '/employee?firstName=' + encodeURIComponent(p.firstName || '') + '&from=0&count=10';
        else if (et === 'customer') ep = '/customer?name=' + encodeURIComponent(p.name || '') + '&from=0&count=10';
        else ep = '/product?name=' + encodeURIComponent(p.name || '') + '&from=0&count=10';
        const s = await tripletexCall('GET', ep);
        if (s.ok && s.data && s.data.values && s.data.values.length > 0) {
          if (et === 'employee') { const m = s.data.values.find(e => (e.firstName||'').toLowerCase() === (p.firstName||'').toLowerCase() && (e.lastName||'').toLowerCase() === (p.lastName||'').toLowerCase()) || s.data.values[0]; eId = m.id; }
          else { eId = s.data.values[0].id; }
        }
      }
      if (eId) { const r = await tripletexCall('DELETE', '/' + et + '/' + eId); results.push(r); success = r.ok; }
      break;
    }
    case 'update_employee': case 'update_customer': {
      const p = plan.extracted_params; const et = plan.task_type.replace('update_', ''); let eId = p.id;
      if (!eId) {
        let ep; if (et === 'employee') ep = '/employee?firstName=' + encodeURIComponent(p.firstName || '') + '&from=0&count=10';
        else ep = '/customer?name=' + encodeURIComponent(p.name || p.oldName || '') + '&from=0&count=10';
        const s = await tripletexCall('GET', ep);
        if (s.ok && s.data && s.data.values && s.data.values.length > 0) eId = s.data.values[0].id;
      }
      if (eId) {
        const cur = await tripletexCall('GET', '/' + et + '/' + eId);
        if (cur.ok) { const ub = { ...cur.data.value, ...(p.updates || p) }; delete ub.id; const r = await tripletexCall('PUT', '/' + et + '/' + eId, ub); results.push(r); success = r.ok; }
      }
      break;
    }
    default: {
      const fp = await callGemini('You are a Tripletex v2 REST API expert. Task: ' + task + fileContext + '\n\nReturn JSON array: [{"method": "POST", "endpoint": "/endpoint", "body": {...}}]');
      const calls = Array.isArray(fp) ? fp : (fp.api_calls || [fp]);
      for (const c of calls) { const r = await tripletexCall(c.method || 'POST', c.endpoint, c.body || null); results.push(r); if (r.ok) success = true; }
    }
  }
} catch (err) { results.push({ error: err.message }); }

return [{ json: { status: 'completed', _debug: { task_type: plan.task_type, confidence: plan.confidence, reasoning: plan.reasoning, success, results } } }];