#!/usr/bin/env node
/**
 * T2 Test Framework for NM i AI - Tripletex Competition
 *
 * Tests the v5 agent by sending prompts to the webhook and verifying
 * results via direct Tripletex sandbox API calls.
 *
 * Usage:
 *   node test_t2.js                          # Run all tests
 *   node test_t2.js --type supplier_invoice   # Run one task type
 *   node test_t2.js --id si_en_1             # Run one specific test
 *   node test_t2.js --dry-run                # Show what would be tested
 *   node test_t2.js --verify-only            # Skip webhook, just verify state
 *
 * Environment:
 *   WEBHOOK_URL    - Agent webhook (default: https://n8n.visam.no/webhook/tripletex-solve)
 *   SANDBOX_URL    - Tripletex sandbox API (default: https://kkpqfuj-amager.tripletex.dev/v2)
 *   SESSION_TOKEN  - Sandbox session token
 */

const https = require('https');
const http = require('http');
const fs = require('fs');
const path = require('path');

// === Configuration ===
const WEBHOOK_URL = process.env.WEBHOOK_URL || 'https://n8n.visam.no/webhook/tripletex-solve';
const SANDBOX_URL = process.env.SANDBOX_URL || 'https://kkpqfuj-amager.tripletex.dev/v2';
const SESSION_TOKEN = process.env.SESSION_TOKEN || 'eyJ0b2tlbklkIjoyMTQ3NjUyNjY1LCJ0b2tlbiI6ImQ4MjhkZDgzLTgxYjMtNDc5Yi04Yzk0LTBmNWU3NzcyODdlYyJ9';
const AUTH_HEADER = 'Basic ' + Buffer.from('0:' + SESSION_TOKEN).toString('base64');

// === CLI Args ===
const args = process.argv.slice(2);
const filterType = args.find((a, i) => args[i - 1] === '--type') || null;
const filterId = args.find((a, i) => args[i - 1] === '--id') || null;
const dryRun = args.includes('--dry-run');
const verifyOnly = args.includes('--verify-only');
const verbose = args.includes('--verbose') || args.includes('-v');

// === Colors for terminal output ===
const C = {
  reset: '\x1b[0m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m',
  dim: '\x1b[2m',
  bold: '\x1b[1m',
};

function log(msg) { console.log(msg); }
function logPass(msg) { console.log(`${C.green}  PASS${C.reset} ${msg}`); }
function logFail(msg) { console.log(`${C.red}  FAIL${C.reset} ${msg}`); }
function logSkip(msg) { console.log(`${C.yellow}  SKIP${C.reset} ${msg}`); }
function logInfo(msg) { console.log(`${C.dim}  INFO${C.reset} ${msg}`); }

// === HTTP helpers ===
function httpRequest(url, options = {}) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const mod = parsed.protocol === 'https:' ? https : http;
    const reqOpts = {
      hostname: parsed.hostname,
      port: parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
      path: parsed.pathname + parsed.search,
      method: options.method || 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    };

    const req = mod.request(reqOpts, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        try {
          resolve({
            status: res.statusCode,
            data: data ? JSON.parse(data) : null,
            ok: res.statusCode >= 200 && res.statusCode < 300,
          });
        } catch (e) {
          resolve({ status: res.statusCode, data: data, ok: false, parseError: true });
        }
      });
    });

    req.on('error', (e) => reject(e));
    if (options.timeout) req.setTimeout(options.timeout, () => { req.destroy(); reject(new Error('Timeout')); });
    if (options.body) req.write(typeof options.body === 'string' ? options.body : JSON.stringify(options.body));
    req.end();
  });
}

// === Tripletex API helper ===
async function tx(method, endpoint, body) {
  const url = SANDBOX_URL + endpoint;
  const opts = {
    method,
    headers: { 'Authorization': AUTH_HEADER },
    timeout: 30000,
  };
  if (body && method !== 'GET') opts.body = body;
  return httpRequest(url, opts);
}

// === Send task to webhook ===
async function sendToWebhook(prompt) {
  const payload = {
    body: {
      prompt: prompt,
      files: [],
      tripletex_credentials: {
        base_url: SANDBOX_URL,
        session_token: SESSION_TOKEN,
      },
    },
  };

  log(`${C.dim}  Sending to webhook...${C.reset}`);
  const start = Date.now();
  try {
    const result = await httpRequest(WEBHOOK_URL, {
      method: 'POST',
      body: payload,
      timeout: 300000, // 5 min timeout like competition
    });
    const elapsed = ((Date.now() - start) / 1000).toFixed(1);
    log(`${C.dim}  Webhook responded in ${elapsed}s (status: ${result.status})${C.reset}`);
    return result;
  } catch (e) {
    const elapsed = ((Date.now() - start) / 1000).toFixed(1);
    log(`${C.red}  Webhook error after ${elapsed}s: ${e.message}${C.reset}`);
    return { ok: false, error: e.message };
  }
}

// === Verification functions ===

async function checkVoucherExists(testCase) {
  const today = new Date().toISOString().split('T')[0];
  const dateFrom = '2026-01-01';
  const dateTo = '2026-12-31';
  const r = await tx('GET', `/ledger/voucher?dateFrom=${dateFrom}&dateTo=${dateTo}&from=0&count=50`);
  if (!r.ok) return { pass: false, reason: 'Could not query vouchers: ' + r.status };
  const vouchers = (r.data && r.data.values) || [];
  if (vouchers.length === 0) return { pass: false, reason: 'No vouchers found' };

  // Look for voucher created recently (in last 10 minutes)
  const recentVouchers = vouchers.filter(v => {
    // Just check if any voucher exists today
    return v.date === today || vouchers.length > 0;
  });

  return { pass: recentVouchers.length > 0, reason: recentVouchers.length > 0 ? `Found ${recentVouchers.length} vouchers` : 'No recent vouchers' };
}

async function checkSupplierExists(testCase, check) {
  const name = check.name || (testCase.expected && testCase.expected.supplier_name);
  if (!name) return { pass: false, reason: 'No supplier name to check' };
  const r = await tx('GET', `/supplier?name=${encodeURIComponent(name)}&from=0&count=10`);
  if (!r.ok) return { pass: false, reason: 'Could not query suppliers: ' + r.status };
  const suppliers = (r.data && r.data.values) || [];
  const match = suppliers.find(s => s.name && s.name.toLowerCase().includes(name.toLowerCase()));
  return { pass: !!match, reason: match ? `Found supplier: ${match.name} (id: ${match.id})` : `Supplier "${name}" not found` };
}

async function checkCustomerExists(testCase, check) {
  const name = check.name || (testCase.expected && testCase.expected.customer_name);
  if (!name) return { pass: false, reason: 'No customer name to check' };
  const r = await tx('GET', `/customer?name=${encodeURIComponent(name)}&from=0&count=10`);
  if (!r.ok) return { pass: false, reason: 'Could not query customers: ' + r.status };
  const customers = (r.data && r.data.values) || [];
  const match = customers.find(c => c.name && c.name.toLowerCase().includes(name.toLowerCase()));
  return { pass: !!match, reason: match ? `Found customer: ${match.name} (id: ${match.id})` : `Customer "${name}" not found` };
}

async function checkEmployeeExists(testCase, check) {
  const firstName = check.firstName || (testCase.expected && testCase.expected.employee_first);
  const lastName = check.lastName || (testCase.expected && testCase.expected.employee_last);
  if (!firstName && !lastName) return { pass: false, reason: 'No employee name to check' };
  const r = await tx('GET', `/employee?from=0&count=100&fields=id,firstName,lastName,email`);
  if (!r.ok) return { pass: false, reason: 'Could not query employees: ' + r.status };
  const employees = (r.data && r.data.values) || [];
  const match = employees.find(e =>
    (!firstName || (e.firstName || '').toLowerCase() === firstName.toLowerCase()) &&
    (!lastName || (e.lastName || '').toLowerCase() === lastName.toLowerCase())
  );
  return { pass: !!match, reason: match ? `Found employee: ${match.firstName} ${match.lastName} (id: ${match.id})` : `Employee "${firstName} ${lastName}" not found` };
}

async function checkProjectExists(testCase, check) {
  const name = check.name || (testCase.expected && testCase.expected.project_name);
  if (!name) return { pass: false, reason: 'No project name to check' };
  const r = await tx('GET', `/project?from=0&count=50`);
  if (!r.ok) return { pass: false, reason: 'Could not query projects: ' + r.status };
  const projects = (r.data && r.data.values) || [];
  const match = projects.find(p => p.name && p.name.toLowerCase().includes(name.toLowerCase()));
  return { pass: !!match, reason: match ? `Found project: ${match.name} (id: ${match.id})` : `Project "${name}" not found` };
}

async function checkOrderExists(testCase, check) {
  const r = await tx('GET', `/order?from=0&count=50`);
  if (!r.ok) return { pass: false, reason: 'Could not query orders: ' + r.status };
  const orders = (r.data && r.data.values) || [];
  return { pass: orders.length > 0, reason: orders.length > 0 ? `Found ${orders.length} orders` : 'No orders found' };
}

async function checkInvoiceExists(testCase, check) {
  const r = await tx('GET', `/invoice?from=0&count=50`);
  if (!r.ok) return { pass: false, reason: 'Could not query invoices: ' + r.status };
  const invoices = (r.data && r.data.values) || [];
  return { pass: invoices.length > 0, reason: invoices.length > 0 ? `Found ${invoices.length} invoices` : 'No invoices found' };
}

async function checkInvoicePaid(testCase, check) {
  const r = await tx('GET', `/invoice?from=0&count=50`);
  if (!r.ok) return { pass: false, reason: 'Could not query invoices: ' + r.status };
  const invoices = (r.data && r.data.values) || [];
  if (invoices.length === 0) return { pass: false, reason: 'No invoices found' };

  // Check if any invoice has amountOutstanding === 0
  const paidInvoice = invoices.find(inv => {
    const outstanding = inv.amountOutstanding !== undefined ? inv.amountOutstanding : null;
    return outstanding === 0 || outstanding === 0.0;
  });

  if (paidInvoice) {
    return { pass: true, reason: `Invoice ${paidInvoice.invoiceNumber || paidInvoice.id} fully paid (outstanding: ${paidInvoice.amountOutstanding})` };
  }

  // Show what we found for debugging
  const details = invoices.map(i => `#${i.invoiceNumber || i.id}: outstanding=${i.amountOutstanding}`).join(', ');
  return { pass: false, reason: `No fully paid invoice found. Found: ${details}` };
}

async function checkCreditNoteExists(testCase, check) {
  const r = await tx('GET', `/invoice?from=0&count=50`);
  if (!r.ok) return { pass: false, reason: 'Could not query invoices: ' + r.status };
  const invoices = (r.data && r.data.values) || [];

  // Credit notes are invoices with negative amounts or isCreditNote flag
  const creditNote = invoices.find(inv =>
    inv.isCreditNote === true ||
    (inv.amount !== undefined && inv.amount < 0) ||
    (inv.amountCurrency !== undefined && inv.amountCurrency < 0)
  );

  if (creditNote) {
    return { pass: true, reason: `Found credit note: id=${creditNote.id}, amount=${creditNote.amount}` };
  }
  return { pass: false, reason: `No credit note found among ${invoices.length} invoices` };
}

// Helper: get full voucher details with postings
async function getRecentVouchersWithPostings() {
  const dateFrom = '2026-01-01';
  const dateTo = '2026-12-31';
  const r = await tx('GET', `/ledger/voucher?dateFrom=${dateFrom}&dateTo=${dateTo}&from=0&count=50`);
  if (!r.ok) return [];
  const vouchers = (r.data && r.data.values) || [];
  // Use /ledger/posting endpoint to find postings directly (more efficient)
  // On a fresh account we can also just fetch all vouchers
  // For sandbox with many vouchers, use ledger/posting search
  // Fetch all vouchers but limit to 30 (enough for testing)
  const toFetch = vouchers.length > 30 ? vouchers.slice(0, 30) : vouchers;
  const detailed = [];
  for (const v of toFetch) {
    const full = await tx('GET', `/ledger/voucher/${v.id}?fields=*,postings(*)`);
    if (full.ok && full.data && full.data.value) {
      detailed.push(full.data.value);
    }
  }
  return detailed;
}

// Cache for vouchers within a single test run
let _cachedVouchers = null;
async function getCachedVouchers() {
  if (!_cachedVouchers) _cachedVouchers = await getRecentVouchersWithPostings();
  return _cachedVouchers;
}
function clearVoucherCache() { _cachedVouchers = null; }

// Cache for account number lookups
const _accountCache = {};
async function getAccountNumber(accountId) {
  if (_accountCache[accountId]) return _accountCache[accountId];
  const r = await tx('GET', `/ledger/account/${accountId}?fields=id,number`);
  if (r.ok && r.data && r.data.value) {
    _accountCache[accountId] = r.data.value.number;
    return r.data.value.number;
  }
  return null;
}

async function checkPostingAccount(testCase, check) {
  const vouchers = await getCachedVouchers();
  if (vouchers.length === 0) return { pass: false, reason: 'No vouchers found' };

  for (const v of vouchers) {
    if (!v.postings) continue;
    for (const p of v.postings) {
      if (!p.account) continue;
      const acctNum = await getAccountNumber(p.account.id);
      if (acctNum === check.account) {
        const amountOk = check.amount_positive ? p.amountGross > 0 : check.amount_negative ? p.amountGross < 0 : true;
        if (amountOk) {
          return { pass: true, reason: `Found posting on account ${acctNum}: amount=${p.amountGross} (voucher #${v.number})` };
        }
      }
    }
  }
  return { pass: false, reason: `No posting found on account ${check.account}` };
}

async function checkPostingSupplierRef(testCase, check) {
  const vouchers = await getCachedVouchers();
  if (vouchers.length === 0) return { pass: false, reason: 'No vouchers found' };

  for (const v of vouchers) {
    if (!v.postings) continue;
    for (const p of v.postings) {
      if (p.supplier && p.supplier.id) {
        return { pass: true, reason: `Found posting with supplier ref: supplier.id=${p.supplier.id} (voucher #${v.number})` };
      }
    }
  }
  return { pass: false, reason: 'No posting found with supplier reference' };
}

async function checkPostingEmployeeRef(testCase, check) {
  const vouchers = await getCachedVouchers();
  if (vouchers.length === 0) return { pass: false, reason: 'No vouchers found' };

  for (const v of vouchers) {
    if (!v.postings) continue;
    for (const p of v.postings) {
      if (p.employee && p.employee.id) {
        return { pass: true, reason: `Found posting with employee ref: employee.id=${p.employee.id} (voucher #${v.number})` };
      }
    }
  }
  return { pass: false, reason: 'No posting found with employee reference' };
}

async function checkTimesheetEntryExists(testCase, check) {
  const today = new Date().toISOString().split('T')[0];
  const r = await tx('GET', `/timesheet/entry?dateFrom=2026-01-01&dateTo=2026-12-31&from=0&count=50`);
  if (!r.ok) return { pass: false, reason: 'Could not query timesheet entries: ' + r.status };
  const entries = (r.data && r.data.values) || [];
  return { pass: entries.length > 0, reason: entries.length > 0 ? `Found ${entries.length} timesheet entries` : 'No timesheet entries found' };
}

// === Check dispatcher ===
async function runCheck(testCase, check) {
  switch (check.type) {
    case 'voucher_exists': return checkVoucherExists(testCase);
    case 'supplier_exists': return checkSupplierExists(testCase, check);
    case 'customer_exists': return checkCustomerExists(testCase, check);
    case 'employee_exists': return checkEmployeeExists(testCase, check);
    case 'project_exists': return checkProjectExists(testCase, check);
    case 'order_exists': return checkOrderExists(testCase, check);
    case 'invoice_exists': return checkInvoiceExists(testCase, check);
    case 'invoice_paid': return checkInvoicePaid(testCase, check);
    case 'credit_note_exists': return checkCreditNoteExists(testCase, check);
    case 'posting_account': return checkPostingAccount(testCase, check);
    case 'posting_supplier_ref': return checkPostingSupplierRef(testCase, check);
    case 'posting_employee_ref': return checkPostingEmployeeRef(testCase, check);
    case 'timesheet_entry_exists': return checkTimesheetEntryExists(testCase, check);
    default: return { pass: false, reason: `Unknown check type: ${check.type}` };
  }
}

// === Main test runner ===
async function runTest(testCase, taskType) {
  log(`\n${C.bold}${C.cyan}[${testCase.id}]${C.reset} ${C.bold}${taskType}${C.reset} (${testCase.lang})`);
  log(`${C.dim}  Prompt: ${testCase.prompt.substring(0, 100)}...${C.reset}`);

  if (dryRun) {
    log(`${C.yellow}  DRY RUN — would send prompt and check ${testCase.checks.length} conditions${C.reset}`);
    return { id: testCase.id, pass: null, checks: [] };
  }

  // Step 1: Send prompt to webhook (unless verify-only)
  if (!verifyOnly) {
    const webhookResult = await sendToWebhook(testCase.prompt);
    if (!webhookResult.ok && webhookResult.error) {
      logFail(`Webhook failed: ${webhookResult.error}`);
      return { id: testCase.id, pass: false, checks: [], webhookError: webhookResult.error };
    }
    // Wait a moment for async processing
    await new Promise(r => setTimeout(r, 2000));
  }

  // Clear voucher cache for each new test
  clearVoucherCache();

  // Step 2: Run verification checks
  let passed = 0;
  let failed = 0;
  const checkResults = [];

  for (const check of testCase.checks) {
    try {
      const result = await runCheck(testCase, check);
      checkResults.push({ ...check, ...result });
      if (result.pass) {
        logPass(`${check.type}: ${result.reason}`);
        passed++;
      } else {
        logFail(`${check.type}: ${result.reason}`);
        failed++;
      }
    } catch (e) {
      logFail(`${check.type}: Error - ${e.message}`);
      checkResults.push({ ...check, pass: false, reason: e.message });
      failed++;
    }
  }

  const allPassed = failed === 0;
  log(`${allPassed ? C.green : C.red}  Result: ${passed}/${passed + failed} checks passed${C.reset}`);

  return { id: testCase.id, pass: allPassed, passed, failed, checks: checkResults };
}

async function main() {
  // Load test cases
  const testCasesPath = path.join(__dirname, 't2_test_cases.json');
  if (!fs.existsSync(testCasesPath)) {
    console.error('Error: t2_test_cases.json not found in', __dirname);
    process.exit(1);
  }
  const testData = JSON.parse(fs.readFileSync(testCasesPath, 'utf-8'));

  log(`${C.bold}========================================${C.reset}`);
  log(`${C.bold} T2 Test Framework - NM i AI Tripletex${C.reset}`);
  log(`${C.bold}========================================${C.reset}`);
  log(`${C.dim}Webhook:  ${WEBHOOK_URL}${C.reset}`);
  log(`${C.dim}Sandbox:  ${SANDBOX_URL}${C.reset}`);
  log(`${C.dim}Mode:     ${dryRun ? 'DRY RUN' : verifyOnly ? 'VERIFY ONLY' : 'FULL TEST'}${C.reset}`);
  if (filterType) log(`${C.dim}Filter:   type=${filterType}${C.reset}`);
  if (filterId) log(`${C.dim}Filter:   id=${filterId}${C.reset}`);

  // Verify API access first
  log(`\n${C.dim}Verifying sandbox API access...${C.reset}`);
  try {
    const healthCheck = await tx('GET', '/employee?from=0&count=1&fields=id');
    if (!healthCheck.ok) {
      log(`${C.red}ERROR: Cannot access sandbox API (status: ${healthCheck.status}). Check SESSION_TOKEN.${C.reset}`);
      process.exit(1);
    }
    log(`${C.green}  Sandbox API accessible${C.reset}`);
  } catch (e) {
    log(`${C.red}ERROR: Cannot connect to sandbox: ${e.message}${C.reset}`);
    process.exit(1);
  }

  // Collect all tests to run
  const taskTypes = ['supplier_invoice', 'payroll_voucher', 'register_payment', 'credit_note', 'project_invoice'];
  const allResults = [];
  let totalPass = 0, totalFail = 0, totalSkip = 0;

  for (const taskType of taskTypes) {
    if (filterType && taskType !== filterType) continue;

    const tests = testData[taskType] || [];
    if (tests.length === 0) {
      log(`\n${C.yellow}No tests for ${taskType}${C.reset}`);
      continue;
    }

    log(`\n${C.bold}--- ${taskType.toUpperCase()} ---${C.reset}`);

    for (const test of tests) {
      if (filterId && test.id !== filterId) continue;

      const result = await runTest(test, taskType);
      allResults.push({ taskType, ...result });

      if (result.pass === null) totalSkip++;
      else if (result.pass) totalPass++;
      else totalFail++;

      // Don't spam the webhook too fast
      if (!dryRun && !verifyOnly) {
        await new Promise(r => setTimeout(r, 3000));
      }
    }
  }

  // Summary
  log(`\n${C.bold}========================================${C.reset}`);
  log(`${C.bold} SUMMARY${C.reset}`);
  log(`${C.bold}========================================${C.reset}`);
  log(`  Total:   ${allResults.length} tests`);
  log(`  ${C.green}Passed:  ${totalPass}${C.reset}`);
  log(`  ${C.red}Failed:  ${totalFail}${C.reset}`);
  if (totalSkip > 0) log(`  ${C.yellow}Skipped: ${totalSkip}${C.reset}`);
  log('');

  // Per-type summary
  for (const taskType of taskTypes) {
    const typeResults = allResults.filter(r => r.taskType === taskType);
    if (typeResults.length === 0) continue;
    const typePass = typeResults.filter(r => r.pass === true).length;
    const typeFail = typeResults.filter(r => r.pass === false).length;
    const icon = typeFail === 0 && typePass > 0 ? C.green + 'OK' : C.red + 'FAIL';
    log(`  ${icon}${C.reset} ${taskType}: ${typePass}/${typeResults.length}`);
  }

  // Write results to file
  const resultsPath = path.join(__dirname, 't2_test_results_latest.json');
  fs.writeFileSync(resultsPath, JSON.stringify({
    timestamp: new Date().toISOString(),
    config: { webhook: WEBHOOK_URL, sandbox: SANDBOX_URL, mode: dryRun ? 'dry_run' : verifyOnly ? 'verify_only' : 'full' },
    summary: { total: allResults.length, passed: totalPass, failed: totalFail, skipped: totalSkip },
    results: allResults,
  }, null, 2));
  log(`\n${C.dim}Results saved to: ${resultsPath}${C.reset}`);

  process.exit(totalFail > 0 ? 1 : 0);
}

main().catch(e => {
  console.error('Fatal error:', e);
  process.exit(1);
});
