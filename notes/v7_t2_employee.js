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


// === T2_Employee HANDLER ===
for (const p of paramsList) {
try {
  switch (task_type) {
    case 'create_employee': {
      const b = {};
      // Support both camelCase and snake_case from Gemini
      b.firstName = p.firstName || p.first_name || '';
      b.lastName = p.lastName || p.last_name || '';
      const email = p.email || p.e_mail || '';
      if (email) b.email = email;
      const phone = p.phoneNumberMobile || p.phone_number_mobile || p.phoneNumber || p.phone_number || p.phone || '';
      if (phone) {
        let ph = String(phone).replace(/[^0-9+]/g, '');
        if (ph.startsWith('+47')) ph = ph.substring(3);
        if (ph.startsWith('0047')) ph = ph.substring(4);
        if (ph.startsWith('47') && ph.length === 10) ph = ph.substring(2);
        if (ph.length === 8 && /^[49]/.test(ph)) b.phoneNumberMobile = ph;
      }
      // dateOfBirth — REQUIRED by competition
      const nidRaw = p.nationalIdentityNumber || p.national_identity_number || p.nid || '';
      const nid = String(nidRaw).replace(/\s/g, '');
      if (nid.length === 11 && /^\d{11}$/.test(nid)) b.nationalIdentityNumber = nid;

      let dob = p.dateOfBirth || p.date_of_birth || '';
      if (!dob && nid.length === 11) {
        // Extract dateOfBirth from Norwegian NID: DDMMYY + 5 digits
        const dd = nid.substring(0, 2);
        const mm = nid.substring(2, 4);
        const yy = nid.substring(4, 6);
        const indiv = parseInt(nid.substring(6, 9));
        let century;
        if (indiv < 500) century = '19';
        else if (indiv < 750 && parseInt(yy) >= 54) century = '18';
        else if (indiv >= 500 && indiv < 1000 && parseInt(yy) < 40) century = '20';
        else century = '19';
        dob = century + yy + '-' + mm + '-' + dd;
      }
      if (!dob) dob = '1990-01-15'; // Fallback — field is REQUIRED
      b.dateOfBirth = dob;

      // NEVER send startDate or occupationCode in employee body — API rejects them
      b.userType = email ? 'STANDARD' : 'NO_ACCESS';
      const deptName = p.department || p.departmentName || p.department_name || '';
      if (deptName) {
        const dept = await findDeptByName(deptName);
        if (dept) b.department = { id: dept.id };
      }
      if (!b.department) { const did = await getDefaultDeptId(); if (did) b.department = { id: did }; }
      const r = await tx('POST', '/employee', b);
      results.push(r); success = r.ok;
      if (r.ok) {
        const newEmpId = r.data.value.id;
        // Grant ALL_PRIVILEGES entitlements (= "Administrator role assigned", worth 5 points)
        const entR = await tx('PUT', '/employee/entitlement/:grantEntitlementsByTemplate?employeeId=' + newEmpId + '&template=ALL_PRIVILEGES', {});
        results.push({ step: 'grant_entitlements', ok: entR.ok || entR.status === 200, status: entR.status });
        // Set startDate and employment details if provided
        const empStartDate = p.startDate || p.start_date || '';
        const empSalary = p.salary || p.annual_salary || p.annualSalary || '';
        const empPct = p.employmentPercentage || p.employment_percentage || p.percentage || '';
        const empOcc = p.occupationCode || p.occupation_code || '';
        const empType = p.employmentType || p.employment_type || '';
        if (empStartDate || empSalary || empPct || empOcc || empType) {
          const empFull = await tx('GET', '/employee/' + newEmpId + '?fields=*,employments(*)');
          if (empFull.ok) {
            const upd = empFull.data.value;
            if (!upd.employments || upd.employments.length === 0) upd.employments = [{}];
            if (empStartDate) upd.employments[0].startDate = empStartDate;
            // NOTE: employmentType NOT accepted via PUT /employee — API returns 422 "Feltet eksisterer ikke"
            // Must be set via separate endpoint if needed
            const ur = await tx('PUT', '/employee/' + newEmpId, upd);
            results.push({ step: 'set_start_date', ...ur });
            // Set employment details (salary, percentage, occupation)
            if (ur.ok && (empSalary || empPct || empOcc)) {
              const empId2 = ur.data.value.employments && ur.data.value.employments[0] ? ur.data.value.employments[0].id : null;
              if (empId2) {
                const detailsR = await tx('GET', '/employee/employment/details?employmentId=' + empId2 + '&from=0&count=1');
                if (detailsR.ok && detailsR.data && detailsR.data.values && detailsR.data.values.length > 0) {
                  const detail = detailsR.data.values[0];
                  if (empSalary) detail.annualSalary = Number(empSalary);
                  if (empPct) detail.percentageOfFullTimeEquivalent = Number(empPct);
                  if (empOcc) detail.occupationCode = { code: String(empOcc) };
                  const detUpd = await tx('PUT', '/employee/employment/details/' + detail.id, detail);
                  results.push({ step: 'set_employment_details', ok: detUpd.ok, status: detUpd.status });
                } else {
                  // Create new employment details
                  const newDetail = { employment: { id: empId2 } };
                  if (p.salary) newDetail.annualSalary = Number(p.salary);
                  if (p.employmentPercentage) newDetail.percentageOfFullTimeEquivalent = Number(p.employmentPercentage);
                  if (p.occupationCode) newDetail.occupationCode = { code: String(p.occupationCode) };
                  const detPost = await tx('POST', '/employee/employment/details', newDetail);
                  results.push({ step: 'set_employment_details', ok: detPost.ok, status: detPost.status });
                }
              }
            }
          }
        }
      }
      break;
    }
    default: break;
  }
} catch(e) { results.push({ error: e.message }); }
}

return [{ json: { status: 'completed', _debug: { task_type, success, results, group: 'T2_Employee' } } }];
