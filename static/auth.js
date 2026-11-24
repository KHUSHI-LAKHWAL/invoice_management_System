
const $ = (id) => document.getElementById(id);
let csrf = '';

async function init() {
  const res = await fetch('/api/me');
  const data = await res.json();
  if (data.authenticated) { window.location.href = '/'; return; }
  csrf = data.csrf;
}

async function post(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: JSON.stringify(body)
  });
  let data = {};
  try { data = await res.json(); } catch (e) {}
  if (!res.ok) throw new Error(data.error || 'Something went wrong.');
  return data;
}

function showError(msg) {
  const box = $('auth-error');
  box.textContent = msg;
  box.classList.remove('hidden');
}
function clearError() { $('auth-error').classList.add('hidden'); }


function switchTab(which) {
  clearError();
  $('tab-login').classList.toggle('active', which === 'login');
  $('tab-register').classList.toggle('active', which === 'register');
  $('login-form').classList.toggle('hidden', which !== 'login');
  $('register-form').classList.toggle('hidden', which !== 'register');
}
$('tab-login').addEventListener('click', () => switchTab('login'));
$('tab-register').addEventListener('click', () => switchTab('register'));


document.querySelectorAll('.pw-toggle').forEach((btn) => {
  btn.addEventListener('click', () => {
    const input = $(btn.dataset.target);
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    btn.textContent = show ? 'Hide' : 'Show';
  });
});

$('r-password').addEventListener('input', (e) => {
  const p = e.target.value;
  let score = 0;
  if (p.length >= 8) score++;
  if (/[a-z]/.test(p) && /[A-Z]/.test(p)) score++;
  if (/\d/.test(p)) score++;
  if (/[^A-Za-z0-9]/.test(p) || p.length >= 12) score++;

  const colors = ['#ef4444', '#ef4444', '#f59e0b', '#22c55e', '#22c55e'];
  const labels = ['Too weak', 'Weak', 'Okay', 'Good', 'Strong'];
  $('strength-bar').style.width = (p ? score * 25 : 0) + '%';
  $('strength-bar').style.background = colors[score];
  $('strength-text').textContent = p ? labels[score] : 'Use 8+ characters with upper, lower and a number.';
});


async function doLogin(email, password) {
  await post('/api/login', { email, password });
  window.location.href = '/';
}

$('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  clearError();
  const btn = $('login-btn');
  btn.disabled = true; btn.textContent = 'Please wait...';
  try {
    await doLogin($('l-email').value.trim(), $('l-password').value);
  } catch (err) {
    showError(err.message);
    btn.disabled = false; btn.textContent = 'Login';
  }
});

$('register-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  clearError();

  const password = $('r-password').value;
  if (password !== $('r-confirm').value) { showError('Dono passwords same nahi hain.'); return; }

  const btn = $('register-btn');
  btn.disabled = true; btn.textContent = 'Please wait...';
  try {
    const email = $('r-email').value.trim();
    await post('/api/register', { full_name: $('r-name').value.trim(), email, password });
    await doLogin(email, password);   // account banne ke baad seedha login
  } catch (err) {
    showError(err.message);
    btn.disabled = false; btn.textContent = 'Create account';
  }
});

init();