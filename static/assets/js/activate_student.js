
  var pendingUserId = null;

  var phases = ['phase-verify', 'phase-password', 'phase-not-found', 'phase-success'];

  function goToPhase(id) {
    phases.forEach(function(p) {
      document.getElementById(p).style.display = 'none';
    });
    document.getElementById(id).style.display = 'block';
  }

  function setStepPills(p1, p2) {
    var colors = { active: '#3b82f6', done: '#10b981', '': 'var(--color-border-tertiary)' };
    document.getElementById('pill-1').style.background = colors[p1] || colors[''];
    document.getElementById('pill-2').style.background = colors[p2] || colors[''];
  }

  /* ── Feedback — reuses your existing showFeedback style ── */
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

  function updateStrength() {
    var val = document.getElementById('password').value;
    var bar = document.getElementById('strength-bar');
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
    var name  = document.getElementById('fullName').value.trim();
    var uid   = document.getElementById('universityId').value.trim();
    var email = document.getElementById('email').value.trim();

    if (!name || !uid || !email) {
      showFeedback('verify-feedback', 'Please fill in all fields.', 'warn');
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
        body: JSON.stringify({ full_name: name, university_id: uid, email: email })
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
    goToPhase('phase-verify');
    setStepPills('active', '');
    hideFeedback('verify-feedback');
    document.getElementById('card-title').textContent = 'Activate Account';
  }
