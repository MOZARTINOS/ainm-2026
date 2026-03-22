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


// === T3_Invoice HANDLER ===
for (const p of paramsList) {
try {
  switch (task_type) {
    case 'create_invoice': {
      await ensureBankAccount();
      // Find customer (or create with orgNumber)
      let customerId;
      let customerEmail = '';
      if (p.customerName) {
        const custResult = await tx('GET', '/customer?name=' + encodeURIComponent(p.customerName) + '&from=0&count=5');
        if (custResult.ok && custResult.data && custResult.data.values && custResult.data.values.length > 0) {
          customerId = custResult.data.values[0].id;
          customerEmail = custResult.data.values[0].email || '';
        } else {
          const custBody = { name: p.customerName, isCustomer: true };
          if (p.customerOrgNumber) custBody.organizationNumber = String(p.customerOrgNumber);
          const nc = await tx('POST', '/customer', custBody);
          if (nc.ok) { customerId = nc.data.value.id; customerEmail = nc.data.value.email || ''; }
          results.push({ step: 'create_customer', ...nc });
        }
      }
      if (!customerId) {
        const ac = await tx('GET', '/customer?from=0&count=1');
        if (ac.ok && ac.data && ac.data.values && ac.data.values.length > 0) {
          customerId = ac.data.values[0].id;
          customerEmail = ac.data.values[0].email || '';
        }
      }
      if (!customerId) { results.push({ error: 'No customer' }); break; }

      const today = new Date().toISOString().split('T')[0];
      const iDate = p.invoiceDate || today;
      // Build orderLines with description fallback from prompt-level fields
      const defaultDesc = p.productDescription || p.description || 'Service';
      const defaultPrice = p.amount || p.productPrice || 1000;
      const oLines = (p.lines && p.lines.length > 0 ? p.lines : [{ description: defaultDesc, quantity: 1, unitPrice: defaultPrice }]).map(l => ({
        description: l.description || l.product || defaultDesc,
        count: l.quantity || 1,
        unitPriceExcludingVatCurrency: l.unitPrice || l.amount || defaultPrice
      }));

      const order = await tx('POST', '/order', {
        customer: { id: customerId }, deliveryDate: iDate, orderDate: iDate, orderLines: oLines
      });
      results.push({ step: 'create_order', ...order });

      let invoiceId = null;
      if (order.ok) {
        const orderId = order.data.value.id;
        const dueDate = p.dueDate || iDate;
        // Primary: POST /invoice with order reference
        const inv = await tx('POST', '/invoice', {
          invoiceDate: iDate,
          invoiceDueDate: dueDate,
          orders: [{ id: orderId }]
        });
        results.push({ step: 'create_invoice', ...inv });
        success = inv.ok;
        if (inv.ok) invoiceId = inv.data.value.id;
        // Fallback: PUT /order/:invoice
        if (!inv.ok) {
          let invoiceUrl = '/order/' + orderId + '/:invoice?invoiceDate=' + iDate + '&sendToCustomer=false';
          if (p.dueDate) invoiceUrl += '&invoiceDueDate=' + p.dueDate;
          const inv2 = await tx('PUT', invoiceUrl, {});
          results.push({ step: 'create_invoice_fallback', ...inv2 });
          success = inv2.ok;
          if (inv2.ok) invoiceId = inv2.data.value.id;
        }
      }
      // Send invoice if requested (envie/send/sende/enviar/envoyer/schicken)
      if (invoiceId && (p.shouldSend || /\b(send|envie|sende|enviar|envoyer|schicken|zuschicken)\b/i.test(task))) {
        const sendR = await tx('PUT', '/invoice/' + invoiceId + '/:send?sendType=EMAIL&overrideEmailAddress=' + encodeURIComponent(customerEmail || 'noreply@tripletex.no'), {});
        results.push({ step: 'send_invoice', ...sendR });
      }
      break;
    }

    case 'credit_note': {
      // Ensure bank account is set (needed for invoice creation)
      await ensureBankAccount();
      let invId = p.invoiceId;
      if (!invId && p.invoiceNumber) {
        const is = await tx('GET', '/invoice?invoiceNumber=' + p.invoiceNumber + '&from=0&count=5');
        if (is.ok && is.data && is.data.values && is.data.values.length > 0) invId = is.data.values[0].id;
      }
      if (!invId) {
        const is = await tx('GET', '/invoice?from=0&count=10');
        if (is.ok && is.data && is.data.values && is.data.values.length > 0) invId = is.data.values[0].id;
      }
      // If no invoice found on fresh account, create the full chain
      if (!invId && (p.customerName || p.amount || p.productDescription)) {
        const today = new Date().toISOString().split('T')[0];
        // 1. Create/find customer
        let custId;
        if (p.customerName) {
          const cs = await tx('GET', '/customer?name=' + encodeURIComponent(p.customerName) + '&from=0&count=5');
          if (cs.ok && cs.data && cs.data.values && cs.data.values.length > 0) {
            custId = cs.data.values[0].id;
          } else {
            const nc = await tx('POST', '/customer', { name: p.customerName, organizationNumber: p.customerOrgNumber ? String(p.customerOrgNumber) : '', isCustomer: true });
            if (nc.ok) custId = nc.data.value.id;
            results.push({ step: 'create_customer', ...nc });
          }
        }
        if (!custId) {
          const ac = await tx('GET', '/customer?from=0&count=1');
          if (ac.ok && ac.data && ac.data.values && ac.data.values.length > 0) custId = ac.data.values[0].id;
        }
        if (custId) {
          // 2. Create order
          const amount = Number(p.amount || p.amountExcludingVat || 0);
          const desc = p.productDescription || p.description || 'Service';
          const order = await tx('POST', '/order', {
            customer: { id: custId }, orderDate: today, deliveryDate: today,
            orderLines: [{ description: desc, count: 1, unitPriceExcludingVatCurrency: amount }]
          });
          results.push({ step: 'create_order', ...order });
          if (order.ok) {
            // 3. Create invoice
            const inv = await tx('POST', '/invoice', { invoiceDate: today, invoiceDueDate: today, orders: [{ id: order.data.value.id }] });
            results.push({ step: 'create_invoice', ...inv });
            if (inv.ok) invId = inv.data.value.id;
          }
        }
      }
      if (invId) {
        const cnDate = new Date().toISOString().split('T')[0];
        const r = await tx('PUT', '/invoice/' + invId + '/:createCreditNote?date=' + cnDate, {});
        results.push(r); success = r.ok;
      }
      else results.push({ error: 'No invoice' });
      break;
    }

    case 'register_payment': {
      await ensureBankAccount();
      let invId = p.invoiceId;
      const today = new Date().toISOString().split('T')[0];
      const payDate = p.paymentDate || today;
      const payAmount = p.amount || p.productPrice || 0;

      // Step 1: Try to find existing invoice
      if (!invId && p.invoiceNumber) {
        const is = await tx('GET', '/invoice?invoiceNumber=' + p.invoiceNumber + '&from=0&count=5');
        if (is.ok && is.data && is.data.values && is.data.values.length > 0) invId = is.data.values[0].id;
      }
      if (!invId) {
        const is = await tx('GET', '/invoice?from=0&count=50');
        if (is.ok && is.data && is.data.values) {
          const outstanding = is.data.values.find(i => i.amountOutstanding && i.amountOutstanding > 0);
          if (outstanding) invId = outstanding.id;
        }
      }

      // Step 2: If no invoice found, create the full chain: customer → order → invoice
      if (!invId && (p.customerName || p.customerOrgNumber || p.productDescription)) {
        // 2a: Find or create customer
        let customerId;
        if (p.customerName) {
          const cs = await tx('GET', '/customer?name=' + encodeURIComponent(p.customerName) + '&from=0&count=5');
          if (cs.ok && cs.data && cs.data.values && cs.data.values.length > 0) {
            customerId = cs.data.values[0].id;
          }
        }
        if (!customerId) {
          const custBody = { name: p.customerName || 'Customer', isCustomer: true };
          if (p.customerOrgNumber) custBody.organizationNumber = String(p.customerOrgNumber);
          const nc = await tx('POST', '/customer', custBody);
          results.push({ step: 'create_customer', ...nc });
          if (nc.ok) customerId = nc.data.value.id;
        }
        if (!customerId) {
          const ac = await tx('GET', '/customer?from=0&count=1');
          if (ac.ok && ac.data && ac.data.values && ac.data.values.length > 0) customerId = ac.data.values[0].id;
        }

        if (customerId) {
          // 2b: Create products and build orderLines
          // Support multiple products: p.products[] OR single p.productDescription/productPrice
          const productList = (p.products && p.products.length > 0) ? p.products
            : [{ name: p.productDescription || p.description || 'Service', number: p.productNumber, unitPrice: p.productPrice || p.amount || 0 }];

          const orderLines = [];
          for (const prod of productList) {
            const prodPrice = Number(prod.unitPrice || prod.price || 0);
            const prodName = prod.name || prod.description || 'Service';
            const prodBody = { name: prodName, priceExcludingVatCurrency: prodPrice };
            if (prod.number) prodBody.number = String(prod.number);
            const prodRes = await tx('POST', '/product', prodBody);
            if (!prodRes.ok) {
              // Retry without number (might conflict) and without vatType
              delete prodBody.number;
              const prodRes2 = await tx('POST', '/product', prodBody);
              results.push({ step: 'create_product', ...prodRes2 });
              const ol = { description: prodName, count: prod.quantity || 1, unitPriceExcludingVatCurrency: prodPrice };
              if (prodRes2.ok) ol.product = { id: prodRes2.data.value.id };
              orderLines.push(ol);
            } else {
              results.push({ step: 'create_product', ...prodRes });
              const ol = { description: prodName, count: prod.quantity || 1, unitPriceExcludingVatCurrency: prodPrice };
              ol.product = { id: prodRes.data.value.id };
              orderLines.push(ol);
            }
          }
          if (orderLines.length === 0) {
            orderLines.push({ description: 'Service', count: 1, unitPriceExcludingVatCurrency: Number(p.amount || 1000) });
          }

          const order = await tx('POST', '/order', {
            customer: { id: customerId },
            deliveryDate: today,
            orderDate: today,
            orderLines: orderLines
          });
          results.push({ step: 'create_order', ...order });

          // 2c: Create invoice from order
          if (order.ok) {
            const orderId = order.data.value.id;
            // Primary: POST /invoice
            const inv = await tx('POST', '/invoice', {
              invoiceDate: today,
              invoiceDueDate: today,
              orders: [{ id: orderId }]
            });
            results.push({ step: 'create_invoice', ...inv });
            if (inv.ok && inv.data && inv.data.value) {
              invId = inv.data.value.id;
            }
            // Fallback: PUT /order/:invoice
            if (!inv.ok) {
              const inv2 = await tx('PUT', '/order/' + orderId + '/:invoice?invoiceDate=' + today + '&sendToCustomer=false', {});
              results.push({ step: 'create_invoice_fallback', ...inv2 });
              if (inv2.ok && inv2.data && inv2.data.value) {
                invId = inv2.data.value.id;
              }
            }
          }
        }
      }

      // Step 3: Register payment on the invoice
      if (invId) {
        // Get the actual invoice amount if we need it
        let actualAmount = payAmount;
        if (!actualAmount || actualAmount === 0) {
          const invDetail = await tx('GET', '/invoice/' + invId);
          if (invDetail.ok && invDetail.data && invDetail.data.value) {
            actualAmount = invDetail.data.value.amount || invDetail.data.value.amountOutstanding || 0;
          }
        }
        // PUT /:payment requires query params. Needs INCOMING payment type from /invoice/paymentType
        // (NOT /ledger/paymentTypeOut which are outgoing!)
        let payTypeId = 0;
        try {
          const ptIn = await tx('GET', '/invoice/paymentType?from=0&count=10');
          if (ptIn.ok && ptIn.data && ptIn.data.values && ptIn.data.values.length > 0) {
            // Prefer "bank" type, fallback to first
            const bankType = ptIn.data.values.find(pt => (pt.description || '').toLowerCase().includes('bank'));
            payTypeId = bankType ? bankType.id : ptIn.data.values[0].id;
          }
        } catch(e) {}
        const r = await tx('PUT', '/invoice/' + invId + '/:payment?paymentDate=' + payDate + '&paymentTypeId=' + payTypeId + '&paidAmount=' + actualAmount, {});
        results.push({ step: 'payment', ...r });
        success = r.ok;

        // Handle exchange rate difference if currency specified
        if (r.ok && p.currency && p.exchangeRateInvoice && p.exchangeRatePayment) {
          const invRate = Number(p.exchangeRateInvoice);
          const payRate = Number(p.exchangeRatePayment);
          const foreignAmount = Number(p.amount || 0);
          const diff = Math.round((invRate - payRate) * foreignAmount * 100) / 100;
          if (Math.abs(diff) > 0.01) {
            // diff > 0 = loss (disagio 8160), diff < 0 = gain (agio 8060)
            const isLoss = diff > 0;
            const acctExch = await tx('GET', '/ledger/account?number=' + (isLoss ? '8160' : '8060') + '&from=0&count=1');
            const acct1500 = await tx('GET', '/ledger/account?number=1500&from=0&count=1');
            if (acctExch.ok && acctExch.data.values.length > 0 && acct1500.ok && acct1500.data.values.length > 0) {
              const exchAcctId = acctExch.data.values[0].id;
              const custAcctId = acct1500.data.values[0].id;
              const absDiff = Math.abs(diff);
              const exchVoucher = await tx('POST', '/ledger/voucher', {
                date: payDate || new Date().toISOString().split('T')[0],
                description: (isLoss ? 'Valutatap (disagio)' : 'Valutagevinst (agio)') + ' - ' + (p.currency || ''),
                postings: [
                  { row: 1, date: payDate || new Date().toISOString().split('T')[0], account: { id: isLoss ? exchAcctId : custAcctId }, amountGross: absDiff, amountGrossCurrency: absDiff },
                  { row: 2, date: payDate || new Date().toISOString().split('T')[0], account: { id: isLoss ? custAcctId : exchAcctId }, amountGross: -absDiff, amountGrossCurrency: -absDiff }
                ]
              });
              results.push({ step: 'exchange_rate_voucher', ...exchVoucher });
            }
          }
        }
      } else {
        results.push({ error: 'No invoice found and could not create one' });
      }
      break;
    }

    case 'reverse_payment': {
      // Payment was made but needs to be reversed (bank reversal, chargeback, etc.)
      // Chain: customer → order → invoice → payment → NEGATIVE payment (reverses it)
      await ensureBankAccount();
      const today = new Date().toISOString().split('T')[0];
      // Create/find customer
      let rpCustId;
      if (p.customerName) {
        const cs = await tx('GET', '/customer?name=' + encodeURIComponent(p.customerName) + '&from=0&count=5');
        if (cs.ok && cs.data && cs.data.values && cs.data.values.length > 0) rpCustId = cs.data.values[0].id;
        else {
          const custBody = { name: p.customerName, isCustomer: true };
          if (p.customerOrgNumber) custBody.organizationNumber = String(p.customerOrgNumber);
          const nc = await tx('POST', '/customer', custBody);
          if (nc.ok) rpCustId = nc.data.value.id;
          results.push({ step: 'create_customer', ...nc });
        }
      }
      if (!rpCustId) { results.push({ error: 'No customer for reverse_payment' }); break; }
      // Create order + invoice
      const rpDesc = p.productDescription || p.description || 'Service';
      const rpAmount = Number(p.amount || p.productPrice || 0);
      const rpOrder = await tx('POST', '/order', {
        customer: { id: rpCustId }, orderDate: today, deliveryDate: today,
        orderLines: [{ description: rpDesc, count: 1, unitPriceExcludingVatCurrency: rpAmount }]
      });
      results.push({ step: 'create_order', ...rpOrder });
      if (!rpOrder.ok) break;
      const rpOrdId = rpOrder.data.value.id;
      const rpInv = await tx('POST', '/invoice', { invoiceDate: today, invoiceDueDate: today, orders: [{ id: rpOrdId }] });
      results.push({ step: 'create_invoice', ...rpInv });
      if (!rpInv.ok) break;
      const rpInvId = rpInv.data.value.id;
      const rpInvAmt = rpInv.data.value.amount || rpAmount;
      // Get payment type
      let rpPtId = 0;
      const rpPt = await tx('GET', '/invoice/paymentType?from=0&count=5');
      if (rpPt.ok && rpPt.data && rpPt.data.values && rpPt.data.values.length > 0) rpPtId = rpPt.data.values[0].id;
      // Register original payment
      const rpPay = await tx('PUT', '/invoice/' + rpInvId + '/:payment?paymentDate=' + today + '&paymentTypeId=' + rpPtId + '&paidAmount=' + rpInvAmt, {});
      results.push({ step: 'register_payment', ...rpPay });
      // Reverse with NEGATIVE payment
      const rpReverse = await tx('PUT', '/invoice/' + rpInvId + '/:payment?paymentDate=' + today + '&paymentTypeId=' + rpPtId + '&paidAmount=-' + rpInvAmt, {});
      results.push({ step: 'reverse_payment', ...rpReverse });
      success = rpReverse.ok;
      break;
    }
    default: break;
  }
} catch(e) { results.push({ error: e.message }); }
}

return [{ json: { status: 'completed', _debug: { task_type, success, results, group: 'T3_Invoice' } } }];
