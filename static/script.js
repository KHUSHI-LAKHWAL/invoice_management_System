
const state = {
  customers: [],
  invoices: [],
  history: [],          
  predictInvoiceId: null 
};
const charts = {};
let csrfToken = null;


const $ = (id) => document.getElementById(id);

const money = (n) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n || 0);

const fmtDate = (s) =>
  s ? new Date(s + 'T00:00:00').toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '-';

const esc = (v) =>
  String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function localDate(d) {
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function statusBadge(status) {
  return `<span class="badge ${status.toLowerCase()}">${esc(status)}</span>`;
}

function riskClass(level) {
  if (level === 'Low Risk') return 'low';
  if (level === 'Medium Risk') return 'medium';
  return 'high';
}

function riskBadge(level, large = false) {
  return `<span class="badge ${riskClass(level)} ${large ? 'lg' : ''}">${esc(level)}</span>`;
}


function toast(message, type = 'success') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  $('toast-container').appendChild(el);
  setTimeout(() => el.remove(), 3500);
}
async function api(url, method = 'GET', body = null) {
  const options = {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': csrfToken || ''
    }
  };
  if (body) options.body = JSON.stringify(body);

  let res;
  try {
    res = await fetch(url, options);
  } catch (e) {
    throw new Error('Cannot connect to the server. Is Flask running?');
  }

  if (res.status === 401) {
    window.location.href = '/login';
    throw new Error('Session expired. Please login again.');
  }

  let data = {};
  try { data = await res.json(); } catch (e) { /* empty response */ }

  if (!res.ok) throw new Error(data.error || 'Something went wrong.');
  return data;
}

async function withLoading(btn, fn) {
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Please wait...';
  try {
    await fn();
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
}


Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.color = '#64748b';

function drawChart(key, canvasId, config, isEmpty) {
  const canvas = $(canvasId);
  const emptyMsg = canvas.nextElementSibling;
  if (charts[key]) { charts[key].destroy(); charts[key] = null; }

  canvas.classList.toggle('hidden', isEmpty);
  emptyMsg.classList.toggle('hidden', !isEmpty);
  if (isEmpty) return;

  config.options = Object.assign({ responsive: true, maintainAspectRatio: false }, config.options);
  charts[key] = new Chart(canvas, config);
}


const titles = {
  dashboard: 'Dashboard',
  customers: 'Customers',
  invoices: 'Invoices',
  predictions: 'AI Predictions',
  reports: 'Reports'
};

const loaders = {
  dashboard: loadDashboard,
  customers: loadCustomers,
  invoices: loadInvoices,
  predictions: loadPredictionPage,
  reports: loadReports
};

function showPage(name) {
  document.querySelectorAll('.page').forEach((p) => p.classList.toggle('active', p.id === name));
  document.querySelectorAll('.nav-link').forEach((a) => a.classList.toggle('active', a.dataset.page === name));
  $('page-title').textContent = titles[name];
  closeSidebar();
  loaders[name]().catch((e) => toast(e.message, 'error'));
}

function openSidebar() { $('sidebar').classList.add('open'); $('overlay').classList.add('show'); }
function closeSidebar() { $('sidebar').classList.remove('open'); $('overlay').classList.remove('show'); }


async function fetchCustomers() { state.customers = await api('/api/customers'); }
async function fetchInvoices() { state.invoices = await api('/api/invoices'); }


async function loadDashboard() {
  const [stats] = await Promise.all([api('/api/dashboard'), fetchInvoices()]);

  $('stat-total').textContent = stats.total_invoices;
  $('stat-paid').textContent = stats.paid_invoices;
  $('stat-pending').textContent = stats.pending_invoices;
  $('stat-overdue').textContent = stats.overdue_invoices;
  $('stat-revenue').textContent = money(stats.total_paid_revenue);

  
  const r = stats.risk_overview;
  const values = [r['Low Risk'], r['Medium Risk'], r['High Risk']];
  const total = values.reduce((a, b) => a + b, 0);
  drawChart('risk', 'riskChart', {
    type: 'doughnut',
    data: {
      labels: ['Low Risk', 'Medium Risk', 'High Risk'],
      datasets: [{ data: values, backgroundColor: ['#16a34a', '#f59e0b', '#dc2626'], borderWidth: 0 }]
    },
    options: { cutout: '65%', plugins: { legend: { position: 'bottom' } } }
  }, total === 0);

  const rows = state.invoices.slice(0, 5).map((i) => `
    <tr>
      <td><strong>${esc(i.invoice_number)}</strong></td>
      <td>${esc(i.customer_name)}</td>
      <td>${money(i.invoice_amount)}</td>
      <td>${statusBadge(i.status)}</td>
    </tr>`).join('');
  $('recent-body').innerHTML = rows || '<tr><td colspan="4" class="empty">No invoices yet.</td></tr>';
}


async function loadCustomers() {
  await Promise.all([fetchCustomers(), fetchInvoices()]);
  renderCustomers();
}

function renderCustomers() {
  const q = $('customer-search').value.trim().toLowerCase();
  const list = state.customers.filter(
    (c) => c.customer_name.toLowerCase().includes(q) || c.email.toLowerCase().includes(q)
  );

  const rows = list.map((c) => {
    const count = state.invoices.filter((i) => i.customer_id === c.customer_id).length;
    return `
      <tr>
        <td>#${c.customer_id}</td>
        <td><strong>${esc(c.customer_name)}</strong></td>
        <td>${esc(c.email)}</td>
        <td>${esc(c.phone)}</td>
        <td>${count}</td>
        <td><button class="btn-sm" data-action="view-invoices" data-name="${esc(c.customer_name)}">View invoices</button></td>
      </tr>`;
  }).join('');

  $('customers-body').innerHTML = rows || '<tr><td colspan="6" class="empty">No customers found.</td></tr>';
}

async function addCustomer() {
  const name = $('c-name').value.trim();
  const email = $('c-email').value.trim();
  const phone = $('c-phone').value.trim();

  if (!name || !email || !phone) throw new Error('Please fill name, email and phone.');

  await api('/api/customers', 'POST', { customer_name: name, email, phone });
  toast('Customer added successfully.');
  $('c-name').value = '';
  $('c-email').value = '';
  $('c-phone').value = '';
  await loadCustomers();
}


async function loadInvoices() {
  await Promise.all([fetchCustomers(), fetchInvoices()]);
  fillCustomerSelect();
  renderInvoices();

  if (!$('i-issue').value) $('i-issue').value = localDate(new Date());
  if (!$('i-due').value) {
    const due = new Date();
    due.setDate(due.getDate() + 30);
    $('i-due').value = localDate(due);
  }
  if (!$('i-number').value) {
    $('i-number').value = 'INV-' + String(state.invoices.length + 1).padStart(3, '0');
  }
}

function fillCustomerSelect() {
  const select = $('i-customer');
  if (state.customers.length === 0) {
    select.innerHTML = '<option value="">Add a customer first</option>';
    return;
  }
  const current = select.value;
  select.innerHTML = state.customers
    .map((c) => `<option value="${c.customer_id}">${esc(c.customer_name)}</option>`)
    .join('');
  if (current) select.value = current;
}

function renderInvoices() {
  const q = $('invoice-search').value.trim().toLowerCase();
  const filter = $('invoice-filter').value;

  const list = state.invoices.filter((i) => {
    const matchText =
      i.invoice_number.toLowerCase().includes(q) || i.customer_name.toLowerCase().includes(q);
    const matchStatus = filter === 'All' || i.status === filter;
    return matchText && matchStatus;
  });

  const rows = list.map((i) => {
    let actions;
    if (i.status === 'Paid') {
      actions = `<button class="btn-sm" data-action="mark-pending" data-id="${i.invoice_id}">Undo paid</button>`;
    } else {
      actions = `
        <button class="btn-sm success" data-action="mark-paid" data-id="${i.invoice_id}">Mark paid</button>
        <button class="btn-sm ai" data-action="predict" data-id="${i.invoice_id}">Predict</button>`;
    }
    return `
      <tr>
        <td><strong>${esc(i.invoice_number)}</strong></td>
        <td>${esc(i.customer_name)}</td>
        <td>${money(i.invoice_amount)}</td>
        <td>${fmtDate(i.issue_date)}</td>
        <td>${fmtDate(i.due_date)}</td>
        <td>${statusBadge(i.status)}</td>
        <td>${actions}</td>
      </tr>`;
  }).join('');

  $('invoices-body').innerHTML = rows || '<tr><td colspan="7" class="empty">No invoices found.</td></tr>';
}

async function createInvoice() {
  const payload = {
    invoice_number: $('i-number').value.trim(),
    customer_id: $('i-customer').value,
    invoice_amount: $('i-amount').value,
    issue_date: $('i-issue').value,
    due_date: $('i-due').value
  };

  if (!payload.customer_id) throw new Error('Please add a customer first.');

  await api('/api/invoices', 'POST', payload);
  toast('Invoice created successfully.');
  $('i-amount').value = '';
  $('i-number').value = '';
  await loadInvoices();
}

async function setStatus(id, status) {
  await api(`/api/invoices/${id}/status`, 'PUT', { payment_status: status });
  toast(status === 'Paid' ? 'Invoice marked as paid.' : 'Invoice moved back to pending.');
  await loadInvoices();
}


async function loadPredictionPage() {
  await fetchInvoices();
  const unpaid = state.invoices.filter((i) => i.status !== 'Paid');
  const select = $('p-invoice');

  if (unpaid.length === 0) {
    select.innerHTML = '<option value="">No unpaid invoices available</option>';
  } else {
    select.innerHTML = unpaid
      .map((i) => `<option value="${i.invoice_id}">${esc(i.invoice_number)} | ${esc(i.customer_name)} | ${money(i.invoice_amount)}</option>`)
      .join('');
  }

  renderHistory();

  if (state.predictInvoiceId) {
    select.value = String(state.predictInvoiceId);
    state.predictInvoiceId = null;
    await runPrediction();
  }
}

async function runPrediction() {
  const id = $('p-invoice').value;
  if (!id) throw new Error('Please select an invoice.');

  const result = await api('/api/predict', 'POST', { invoice_id: Number(id) });
  const inv = state.invoices.find((i) => i.invoice_id === Number(id));

  state.history.unshift({
    invoice: inv ? inv.invoice_number : '#' + id,
    customer: inv ? inv.customer_name : '-',
    probability: result.late_payment_probability,
    risk: result.risk_level
  });

  renderPrediction(result, inv);
  renderHistory();
  toast('Prediction generated.');
}

function renderPrediction(r, inv) {
  const pct = Math.round(r.late_payment_probability * 100);
  const cls = riskClass(r.risk_level);
  const f = r.features_used;

  $('prediction-result').innerHTML = `
    <div class="result-card">
      <div class="result-top">
        <div>
          <h4>${inv ? esc(inv.invoice_number) + ' | ' + esc(inv.customer_name) : 'Invoice #' + r.invoice_id}</h4>
          <span class="muted">Probability of late payment</span>
          <div class="big-prob">${pct}%</div>
        </div>
        ${riskBadge(r.risk_level, true)}
      </div>

      <div class="bar"><div class="bar-fill ${cls}" style="width:${pct}%"></div></div>
      <div class="bar-scale"><span>0%</span><span>Low &lt; 35%</span><span>High &gt; 65%</span><span>100%</span></div>

      <p class="result-title">Inputs used by the model</p>
      <div class="features">
        <div class="feature"><span>Invoice amount</span><strong>${money(f.invoice_amount)}</strong></div>
        <div class="feature"><span>Previous late payments</span><strong>${f.prev_late_count}</strong></div>
        <div class="feature"><span>Previous on-time payments</span><strong>${f.prev_ontime_count}</strong></div>
        <div class="feature"><span>Avg. delay (days)</span><strong>${f.avg_delay_days}</strong></div>
        <div class="feature"><span>Payment terms (days)</span><strong>${f.payment_terms}</strong></div>
        <div class="feature"><span>Days until due</span><strong>${f.days_until_due}</strong></div>
      </div>
    </div>`;
  $('prediction-result').classList.remove('hidden');
}

function renderHistory() {
  const rows = state.history.map((h) => `
    <tr>
      <td><strong>${esc(h.invoice)}</strong></td>
      <td>${esc(h.customer)}</td>
      <td>${Math.round(h.probability * 100)}%</td>
      <td>${riskBadge(h.risk)}</td>
    </tr>`).join('');
  $('history-body').innerHTML = rows || '<tr><td colspan="4" class="empty">No predictions run yet.</td></tr>';
}


async function loadReports() {
  const data = await api('/api/reports');

  $('r-high').textContent = data.high_risk_count;
  $('r-overdue').textContent = money(data.overdue_amount);

  const s = data.status_count;
  const statusValues = [s.Paid, s.Pending, s.Overdue];
  drawChart('status', 'statusChart', {
    type: 'doughnut',
    data: {
      labels: ['Paid', 'Pending', 'Overdue'],
      datasets: [{ data: statusValues, backgroundColor: ['#16a34a', '#f59e0b', '#dc2626'], borderWidth: 0 }]
    },
    options: { cutout: '60%', plugins: { legend: { position: 'bottom' } } }
  }, statusValues.every((v) => v === 0));


  const months = Object.keys(data.payment_trend);
  drawChart('trend', 'trendChart', {
    type: 'line',
    data: {
      labels: months,
      datasets: [{
        label: 'Paid amount (₹)',
        data: Object.values(data.payment_trend),
        borderColor: '#4f46e5',
        backgroundColor: 'rgba(79,70,229,.12)',
        fill: true,
        tension: 0.35
      }]
    },
    options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
  }, months.length === 0);

  
  const names = Object.keys(data.customer_history);
  drawChart('history', 'historyChart', {
    type: 'bar',
    data: {
      labels: names,
      datasets: [
        { label: 'On time', data: names.map((n) => data.customer_history[n].on_time), backgroundColor: '#16a34a' },
        { label: 'Late', data: names.map((n) => data.customer_history[n].late), backgroundColor: '#dc2626' }
      ]
    },
    options: {
      plugins: { legend: { position: 'bottom' } },
      scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } } }
    }
  }, names.length === 0);
}


document.querySelectorAll('.nav-link').forEach((a) => {
  a.addEventListener('click', (e) => {
    e.preventDefault();
    showPage(a.dataset.page);
  });
});

$('menu-btn').addEventListener('click', openSidebar);
$('overlay').addEventListener('click', closeSidebar);

$('add-customer-btn').addEventListener('click', (e) => withLoading(e.target, addCustomer));
$('add-invoice-btn').addEventListener('click', (e) => withLoading(e.target, createInvoice));
$('predict-btn').addEventListener('click', (e) => withLoading(e.target, runPrediction));

$('customer-search').addEventListener('input', renderCustomers);
$('invoice-search').addEventListener('input', renderInvoices);
$('invoice-filter').addEventListener('change', renderInvoices);

$('customers-body').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-action="view-invoices"]');
  if (!btn) return;
  showPage('invoices');
  setTimeout(() => {
    $('invoice-search').value = btn.dataset.name;
    $('invoice-filter').value = 'All';
    renderInvoices();
  }, 150);
});

$('invoices-body').addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-action]');
  if (!btn) return;
  const id = Number(btn.dataset.id);

  try {
    if (btn.dataset.action === 'mark-paid') await setStatus(id, 'Paid');
    if (btn.dataset.action === 'mark-pending') await setStatus(id, 'Pending');
    if (btn.dataset.action === 'predict') {
      state.predictInvoiceId = id;
      showPage('predictions');
    }
  } catch (err) {
    toast(err.message, 'error');
  }
});


$('today-label').textContent = new Date().toLocaleDateString('en-IN', {
  weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
});
$('logout-btn').addEventListener('click', async () => {
  try { await api('/api/logout', 'POST'); } catch (e) {}
  window.location.href = '/login';
});

async function start() {
  const res = await fetch('/api/me');
  const me = await res.json();
  if (!me.authenticated) { window.location.href = '/login'; return; }
  csrfToken = me.csrf;
  $('user-name').textContent = me.name;
  $('user-avatar').textContent = me.name.charAt(0).toUpperCase();
  showPage('dashboard');
}
start();
