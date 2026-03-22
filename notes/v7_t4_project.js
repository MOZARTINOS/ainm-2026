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
const GEMINI_KEY = 'AIzaSyC_ya1fW-hpajZyb8osz35Y4znS9cx_h4g';

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


// === T4_Project HANDLER ===
for (const p of paramsList) {
try {
  switch (task_type) {
    case 'project_invoice': {
      // T2 multi-step: customer → employee → project → activity → timesheet → order → invoice
      await ensureBankAccount();
      const today = new Date().toISOString().split('T')[0];

      // 1. Customer
      let piCustId;
      const custName = p.customerName || p.customer_name || '';
      const custOrg = p.customerOrgNumber || p.customer_org_number || '';
      if (custName) {
        const cs = await tx('GET', '/customer?name=' + encodeURIComponent(custName) + '&from=0&count=5');
        if (cs.ok && cs.data && cs.data.values && cs.data.values.length > 0) {
          piCustId = cs.data.values[0].id;
        } else {
          const cb = { name: custName, isCustomer: true };
          if (custOrg) cb.organizationNumber = String(custOrg);
          const nc = await tx('POST', '/customer', cb);
          results.push({ step: 'create_customer', ...nc });
          if (nc.ok) piCustId = nc.data.value.id;
        }
      }
      if (!piCustId) {
        // Fallback: create customer from task text
        const fallbackName = custName || 'Project Customer';
        const nc = await tx('POST', '/customer', { name: fallbackName, isCustomer: true });
        results.push({ step: 'create_customer_fallback', ...nc });
        if (nc.ok) piCustId = nc.data.value.id;
        if (!piCustId) { results.push({ error: 'No customer for project invoice' }); break; }
      }

      // 2. Employee (the person logging hours)
      let piEmpId;
      const piFirst = p.employeeFirstName || p.employee_first_name || p.projectManagerFirstName || '';
      const piLast = p.employeeLastName || p.employee_last_name || p.projectManagerLastName || '';
      if (piFirst || piLast) {
        const existingEmp = await findEmployee(piFirst, piLast);
        if (existingEmp) {
          piEmpId = existingEmp.id;
        } else {
          const eb = { firstName: piFirst, lastName: piLast, userType: 'NO_ACCESS' };
          if (p.employeeEmail) { eb.email = p.employeeEmail; eb.userType = 'STANDARD'; }
          const did = await getDefaultDeptId();
          if (did) eb.department = { id: did };
          const ne = await tx('POST', '/employee', eb);
          results.push({ step: 'create_employee', ...ne });
          if (ne.ok) {
            piEmpId = ne.data.value.id;
            await tx('PUT', '/employee/entitlement/:grantEntitlementsByTemplate?employeeId=' + piEmpId + '&template=ALL_PRIVILEGES', {});
          }
        }
      }
      if (!piEmpId) piEmpId = await getFirstEmployeeId();

      // 3. Project
      // Handle multiple employees from Gemini (employees array)
      const piEmployees = p.employees || [];
      if (piEmployees.length > 0 && !piFirst) {
        // Create all employees and log hours
        for (const emp of piEmployees) {
          const ef = emp.firstName || emp.first_name || '';
          const el = emp.lastName || emp.last_name || '';
          if (!ef && !el) continue;
          let empId;
          const existing = await findEmployee(ef, el);
          if (existing) {
            empId = existing.id;
          } else {
            const eb = { firstName: ef, lastName: el, userType: emp.email ? 'STANDARD' : 'NO_ACCESS' };
            if (emp.email) eb.email = emp.email;
            const did = await getDefaultDeptId();
            if (did) eb.department = { id: did };
            const ne = await tx('POST', '/employee', eb);
            results.push({ step: 'create_employee_' + ef, ...ne });
            if (ne.ok) {
              empId = ne.data.value.id;
              await tx('PUT', '/employee/entitlement/:grantEntitlementsByTemplate?employeeId=' + empId + '&template=ALL_PRIVILEGES', {});
            }
          }
          if (!piEmpId) piEmpId = empId; // Use first as PM
        }
      }

      const projBody = {
        name: p.projectName || p.project_name || p.name || 'Project',
        isInternal: false,
        customer: { id: piCustId },
        projectManager: { id: piEmpId },
        startDate: today
      };
      const proj = await tx('POST', '/project', projBody);
      results.push({ step: 'create_project', ...proj });
      const piProjId = proj.ok ? proj.data.value.id : null;
      if (!piProjId) break;

      // 4. Activity (create or find)
      const actName = p.activityName || p.description || 'Work';
      let piActId;
      const existingActs = await tx('GET', '/activity?from=0&count=50');
      if (existingActs.ok && existingActs.data && existingActs.data.values) {
        const match = existingActs.data.values.find(a => a.name.toLowerCase() === actName.toLowerCase() && a.isProjectActivity);
        if (match) piActId = match.id;
      }
      if (!piActId) {
        const newAct = await tx('POST', '/activity', { name: actName, activityType: 'PROJECT_GENERAL_ACTIVITY' });
        results.push({ step: 'create_activity', ...newAct });
        if (newAct.ok) piActId = newAct.data.value.id;
      }

      // 5. Link activity to project
      if (piActId) {
        const link = await tx('POST', '/project/projectActivity', { project: { id: piProjId }, activity: { id: piActId } });
        results.push({ step: 'link_activity', ok: link.ok, status: link.status });
      }

      // 6. Timesheet entry
      const hours = Number(p.hours || 0);
      const hourlyRate = Number(p.hourlyRate || 0);
      if (hours > 0 && piActId) {
        const tsEntry = await tx('POST', '/timesheet/entry', {
          employee: { id: piEmpId },
          project: { id: piProjId },
          activity: { id: piActId },
          date: today,
          hours: hours
        });
        results.push({ step: 'timesheet', ...tsEntry });
      }

      // 7. Set hourly rate on project
      if (hourlyRate > 0) {
        // Try project-level hourly rates
        const rates = await tx('GET', '/project/hourlyRates?projectId=' + piProjId + '&from=0&count=5');
        if (rates.ok && rates.data && rates.data.values && rates.data.values.length > 0) {
          const rate = rates.data.values[0];
          rate.fixedRate = hourlyRate;
          const rateUpd = await tx('PUT', '/project/hourlyRates/' + rate.id, rate);
          results.push({ step: 'set_hourly_rate', ok: rateUpd.ok });
        } else {
          // Create hourly rate entry
          const newRate = await tx('POST', '/project/hourlyRates', {
            project: { id: piProjId },
            startDate: today,
            fixedRate: hourlyRate
          });
          results.push({ step: 'create_hourly_rate', ok: newRate.ok });
        }
      }

      // 8. Order + Invoice (use order-to-invoice conversion)
      const totalAmount = hours > 0 && hourlyRate > 0 ? hours * hourlyRate : (Number(p.amount || p.fixedPrice || 0));
      // Create product for invoice line
      const piProdName = (actName || 'Consulting') + (hours > 0 ? ' - ' + hours + 'h' : '');
      const piProd = await tx('POST', '/product', {
        name: piProdName,
        priceExcludingVatCurrency: hourlyRate || totalAmount || 0,
        vatType: { id: 3 }
      });
      let piProdId = piProd.ok ? piProd.data.value.id : null;
      if (!piProdId) {
        const ps = await tx('GET', '/product?name=' + encodeURIComponent(piProdName) + '&from=0&count=1');
        if (ps.ok && ps.data && ps.data.values && ps.data.values.length > 0) piProdId = ps.data.values[0].id;
      }

      const oLines = [{
        product: piProdId ? { id: piProdId } : undefined,
        description: piProdName,
        count: hours || 1,
        unitPriceExcludingVatCurrency: hourlyRate || totalAmount || 0
      }];
      const order = await tx('POST', '/order', {
        customer: { id: piCustId }, orderDate: today, deliveryDate: today,
        project: { id: piProjId }, orderLines: oLines
      });
      results.push({ step: 'create_order', ...order });

      if (order.ok) {
        const ordId = order.data.value.id;
        // Convert order to invoice (more reliable than POST /invoice)
        const inv = await tx('PUT', '/order/' + ordId + '/:invoice', {});
        results.push({ step: 'create_invoice', ...inv });
        success = inv.ok;
      }
      break;
    }

    case 'create_project': {
      // Find or create customer if linked
      let pcId;
      if (p.customerName) {
        const cs = await tx('GET', '/customer?name=' + encodeURIComponent(p.customerName) + '&from=0&count=3');
        if (cs.ok && cs.data && cs.data.values && cs.data.values.length > 0) {
          pcId = cs.data.values[0].id;
        } else {
          const custBody = { name: p.customerName, isCustomer: true };
          if (p.customerOrgNumber) custBody.organizationNumber = String(p.customerOrgNumber);
          const nc = await tx('POST', '/customer', custBody);
          results.push({ step: 'create_customer', ...nc });
          if (nc.ok) pcId = nc.data.value.id;
        }
      }

      // Find or create project manager if specified
      let pmId = await getFirstEmployeeId();
      if (p.projectManagerFirstName || p.projectManagerLastName || p.projectManagerEmail) {
        const pmFirst = p.projectManagerFirstName || '';
        const pmLast = p.projectManagerLastName || '';
        // Try to find existing employee
        const existingPm = await findEmployee(pmFirst, pmLast);
        if (existingPm) {
          pmId = existingPm.id;
          // Always grant entitlements — PM needs project manager access
          await tx('PUT', '/employee/entitlement/:grantEntitlementsByTemplate?employeeId=' + pmId + '&template=ALL_PRIVILEGES', {});
        } else {
          // Create employee as project manager
          const pmBody = { userType: 'NO_ACCESS' };
          if (pmFirst) pmBody.firstName = pmFirst;
          if (pmLast) pmBody.lastName = pmLast;
          if (p.projectManagerEmail) { pmBody.email = p.projectManagerEmail; pmBody.userType = 'STANDARD'; }
          const ddi = await getDefaultDeptId(); if (ddi) pmBody.department = { id: ddi };
          const pmRes = await tx('POST', '/employee', pmBody);
          results.push({ step: 'create_pm', ...pmRes });
          if (pmRes.ok) {
            pmId = pmRes.data.value.id;
            // Grant entitlements
            await tx('PUT', '/employee/entitlement/:grantEntitlementsByTemplate?employeeId=' + pmId + '&template=ALL_PRIVILEGES', {});
          }
        }
      }

      const b = { name: p.name || '' };
      b.isInternal = pcId ? false : (p.isInternal !== false);
      if (p.number || p.projectNumber) b.number = String(p.number || p.projectNumber);
      if (pcId) b.customer = { id: pcId };
      b.startDate = p.startDate || new Date().toISOString().split('T')[0];
      if (p.endDate) b.endDate = p.endDate;
      if (pmId) b.projectManager = { id: pmId };
      const r = await tx('POST', '/project', b);
      results.push(r); success = r.ok;
      break;
    }
    default: break;
  }
} catch(e) { results.push({ error: e.message }); }
}

return [{ json: { status: 'completed', _debug: { task_type, success, results, group: 'T4_Project' } } }];
