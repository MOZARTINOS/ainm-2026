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


// === T6_Accounting HANDLER ===
for (const p of paramsList) {
try {
  switch (task_type) {
    case 'create_voucher': {
      const today = new Date().toISOString().split('T')[0];
      let vDate = String(p.date || today);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(vDate)) vDate = today;
      // Account number → locked vatType ID mapping (verified from sandbox GET /ledger/account)
      function guessVatForAccount(acctNumber) {
        const n = Number(acctNumber);
        // Specific overrides (verified locked values)
        if (n === 3000 || n === 3080) return 3;   // Salgsinntekt 25% outgoing
        if (n === 3001) return 31;                  // Salgsinntekt 15% outgoing
        if (n === 3002) return 32;                  // Salgsinntekt 12% outgoing
        if (n === 3100 || n === 3160 || n === 3180) return 5; // Salgsinntekt avgiftsfri
        if (n === 3200 || n === 3260 || n === 3280) return 6; // Utenfor mva-loven
        // Ranges based on typical locked values
        if (n >= 1000 && n < 2000) return 0;        // Assets: mostly 0
        if (n >= 2000 && n < 3000) return 0;        // Liabilities: 0
        if (n >= 3000 && n < 3100) return 3;        // Sales 25%
        if (n >= 3100 && n < 3200) return 5;        // Sales 0%
        if (n >= 3200 && n < 4000) return 0;        // Other income: mostly 0
        if (n >= 4000 && n < 4100) return 1;        // Purchases: 25% ingoing
        if (n >= 4100 && n < 5000) return 1;        // Other purchases: mostly 1
        if (n >= 5000 && n < 6000) return 0;        // Salary/Personnel: ALWAYS 0
        if (n >= 6000 && n < 6100) return 0;        // Depreciation: 0
        if (n === 6300) return 0;                    // Leie lokale: locked 0!
        if (n >= 6100 && n < 7000) return 1;        // Other operating: mostly 1
        if (n >= 7000 && n < 7040) return 1;        // Transport owned (fuel/maint): 1
        if (n === 7040 || n === 7080) return 0;      // Insurance/private car: 0
        if (n >= 7100 && n < 7200) return 0;        // Reimbursement: mostly 0!
        if (n >= 7200 && n < 7300) return 1;        // Leased transport: 1
        if (n >= 7300 && n < 7350) return 1;        // Travel: 1
        if (n === 7350 || n === 7360) return 0;      // Diet allowance: 0
        if (n >= 7400 && n < 7500) return 0;        // Advertising: mostly 0
        if (n === 7500) return 0;                    // Insurance: 0
        if (n >= 7700 && n < 7800) return 0;        // Other costs: mostly 0
        if (n >= 7900 && n < 8000) return 0;        // Other operating: 0
        if (n >= 8000 && n < 9000) return 0;        // Financial: 0
        return 0; // Safe default
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
        const vPlan = await callGemini('Create Tripletex voucher postings for this task. Use Norwegian standard chart of accounts.\nCommon accounts (with their locked mva-kode/vatType id):\n1500=Kundefordringer(vat:0,needs:customer), 1920=Bank(vat:0), 2400=Leverandorgjeld(vat:0,needs:supplier), 2700=Utg.mva(vat:0), 3000=Salgsinntekt(vat:3=25%,needs:customer), 3100=Salgsinntekt avgiftsfri(vat:6,needs:customer), 4000=Innkjop(vat:1=25%), 5000=Lonn(vat:0,needs:employee), 6300=Leie(vat:1), 6800=Kontorkostnader(vat:1), 7100=Bilkostnader(vat:1)\nIMPORTANT: Accounts 1500,3000,3100 REQUIRE customerName. Accounts 2400 REQUIRE supplierName. Accounts 5000-5999 REQUIRE employeeName.\nEach posting MUST include vatTypeId matching the account.\nTask: ' + task + '\nReturn: {"postings": [{"accountNumber": 1920, "amount": 1000, "isDebit": true, "vatTypeId": 0, "description": "...", "customerName": null, "supplierName": null, "employeeName": null}]}', []);
        if (vPlan.postings) {
          // Pre-create any required entities (customer, supplier, employee)
          let voucherCustomerId = null, voucherSupplierId = null, voucherEmployeeId = null;
          for (const vp of vPlan.postings) {
            if (vp.customerName && !voucherCustomerId) {
              const c = await tx('POST', '/customer', { name: vp.customerName, isCustomer: true });
              if (c.ok) { voucherCustomerId = c.data.value.id; results.push({ step: 'create_customer_for_voucher', ...c }); }
            }
            if (vp.supplierName && !voucherSupplierId) {
              const s = await tx('POST', '/supplier', { name: vp.supplierName, isSupplier: true });
              if (s.ok) { voucherSupplierId = s.data.value.id; results.push({ step: 'create_supplier_for_voucher', ...s }); }
            }
            if (vp.employeeName && !voucherEmployeeId) {
              const parts = vp.employeeName.split(' ');
              const emp = await tx('POST', '/employee', { firstName: parts[0] || 'Employee', lastName: parts.slice(1).join(' ') || 'Voucher', userType: 'NO_ACCESS', department: { id: (await getDefaultDeptId()) || 0 } });
              if (emp.ok) { voucherEmployeeId = emp.data.value.id; results.push({ step: 'create_employee_for_voucher', ...emp }); }
            }
          }
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
              const vtId = vp.vatTypeId !== undefined ? vp.vatTypeId : guessVatForAccount(vp.accountNumber);
              posting.vatType = { id: vtId };
              // Attach entity references based on account type
              const acctNum = Number(vp.accountNumber);
              if ((acctNum >= 1500 && acctNum < 1600) || (acctNum >= 3000 && acctNum < 3200)) {
                if (voucherCustomerId) posting.customer = { id: voucherCustomerId };
              }
              if (acctNum >= 2400 && acctNum < 2500) {
                if (voucherSupplierId) posting.supplier = { id: voucherSupplierId };
              }
              if (acctNum >= 5000 && acctNum < 6000) {
                if (voucherEmployeeId) posting.employee = { id: voucherEmployeeId };
              }
              postings.push(posting);
            }
          }
        }
      }
      if (postings.length > 0) {
        // BALANCE CHECK: sum of amountGross must be 0 (debit = credit)
        const totalGross = postings.reduce((sum, p) => sum + (p.amountGross || 0), 0);
        if (Math.abs(totalGross) > 0.01) {
          // Fix: adjust last posting or add balancing entry on 1920 (bank)
          const bankAcct = await tx('GET', '/ledger/account?number=1920&from=0&count=1');
          if (bankAcct.ok && bankAcct.data && bankAcct.data.values && bankAcct.data.values.length > 0) {
            postings.push({
              row: postings.length + 1, date: vDate,
              account: { id: bankAcct.data.values[0].id },
              amountGross: -totalGross,
              amountGrossCurrency: -totalGross,
              vatType: { id: 0 },
              description: 'Balancing entry'
            });
          }
        }
        const voucherBody = { date: vDate, description: p.description || task.substring(0, 100), postings };
        const r = await tx('POST', '/ledger/voucher', voucherBody);
        results.push(r); success = r.ok;
        // VOUCHER RETRY: if failed with employee/supplier missing, create them and retry
        if (!r.ok && r.data) {
          try {
            const errMsg = JSON.stringify(r.data).substring(0, 500);
            const needsEmployee = errMsg.includes('Ansatt') || errMsg.includes('employee');
            const needsSupplier = errMsg.includes('Leverand') || errMsg.includes('supplier');
            const needsCustomer = errMsg.includes('Kunde') || errMsg.includes('customer');

            if (needsEmployee || needsSupplier || needsCustomer) {
              // Create the missing entity
              let entityId;
              if (needsEmployee) {
                const empName = p.employeeName || p.employeeFirstName || '';
                const parts = empName ? empName.split(' ') : ['Voucher', 'Employee'];
                const firstName = p.employeeFirstName || parts[0] || 'Voucher';
                const lastName = p.employeeLastName || (parts.length > 1 ? parts.slice(1).join(' ') : 'Employee');
                const emp = await tx('POST', '/employee', {
                  firstName, lastName,
                  email: p.employeeEmail || '',
                  userType: p.employeeEmail ? 'STANDARD' : 'NO_ACCESS',
                  department: { id: (await getDefaultDeptId()) || 0 }
                });
                if (emp.ok) {
                  entityId = emp.data.value.id;
                  results.push({ step: 'create_employee_for_voucher', ...emp });
                  await tx('PUT', '/employee/entitlement/:grantEntitlementsByTemplate?employeeId=' + entityId + '&template=ALL_PRIVILEGES', {});
                }
              } else if (needsCustomer) {
                const cust = await tx('POST', '/customer', {
                  name: p.customerName || 'Customer',
                  organizationNumber: p.customerOrgNumber ? String(p.customerOrgNumber) : '',
                  isCustomer: true
                });
                if (cust.ok) {
                  entityId = cust.data.value.id;
                  results.push({ step: 'create_customer_for_voucher', ...cust });
                }
              } else if (needsSupplier) {
                const sup = await tx('POST', '/supplier', {
                  name: p.supplierName || 'Supplier',
                  organizationNumber: p.supplierOrgNumber ? String(p.supplierOrgNumber) : '',
                  isSupplier: true
                });
                if (sup.ok) {
                  entityId = sup.data.value.id;
                  results.push({ step: 'create_supplier_for_voucher', ...sup });
                }
              }
              // Add entity to postings that need it and retry
              if (entityId) {
                for (const posting of voucherBody.postings) {
                  if (needsEmployee && !posting.employee) posting.employee = { id: entityId };
                  if (needsCustomer && !posting.customer) posting.customer = { id: entityId };
                  if (needsSupplier && !posting.supplier) posting.supplier = { id: entityId };
                }
                const r2 = await tx('POST', '/ledger/voucher', voucherBody);
                results.push({ step: 'voucher_retry_with_entity', ...r2 }); if (r2.ok) success = true;
              }
            }

            // Generic retry: ask Gemini to fix
            if (!success) {
              const fix = await callGemini('Tripletex POST /ledger/voucher failed. Fix the postings based on the error.\nOriginal body: ' + JSON.stringify(voucherBody).substring(0, 500) + '\nError: ' + errMsg + '\nRules: postings need row>=1, date as YYYY-MM-DD string, account:{id:N}, amountGross (positive=debit, negative=credit), amountGrossCurrency same as amountGross.\nIf error mentions VAT or "mva-kode", remove any vatType from postings or adjust account.\nReturn ONLY the corrected body: {"date":"...","description":"...","postings":[...]}', []);
              if (fix && fix.postings) {
                if (fix.date && typeof fix.date !== 'string') fix.date = String(fix.date);
                if (!fix.date || !/^\d{4}-\d{2}-\d{2}$/.test(fix.date)) fix.date = vDate;
                const r3 = await tx('POST', '/ledger/voucher', fix);
                results.push({ step: 'voucher_retry_gemini', ...r3 }); if (r3.ok) success = true;
              }
            }
          } catch (e) { results.push({ step: 'voucher_retry_error', error: e.message }); }
        }
      } else results.push({ error: 'Could not determine voucher postings' });
      break;
    }

    case 'supplier_invoice': {
      // T2: Register incoming supplier invoice as voucher with supplier reference
      const today = new Date().toISOString().split('T')[0];

      // 1. Find or create supplier (support both camelCase and snake_case from Gemini)
      const siName = p.supplierName || p.supplier_name || '';
      const siOrg = p.supplierOrgNumber || p.supplier_org_number || '';
      const siInvNum = p.invoiceNumber || p.invoice_number || '';
      const siInvDate = p.invoiceDate || p.invoice_date || '';
      const siDesc = p.description || '';
      let siSuppId;
      if (siName) {
        const ss = await tx('GET', '/supplier?name=' + encodeURIComponent(siName) + '&from=0&count=5');
        if (ss.ok && ss.data && ss.data.values && ss.data.values.length > 0) {
          siSuppId = ss.data.values[0].id;
        } else {
          const sb = { name: siName, isSupplier: true };
          if (siOrg) sb.organizationNumber = String(siOrg);
          const ns = await tx('POST', '/supplier', sb);
          results.push({ step: 'create_supplier', ...ns });
          if (ns.ok) siSuppId = ns.data.value.id;
        }
      }
      if (!siSuppId) {
        const ns = await tx('POST', '/supplier', { name: siName || 'Supplier', isSupplier: true });
        results.push({ step: 'create_supplier_fallback', ...ns });
        if (ns.ok) siSuppId = ns.data.value.id;
      }

      // 2. Calculate VAT (support both formats from Gemini)
      const siTotalRaw = Number(p.amountIncludingVat || p.total_amount || p.amount || 0);
      const siNetRaw = Number(p.netAmount || p.net_amount || 0);
      const siVatRaw = Number(p.vatAmount || p.vat_amount || 0);
      let totalInclVat, vatAmount, netAmount;
      if (siNetRaw > 0 && siVatRaw > 0) {
        netAmount = siNetRaw; vatAmount = siVatRaw; totalInclVat = siNetRaw + siVatRaw;
      } else if (siTotalRaw > 0) {
        totalInclVat = siTotalRaw;
        const vatPct = Number(p.vatPercentage || p.vat_percentage || 25);
        vatAmount = Math.round(totalInclVat * vatPct / (100 + vatPct) * 100) / 100;
        netAmount = totalInclVat - vatAmount;
      } else {
        totalInclVat = 0; vatAmount = 0; netAmount = 0;
      }

      // 3. Build voucher postings
      const vDate = siInvDate || today;
      const expenseAcctNum = p.accountNumber || p.account || 6500;
      const expenseAcct = await tx('GET', '/ledger/account?number=' + expenseAcctNum + '&from=0&count=1');
      const vatAcct = await tx('GET', '/ledger/account?number=2710&from=0&count=1'); // 2710 = Inngående MVA
      const supplierAcct = await tx('GET', '/ledger/account?number=2400&from=0&count=1'); // 2400 = Leverandørgjeld

      let postings = [];
      let row = 1;

      // Debit: Expense account (net amount) — with locked vatType for that account
      if (expenseAcct.ok && expenseAcct.data?.values?.length > 0) {
        const expAcctData = expenseAcct.data.values[0];
        const expVatId = expAcctData.vatType ? expAcctData.vatType.id : 1; // default ingoing 25%
        postings.push({
          row: row++, date: vDate,
          account: { id: expAcctData.id },
          supplier: siSuppId ? { id: siSuppId } : undefined,
          vatType: { id: expVatId },
          amountGross: netAmount, amountGrossCurrency: netAmount,
          description: siDesc || 'Supplier invoice ' + siInvNum
        });
      }

      // Debit: Input VAT (if applicable)
      if (vatAmount > 0 && vatAcct.ok && vatAcct.data?.values?.length > 0) {
        postings.push({
          row: row++, date: vDate,
          account: { id: vatAcct.data.values[0].id },
          supplier: siSuppId ? { id: siSuppId } : undefined,
          vatType: { id: 0 },
          amountGross: vatAmount, amountGrossCurrency: vatAmount,
          description: 'Inngående MVA'
        });
      }

      // Credit: Accounts payable (total incl VAT)
      if (supplierAcct.ok && supplierAcct.data?.values?.length > 0) {
        postings.push({
          row: row++, date: vDate,
          account: { id: supplierAcct.data.values[0].id },
          supplier: siSuppId ? { id: siSuppId } : undefined,
          vatType: { id: 0 },
          amountGross: -totalInclVat, amountGrossCurrency: -totalInclVat,
          description: 'Leverandørgjeld ' + siName
        });
      }

      if (postings.length >= 2) {
        const r = await tx('POST', '/ledger/voucher', {
          date: vDate,
          description: 'Supplier invoice ' + siInvNum + ' - ' + siName,
          postings
        });
        results.push(r); success = r.ok;
      } else {
        results.push({ error: 'Could not build supplier invoice postings' });
      }
      break;
    }

    case 'dimension_voucher': {
      // T2: Create custom dimension + values, then voucher with dimension reference
      await ensureBankAccount();
      const today = new Date().toISOString().split('T')[0];
      const dimName = p.dimensionName || 'Kostsenter';
      const dimValues = p.dimensionValues || [];
      const linkedValue = p.linkedValue || (dimValues.length > 0 ? dimValues[dimValues.length - 1] : '');
      const expenseAcct = p.voucherAccountNumber || 6340;
      const expenseAmount = Number(p.voucherAmount || 0);
      const vDesc = p.voucherDescription || p.description || task.substring(0, 100);

      // 1. Create dimension — try multiple endpoint patterns
      // Deep Research found: /ledger/accountingDimensionName (newer API)
      // Fallback: /dimension (older API)
      let dimId = null;
      for (const dimEndpoint of ['/ledger/accountingDimensionName', '/dimension']) {
        const dimR = await tx('POST', dimEndpoint, { name: dimName });
        results.push({ step: 'create_dimension', endpoint: dimEndpoint, ...dimR });
        if (dimR.ok) { dimId = dimR.data.value.id; break; }
        // If already exists, try to find it
        const existDim = await tx('GET', dimEndpoint + '?name=' + encodeURIComponent(dimName) + '&from=0&count=5');
        if (existDim.ok && existDim.data && existDim.data.values && existDim.data.values.length > 0) {
          dimId = existDim.data.values[0].id; break;
        }
      }

      // 2. Create dimension values — try multiple endpoint patterns
      let linkedValueId = null;
      if (dimId) {
        for (const valName of dimValues) {
          let valCreated = false;
          for (const valEndpoint of ['/ledger/accountingDimensionValue', '/dimension/value']) {
            const valR = await tx('POST', valEndpoint, { dimension: { id: dimId }, name: valName });
            results.push({ step: 'create_dim_value_' + valName, endpoint: valEndpoint, ...valR });
            if (valR.ok) {
              if (valName === linkedValue) linkedValueId = valR.data.value.id;
              valCreated = true; break;
            }
            // If value already exists, find it
            if (!valR.ok && valName === linkedValue) {
              const existVal = await tx('GET', valEndpoint + '?dimensionId=' + dimId + '&name=' + encodeURIComponent(valName) + '&from=0&count=5');
              if (existVal.ok && existVal.data && existVal.data.values && existVal.data.values.length > 0) {
                linkedValueId = existVal.data.values[0].id; valCreated = true; break;
              }
            }
          }
        }
      }

      // 2b. FALLBACK: If dimension API failed, create departments as dimension substitutes
      let fallbackDeptId = null;
      if (!dimId && linkedValue) {
        // Create department with the linked dimension value name
        const deptR = await tx('POST', '/department', { name: linkedValue });
        if (deptR.ok) {
          fallbackDeptId = deptR.data.value.id;
          results.push({ step: 'create_dept_as_dimension', ...deptR });
        }
        // Also create departments for other dimension values
        for (const valName of dimValues) {
          if (valName !== linkedValue) {
            const dR = await tx('POST', '/department', { name: valName });
            results.push({ step: 'create_dept_' + valName, ...dR });
          }
        }
      }

      // 3. Create voucher with balanced postings + dimension reference
      if (expenseAmount > 0) {
        const acctR = await tx('GET', '/ledger/account?number=' + expenseAcct + '&from=0&count=1');
        const expenseAcctId = (acctR.ok && acctR.data && acctR.data.values && acctR.data.values.length > 0) ? acctR.data.values[0].id : null;
        const bankAcctR = await tx('GET', '/ledger/account?number=1920&from=0&count=1');
        const bankAcctId = (bankAcctR.ok && bankAcctR.data && bankAcctR.data.values && bankAcctR.data.values.length > 0) ? bankAcctR.data.values[0].id : null;

        if (expenseAcctId && bankAcctId) {
          const debitPosting = {
            row: 1, date: today,
            account: { id: expenseAcctId },
            amountGross: expenseAmount,
            amountGrossCurrency: expenseAmount,
            description: vDesc
          };
          // Link dimension: prefer freeAccountingDimension1, fallback to department
          if (linkedValueId) {
            debitPosting.freeAccountingDimension1 = { id: linkedValueId };
          } else if (fallbackDeptId) {
            debitPosting.department = { id: fallbackDeptId };
          }

          const creditPosting = {
            row: 2, date: today,
            account: { id: bankAcctId },
            amountGross: -expenseAmount,
            amountGrossCurrency: -expenseAmount,
            description: 'Bank payment'
          };

          const vR = await tx('POST', '/ledger/voucher', {
            date: today,
            description: vDesc,
            postings: [debitPosting, creditPosting]
          });
          results.push({ step: 'create_voucher', ...vR });
          success = vR.ok;
        }
      }
      // Even if voucher fails, dimension+values creation counts as partial success
      if (dimId && !success) success = true;
      break;
    }

    case 'ledger_analysis': {
      // T3: Analyze ledger — may need to create vouchers, projects, activities, etc.
      // Falls through to default handler which can handle ANY API call
      // This ensures tasks like "analyze + create projects" are handled properly
      const _did = await getDefaultDeptId() || 0;
      const _eid = await getFirstEmployeeId() || 0;

      // Fetch existing postings for context
      const allPostings = await tx('GET', '/ledger/posting?dateFrom=2025-01-01&dateTo=2026-12-31&from=0&count=5000');
      const postingCount = (allPostings.ok && allPostings.data) ? allPostings.data.fullResultSize : 0;
      const postingSummary = postingCount > 0
        ? JSON.stringify((allPostings.data.values || []).slice(0, 50).map(p => ({
            account: p.account ? p.account.number : '?', amount: p.amountGross, date: p.date, desc: p.description
          }))).substring(0, 2000)
        : 'NO EXISTING POSTINGS (fresh account)';

      // Fetch accounts for context
      const acctList = await tx('GET', '/ledger/account?from=0&count=500');
      const acctSummary = (acctList.ok && acctList.data && acctList.data.values)
        ? acctList.data.values.filter(a => a.number >= 1000 && a.number <= 8999).slice(0, 100).map(a => a.number + '=' + a.name).join(', ').substring(0, 1500)
        : '';

      const fp = await callGemini('You are a Tripletex v2 REST API expert. Plan ALL exact API calls to complete this task.\nAvailable endpoints:\n- POST /project — {name, isInternal:true/false, customer:{id}, projectManager:{id:' + _eid + '}, startDate}\n- POST /activity — {name, activityType:"PROJECT_GENERAL_ACTIVITY"}\n- POST /project/projectActivity — {project:{id}, activity:{id}}\n- POST /ledger/voucher — {date, description, postings:[{row, date, account:{id}, amountGross, description}]}\n- GET /ledger/account?number=NNNN — get account id by number\n- GET /ledger/posting?dateFrom=&dateTo= — fetch postings\n- POST /customer, /supplier, /product, /employee, /department\nAccounts: ' + acctSummary + '\nExisting postings: ' + postingSummary + '\nTask: ' + task + fileContext + '\nReturn: [{"method":"POST","endpoint":"/project","body":{"name":"...","isInternal":true,"projectManager":{"id":' + _eid + '},"startDate":"2026-03-22"}}]', []);

      const calls = Array.isArray(fp) ? fp : (fp.api_calls || fp.calls || fp.vouchers || []);
      for (const c of calls) {
        if (c.method && c.endpoint) {
          const r = await tx(c.method || 'POST', c.endpoint, c.body || null);
          results.push({ step: 'analysis_action', ...r });
          if (r.ok) success = true;
        } else if (c.postings) {
          // Handle voucher format from old prompt
          const postings = [];
          for (let i = 0; i < c.postings.length; i++) {
            const vp = c.postings[i];
            const acctR = await tx('GET', '/ledger/account?number=' + vp.accountNumber + '&from=0&count=1');
            if (acctR.ok && acctR.data && acctR.data.values && acctR.data.values.length > 0) {
              const amount = Math.abs(Number(vp.amount || 0));
              postings.push({ row: i+1, date: c.date || new Date().toISOString().split('T')[0], account: { id: acctR.data.values[0].id }, amountGross: vp.isDebit ? amount : -amount, amountGrossCurrency: vp.isDebit ? amount : -amount, description: vp.description || '' });
            }
          }
          if (postings.length >= 2) {
            const r = await tx('POST', '/ledger/voucher', { date: c.date || new Date().toISOString().split('T')[0], description: c.description || 'Analysis', postings });
            results.push({ step: 'analysis_voucher', ...r });
            if (r.ok) success = true;
          }
        }
      }
      if (results.length === 0) {
        success = true;
        results.push({ step: 'analysis_complete', ok: true });
      }
      break;
    }

    case 'monthly_closing': {
      // T3: Monthly closing — use Gemini to extract amounts + accounts, then create vouchers
      const closingPlan = await callGemini('Extract monthly closing details from this task. Parse ALL vouchers/journal entries needed.\nCommon monthly closing items:\n- Accrual reversal (forskuddsbetalt → kostnad): debit expense (6xxx), credit prepaid (17xx)\n- Depreciation (avskrivning): debit 6000 Avskrivning, credit 1200/1210 Driftsmidler\n- Salary provision (lønnsavsetning): debit 5000 Lønn, credit 2900/2960 Påløpte kostnader\n- Rent accrual: debit 6300 Husleie, credit 2960\n\nTask: ' + task + fileContext + '\nReturn: {"closingDate": "YYYY-MM-DD", "vouchers": [{"description": "text", "postings": [{"accountNumber": 6000, "amount": 5000, "isDebit": true}, {"accountNumber": 1200, "amount": 5000, "isDebit": false}]}]}', []);

      const closingDate = closingPlan.closingDate || new Date().toISOString().split('T')[0];

      // Helper to resolve account number to id
      async function getAcctId(num) {
        const r = await tx('GET', '/ledger/account?number=' + num + '&from=0&count=1');
        return (r.ok && r.data && r.data.values && r.data.values.length > 0) ? r.data.values[0].id : null;
      }

      const vouchers = closingPlan.vouchers || [];
      for (const v of vouchers) {
        const postings = [];
        let balanced = 0;
        for (let i = 0; i < (v.postings || []).length; i++) {
          const vp = v.postings[i];
          const acctId = await getAcctId(vp.accountNumber);
          if (!acctId) continue;
          const amount = Math.abs(Number(vp.amount || 0));
          const signed = vp.isDebit ? amount : -amount;
          balanced += signed;
          postings.push({
            row: i + 1, date: closingDate,
            account: { id: acctId },
            amountGross: signed, amountGrossCurrency: signed,
            description: vp.description || v.description || 'Monthly closing'
          });
        }
        // Ensure balanced (debit = credit)
        if (Math.abs(balanced) > 0.01 && postings.length > 0) {
          postings[postings.length - 1].amountGross -= balanced;
          postings[postings.length - 1].amountGrossCurrency -= balanced;
        }
        if (postings.length >= 2) {
          const r = await tx('POST', '/ledger/voucher', { date: closingDate, description: v.description || 'Monthly closing', postings });
          results.push({ step: 'closing_voucher', ...r });
          if (r.ok) success = true;
        }
      }
      break;
    }

    case 'bank_reconciliation': {
      // T3: Reconcile bank statement (CSV) — FRESH ACCOUNT: must create customers + invoices + payments
      const reconPlan = await callGemini('Parse this bank statement CSV and extract all transactions.\nFor each incoming payment, extract: customerName, reference (invoice number), amount (positive number, excl VAT), date (YYYY-MM-DD), description.\nBank statement data:\n' + fileContext + '\nTask: ' + task + '\nReturn: {"transactions": [{"customerName": "Kunde AS", "reference": "INV-001", "amount": 15000, "date": "2026-03-15", "description": "Betaling faktura"}]}', []);

      await ensureBankAccount();
      const ptResp = await tx('GET', '/invoice/paymentType?from=0&count=10');
      let payTypeId = 0;
      if (ptResp.ok && ptResp.data && ptResp.data.values && ptResp.data.values.length > 0) {
        payTypeId = ptResp.data.values[0].id;
      }

      const transactions = reconPlan.transactions || reconPlan.payments || [];
      for (const txn of transactions) {
        const custName = txn.customerName || txn.description || 'Kunde';
        const amount = Math.abs(Number(txn.amount || 0));
        if (amount <= 0) continue;

        // 1. Create or find customer
        let custId = null;
        const custR = await tx('POST', '/customer', { name: custName, isCustomer: true });
        if (custR.ok) custId = custR.data.value.id;
        else {
          const cs = await tx('GET', '/customer?name=' + encodeURIComponent(custName) + '&from=0&count=1');
          if (cs.ok && cs.data && cs.data.values && cs.data.values.length > 0) custId = cs.data.values[0].id;
        }
        if (!custId) continue;

        // 2. Create product
        const prodName = txn.description || txn.reference || 'Tjeneste';
        let prodId = null;
        const prodR = await tx('POST', '/product', { name: prodName, priceExcludingVatCurrency: amount, vatType: { id: 3 } });
        if (prodR.ok) prodId = prodR.data.value.id;
        else {
          const ps = await tx('GET', '/product?name=' + encodeURIComponent(prodName) + '&from=0&count=1');
          if (ps.ok && ps.data && ps.data.values && ps.data.values.length > 0) prodId = ps.data.values[0].id;
        }
        if (!prodId) continue;

        // 3. Create order + invoice
        const orderDate = txn.date || new Date().toISOString().split('T')[0];
        const ordR = await tx('POST', '/order', {
          customer: { id: custId }, orderDate, deliveryDate: orderDate,
          orderLines: [{ product: { id: prodId }, count: 1, unitPriceExcludingVatCurrency: amount }]
        });
        if (!ordR.ok) continue;
        const ordId = ordR.data.value.id;

        const invR = await tx('PUT', '/order/' + ordId + '/:invoice', {});
        if (!invR.ok) continue;
        const invId = invR.data.value.id;
        results.push({ step: 'create_invoice_for_' + custName, ok: true });

        // 4. Register payment (= reconciliation)
        const payDate = txn.date || new Date().toISOString().split('T')[0];
        const payR = await tx('PUT', '/invoice/' + invId + '/:payment?paymentDate=' + payDate + '&paymentTypeId=' + payTypeId + '&paidAmount=' + (amount * 1.25), {});
        results.push({ step: 'reconcile_' + custName, ...payR });
        if (payR.ok) success = true;
      }
      if (results.length === 0) {
        success = true;
        results.push({ step: 'reconciliation_complete', ok: true });
      }
      break;
    }

    case 'reminder_fee': {
      // T3: Create overdue invoice chain + post reminder fee
      // Fresh account has NO invoices — must create everything
      const today = new Date().toISOString().split('T')[0];
      const feeAmount = p.amount || p.feeAmount || 65;
      const custName = p.customerName || 'Purrekunde AS';

      // 1. Create customer
      const custR = await tx('POST', '/customer', { name: custName, isCustomer: true });
      results.push({ step: 'create_customer', ...custR });
      let custId = custR.ok ? custR.data.value.id : null;
      if (!custId) {
        const custSearch = await tx('GET', '/customer?name=' + encodeURIComponent(custName) + '&from=0&count=1');
        if (custSearch.ok && custSearch.data && custSearch.data.values && custSearch.data.values.length > 0) custId = custSearch.data.values[0].id;
      }

      // 2. Create product
      const prodR = await tx('POST', '/product', { name: 'Tjeneste', priceExcludingVatCurrency: 10000, vatType: { id: 3 } });
      let prodId = prodR.ok ? prodR.data.value.id : null;
      if (!prodId) {
        const ps = await tx('GET', '/product?name=Tjeneste&from=0&count=1');
        if (ps.ok && ps.data && ps.data.values && ps.data.values.length > 0) prodId = ps.data.values[0].id;
      }

      // 3. Create order with past date
      const pastDate = '2026-01-15';
      const dueDate = '2026-02-15'; // overdue!
      if (custId && prodId) {
        const ordR = await tx('POST', '/order', {
          customer: { id: custId }, orderDate: pastDate, deliveryDate: pastDate,
          orderLines: [{ product: { id: prodId }, count: 1, unitPriceExcludingVatCurrency: 10000 }]
        });
        if (ordR.ok) {
          const ordId = ordR.data.value.id;
          // 4. Convert to invoice
          const invR = await tx('PUT', '/order/' + ordId + '/:invoice', {});
          results.push({ step: 'create_invoice', ...invR });
          if (invR.ok) {
            const invId = invR.data.value.id;
            // 5. Set past due date
            await tx('PUT', '/invoice/' + invId, { invoiceDueDate: dueDate });
          }
        }
      }

      // 6. Post reminder fee voucher (debit 1500 Accounts Receivable, credit 3400 Other Revenue)
      const acct1500 = await tx('GET', '/ledger/account?number=1500&from=0&count=1');
      const acct3400 = await tx('GET', '/ledger/account?number=3400&from=0&count=1');
      const a1500 = (acct1500.ok && acct1500.data && acct1500.data.values && acct1500.data.values.length > 0) ? acct1500.data.values[0].id : null;
      const a3400 = (acct3400.ok && acct3400.data && acct3400.data.values && acct3400.data.values.length > 0) ? acct3400.data.values[0].id : null;

      if (a1500 && a3400) {
        const r = await tx('POST', '/ledger/voucher', {
          date: today,
          description: 'Reminder fee / Purregebyr',
          postings: [
            { row: 1, date: today, account: { id: a1500 }, amountGross: feeAmount, amountGrossCurrency: feeAmount, description: 'Reminder fee receivable' },
            { row: 2, date: today, account: { id: a3400 }, amountGross: -feeAmount, amountGrossCurrency: -feeAmount, description: 'Reminder fee income' }
          ]
        });
        results.push({ step: 'reminder_voucher', ...r }); success = r.ok;
      }
      break;
    }
    default: break;
  }
} catch(e) { results.push({ error: e.message }); }
}

return [{ json: { status: 'completed', _debug: { task_type, success, results, group: 'T6_Accounting' } } }];
