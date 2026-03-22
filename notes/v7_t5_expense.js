// === SHARED UTILITIES (included at top of every handler node) ===
const items = $input.all();
const d = items[0].json;
const task = d.task || '';
const base_url = d.base_url || '';
const session_token = d.session_token || '';
const task_type = d.task_type || '';
const fileContext = d.fileContext || '';
const pdfFiles = d.pdfFiles || [];

const authHeader = 'Basic ' + Buffer.from('0:' + session_token).toString('base64');
const apiBase = base_url.replace(/\/+$/, '');
const _helpers = this.helpers;
const GEMINI_KEY = 'GEMINI_API_KEY_REDACTED';

// Multi-entity support
const entities = d.entities || null;
const paramsList = entities && entities.length > 0
  ? entities.map(e => ({ ...(d.extracted_params || {}), ...e }))
  : [d.extracted_params || {}];

// === HTTP helper ===
const FIELD_FIXES = { 'unitPrice': 'unitPriceExcludingVatCurrency', 'unitCostCurrency': 'unitPriceExcludingVatCurrency', 'price': 'priceExcludingVatCurrency' };
function sanitizeBody(endpoint, body) {
  if (!body || typeof body !== 'object') return body;
  const b = JSON.parse(JSON.stringify(body));
  if (b.orderLines) { b.orderLines = b.orderLines.map(ol => { for (const [k, v] of Object.entries(FIELD_FIXES)) { if (ol[k] && !ol[v]) { ol[v] = ol[k]; delete ol[k]; } } return ol; }); }
  if (endpoint && endpoint.includes('/invoice') && !b.invoiceDate) { b.invoiceDate = new Date().toISOString().split('T')[0]; if (!b.invoiceDueDate) b.invoiceDueDate = b.invoiceDate; }
  if (b.postings) { b.postings = b.postings.map((p, i) => { p.row = p.row || i + 1; if (!p.date) p.date = b.date || new Date().toISOString().split('T')[0]; if (p.amountGrossCurrency === undefined) p.amountGrossCurrency = p.amountGross; return p; }); }
  return b;
}

async function tx(method, endpoint, reqBody) {
  const url = apiBase + endpoint;
  const sanitized = (method !== 'GET') ? sanitizeBody(endpoint, reqBody) : reqBody;
  const opts = { method, url, headers: { 'Authorization': authHeader, 'Content-Type': 'application/json' }, returnFullResponse: true, ignoreHttpStatusErrors: true, json: true };
  if (sanitized && method !== 'GET') opts.body = typeof sanitized === 'string' ? JSON.parse(sanitized) : sanitized;
  try {
    const r = await _helpers.httpRequest(opts);
    return { ok: r.statusCode >= 200 && r.statusCode < 300, status: r.statusCode, data: r.body };
  } catch (e) {
    let ed; try { ed = typeof e.body === 'string' ? JSON.parse(e.body) : (e.body || e.message); } catch (_) { ed = e.message; }
    return { ok: false, error: ed, status: e.statusCode || 0, data: ed };
  }
}

async function callGemini(prompt, pdfs) {
  try {
    const parts = [{ text: prompt }];
    if (pdfs && pdfs.length > 0) { for (const f of pdfs) { if (f.content_base64) parts.push({ inline_data: { mime_type: 'application/pdf', data: f.content_base64 } }); } }
    const r = await _helpers.httpRequest({
      method: 'POST', url: 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=' + GEMINI_KEY,
      body: { contents: [{ parts }], generationConfig: { temperature: 0, topK: 1, topP: 0.1, maxOutputTokens: 4096, responseMimeType: 'application/json' }, safetySettings: [{ category: 'HARM_CATEGORY_HARASSMENT', threshold: 'BLOCK_NONE' }, { category: 'HARM_CATEGORY_HATE_SPEECH', threshold: 'BLOCK_NONE' }, { category: 'HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold: 'BLOCK_NONE' }, { category: 'HARM_CATEGORY_DANGEROUS_CONTENT', threshold: 'BLOCK_NONE' }] },
      headers: { 'Content-Type': 'application/json' }, json: true
    });
    const raw = r.candidates[0].content.parts.find(p => p.text)?.text || '{}';
    try { return JSON.parse(raw); } catch(e) {
      const m = raw.match(/```(?:json)?\s*([\s\S]*?)```/); if (m) try { return JSON.parse(m[1].trim()); } catch(_) {}
      const idx = raw.search(/[{[]/); if (idx >= 0) try { return JSON.parse(raw.substring(idx)); } catch(_) {}
      return {};
    }
  } catch(e) { return {}; }
}

// Cache
let _departments = null, _employees = null;
async function getDepartments() { if (!_departments) { const r = await tx('GET', '/department?from=0&count=100'); _departments = (r.ok && r.data && r.data.values) ? r.data.values : []; } return _departments; }
async function getEmployees() { if (!_employees) { const r = await tx('GET', '/employee?from=0&count=100&fields=id,firstName,lastName,email,department'); _employees = (r.ok && r.data && r.data.values) ? r.data.values : []; } return _employees; }
async function getDefaultDeptId() { const d = await getDepartments(); return d.length > 0 ? d[0].id : null; }
async function getFirstEmployeeId() { const e = await getEmployees(); return e.length > 0 ? e[0].id : null; }
async function findEmployee(firstName, lastName) { const emps = await getEmployees(); return emps.find(e => (!firstName || (e.firstName||'').toLowerCase() === firstName.toLowerCase()) && (!lastName || (e.lastName||'').toLowerCase() === lastName.toLowerCase())) || null; }
async function findDeptByName(name) { if (!name) return null; const depts = await getDepartments(); return depts.find(d => d.name && d.name.toLowerCase().includes(name.toLowerCase())) || null; }

let _bankSetupDone = false;
async function ensureBankAccount() {
  if (_bankSetupDone) return; _bankSetupDone = true;
  try { const ba = await tx('GET', '/ledger/account?number=1920&from=0&count=1&fields=id,bankAccountNumber'); if (ba.ok && ba.data && ba.data.values && ba.data.values.length > 0) { const a = ba.data.values[0]; if (!a.bankAccountNumber) { const f = await tx('GET', '/ledger/account/' + a.id); if (f.ok) { f.data.value.bankAccountNumber = '86010517941'; await tx('PUT', '/ledger/account/' + a.id, f.data.value); } } } } catch(e) {}
}

function getOutgoingVatId(pct) { const t = pct != null ? Number(pct) : 25; return { 25: 3, 15: 31, 12: 32, 0: 6 }[t] || 3; }

let results = [], success = false;
// === END SHARED UTILITIES ===


// === T5_Expense HANDLER ===
for (const p of paramsList) {
try {
  switch (task_type) {
    case 'create_travel_expense': {
      // Create employee if specified and not found
      let eId;
      if (p.employeeName) {
        const parts = p.employeeName.split(' ');
        const emp = await findEmployee(parts[0], parts.length > 1 ? parts.slice(1).join(' ') : null);
        if (emp) eId = emp.id;
        if (!eId && p.employeeEmail) {
          const newEmp = await tx('POST', '/employee', {
            firstName: parts[0] || 'Employee', lastName: parts.slice(1).join(' ') || 'Travel',
            email: p.employeeEmail, userType: 'STANDARD',
            department: { id: (await getDefaultDeptId()) || 0 }
          });
          if (newEmp.ok) {
            eId = newEmp.data.value.id;
            results.push({ step: 'create_employee', ...newEmp });
            await tx('PUT', '/employee/entitlement/:grantEntitlementsByTemplate?employeeId=' + eId + '&template=ALL_PRIVILEGES', {});
          }
        }
      }
      if (!eId) eId = await getFirstEmployeeId();
      const today = new Date().toISOString().split('T')[0];
      const costItems = p.costs || p.expense_items || p.expenseItems || [];
      const depDate = p.departureDate || p.startDate || p.date || today;
      const retDate = p.returnDate || p.endDate || depDate;
      // Find department if specified
      let deptId = null;
      const deptName = p.department || p.departmentName || '';
      if (deptName) {
        const dept = await findDeptByName(deptName);
        if (dept) deptId = dept.id;
        if (!deptId) {
          // Create department
          const nd = await tx('POST', '/department', { name: deptName });
          if (nd.ok) deptId = nd.data.value.id;
        }
      }

      const teBody = {
        employee: { id: eId },
        title: p.title || p.description || p.purpose || (costItems.length > 0 ? costItems[0].description : '') || 'Travel Expense',
        travelDetails: {
          departureDate: depDate,
          returnDate: retDate,
          destination: p.destination || ''
        }
      };
      if (deptId) teBody.department = { id: deptId };
      const r = await tx('POST', '/travelExpense', teBody);
      results.push(r); success = r.ok;
      // Add costs (flights, taxi, etc.) if specified
      if (r.ok && costItems.length > 0) {
        const teId = r.data.value.id;
        // Cost category mapping (name → id, based on sandbox data)
        const COST_CATS = {
          'fly': 34000208, 'flight': 34000208, 'flug': 34000208, 'vol': 34000208, 'avion': 34000208, 'voo': 34000208,
          'taxi': 34000222, 'drosje': 34000222,
          'hotell': 34000211, 'hotel': 34000211, 'hôtel': 34000211,
          'buss': 34000202, 'bus': 34000202,
          'tog': 34000210, 'train': 34000210, 'zug': 34000210,
          'parkering': 34000218, 'parking': 34000218,
          'mat': 34000216, 'food': 34000216, 'meal': 34000216,
          'ferge': 34000207, 'ferry': 34000207,
          'leiebil': 34000214, 'rental car': 34000214, 'mietwagen': 34000214,
        };
        // Fetch actual categories to find best match
        let costCats = null;
        // ALWAYS fetch costCategories from API (IDs differ between sandbox and competition)
        if (!costCats) {
          const cc = await tx('GET', '/travelExpense/costCategory?from=0&count=50');
          costCats = (cc.ok && cc.data && cc.data.values) ? cc.data.values : [];
        }
        for (const cost of costItems) {
          const costDesc = (cost.description || cost.name || '').toLowerCase();
          let catId = null;
          // Match by description keywords against actual categories
          const KEYWORDS = {
            'fly': ['fly', 'flight', 'flug', 'vol', 'avion', 'voo', 'billete de avión'],
            'taxi': ['taxi', 'drosje'],
            'hotell': ['hotell', 'hotel', 'hôtel'],
            'buss': ['buss', 'bus'],
            'tog': ['tog', 'train', 'zug', 'tren'],
            'parkering': ['parkering', 'parking'],
            'mat': ['mat', 'food', 'meal', 'comida'],
            'ferge': ['ferge', 'ferry'],
            'leiebil': ['leiebil', 'rental', 'mietwagen', 'alquiler'],
          };
          for (const [catKey, keywords] of Object.entries(KEYWORDS)) {
            if (keywords.some(kw => costDesc.includes(kw))) {
              const match = costCats.find(c => (c.description || '').toLowerCase().includes(catKey));
              if (match) { catId = match.id; break; }
            }
          }
          // Direct match on category description
          if (!catId) {
            const match = costCats.find(c => costDesc.includes((c.description || '').toLowerCase()) || (c.description || '').toLowerCase().includes(costDesc));
            if (match) catId = match.id;
          }
          // Fallback: first travel-related category
          if (!catId && costCats.length > 0) {
            catId = costCats.find(c => (c.description || '').toLowerCase().includes('reise'))?.id || costCats[0].id;
          }
          if (catId) {
            const cr = await tx('POST', '/travelExpense/cost', {
              travelExpense: { id: teId },
              costCategory: { id: catId },
              paymentType: { id: 0 },
              amountCurrencyIncVat: Number(cost.amount || 0),
              comments: cost.description || ''
            });
            results.push({ step: 'add_cost', ...cr });
          }
        }
      }
      // Add per diem compensation if specified
      if (r.ok && p.perDiem) {
        const teId = r.data.value.id;
        const pd = await tx('POST', '/travelExpense/perDiemCompensation', {
          travelExpense: { id: teId },
          overnightAccommodation: p.perDiem.accommodation || 'HOTEL',
          location: p.perDiem.location || p.destination || 'Norway',
          count: p.perDiem.days || p.perDiem.count || 1
        });
        results.push({ step: 'add_per_diem', ...pd });
      }
      break;
    }

    case 'payroll_voucher': {
      // T2: Create employee + payroll voucher with employee reference in postings
      const today = new Date().toISOString().split('T')[0];

      // 1. Create employee
      let prEmpId;
      let prFirst = p.employeeFirstName || '';
      let prLast = p.employeeLastName || '';
      // Fallback: parse employeeName if firstName/lastName not extracted
      if (!prFirst && p.employeeName) {
        const nameParts = p.employeeName.split(' ');
        prFirst = nameParts[0] || '';
        prLast = nameParts.slice(1).join(' ') || '';
      }
      if (prFirst || prLast) {
        const existingEmp = await findEmployee(prFirst, prLast);
        if (existingEmp) {
          prEmpId = existingEmp.id;
        } else {
          const eb = { firstName: prFirst, lastName: prLast, userType: 'NO_ACCESS' };
          if (p.employeeEmail) { eb.email = p.employeeEmail; eb.userType = 'STANDARD'; }
          const did = await getDefaultDeptId();
          if (did) eb.department = { id: did };
          const ne = await tx('POST', '/employee', eb);
          results.push({ step: 'create_employee', ...ne });
          if (ne.ok) {
            prEmpId = ne.data.value.id;
            await tx('PUT', '/employee/entitlement/:grantEntitlementsByTemplate?employeeId=' + prEmpId + '&template=ALL_PRIVILEGES', {});
          }
        }
      }
      if (!prEmpId) prEmpId = await getFirstEmployeeId();

      // 2. Build voucher postings from salary items
      let postings = [];
      let totalExpense = 0;
      const items = p.salaryItems || [];

      if (items.length > 0) {
        for (let i = 0; i < items.length; i++) {
          const item = items[i];
          const amount = Number(item.amount || 0);
          totalExpense += amount;
          let accountId;
          const acctNum = item.accountNumber || 5000;
          const acctResp = await tx('GET', '/ledger/account?number=' + acctNum + '&from=0&count=1');
          if (acctResp.ok && acctResp.data && acctResp.data.values && acctResp.data.values.length > 0) {
            accountId = acctResp.data.values[0].id;
          }
          if (accountId) {
            postings.push({
              row: i + 1, date: today,
              account: { id: accountId },
              employee: { id: prEmpId },
              amountGross: amount, amountGrossCurrency: amount,
              description: item.description || 'Salary'
            });
          }
        }
      } else {
        // Fallback: use Gemini to determine salary breakdown
        const salaryPlan = await callGemini('Parse this payroll task into salary line items. Do NOT include arbeidsgiveravgift — it is calculated automatically at 14.1%.\nCommon Norwegian payroll accounts: 5000=Lønn til ansatte (base salary), 5001=Overtid (overtime), 5090=Påløpt lønn, 5200=Fri bil, 5420=Pensjonskostnad, 5900=Gave til ansatte, 5990=Annen personalkostnad\nBonus/tillegg/godtgjørelse should use 5000 unless specified.\nTask: ' + task + '\nReturn: {"items": [{"description": "Salary", "amount": 50000, "accountNumber": 5000}]}', []);
        if (salaryPlan.items) {
          for (let i = 0; i < salaryPlan.items.length; i++) {
            const item = salaryPlan.items[i];
            const amount = Number(item.amount || 0);
            totalExpense += amount;
            const acctResp = await tx('GET', '/ledger/account?number=' + (item.accountNumber || 5000) + '&from=0&count=1');
            if (acctResp.ok && acctResp.data && acctResp.data.values && acctResp.data.values.length > 0) {
              postings.push({
                row: i + 1, date: today,
                account: { id: acctResp.data.values[0].id },
                employee: { id: prEmpId },
                amountGross: amount, amountGrossCurrency: amount,
                description: item.description || 'Salary'
              });
            }
          }
        }
      }

      // Add arbeidsgiveravgift (employer's social security contribution ~14.1%)
      if (totalExpense > 0) {
        const avgiftAmount = Math.round(totalExpense * 0.141);
        const avgiftAcct = await tx('GET', '/ledger/account?number=5400&from=0&count=1');
        const skyldAvgiftAcct = await tx('GET', '/ledger/account?number=2770&from=0&count=1');
        if (avgiftAcct.ok && avgiftAcct.data?.values?.length > 0 && skyldAvgiftAcct.ok && skyldAvgiftAcct.data?.values?.length > 0) {
          postings.push({
            row: postings.length + 1, date: today,
            account: { id: avgiftAcct.data.values[0].id },
            amountGross: avgiftAmount, amountGrossCurrency: avgiftAmount,
            description: 'Arbeidsgiveravgift 14.1%'
          });
          postings.push({
            row: postings.length + 1, date: today,
            account: { id: skyldAvgiftAcct.data.values[0].id },
            amountGross: -avgiftAmount, amountGrossCurrency: -avgiftAmount,
            description: 'Skyldig arbeidsgiveravgift'
          });
        }
      }

      // Add credit posting (bank) for salary payment
      if (totalExpense > 0) {
        const bankAcct = await tx('GET', '/ledger/account?number=1920&from=0&count=1');
        if (bankAcct.ok && bankAcct.data && bankAcct.data.values && bankAcct.data.values.length > 0) {
          postings.push({
            row: postings.length + 1, date: today,
            account: { id: bankAcct.data.values[0].id },
            amountGross: -totalExpense, amountGrossCurrency: -totalExpense,
            description: 'Bank payment - payroll'
          });
        }
      }

      if (postings.length > 0) {
        const r = await tx('POST', '/ledger/voucher', {
          date: today,
          description: 'Payroll - ' + (prFirst + ' ' + prLast).trim(),
          postings
        });
        results.push(r); success = r.ok;
      } else results.push({ error: 'Could not build payroll postings' });
      break;
    }
    default: break;
  }
} catch(e) { results.push({ error: e.message }); }
}

return [{ json: { status: 'completed', _debug: { task_type, success, results, group: 'T5_Expense' } } }];
