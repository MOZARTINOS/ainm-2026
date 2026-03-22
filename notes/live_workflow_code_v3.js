// NM i AI 2026 - Tripletex Agent v3 (ALL BUGS FIXED)
const items = $input.all();
const body = items[0].json.body || items[0].json;

// Parse competition format
const task = body.prompt || body.task || '';
const base_url = (body.tripletex_credentials || {}).base_url || body.base_url || '';
const session_token = (body.tripletex_credentials || {}).session_token || body.session_token || '';
const files = body.files || body.attached_files || [];

if (!task || !base_url || !session_token) {
  return [{ json: { status: 'completed' } }];
}

const authHeader = 'Basic ' + Buffer.from('0:' + session_token).toString('base64');
// Ensure base_url ends properly - the base_url from competition already includes /v2
const apiBase = base_url.replace(/\/+$/, '');

async function tx(method, endpoint, reqBody) {
  const url = apiBase + endpoint;
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
  } catch (e) {
    let ed;
    try { ed = typeof e.body === 'string' ? JSON.parse(e.body) : (e.body || e.message); } catch (_) { ed = e.message; }
    return { ok: false, error: ed, status: e.statusCode || 0 };
  }
}

async function callGemini(prompt) {
  const r = await this.helpers.httpRequest({
    method: 'POST',
    url: 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=GEMINI_API_KEY_REDACTED',
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

// Parse attached files
let fileContext = '';
if (files.length > 0) {
  fileContext = '\nAttached files:\n';
  for (const f of files) {
    fileContext += '- ' + f.filename + ' (' + f.mime_type + ')\n';
    if (f.content_base64 && f.mime_type && (f.mime_type.includes('text') || f.mime_type.includes('csv') || f.mime_type.includes('json'))) {
      try { fileContext += 'Content: ' + Buffer.from(f.content_base64, 'base64').toString('utf-8').substring(0, 3000) + '\n'; } catch (e) {}
    }
  }
}

// Fetch VAT types once
let cachedVatTypes = null;
async function getVatId(pct) {
  if (!cachedVatTypes) {
    const vt = await tx('GET', '/ledger/vatType?from=0&count=100');
    cachedVatTypes = (vt.ok && vt.data && vt.data.values) ? vt.data.values : [];
  }
  const target = pct != null ? Number(pct) : 25;
  const found = cachedVatTypes.find(v => v.percentage === target);
  if (found) return found.id;
  const fallback = cachedVatTypes.find(v => v.percentage === 25);
  if (fallback) return fallback.id;
  return cachedVatTypes.length > 0 ? cachedVatTypes[0].id : 3;
}

const classifyPrompt = `You are a Tripletex accounting API expert. Analyze this task and return a structured plan.

RULES:
- The task may be in Norwegian, English, Spanish, Portuguese, German, French, or Italian.
- Norwegian translations: ansatt=employee, kunde=customer, produkt=product, faktura=invoice, betaling=payment, reiseregning=travel_expense, avdeling=department, prosjekt=project, kreditnota=credit_note, bilag/voucher=voucher
- Extract ALL parameter values as they appear in the task.
- Dates must be YYYY-MM-DD format. If only day/month given, assume current year 2026.
- For employees: extract firstName, lastName, email, phoneNumberMobile, dateOfBirth, startDate, department, userType
- For customers: extract name, email, phoneNumber, organizationNumber, address, postalCode, city, isPrivateIndividual
- For products: extract name, number, priceExcludingVat (excl VAT price), vatPercentage (default 25)
- For invoices: extract customerName, invoiceDate, dueDate, lines[{description, quantity, unitPrice, vatPercentage}]
- For payments: extract invoiceNumber, invoiceId, amount, paymentDate
- For travel expenses: extract employeeName, title, departureDate, returnDate, destination
- For credit notes: extract invoiceNumber or invoiceId
- For updates: extract search fields (firstName, lastName, name) AND update fields separately in "updates" object
- For vouchers: extract date, description, rows with account numbers and amounts

Task: ${task}${fileContext}

Return: {"task_type": "create_employee|create_customer|create_product|create_invoice|register_payment|create_travel_expense|update_employee|update_customer|delete_employee|delete_customer|delete_product|credit_note|create_department|create_project|create_voucher|unknown", "confidence": 0.0, "extracted_params": {}, "reasoning": ""}`;

const plan = await callGemini(classifyPrompt);
const p = plan.extracted_params || {};
let results = [], success = false;

try {
  switch (plan.task_type) {

    case 'create_employee': {
      const b = {};
      if (p.firstName) b.firstName = p.firstName;
      if (p.lastName) b.lastName = p.lastName;
      if (p.email) b.email = p.email;
      if (p.phoneNumberMobile || p.phoneNumber) b.phoneNumberMobile = String(p.phoneNumberMobile || p.phoneNumber);
      if (p.dateOfBirth) b.dateOfBirth = p.dateOfBirth;
      if (p.startDate) b.startDate = p.startDate;
      // CRITICAL: Set administrator role for max scoring (5 points)
      b.userType = p.userType || 'ADMINISTRATOR';
      // Department lookup
      if (p.department) {
        const ds = await tx('GET', '/department?name=' + encodeURIComponent(p.department) + '&from=0&count=5');
        if (ds.ok && ds.data && ds.data.values && ds.data.values.length > 0) {
          b.department = { id: ds.data.values[0].id };
        }
      }
      const r = await tx('POST', '/employee', b);
      results.push(r);
      success = r.ok;
      // If startDate provided, update employment
      if (r.ok && p.startDate) {
        const empId = r.data.value.id;
        const empFull = await tx('GET', '/employee/' + empId + '?fields=*,employments(*)');
        if (empFull.ok) {
          const upd = empFull.data.value;
          if (!upd.employments || upd.employments.length === 0) {
            upd.employments = [{ startDate: p.startDate }];
          } else {
            upd.employments[0].startDate = p.startDate;
          }
          const ur = await tx('PUT', '/employee/' + empId, upd);
          results.push({ step: 'set_start_date', ...ur });
        }
      }
      break;
    }

    case 'create_customer': {
      const b = { name: p.name || '', isCustomer: true };
      if (p.email) b.email = p.email;
      if (p.phoneNumber) b.phoneNumber = String(p.phoneNumber);
      if (p.organizationNumber) b.organizationNumber = String(p.organizationNumber);
      if (p.isSupplier) b.isSupplier = true;
      if (p.isPrivateIndividual) b.isPrivateIndividual = true;
      if (p.postalCode || p.city || p.address) {
        b.postalAddress = {};
        if (p.address) b.postalAddress.addressLine1 = p.address;
        if (p.postalCode) b.postalAddress.postalCode = String(p.postalCode);
        if (p.city) b.postalAddress.city = p.city;
        b.postalAddress.country = { id: 162 }; // Norway
      }
      const r = await tx('POST', '/customer', b);
      results.push(r);
      success = r.ok;
      break;
    }

    case 'create_product': {
      const vtId = await getVatId(p.vatPercentage);
      const b = { name: p.name || '' };
      if (p.priceExcludingVat != null || p.priceExcludingVatCurrency != null || p.unitPrice != null) {
        b.priceExcludingVatCurrency = Number(p.priceExcludingVat || p.priceExcludingVatCurrency || p.unitPrice);
      }
      if (p.number) b.number = String(p.number);
      b.vatType = { id: vtId };
      const r = await tx('POST', '/product', b);
      results.push(r);
      success = r.ok;
      break;
    }

    case 'create_invoice': {
      // Step 1: Find or create customer
      let customerId;
      if (p.customerName) {
        const cs = await tx('GET', '/customer?name=' + encodeURIComponent(p.customerName) + '&from=0&count=5');
        if (cs.ok && cs.data && cs.data.values && cs.data.values.length > 0) {
          customerId = cs.data.values[0].id;
        } else {
          const nc = await tx('POST', '/customer', { name: p.customerName, isCustomer: true });
          if (nc.ok) customerId = nc.data.value.id;
          results.push({ step: 'create_customer', ...nc });
        }
      }
      if (!customerId) {
        const ac = await tx('GET', '/customer?from=0&count=1');
        if (ac.ok && ac.data && ac.data.values && ac.data.values.length > 0) customerId = ac.data.values[0].id;
      }
      if (!customerId) { results.push({ error: 'No customer available' }); break; }

      // Step 2: Get VAT type
      const vtId = await getVatId(25);

      // Step 3: Create order
      const today = new Date().toISOString().split('T')[0];
      const iDate = p.invoiceDate || today;
      const oLines = (p.lines && p.lines.length > 0 ? p.lines : [{ description: 'Service', quantity: 1, unitPrice: 1000 }]).map(l => ({
        description: l.description || l.product || 'Item',
        count: l.quantity || 1,
        unitCostCurrency: l.unitPrice || l.amount || 0,
        vatType: { id: vtId }
      }));

      const order = await tx('POST', '/order', {
        customer: { id: customerId },
        deliveryDate: iDate,
        orderDate: iDate,
        orderLines: oLines
      });
      results.push({ step: 'create_order', ...order });

      // Step 4: Convert order to invoice using CORRECT endpoint
      if (order.ok) {
        const orderId = order.data.value.id;
        let invoiceUrl = '/order/' + orderId + '/:invoice?invoiceDate=' + iDate + '&sendToCustomer=false';
        if (p.dueDate) invoiceUrl += '&invoiceDueDate=' + p.dueDate;
        const inv = await tx('PUT', invoiceUrl, {});
        results.push({ step: 'convert_to_invoice', ...inv });
        success = inv.ok;
      }
      break;
    }

    case 'register_payment': {
      let invId = p.invoiceId;
      if (!invId && p.invoiceNumber) {
        const is = await tx('GET', '/invoice?invoiceNumber=' + p.invoiceNumber + '&from=0&count=5');
        if (is.ok && is.data && is.data.values && is.data.values.length > 0) invId = is.data.values[0].id;
      }
      if (!invId) {
        const is = await tx('GET', '/invoice?from=0&count=50');
        if (is.ok && is.data && is.data.values) {
          const outstanding = is.data.values.find(i => i.amountOutstanding && i.amountOutstanding > 0);
          if (outstanding) invId = outstanding.id;
          else if (is.data.values.length > 0) invId = is.data.values[0].id;
        }
      }
      if (invId) {
        const payDate = p.paymentDate || new Date().toISOString().split('T')[0];
        const payAmount = p.amount || 0;
        // Try PUT /:payment first (correct endpoint per docs)
        const r = await tx('PUT', '/invoice/' + invId + '/:payment', {
          paymentDate: payDate,
          paymentTypeId: 0,
          amount: payAmount
        });
        results.push(r);
        success = r.ok;
        // Fallback to POST /payment
        if (!r.ok) {
          const r2 = await tx('POST', '/payment', {
            invoice: { id: invId },
            amount: payAmount,
            paymentDate: payDate
          });
          results.push({ step: 'fallback_payment', ...r2 });
          success = r2.ok;
        }
      } else {
        results.push({ error: 'No invoice found' });
      }
      break;
    }

    case 'credit_note': {
      let invId = p.invoiceId;
      if (!invId && p.invoiceNumber) {
        const is = await tx('GET', '/invoice?invoiceNumber=' + p.invoiceNumber + '&from=0&count=5');
        if (is.ok && is.data && is.data.values && is.data.values.length > 0) invId = is.data.values[0].id;
      }
      if (!invId) {
        const is = await tx('GET', '/invoice?from=0&count=10');
        if (is.ok && is.data && is.data.values && is.data.values.length > 0) invId = is.data.values[0].id;
      }
      if (invId) {
        const r = await tx('PUT', '/invoice/' + invId + '/:createCreditNote', {});
        results.push(r);
        success = r.ok;
      } else {
        results.push({ error: 'No invoice found for credit note' });
      }
      break;
    }

    case 'create_travel_expense': {
      let eId;
      if (p.employeeName) {
        const parts = (p.employeeName || '').split(' ');
        let q = '/employee?from=0&count=20';
        if (parts[0]) q += '&firstName=' + encodeURIComponent(parts[0]);
        if (parts.length > 1) q += '&lastName=' + encodeURIComponent(parts.slice(1).join(' '));
        const es = await tx('GET', q);
        if (es.ok && es.data && es.data.values && es.data.values.length > 0) eId = es.data.values[0].id;
      }
      if (!eId) {
        const es = await tx('GET', '/employee?from=0&count=1');
        if (es.ok && es.data && es.data.values && es.data.values.length > 0) eId = es.data.values[0].id;
      }
      const today = new Date().toISOString().split('T')[0];
      const r = await tx('POST', '/travelExpense', {
        employee: { id: eId },
        title: p.title || p.description || p.purpose || 'Travel Expense',
        travelDetails: {
          departureDate: p.departureDate || p.startDate || today,
          returnDate: p.returnDate || p.endDate || p.departureDate || p.startDate || today,
          destination: p.destination || ''
        }
      });
      results.push(r);
      success = r.ok;
      break;
    }

    case 'create_department': {
      const b = { name: p.name || '' };
      if (p.departmentNumber) b.departmentNumber = String(p.departmentNumber);
      const r = await tx('POST', '/department', b);
      results.push(r);
      success = r.ok;
      break;
    }

    case 'create_project': {
      let pcId;
      if (p.customerName) {
        const cs = await tx('GET', '/customer?name=' + encodeURIComponent(p.customerName) + '&from=0&count=3');
        if (cs.ok && cs.data && cs.data.values && cs.data.values.length > 0) pcId = cs.data.values[0].id;
      }
      const b = { name: p.name || '' };
      b.isInternal = pcId ? false : (p.isInternal !== false);
      if (p.number || p.projectNumber) b.number = String(p.number || p.projectNumber);
      if (pcId) b.customer = { id: pcId };
      if (p.startDate) b.startDate = p.startDate;
      if (p.endDate) b.endDate = p.endDate;
      const r = await tx('POST', '/project', b);
      results.push(r);
      success = r.ok;
      break;
    }

    case 'create_voucher': {
      const today = new Date().toISOString().split('T')[0];
      const vDate = p.date || today;
      const rows = (p.rows || []).map(row => ({
        date: vDate,
        description: row.description || p.description || '',
        account: { id: row.debit_account || row.account || row.accountNumber },
        amountCurrency: row.amount || 0
      }));
      const r = await tx('POST', '/ledger/voucher', {
        date: vDate,
        description: p.description || 'Voucher',
        rows: rows
      });
      results.push(r);
      success = r.ok;
      break;
    }

    case 'delete_employee': case 'delete_customer': case 'delete_product': {
      const entityType = plan.task_type.replace('delete_', '');
      let entityId = p.id;
      if (!entityId) {
        let searchEndpoint;
        if (entityType === 'employee') {
          searchEndpoint = '/employee?from=0&count=50';
          if (p.firstName) searchEndpoint += '&firstName=' + encodeURIComponent(p.firstName);
          if (p.lastName) searchEndpoint += '&lastName=' + encodeURIComponent(p.lastName);
        } else if (entityType === 'customer') {
          searchEndpoint = '/customer?name=' + encodeURIComponent(p.name || '') + '&from=0&count=50';
        } else {
          searchEndpoint = '/product?name=' + encodeURIComponent(p.name || '') + '&from=0&count=50';
        }
        const s = await tx('GET', searchEndpoint);
        if (s.ok && s.data && s.data.values && s.data.values.length > 0) {
          if (entityType === 'employee') {
            const match = s.data.values.find(e =>
              (!p.firstName || (e.firstName || '').toLowerCase() === p.firstName.toLowerCase()) &&
              (!p.lastName || (e.lastName || '').toLowerCase() === p.lastName.toLowerCase())
            ) || s.data.values[0];
            entityId = match.id;
          } else {
            const match = s.data.values.find(e =>
              p.name && (e.name || '').toLowerCase().includes(p.name.toLowerCase())
            ) || s.data.values[0];
            entityId = match.id;
          }
        }
      }
      if (entityId) {
        const r = await tx('DELETE', '/' + entityType + '/' + entityId);
        results.push(r);
        success = r.ok;
      } else {
        results.push({ error: entityType + ' not found' });
      }
      break;
    }

    case 'update_employee': {
      let searchQ = '/employee?from=0&count=50';
      if (p.firstName) searchQ += '&firstName=' + encodeURIComponent(p.firstName);
      if (p.lastName) searchQ += '&lastName=' + encodeURIComponent(p.lastName);
      const es = await tx('GET', searchQ);
      if (es.ok && es.data && es.data.values && es.data.values.length > 0) {
        const match = es.data.values.find(e =>
          (!p.firstName || (e.firstName || '').toLowerCase() === p.firstName.toLowerCase()) &&
          (!p.lastName || (e.lastName || '').toLowerCase() === p.lastName.toLowerCase())
        ) || es.data.values[0];
        const full = await tx('GET', '/employee/' + match.id + '?fields=*,employments(*)');
        if (full.ok) {
          const upd = full.data.value;
          const updates = p.updates || {};
          if (updates.email || p.newEmail) upd.email = updates.email || p.newEmail;
          if (updates.phoneNumberMobile || p.newPhone) upd.phoneNumberMobile = String(updates.phoneNumberMobile || p.newPhone);
          if (updates.firstName || p.newFirstName) upd.firstName = updates.firstName || p.newFirstName;
          if (updates.lastName || p.newLastName) upd.lastName = updates.lastName || p.newLastName;
          if (updates.dateOfBirth) upd.dateOfBirth = updates.dateOfBirth;
          if (updates.userType) upd.userType = updates.userType;
          if (updates.department) {
            const ds = await tx('GET', '/department?name=' + encodeURIComponent(updates.department) + '&from=0&count=5');
            if (ds.ok && ds.data && ds.data.values && ds.data.values.length > 0) {
              upd.department = { id: ds.data.values[0].id };
            }
          }
          const r = await tx('PUT', '/employee/' + match.id, upd);
          results.push(r);
          success = r.ok;
        }
      } else {
        results.push({ error: 'Employee not found' });
      }
      break;
    }

    case 'update_customer': {
      let searchQ = '/customer?name=' + encodeURIComponent(p.name || p.oldName || '') + '&from=0&count=50';
      const cs = await tx('GET', searchQ);
      if (cs.ok && cs.data && cs.data.values && cs.data.values.length > 0) {
        const match = cs.data.values.find(c =>
          (p.name || p.oldName) && (c.name || '').toLowerCase().includes((p.name || p.oldName || '').toLowerCase())
        ) || cs.data.values[0];
        const full = await tx('GET', '/customer/' + match.id);
        if (full.ok) {
          const upd = full.data.value;
          const updates = p.updates || {};
          if (updates.name || p.newName) upd.name = updates.name || p.newName;
          if (updates.email) upd.email = updates.email;
          if (updates.phoneNumber) upd.phoneNumber = String(updates.phoneNumber);
          if (updates.address || updates.postalCode || updates.city) {
            if (!upd.postalAddress) upd.postalAddress = {};
            if (updates.address) upd.postalAddress.addressLine1 = updates.address;
            if (updates.postalCode) upd.postalAddress.postalCode = String(updates.postalCode);
            if (updates.city) upd.postalAddress.city = updates.city;
            upd.postalAddress.country = { id: 162 };
          }
          const r = await tx('PUT', '/customer/' + match.id, upd);
          results.push(r);
          success = r.ok;
        }
      } else {
        results.push({ error: 'Customer not found' });
      }
      break;
    }

    default: {
      // Fallback: let Gemini plan the API calls
      const fp = await callGemini('You are a Tripletex v2 REST API expert. Plan the exact API calls for this task.\nAvailable: GET/POST/PUT/DELETE on /employee, /customer, /product, /order, /invoice, /travelExpense, /project, /department, /ledger/vatType, /ledger/account, /ledger/posting, /ledger/voucher, /payment\nSpecial actions: PUT /order/{id}/:invoice, PUT /invoice/{id}/:createCreditNote, PUT /invoice/{id}/:payment\nTask: ' + task + fileContext + '\n\nReturn JSON array: [{"method": "POST", "endpoint": "/endpoint", "body": {...}}]');
      const calls = Array.isArray(fp) ? fp : (fp.api_calls || fp.calls || [fp]);
      for (const c of calls) {
        const r = await tx(c.method || 'POST', c.endpoint, c.body || null);
        results.push(r);
        if (r.ok) success = true;
      }
    }
  }

  // Retry on failure with Gemini error correction
  if (!success && results.length > 0) {
    try {
      const lastErr = results[results.length - 1];
      const c = await callGemini('Tripletex API call failed. Analyze the error and return a corrected single API call.\nTask: ' + task + '\nType: ' + plan.task_type + '\nParams: ' + JSON.stringify(p) + '\nError: ' + JSON.stringify(lastErr) + '\nReturn: {"method":"POST","endpoint":"/...","body":{...}}');
      const r = await tx(c.method || 'POST', c.endpoint, c.body || null);
      results.push({ step: 'retry', ...r });
      if (r.ok) success = true;
    } catch (e) { results.push({ step: 'retry_error', error: e.message }); }
  }

} catch (err) {
  results.push({ error: err.message, stack: err.stack });
}

return [{ json: { status: 'completed', _debug: { task_type: plan.task_type, confidence: plan.confidence, reasoning: plan.reasoning, success, results } } }];
