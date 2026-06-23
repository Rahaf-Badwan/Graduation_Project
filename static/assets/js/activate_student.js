/* ══════════════════════════════════════════════════════════════
   activate_student.js  —  Student + Supervisor activation flows
══════════════════════════════════════════════════════════════ */

/* ─────────────────────────────────────────────────────────────
   SHARED UTILITIES
───────────────────────────────────────────────────────────── */

function showFeedback(id, msg, type) {
  var el = document.getElementById(id);
  var styles = {
    success: { color:'var(--color-text-success)', background:'var(--color-background-success)', border:'var(--color-border-success)' },
    error:   { color:'var(--color-text-danger)',  background:'var(--color-background-danger)',  border:'var(--color-border-danger)'  },
    warn:    { color:'var(--color-text-warning)', background:'var(--color-background-warning)', border:'var(--color-border-warning)' }
  };
  var s = styles[type] || styles.warn;
  el.removeAttribute('style');
  el.style.display      = 'block';
  el.style.padding      = '10px 14px';
  el.style.borderRadius = '8px';
  el.style.fontSize     = '13px';
  el.style.marginTop    = '12px';
  el.style.lineHeight   = '1.5';
  el.style.color        = s.color;
  el.style.background   = s.background;
  el.style.border       = '0.5px solid ' + s.border;
  el.textContent        = msg;
  clearTimeout(el._timer);
  el._timer = setTimeout(function() { hideFeedback(id); }, 5000);
}

function hideFeedback(id) {
  var el = document.getElementById(id);
  if (el) el.style.display = 'none';
}

/* ── Role switcher ── */
function switchRole(role) {
  var isStudent = role === 'student';
  document.getElementById('student-card').style.display = isStudent ? '' : 'none';
  document.getElementById('sup-card').style.display     = isStudent ? 'none' : '';

  var tabS   = document.getElementById('tab-student');
  var tabSup = document.getElementById('tab-supervisor');
  tabS.classList.toggle('is-active', isStudent);
  tabSup.classList.toggle('is-active', !isStudent);
  tabS.style.background   = isStudent ? '#2d6a38' : 'transparent';
  tabS.style.color        = isStudent ? '#fff'    : 'var(--green)';
  tabS.style.border       = isStudent ? 'none'    : '0.5px solid #e5e7eb';
  tabSup.style.background = isStudent ? 'transparent' : '#2d6a38';
  tabSup.style.color      = isStudent ? 'var(--green)' : '#fff';
  tabSup.style.border     = isStudent ? '0.5px solid #e5e7eb' : 'none';
}

function activationColor(token, fallback) {
  var value = getComputedStyle(document.documentElement).getPropertyValue(token).trim();
  return value || fallback;
}

function clearActivationFields() {
  [
    'universityId',
    'password',
    'confirmPassword',
    'supervisor-id',
    'supervisor-email',
    'sup-hours',
    'sup-password',
    'sup-confirmPassword'
  ].forEach(function(id) {
    var el = document.getElementById(id);
    if (!el) return;
    if (document.activeElement === el) return;
    el.value = '';
    el.defaultValue = '';
    el.setAttribute('autocomplete', 'new-password');
    if (['universityId', 'supervisor-id', 'supervisor-email'].indexOf(id) !== -1) {
      el.setAttribute('readonly', 'readonly');
    }
  });

  pendingUserId = null;
  pendingSupUserId = null;
  try { sessionStorage.removeItem('activateStudentDraft'); } catch (e) {}
}

document.addEventListener('DOMContentLoaded', function() {
  clearActivationFields();
  switchRole('student');
  setTimeout(clearActivationFields, 80);
  setTimeout(clearActivationFields, 450);
});

window.addEventListener('pageshow', function(event) {
  if (event.persisted) clearActivationFields();
});


/* ─────────────────────────────────────────────────────────────
   STUDENT FLOW
───────────────────────────────────────────────────────────── */

var pendingUserId = null;
var phases = ['phase-verify', 'phase-password', 'phase-not-found', 'phase-success'];

function goToPhase(id) {
  phases.forEach(function(p) {
    document.getElementById(p).style.display = 'none';
  });
  document.getElementById(id).style.display = 'block';
}

function setStepPills(p1, p2) {
  var colors = {
    active: activationColor('--activate-primary', '#2d6a38'),
    done: '#10b981',
    '': activationColor('--activate-track', '#e5e7eb')
  };
  document.getElementById('pill-1').style.background = colors[p1] || colors[''];
  document.getElementById('pill-2').style.background = colors[p2] || colors[''];
}

function updateStrength() {
  var val  = document.getElementById('password').value;
  var bar  = document.getElementById('strength-bar');
  var score = 0;
  if (val.length >= 8)           score++;
  if (/[A-Z]/.test(val))         score++;
  if (/[0-9]/.test(val))         score++;
  if (/[^A-Za-z0-9]/.test(val))  score++;
  var widths = ['0%','25%','50%','75%','100%'];
  var colors = ['#ef4444','#f97316','#eab308','#22c55e','#10b981'];
  bar.style.width      = widths[score];
  bar.style.background = colors[score];
}

async function verifyStudent() {
  hideFeedback('verify-feedback');
  var uid   = document.getElementById('universityId').value.trim();

  if (!uid) {
    showFeedback('verify-feedback', 'Please enter your university ID.', 'warn');
    return;
  }
  if (!/^\d{7}$/.test(uid)) {
    showFeedback('verify-feedback', 'University ID must be exactly 7 digits.', 'warn');
    return;
  }

  var btn = document.getElementById('verifyBtn');
  btn.disabled = true; btn.textContent = 'Verifying...';

  try {
    var res  = await fetch('/api/activate/verify', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ university_id: uid })
    });
    var data = await res.json();

    if (res.ok) {
      pendingUserId = data.user_id;
      goToPhase('phase-password');
      setStepPills('done', 'active');
      document.getElementById('card-title').textContent = 'Set Your Password';
    } else if (res.status === 404) {
      goToPhase('phase-not-found');
      setStepPills('done', 'active');
      document.getElementById('card-title').textContent = 'Account Not Found';
    } else {
      showFeedback('verify-feedback', data.error || 'Something went wrong.', 'error');
    }
  } catch (e) {
    showFeedback('verify-feedback', 'Could not reach the server.', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Verify Identity &#x2197;';
  }
}

async function setPassword() {
  hideFeedback('pass-feedback');
  var pass    = document.getElementById('password').value;
  var confirm = document.getElementById('confirmPassword').value;

  if (!pass || !confirm) { showFeedback('pass-feedback', 'Please fill in both fields.', 'warn'); return; }
  if (pass.length < 8)   { showFeedback('pass-feedback', 'Password must be at least 8 characters.', 'warn'); return; }
  if (pass !== confirm)  { showFeedback('pass-feedback', 'Passwords do not match.', 'error'); return; }

  var btn = document.getElementById('setPassBtn');
  btn.disabled = true; btn.textContent = 'Activating...';

  try {
    var res  = await fetch('/api/activate/set-password', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ user_id: pendingUserId, password: pass, confirm_password: confirm })
    });
    var data = await res.json();

    if (res.ok) {
      goToPhase('phase-success');
      setStepPills('done', 'done');
      document.getElementById('card-title').textContent = 'Account Activated';
    } else {
      showFeedback('pass-feedback', data.error || 'Something went wrong.', 'error');
    }
  } catch (e) {
    showFeedback('pass-feedback', 'Could not reach the server.', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Activate Account &#x2197;';
  }
}

function resetToStep1() {
  pendingUserId = null;
  ['password', 'confirmPassword'].forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.value = '';
  });
  goToPhase('phase-verify');
  setStepPills('active', '');
  hideFeedback('verify-feedback');
  document.getElementById('card-title').textContent = 'Activate Account';
}


/* ─────────────────────────────────────────────────────────────
   SUPERVISOR FLOW
───────────────────────────────────────────────────────────── */

var pendingSupUserId = null;
var supPhases = ['sup-phase-verify', 'sup-phase-password', 'sup-phase-not-found', 'sup-phase-success'];

function goToSupPhase(id) {
  supPhases.forEach(function(p) {
    document.getElementById(p).style.display = 'none';
  });
  document.getElementById(id).style.display = 'block';
}

function setSupPills(p1, p2) {
  var colors = {
    active: activationColor('--activate-primary', '#2d6a38'),
    done: '#10b981',
    '': activationColor('--activate-track', '#e5e7eb')
  };
  document.getElementById('sup-pill-1').style.background = colors[p1] || colors[''];
  document.getElementById('sup-pill-2').style.background = colors[p2] || colors[''];
}

function updateSupStrength() {
  var val  = document.getElementById('sup-password').value;
  var bar  = document.getElementById('sup-strength-bar');
  var score = 0;
  if (val.length >= 8)           score++;
  if (/[A-Z]/.test(val))         score++;
  if (/[0-9]/.test(val))         score++;
  if (/[^A-Za-z0-9]/.test(val))  score++;
  var widths = ['0%','25%','50%','75%','100%'];
  var colors = ['#ef4444','#f97316','#eab308','#22c55e','#10b981'];
  bar.style.width      = widths[score];
  bar.style.background = colors[score];
}

async function verifySupervisor() {
  hideFeedback('sup-verify-feedback');
  var uid   = document.getElementById('supervisor-id').value.trim();
  var email = document.getElementById('supervisor-email').value.trim();

  if (!uid || !email) {
    showFeedback('sup-verify-feedback', 'Please fill in all fields.', 'warn');
    return;
  }
  if (!/^\d{4}$/.test(uid)) {
    showFeedback('sup-verify-feedback', 'Supervisor ID must be exactly 4 digits.', 'warn');
    return;
  }

  var btn = document.getElementById('sup-verifyBtn');
  btn.disabled = true; btn.textContent = 'Verifying...';

  try {
    var res  = await fetch('/api/activate/supervisor/verify', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ university_id: uid, email: email })
    });
    var data = await res.json();

    if (res.ok) {
      pendingSupUserId = data.user_id;
      goToSupPhase('sup-phase-password');
      setSupPills('done', 'active');
      document.getElementById('sup-card-title').textContent = 'Set Hours & Password';
    } else if (res.status === 404) {
      goToSupPhase('sup-phase-not-found');
      setSupPills('done', 'active');
      document.getElementById('sup-card-title').textContent = 'Account Not Found';
    } else {
      showFeedback('sup-verify-feedback', data.error || 'Something went wrong.', 'error');
    }
  } catch (e) {
    showFeedback('sup-verify-feedback', 'Could not reach the server.', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Verify Identity &#x2197;';
  }
}

async function setSupPassword() {
  hideFeedback('sup-pass-feedback');
  var hours   = document.getElementById('sup-hours').value.trim();
  var pass    = document.getElementById('sup-password').value;
  var confirm = document.getElementById('sup-confirmPassword').value;

  if (!hours || !pass || !confirm) {
    showFeedback('sup-pass-feedback', 'Please fill in all fields.', 'warn');
    return;
  }
  if (isNaN(hours) || parseFloat(hours) < 0) {
    showFeedback('sup-pass-feedback', 'Please enter a valid hours value.', 'warn');
    return;
  }
  if (pass.length < 8) {
    showFeedback('sup-pass-feedback', 'Password must be at least 8 characters.', 'warn');
    return;
  }
  if (pass !== confirm) {
    showFeedback('sup-pass-feedback', 'Passwords do not match.', 'error');
    return;
  }

  var btn = document.getElementById('sup-setPassBtn');
  btn.disabled = true; btn.textContent = 'Activating...';

  try {
    var res  = await fetch('/api/activate/supervisor/set-password', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        user_id: pendingSupUserId,
        graduation_project_hours: parseFloat(hours),
        password: pass,
        confirm_password: confirm
      })
    });
    var data = await res.json();

    if (res.ok) {
      goToSupPhase('sup-phase-success');
      setSupPills('done', 'done');
      document.getElementById('sup-card-title').textContent = 'Account Activated';
    } else {
      showFeedback('sup-pass-feedback', data.error || 'Something went wrong.', 'error');
    }
  } catch (e) {
    showFeedback('sup-pass-feedback', 'Could not reach the server.', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Activate Account &#x2197;';
  }
}

function resetSupToStep1() {
  pendingSupUserId = null;
  ['sup-hours', 'sup-password', 'sup-confirmPassword'].forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.value = '';
  });
  goToSupPhase('sup-phase-verify');
  setSupPills('active', '');
  hideFeedback('sup-verify-feedback');
  document.getElementById('sup-card-title').textContent = 'Activate Account';
}
