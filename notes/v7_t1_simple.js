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


// === T1_Simple HANDLER ===
for (const p of paramsList) {
try {
  switch (task_type) {
    case 'create_customer': {
      const b = { name: p.name || p.customerName || p.customer_name || '', isCustomer: true };
      if (p.email) { b.email = p.email; b.invoiceEmail = p.email; }
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

    case 'create_supplier': {
      const b = { name: p.name || p.supplierName || p.supplier_name || '', isSupplier: true };
      if (p.email) { b.email = p.email; b.invoiceEmail = p.email; }
      if (p.phoneNumber) b.phoneNumber = String(p.phoneNumber);
      if (p.organizationNumber) b.organizationNumber = String(p.organizationNumber);
      if (p.postalCode || p.city || p.address) {
        b.postalAddress = {};
        if (p.address) b.postalAddress.addressLine1 = p.address;
        if (p.postalCode) b.postalAddress.postalCode = String(p.postalCode);
        if (p.city) b.postalAddress.city = p.city;
        b.postalAddress.country = { id: 161 };
      }
      const r = await tx('POST', '/supplier', b);
      results.push(r); success = r.ok;
      break;
    }

    case 'create_product': {
      const vtId = getOutgoingVatId(p.vatPercentage);
      const b = { name: p.name || p.productName || p.product_name || '' };
      if (p.priceExcludingVat != null || p.priceExcludingVatCurrency != null || p.unitPrice != null) {
        b.priceExcludingVatCurrency = Number(p.priceExcludingVat || p.priceExcludingVatCurrency || p.unitPrice);
      }
      if (p.number) b.number = String(p.number);
      b.vatType = { id: vtId };
      const r = await tx('POST', '/product', b);
      if (r.ok) { results.push(r); success = true; }
      else {
        // Retry without vatType (some envs reject it)
        delete b.vatType;
        const r2 = await tx('POST', '/product', b);
        results.push(r2); success = r2.ok;
      }
      break;
    }

    case 'create_department': {
      const b = { name: p.name || p.departmentName || p.department_name || '' };
      if (p.departmentNumber) b.departmentNumber = String(p.departmentNumber);
      const r = await tx('POST', '/department', b);
      results.push(r); success = r.ok;
      break;
    }

    case 'delete_employee': case 'delete_customer': case 'delete_product': {
      const entityType = task_type.replace('delete_', '');
      let entityId = p.id;
      const dsf = p.search_fields || {};
      const dFirst = p.firstName || dsf.firstName;
      const dLast = p.lastName || dsf.lastName;
      if (!entityId && entityType === 'employee') {
        const emp = await findEmployee(dFirst, dLast);
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

    case 'delete_travel_expense': {
      // Find travel expense by employee name or get all, then delete
      let teId = p.id || p.travelExpenseId;
      if (!teId) {
        let q = '/travelExpense?from=0&count=50';
        if (p.employeeName) {
          // Find employee first, then their travel expenses
          const parts = p.employeeName.split(' ');
          const emp = await findEmployee(parts[0], parts.length > 1 ? parts.slice(1).join(' ') : null);
          if (emp) q += '&employeeId=' + emp.id;
        }
        const tes = await tx('GET', q);
        if (tes.ok && tes.data && tes.data.values && tes.data.values.length > 0) {
          // Match by title/description if provided
          if (p.title || p.description) {
            const search = (p.title || p.description).toLowerCase();
            const match = tes.data.values.find(te => (te.title || '').toLowerCase().includes(search));
            teId = match ? match.id : tes.data.values[0].id;
          } else {
            teId = tes.data.values[tes.data.values.length - 1].id; // delete most recent
          }
        }
      }
      if (teId) {
        const r = await tx('DELETE', '/travelExpense/' + teId);
        results.push(r); success = r.ok;
      } else results.push({ error: 'Travel expense not found' });
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
      let emp = await findEmployee(searchFirst, searchLast);
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
            const dept = await findDeptByName(updates.department);
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
    default: break;
  }
} catch(e) { results.push({ error: e.message }); }
}

return [{ json: { status: 'completed', _debug: { task_type, success, results, group: 'T1_Simple' } } }];
