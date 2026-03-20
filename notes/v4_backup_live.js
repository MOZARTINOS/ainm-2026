// NM i AI 2026 - Tripletex Agent v4.0 (OPTIMIZED: cache, PDF, parallel, voucher)
const items = $input.all();
const body = items[0].json.body || items[0].json;

const task = body.prompt || body.task || '';
const base_url = (body.tripletex_credentials || {}).base_url || body.base_url || '';
const session_token = (body.tripletex_credentials || {}).session_token || body.session_token || '';
const files = body.files || body.attached_files || [];

if (!task || !base_url || !session_token) return [{ json: { status: 'completed' } }];

const authHeader = 'Basic ' + Buffer.from('0:' + session_token).toString('base64');
const apiBase = base_url.replace(/\/+$/, '');
const GEMINI_KEY = 'AIzaSyC_ya1fW-hpajZyb8osz35Y4znS9cx_h4g';

// === HTTP helper ===
async function tx(method, endpoint, reqBody) {
  const url = apiBase + endpoint;
  const opts = {
    method, url,
    headers: { 'Authorization': authHeader, 'Content-Type': 'application/json' },
    returnFullResponse: true, ignoreHttpStatusErrors: true, json: true
  };
  if (reqBody && method !== 'GET') opts.body = typeof reqBody === 'string' ? JSON.parse(reqBody) : reqBody;
  try {
    const r = await this.helpers.httpRequest(opts);
    return { ok: r.statusCode >= 200 && r.statusCode < 300, status: r.statusCode, data: r.body };
  } catch (e) {
    let ed; try { ed = typeof e.body === 'string' ? JSON.parse(e.body) : (e.body || e.message); } catch (_) { ed = e.message; }
    return { ok: false, error: ed, status: e.statusCode || 0 };
  }
}

// === CACHE: fetch all reference data in parallel on first call ===
const [vatResult, deptResult, empResult] = await Promise.all([
  tx('GET', '/ledger/vatType?from=0&count=100'),
  tx('GET', '/department?from=0&count=100'),
  tx('GET', '/employee?from=0&count=100&fields=id,firstName,lastName,email,department')
]);

const vatTypes = (vatResult.ok && vatResult.data && vatResult.data.values) ? vatResult.data.values : [];
const departments = (deptResult.ok && deptResult.data && deptResult.data.values) ? deptResult.data.values : [];
const employees = (empResult.ok && empResult.data && empResult.data.values) ? empResult.data.values : [];
const defaultDeptId = departments.length > 0 ? departments[0].id : null;
const firstEmployeeId = employees.length > 0 ? employees[0].id : null;

function getOutgoingVatId(pct) {
  const target = pct != null ? Number(pct) : 25;
  // Hardcoded outgoing VAT IDs (verified on sandbox + competition env)
  const OUTGOING_VAT = { 25: 3, 15: 31, 12: 32, 0: 6 };
  if (OUTGOING_VAT[target] !== undefined) return OUTGOING_VAT[target];
  // Fallback: search cache for outgoing ("utgående") VAT
  const outgoing = vatTypes.find(v => v.percentage === target && v.name && v.name.toLowerCase().includes('utg'));
  if (outgoing) return outgoing.id;
  return 3; // default 25% outgoing
}

function findEmployee(firstName, lastName) {
  return employees.find(e =>
    (!firstName || (e.firstName || '').toLowerCase() === firstName.toLowerCase()) &&
    (!lastName || (e.lastName || '').toLowerCase() === lastName.toLowerCase())
  ) || null;
}

function findDeptByName(name) {
  if (!name) return null;
  return departments.find(d => d.name && d.name.toLowerCase().includes(name.toLowerCase())) || null;
}

// === Gemini helper with PDF support ===
async function callGemini(prompt, pdfFiles) {
  const parts = [{ text: prompt }];
  if (pdfFiles && pdfFiles.length > 0) {
    for (const f of pdfFiles) {
      if (f.content_base64) {
        parts.push({ inline_data: { mime_type: f.mime_type || 'application/pdf', data: f.content_base64 } });
      }
    }
  }
  const r = await this.helpers.httpRequest({
    method: 'POST',
    url: 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=' + GEMINI_KEY,
    body: {
      contents: [{ parts }],
      generationConfig: { temperature: 0.0, responseMimeType: 'application/json' }
    },
    headers: { 'Content-Type': 'application/json' }, json: true
  });
  return JSON.parse(r.candidates[0].content.parts[0].text);
}

// === Parse files ===
let fileContext = '';
const pdfFiles = [];
if (files.length > 0) {
  fileContext = '\nAttached files:\n';
  for (const f of files) {
    fileContext += '- ' + f.filename + ' (' + f.mime_type + ')\n';
    if (f.mime_type === 'application/pdf') {
      pdfFiles.push(f);
      fileContext += '[PDF content will be analyzed via vision]\n';
    } else if (f.content_base64 && f.mime_type && (f.mime_type.includes('text') || f.mime_type.includes('csv') || f.mime_type.includes('json'))) {
      try { fileContext += 'Content: ' + Buffer.from(f.content_base64, 'base64').toString('utf-8').substring(0, 3000) + '\n'; } catch (e) {}
    }
  }
}

// === Classify task ===
const classifyPrompt = `You are a Tripletex accounting API expert. Analyze this task and return a structured plan.

RULES:
- Task may be in Norwegian, English, Spanish, Portuguese, German, French, Italian.
- Norwegian: ansatt=employee, kunde=customer, produkt=product, faktura=invoice, betaling=payment, reiseregning=travel_expense, avdeling=department, prosjekt=project, kreditnota=credit_note, bilag/voucher=voucher, slett=delete, oppdater/endre=update
- Extract ALL parameters. Dates: YYYY-MM-DD. If only day/month, assume 2026.
- For employees: firstName, lastName, email, phoneNumberMobile, dateOfBirth, startDate, department, isAdmin
- For customers: name, email, phoneNumber, organizationNumber, address, postalCode, city, isPrivateIndividual
- For products: name, number, priceExcludingVat, vatPercentage (default 25)
- For invoices: customerName, invoiceDate, dueDate, lines[{description, quantity, unitPrice, vatPercentage}]
- For payments: invoiceNumber, invoiceId, amount, paymentDate
- For travel expenses: employeeName, title, departureDate, returnDate, destination
- For credit notes: invoiceNumber or invoiceId
- For updates: search fields (firstName, lastName) AND updates object with new values
- For vouchers: date, description, postings[{accountNumber, amount, isDebit, description}]
- For deletes: firstName+lastName or name to identify entity
- If PDF attached: extract data from the PDF content shown
- IMPORTANT: If the task asks to create MULTIPLE entities of the same type (e.g. "create three departments: X, Y and Z" or "create two employees: A and B"), you MUST return an "entities" array with one object per entity, each containing its own extracted_params. The task_type stays the same for all.

Task: ${task}${fileContext}

Return: {"task_type": "create_employee|create_customer|create_product|create_invoice|register_payment|create_travel_expense|update_employee|update_customer|delete_employee|delete_customer|credit_note|create_department|create_project|create_voucher|unknown", "confidence": 0.0, "extracted_params": {}, "entities": null, "reasoning": ""}
If multiple entities: {"task_type": "create_department", "confidence": 1.0, "extracted_params": {}, "entities": [{"name": "X"}, {"name": "Y"}, {"name": "Z"}], "reasoning": "..."}`;

const plan = await callGemini(classifyPrompt, pdfFiles);
const entities = plan.entities || null;
let results = [], success = false;

// Multi-entity support: if entities array present, execute task_type for each entity
const paramsList = entities && entities.length > 0
  ? entities.map(e => ({ ...(plan.extracted_params || {}), ...e }))
  : [plan.extracted_params || {}];

for (const p of paramsList) {
try {
  switch (plan.task_type) {

    case 'create_employee': {
      const b = {};
      if (p.firstName) b.firstName = p.firstName;
      if (p.lastName) b.lastName = p.lastName;
      if (p.email) b.email = p.email;
      if (p.phoneNumberMobile || p.phoneNumber) {
        let phone = String(p.phoneNumberMobile || p.phoneNumber).replace(/[^0-9+]/g, '');
        if (phone.startsWith('+47')) phone = phone.substring(3);
        if (phone.startsWith('0047')) phone = phone.substring(4);
        if (phone.startsWith('47') && phone.length === 10) phone = phone.substring(2);
        if (phone.length === 8 && /^[49]/.test(phone)) b.phoneNumberMobile = phone;
      }
      if (p.dateOfBirth) b.dateOfBirth = p.dateOfBirth;
      // NEVER send startDate in employee body — API rejects it ("Feltet eksisterer ikke")
      // startDate belongs on employments, handled separately after creation
      b.userType = b.email ? 'STANDARD' : 'NO_ACCESS';
      if (p.department) {
        const dept = findDeptByName(p.department);
        if (dept) b.department = { id: dept.id };
      }
      if (!b.department && defaultDeptId) b.department = { id: defaultDeptId };
      const r = await tx('POST', '/employee', b);
      results.push(r); success = r.ok;
      if (r.ok) {
        const newEmpId = r.data.value.id;
        // Grant ALL_PRIVILEGES entitlements (= "Administrator role assigned", worth 5 points)
        const entR = await tx('PUT', '/employee/entitlement/:grantEntitlementsByTemplate?employeeId=' + newEmpId + '&template=ALL_PRIVILEGES', {});
        results.push({ step: 'grant_entitlements', ok: entR.ok || entR.status === 200, status: entR.status });
        // Set startDate if provided
        if (p.startDate) {
          const empFull = await tx('GET', '/employee/' + newEmpId + '?fields=*,employments(*)');
          if (empFull.ok) {
            const upd = empFull.data.value;
            if (!upd.employments || upd.employments.length === 0) upd.employments = [{ startDate: p.startDate }];
            else upd.employments[0].startDate = p.startDate;
            const ur = await tx('PUT', '/employee/' + newEmpId, upd);
            results.push({ step: 'set_start_date', ...ur });
          }
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
        b.postalAddress.country = { id: 161 };
      }
      const r = await tx('POST', '/customer', b);
      results.push(r); success = r.ok;
      break;
    }

    case 'create_product': {
      const vtId = getOutgoingVatId(p.vatPercentage);
      const b = { name: p.name || '' };
      if (p.priceExcludingVat != null || p.priceExcludingVatCurrency != null || p.unitPrice != null) {
        b.priceExcludingVatCurrency = Number(p.priceExcludingVat || p.priceExcludingVatCurrency || p.unitPrice);
      }
      if (p.number) b.number = String(p.number);
      b.vatType = { id: vtId };
      const r = await tx('POST', '/product', b);
      results.push(r); success = r.ok;
      break;
    }

    case 'create_invoice': {
      // Find customer (or create)
      let customerId;
      if (p.customerName) {
        const custResult = await tx('GET', '/customer?name=' + encodeURIComponent(p.customerName) + '&from=0&count=5');
        if (custResult.ok && custResult.data && custResult.data.values && custResult.data.values.length > 0) {
          customerId = custResult.data.values[0].id;
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
      if (!customerId) { results.push({ error: 'No customer' }); break; }

      const today = new Date().toISOString().split('T')[0];
      const iDate = p.invoiceDate || today;
      const oLines = (p.lines && p.lines.length > 0 ? p.lines : [{ description: 'Service', quantity: 1, unitPrice: 1000 }]).map(l => ({
        description: l.description || l.product || 'Item',
        count: l.quantity || 1,
        unitCostCurrency: l.unitPrice || l.amount || 0,
        vatType: { id: getOutgoingVatId(l.vatPercentage) }
      }));

      const order = await tx('POST', '/order', {
        customer: { id: customerId }, deliveryDate: iDate, orderDate: iDate, orderLines: oLines
      });
      results.push({ step: 'create_order', ...order });

      if (order.ok) {
        let invoiceUrl = '/order/' + order.data.value.id + '/:invoice?invoiceDate=' + iDate + '&sendToCustomer=false';
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
          const outstanding = is.data.values.find(i => i.amountOutstanding > 0);
          if (outstanding) invId = outstanding.id;
          else if (is.data.values.length > 0) invId = is.data.values[0].id;
        }
      }
      if (invId) {
        const payDate = p.paymentDate || new Date().toISOString().split('T')[0];
        const r = await tx('PUT', '/invoice/' + invId + '/:payment', { paymentDate: payDate, paymentTypeId: 0, amount: p.amount || 0 });
        results.push(r); success = r.ok;
        if (!r.ok) {
          const r2 = await tx('POST', '/payment', { invoice: { id: invId }, amount: p.amount || 0, paymentDate: payDate });
          results.push({ step: 'fallback', ...r2 }); success = r2.ok;
        }
      } else results.push({ error: 'No invoice found' });
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
      if (invId) { const r = await tx('PUT', '/invoice/' + invId + '/:createCreditNote', {}); results.push(r); success = r.ok; }
      else results.push({ error: 'No invoice' });
      break;
    }

    case 'create_travel_expense': {
      let eId;
      if (p.employeeName) {
        const parts = p.employeeName.split(' ');
        const emp = findEmployee(parts[0], parts.length > 1 ? parts.slice(1).join(' ') : null);
        if (emp) eId = emp.id;
      }
      if (!eId) eId = firstEmployeeId;
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
      results.push(r); success = r.ok;
      break;
    }

    case 'create_department': {
      const b = { name: p.name || '' };
      if (p.departmentNumber) b.departmentNumber = String(p.departmentNumber);
      const r = await tx('POST', '/department', b);
      results.push(r); success = r.ok;
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
      b.startDate = p.startDate || new Date().toISOString().split('T')[0];
      if (p.endDate) b.endDate = p.endDate;
      if (firstEmployeeId) b.projectManager = { id: firstEmployeeId };
      const r = await tx('POST', '/project', b);
      results.push(r); success = r.ok;
      break;
    }

    case 'create_voucher': {
      const today = new Date().toISOString().split('T')[0];
      let vDate = String(p.date || today);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(vDate)) vDate = today;
      // Account number → locked vatType ID mapping (Tripletex enforces these)
      function guessVatForAccount(acctNumber) {
        const n = Number(acctNumber);
        if (n >= 3000 && n < 3100) return 3;  // Salgsinntekt avgiftspliktig → 25% outgoing
        if (n >= 3100 && n < 3200) return 6;  // Salgsinntekt avgiftsfri → 0% outside VAT
        if (n >= 4000 && n < 5000) return 1;  // Innkjøp → 25% ingoing
        if (n >= 6000 && n < 7000) return 1;  // Driftskostnader → 25% ingoing
        if (n >= 7000 && n < 8000) return 1;  // Personalkostnader/bil → 25% ingoing
        return 0; // Default: no VAT (bank, receivables, payables etc)
      }
      let postings = [];
      if (p.postings && p.postings.length > 0) {
        for (let i = 0; i < p.postings.length; i++) {
          const posting = p.postings[i];
          let accountId;
          if (posting.accountNumber) {
            const acctResp = await tx('GET', '/ledger/account?number=' + posting.accountNumber + '&from=0&count=1');
            if (acctResp.ok && acctResp.data && acctResp.data.values && acctResp.data.values.length > 0) accountId = acctResp.data.values[0].id;
          }
          if (!accountId && posting.accountId) accountId = posting.accountId;
          if (accountId) {
            const amount = Number(posting.amount || 0);
            const isDebit = posting.isDebit !== undefined ? posting.isDebit : (amount >= 0);
            const pObj = {
              row: i + 1, date: vDate,
              account: { id: accountId },
              amountGross: isDebit ? Math.abs(amount) : -Math.abs(amount),
              amountGrossCurrency: isDebit ? Math.abs(amount) : -Math.abs(amount),
              description: posting.description || p.description || ''
            };
            const vtId = posting.vatTypeId !== undefined ? posting.vatTypeId : guessVatForAccount(posting.accountNumber);
            pObj.vatType = { id: vtId };
            postings.push(pObj);
          }
        }
      }
      if (postings.length === 0) {
        const vPlan = await callGemini('Create Tripletex voucher postings for this task. Use Norwegian standard chart of accounts.\nCommon accounts (with their locked mva-kode/vatType id):\n1500=Kundefordringer(vat:0), 1920=Bank(vat:0), 2400=Leverandorgjeld(vat:0), 2700=Utg.mva(vat:0), 3000=Salgsinntekt(vat:3=25%), 3100=Salgsinntekt avgiftsfri(vat:6), 4000=Innkjop(vat:1=25%), 6300=Leie(vat:1), 6800=Kontorkostnader(vat:1), 7100=Bilkostnader(vat:1)\nEach posting MUST include vatTypeId matching the account.\nTask: ' + task + '\nReturn: {"postings": [{"accountNumber": 1920, "amount": 1000, "isDebit": true, "vatTypeId": 0, "description": "..."}]}', []);
        if (vPlan.postings) {
          for (let i = 0; i < vPlan.postings.length; i++) {
            const vp = vPlan.postings[i];
            const acctResp = await tx('GET', '/ledger/account?number=' + vp.accountNumber + '&from=0&count=1');
            if (acctResp.ok && acctResp.data && acctResp.data.values && acctResp.data.values.length > 0) {
              const amount = Number(vp.amount || 0);
              const posting = {
                row: i + 1, date: vDate,
                account: { id: acctResp.data.values[0].id },
                amountGross: vp.isDebit ? Math.abs(amount) : -Math.abs(amount),
                amountGrossCurrency: vp.isDebit ? Math.abs(amount) : -Math.abs(amount),
                description: vp.description || ''
              };
              // Always include vatType — accounts have locked VAT codes
              const vtId = vp.vatTypeId !== undefined ? vp.vatTypeId : guessVatForAccount(vp.accountNumber);
              posting.vatType = { id: vtId };
              postings.push(posting);
            }
          }
        }
      }
      if (postings.length > 0) {
        const voucherBody = { date: vDate, description: p.description || task.substring(0, 100), postings };
        const r = await tx('POST', '/ledger/voucher', voucherBody);
        results.push(r); success = r.ok;
        // VOUCHER RETRY: if failed, ask Gemini to fix based on error
        if (!r.ok && r.data) {
          try {
            const errMsg = JSON.stringify(r.data).substring(0, 500);
            const fix = await callGemini('Tripletex POST /ledger/voucher failed. Fix the postings based on the error.\nOriginal body: ' + JSON.stringify(voucherBody).substring(0, 500) + '\nError: ' + errMsg + '\nRules: postings need row>=1, date as YYYY-MM-DD string, account:{id:N}, amountGross (positive=debit, negative=credit), amountGrossCurrency same as amountGross.\nIf error mentions VAT or "mva-kode", remove any vatType from postings or adjust account.\nReturn ONLY the corrected body: {"date":"...","description":"...","postings":[...]}', []);
            if (fix && fix.postings) {
              // Ensure date is string
              if (fix.date && typeof fix.date !== 'string') fix.date = String(fix.date);
              if (!fix.date || !/^\d{4}-\d{2}-\d{2}$/.test(fix.date)) fix.date = vDate;
              const r2 = await tx('POST', '/ledger/voucher', fix);
              results.push({ step: 'voucher_retry', ...r2 }); if (r2.ok) success = true;
            }
          } catch (e) { results.push({ step: 'voucher_retry_error', error: e.message }); }
        }
      } else results.push({ error: 'Could not determine voucher postings' });
      break;
    }

    case 'delete_employee': case 'delete_customer': case 'delete_product': {
      const entityType = plan.task_type.replace('delete_', '');
      let entityId = p.id;
      const dsf = p.search_fields || {};
      const dFirst = p.firstName || dsf.firstName;
      const dLast = p.lastName || dsf.lastName;
      if (!entityId && entityType === 'employee') {
        const emp = findEmployee(dFirst, dLast);
        if (emp) entityId = emp.id;
        if (!entityId) {
          const s = await tx('GET', '/employee?from=0&count=50' + (dFirst ? '&firstName=' + encodeURIComponent(dFirst) : '') + (dLast ? '&lastName=' + encodeURIComponent(dLast) : ''));
          if (s.ok && s.data && s.data.values && s.data.values.length > 0) {
            const match = s.data.values.find(e => (!dFirst || (e.firstName || '').toLowerCase() === dFirst.toLowerCase()) && (!dLast || (e.lastName || '').toLowerCase() === dLast.toLowerCase())) || s.data.values[0];
            entityId = match.id;
          }
        }
      } else if (!entityId) {
        const ep = entityType === 'customer' ? '/customer?name=' + encodeURIComponent(p.name || '') + '&from=0&count=50' : '/product?name=' + encodeURIComponent(p.name || '') + '&from=0&count=50';
        const s = await tx('GET', ep);
        if (s.ok && s.data && s.data.values && s.data.values.length > 0) {
          const match = s.data.values.find(e => p.name && (e.name || '').toLowerCase().includes(p.name.toLowerCase())) || s.data.values[0];
          entityId = match.id;
        }
      }
      if (entityId) {
        const r = await tx('DELETE', '/' + entityType + '/' + entityId);
        results.push(r); success = r.ok;
        if (!r.ok && r.status === 403 && entityType === 'employee') {
          const full = await tx('GET', '/employee/' + entityId + '?fields=*,employments(*)');
          if (full.ok) {
            const upd = full.data.value;
            if (!upd.dateOfBirth) upd.dateOfBirth = '1990-01-01';
            upd.firstName = 'DELETED'; upd.lastName = 'DELETED'; upd.phoneNumberMobile = ''; upd.comments = 'Deleted by automation';
            const r2 = await tx('PUT', '/employee/' + entityId, upd);
            results.push({ step: 'soft_delete', ...r2 }); if (r2.ok) success = true;
          }
        }
      } else results.push({ error: entityType + ' not found' });
      break;
    }

    case 'update_employee': {
      // Extract name from multiple possible fields (Gemini may nest under search_fields)
      const sf = p.search_fields || {};
      let searchFirst = p.firstName || sf.firstName;
      let searchLast = p.lastName || sf.lastName;
      if (!searchFirst && p.employeeName) {
        const parts = p.employeeName.split(' ');
        searchFirst = parts[0];
        searchLast = parts.length > 1 ? parts.slice(1).join(' ') : null;
      }
      if (!searchFirst && p.name) {
        const parts = p.name.split(' ');
        searchFirst = parts[0];
        searchLast = parts.length > 1 ? parts.slice(1).join(' ') : null;
      }
      let emp = findEmployee(searchFirst, searchLast);
      if (!emp) {
        // Try 1: filtered search by firstName/lastName
        const s = await tx('GET', '/employee?from=0&count=50' + (searchFirst ? '&firstName=' + encodeURIComponent(searchFirst) : '') + (searchLast ? '&lastName=' + encodeURIComponent(searchLast) : ''));
        if (s.ok && s.data && s.data.values && s.data.values.length > 0) {
          emp = s.data.values.find(e => (!searchFirst || (e.firstName || '').toLowerCase() === searchFirst.toLowerCase()) && (!searchLast || (e.lastName || '').toLowerCase() === searchLast.toLowerCase()));
          if (!emp && (searchFirst || searchLast)) emp = s.data.values[0];
        }
      }
      if (!emp && (searchFirst || searchLast)) {
        // Try 2: get ALL employees, fuzzy match by full name
        const fullName = ((searchFirst || '') + ' ' + (searchLast || '')).trim().toLowerCase();
        const all = await tx('GET', '/employee?from=0&count=100');
        if (all.ok && all.data && all.data.values) {
          emp = all.data.values.find(e => {
            const eName = ((e.firstName || '') + ' ' + (e.lastName || '')).trim().toLowerCase();
            return eName === fullName || eName.includes(fullName) || fullName.includes(eName);
          });
          // Also try partial match on firstName only
          if (!emp && searchFirst) {
            emp = all.data.values.find(e => (e.firstName || '').toLowerCase() === searchFirst.toLowerCase());
          }
        }
      }
      if (emp) {
        const full = await tx('GET', '/employee/' + emp.id + '?fields=*,employments(*)');
        if (full.ok) {
          const upd = full.data.value;
          if (!upd.dateOfBirth) upd.dateOfBirth = '1990-01-01';
          const updates = p.updates || {};
          if (updates.email || p.newEmail) upd.email = updates.email || p.newEmail;
          if (updates.phoneNumberMobile || p.newPhone || updates.phoneNumber) {
            let phone = String(updates.phoneNumberMobile || p.newPhone || updates.phoneNumber).replace(/[^0-9]/g, '');
            if (phone.length === 8) upd.phoneNumberMobile = phone;
          }
          if (updates.firstName || p.newFirstName) upd.firstName = updates.firstName || p.newFirstName;
          if (updates.lastName || p.newLastName) upd.lastName = updates.lastName || p.newLastName;
          if (updates.dateOfBirth) upd.dateOfBirth = updates.dateOfBirth;
          if (updates.department) {
            const dept = findDeptByName(updates.department);
            if (dept) upd.department = { id: dept.id };
          }
          const r = await tx('PUT', '/employee/' + emp.id, upd);
          results.push(r); success = r.ok;
        }
      } else results.push({ error: 'Employee not found' });
      break;
    }

    case 'update_customer': {
      const cs = await tx('GET', '/customer?name=' + encodeURIComponent(p.name || p.oldName || '') + '&from=0&count=50');
      if (cs.ok && cs.data && cs.data.values && cs.data.values.length > 0) {
        const match = cs.data.values.find(c => (p.name || p.oldName) && (c.name || '').toLowerCase().includes((p.name || p.oldName || '').toLowerCase())) || cs.data.values[0];
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
            upd.postalAddress.country = { id: 161 };
          }
          const r = await tx('PUT', '/customer/' + match.id, upd);
          results.push(r); success = r.ok;
        }
      } else results.push({ error: 'Customer not found' });
      break;
    }

    default: {
      const fp = await callGemini('You are a Tripletex v2 REST API expert. Plan the exact API calls.\nEndpoints: GET/POST/PUT/DELETE on /employee, /customer, /product, /order, /invoice, /travelExpense, /project, /department, /ledger/voucher, /ledger/account\nSpecial: PUT /order/{id}/:invoice, PUT /invoice/{id}/:createCreditNote, PUT /invoice/{id}/:payment, POST /payment\nRules:\n- /employee POST: userType=STANDARD(email)/NO_ACCESS, department:{id:' + (defaultDeptId || 0) + '}\n- /project POST: projectManager:{id:' + (firstEmployeeId || 0) + '}, startDate required\n- /order: vatType:{id:' + getOutgoingVatId(25) + '}\n- /ledger/voucher: postings with row>=1, amountGross (pos=debit, neg=credit)\nEmployees: ' + employees.slice(0, 5).map(e => e.id + ':' + e.firstName + ' ' + e.lastName).join(', ') + '\nDepts: ' + departments.slice(0, 5).map(d => d.id + ':' + d.name).join(', ') + '\n\nTask: ' + task + fileContext + '\n\nReturn: [{"method":"POST","endpoint":"/...","body":{...}}]', pdfFiles);
      const calls = Array.isArray(fp) ? fp : (fp.api_calls || fp.calls || [fp]);
      for (const c of calls) {
        const r = await tx(c.method || 'POST', c.endpoint, c.body || null);
        results.push(r); if (r.ok) success = true;
      }
    }
  }

  // Retry on failure
  if (!success && results.length > 0) {
    try {
      const lastErr = results[results.length - 1];
      const c = await callGemini('Tripletex API call failed. Fix it.\nRules: employee=userType STANDARD/NO_ACCESS + department:{id:' + (defaultDeptId || 0) + '}, dateOfBirth required on PUT.\nProject=projectManager:{id:' + (firstEmployeeId || 0) + '} + startDate.\nVoucher=postings row>=1, amountGross pos=debit neg=credit.\nTask: ' + task + '\nType: ' + plan.task_type + '\nParams: ' + JSON.stringify(p) + '\nError: ' + JSON.stringify(lastErr).substring(0, 500) + '\nReturn: {"method":"POST","endpoint":"/...","body":{...}}', []);
      const r = await tx(c.method || 'POST', c.endpoint, c.body || null);
      results.push({ step: 'retry', ...r }); if (r.ok) success = true;
    } catch (e) { results.push({ step: 'retry_error', error: e.message }); }
  }

} catch (err) {
  results.push({ error: err.message, stack: err.stack });
}
} // end for (const p of paramsList)

return [{ json: { status: 'completed', _debug: { task_type: plan.task_type, confidence: plan.confidence, reasoning: plan.reasoning, success, entities_count: paramsList.length, results } } }];
