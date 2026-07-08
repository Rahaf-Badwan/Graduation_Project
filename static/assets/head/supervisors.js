/* assets/head/supervisors.js */

let allSupervisors  = [];   // active supervisors
let pendingSupId    = null; // user_id being activated via modal

/* ════════════════════════════════════════════
   BOOTSTRAP
════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', loadAll);

function loadAll() {
  loadSupervisors();
}

/* ════════════════════════════════════════════
   1. LOAD  –  GET /api/head/supervisors
════════════════════════════════════════════ */
async function loadSupervisors() {
  try {
    const res  = await fetch('/head/supervisors-api');
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to load');

    allSupervisors = data.supervisors || [];

    renderStats(data.stats);
    renderActiveList(allSupervisors.filter(s => s.is_active));


  } catch (err) {
    document.getElementById('supervisors-list').innerHTML =
      `<div style="color:var(--red,#dc2626);font-size:13px;padding:12px 0">${err.message}</div>`;
  }
}

/* ════════════════════════════════════════════
   2. RENDER  –  Stats
════════════════════════════════════════════ */
function renderStats(stats) {
  if (!stats) return;

  const total    = stats.total    ?? 0;
  const active   = stats.active   ?? 0;
  const pending  = stats.pending  ?? 0;
  const projects = stats.projects ?? 0;

  document.getElementById('stat-total').textContent    = total;
  document.getElementById('stat-active').textContent   = active;
  document.getElementById('stat-pending').textContent  = pending;
  document.getElementById('stat-projects').textContent = projects;
  document.getElementById('active-count-badge').textContent = active;

  const avg = active > 0 ? (projects / active).toFixed(1) : '0';
  document.getElementById('distribution-banner').textContent =
    `✓ ${active} active supervisor${active !== 1 ? 's' : ''} — ` +
    `${projects} total project${projects !== 1 ? 's' : ''} — ` +
    `avg ${avg} projects/supervisor`;
}

/* ════════════════════════════════════════════
   3. RENDER  –  Active supervisors list (LEFT)
════════════════════════════════════════════ */
function renderActiveList(list) {
  const el = document.getElementById('supervisors-list');

  if (!list.length) {
    el.innerHTML =
      `<div style="color:var(--color-text-secondary);font-size:13px;padding:16px 0">
         No active supervisors yet.
       </div>`;
    return;
  }

  el.innerHTML = list.map(s => {
    const initials = (s.full_name || '?')
      .split(' ').slice(0,2).map(w => w[0]).join('').toUpperCase();

    return `
      <div style="display:flex;align-items:center;gap:10px;padding:10px 12px;
                  background:var(--color-background-secondary);
                  border:0.5px solid var(--color-border-tertiary);
                  border-radius:var(--rm)">

        <!-- Avatar -->
        <div style="width:36px;height:36px;border-radius:8px;flex-shrink:0;
                    background:var(--teal-light);color:var(--teal);
                    display:flex;align-items:center;justify-content:center;
                    font-weight:700;font-size:13px">${initials}</div>

        <!-- Info -->
        <div style="flex:1;min-width:0">
          <div style="font-weight:600;font-size:13px;
                      white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
            ${esc(s.full_name)}
          </div>
          <div style="font-size:11px;color:var(--color-text-secondary);margin-top:1px">
            ${esc(s.specialization || 'No specialization')}
          </div>
        </div>

        <!-- Project count -->
        <div style="text-align:right;flex-shrink:0">
          <div style="font-weight:700;font-size:16px;color:var(--blue);line-height:1">
            ${s.project_count ?? 0}
          </div>
          <div style="font-size:10px;color:var(--color-text-secondary)">
            project${s.project_count !== 1 ? 's' : ''}
          </div>
        </div>

        <!-- Active dot -->
        <div style="width:8px;height:8px;border-radius:50%;flex-shrink:0;
                    background:var(--teal);
                    box-shadow:0 0 5px var(--teal)"></div>
      </div>`;
  }).join('');
}



/* ════════════════════════════════════════════
   5. SEARCH  (live filter)
════════════════════════════════════════════ */
function filterSupervisors(q) {
  q = q.toLowerCase().trim();
  const filtered = q
    ? allSupervisors.filter(s => s.is_active && (
        (s.full_name      || '').toLowerCase().includes(q) ||
        (s.specialization || '').toLowerCase().includes(q)
      ))
    : allSupervisors.filter(s => s.is_active);

  renderActiveList(filtered);
}

/* ════════════════════════════════════════════
   6. ADD SUPERVISOR
════════════════════════════════════════════ */
async function addSupervisor() {
  const btn   = document.getElementById('add-btn');
  const errEl = document.getElementById('add-error');
  errEl.textContent = '';
  errEl.style.color = 'var(--red,#dc2626)';

  const name  = document.getElementById('add-name').value.trim();
  const uid   = document.getElementById('add-uid').value.trim();
  const spec  = (typeof getSpecValue === 'function'
    ? getSpecValue()
    : document.getElementById('add-spec').value
  ).trim();
  const specCustom = typeof getSpecCustom === 'function' ? getSpecCustom() : '';

  if (!name || !uid) {
    errEl.textContent = 'Full name and university ID are required.'; return;
  }
  if (!/^\d{4}$/.test(uid)) {
    errEl.textContent = 'University ID must be exactly 4 digits.'; return;
  }

  btn.disabled    = true;
  btn.textContent = 'Adding…';

  try {
    const res  = await fetch('/head/supervisors-api/add', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        full_name: name,
        university_id: uid,
        specialization: spec,
        spec_custom: specCustom
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed');

    if (data.already_exists) {
      errEl.style.color = 'var(--amber,#d97706)';
      errEl.textContent = data.message || 'This supervisor already exists.';
      showToast(data.message || 'This supervisor already exists.', 'info');
      return;
    }

    showToast('Supervisor added! They can activate at /activate', 'success');
    ['add-name','add-uid','add-spec','add-spec-other'].forEach(id =>
      document.getElementById(id).value = ''
    );
    if (typeof toggleOtherSpec === 'function') toggleOtherSpec('');
    if (typeof updateSpecSelectStyle === 'function') updateSpecSelectStyle();
    loadSupervisors();

  } catch (err) {
    errEl.textContent = err.message;
  } finally {
    btn.disabled    = false;
    btn.textContent = 'Add Supervisor ↗';
  }
}

/* ════════════════════════════════════════════
   7. ACTIVATE MODAL  (head activates on behalf)
════════════════════════════════════════════ */
function openActivateModal(userId, name) {
  pendingSupId = userId;
  document.getElementById('activate-modal-name').textContent  = name;
  document.getElementById('activate-modal-error').textContent = '';
  document.getElementById('activate-password').value = '';
  document.getElementById('activate-confirm').value  = '';

  const modal = document.getElementById('supervisor-activate-modal');
  modal.style.display = 'flex';
}

function closeActivateModal() {
  document.getElementById('supervisor-activate-modal').style.display = 'none';
  pendingSupId = null;
}

async function submitActivateSupervisor() {
  const errEl   = document.getElementById('activate-modal-error');
  errEl.textContent = '';

  const pass    = document.getElementById('activate-password').value;
  const confirm = document.getElementById('activate-confirm').value;

  if (!pass || !confirm) {
    errEl.textContent = 'Please fill in all fields.'; return;
  }
  if (pass.length < 8) {
    errEl.textContent = 'Password must be at least 8 characters.'; return;
  }
  if (pass !== confirm) {
    errEl.textContent = 'Passwords do not match.'; return;
  }

  try {
    const res  = await fetch('/api/activate/supervisor/set-password', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        user_id: pendingSupId,
        password: pass,
        confirm_password: confirm
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed');

    closeActivateModal();
    showToast('Supervisor activated successfully!', 'success');
    loadSupervisors();

  } catch (err) {
    errEl.textContent = err.message;
  }
}

/* ════════════════════════════════════════════
   HELPERS
════════════════════════════════════════════ */
function esc(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

let _toastTimer;
function showToast(msg, type = 'info') {
  let t = document.getElementById('_toast');
  if (!t) {
    t = document.createElement('div');
    t.id = '_toast';
    Object.assign(t.style, {
      position:'fixed', bottom:'24px', right:'24px',
      padding:'10px 18px', borderRadius:'8px',
      fontSize:'13px', fontWeight:'500',
      opacity:'0', transform:'translateY(8px)',
      transition:'opacity .25s, transform .25s',
      zIndex:'9999', maxWidth:'300px'
    });
    document.body.appendChild(t);
  }

  const colors = {
    success: { bg:'var(--teal)',  color:'#fff' },
    error:   { bg:'#dc2626',     color:'#fff' },
    info:    { bg:'var(--blue)',  color:'#fff' },
  };
  const c = colors[type] || colors.info;
  t.style.background = c.bg;
  t.style.color      = c.color;
  t.textContent      = msg;

  requestAnimationFrame(() => {
    t.style.opacity   = '1';
    t.style.transform = 'translateY(0)';
  });

  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => {
    t.style.opacity   = '0';
    t.style.transform = 'translateY(8px)';
  }, 3500);
}
