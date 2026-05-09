const SIDEBAR_PIN_KEY = 'coordSidebarPinned';
let sidebarPinned = false;
let distributionWindowOpen = false;
let professorsCache = [];
let formsCache = [];
let unassignedCache = [];
let committeeDashboardCache = null;

function normalizeText(t) {
  return (t || '').toLowerCase().replace(/\s+/g, ' ').trim();
}

function getSidebar() {
  return document.getElementById('sidebar');
}

function persistSidebarState() {
  try { localStorage.setItem(SIDEBAR_PIN_KEY, sidebarPinned ? '1' : '0'); } catch (e) {}
}

function readSidebarState() {
  try { return localStorage.getItem(SIDEBAR_PIN_KEY) === '1'; } catch (e) { return false; }
}

function openSidebar() {
  const s = getSidebar();
  if (s) s.classList.remove('collapsed');
}

function closeSidebar() {
  const s = getSidebar();
  if (s && !sidebarPinned) s.classList.add('collapsed');
}

function applySidebarState() {
  const s = getSidebar();
  if (!s) return;
  sidebarPinned = readSidebarState();
  s.classList.toggle('collapsed', !sidebarPinned);
}

function toggleCoordSidebar() {
  const s = getSidebar();
  if (!s) return;
  sidebarPinned = !sidebarPinned;
  s.classList.toggle('collapsed', !sidebarPinned);
  persistSidebarState();
}

function bindSidebarHover() {
  const s = getSidebar();
  if (!s) return;
  s.addEventListener('mouseenter', () => { if (!sidebarPinned) openSidebar(); });
  s.addEventListener('mouseleave', () => { if (!sidebarPinned) closeSidebar(); });
}

function bindTabs() {
  document.querySelectorAll('.tab-bar').forEach(bar => {
    const tabs = Array.from(bar.querySelectorAll('.tab'));
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('on'));
        tab.classList.add('on');
      });
    });
  });
}

function appendChatMessage(text, kind) {
  const body = document.querySelector('.chat-body');
  if (!body) return;
  const msg = document.createElement('div');
  msg.className = 'chat-msg ' + (kind === 'user' ? 'chat-user' : 'chat-bot');
  msg.textContent = text;
  body.appendChild(msg);
  body.scrollTop = body.scrollHeight;
}

async function askAI() {
  const input = document.getElementById('chatIn');
  if (!input) return;
  const q = input.value.trim();
  if (!q) return;
  appendChatMessage(q, 'user');
  input.value = '';
  try {
    const res = await fetch('/api/ai/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q })
    });
    const data = await readApiJson(res);
    appendChatMessage(data.answer || data.error || 'No answer returned.', 'bot');
  } catch (e) {
    appendChatMessage('Could not connect to the AI service.', 'bot');
  }
}

function bindAI() {
  const btn = document.querySelector('[data-action="ask-ai"]');
  const inp = document.getElementById('chatIn');
  if (btn) btn.addEventListener('click', askAI);
  if (inp) inp.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      e.preventDefault();
      askAI();
    }
  });

  document.querySelectorAll('[data-question]').forEach(item => {
    item.addEventListener('click', () => {
      if (!inp) return;
      inp.value = item.dataset.question || '';
      inp.focus();
    });
  });
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function committeeEscapeHtml(value) {
  return escapeHtml(value);
}

function statusBadge(status) {
  const value = (status || '').toLowerCase();
  if (value === 'accepted' || value === 'under_review' || value === 'committee_evaluation') return '<span class="pill p-accepted">Assigned ✓</span>';
  if (value === 'submitted') return '<span class="pill p-review">Being Assigned</span>';
  return `<span class="pill p-pending">${escapeHtml(status || 'Pending')}</span>`;
}

function committeeStatusBadge(status) {
  const s = normalizeText(status);
  if (s === 'completed') return '<span class="pill p-accepted">Completed</span>';
  if (s === 'ongoing' || s === 'in_progress') return '<span class="pill p-review">Ongoing</span>';
  if (s === 'scheduled') return '<span class="pill p-pending">Scheduled</span>';
  return `<span class="pill p-pending">${committeeEscapeHtml(status || 'Unknown')}</span>`;
}

/* =========================
   REGISTRATION / DISTRIBUTION
========================= */
function updateSelectedStudentsCount() {
  const el = document.getElementById('selectedStudentsCount');
  if (!el) return;
  el.textContent = getSelectedStudentIds().length;
}

function getSelectedStudentIds() {
  return Array.from(document.querySelectorAll('.unassigned-student-checkbox:checked'))
    .map(el => parseInt(el.value, 10))
    .filter(Number.isFinite);
}

function handleStudentCheckboxChange(changedBox) {
  const checked = Array.from(document.querySelectorAll('.unassigned-student-checkbox:checked'));
  if (checked.length > 3) {
    changedBox.checked = false;
    alert('You can select at most 3 students.');
  }
  updateSelectedStudentsCount();
}

async function loadDistributionWindow() {
  const statusText = document.getElementById('windowStatusText');
  const statusMeta = document.getElementById('windowStatusMeta');
  const btn = document.getElementById('toggleWindowBtn');
  const msg = document.getElementById('windowMsg');
  const closeInput = document.getElementById('registrationCloseAt');
  if (!statusText || !statusMeta || !btn) return;

  try {
    const res = await fetch('/api/coordinator/distribution-window', { credentials: 'same-origin' });
    const data = await readJsonResponse(res);
    if (!res.ok) throw new Error(data.error || 'Failed to load window status.');

    distributionWindowOpen = !!data.is_open;
    statusText.textContent = distributionWindowOpen ? 'Registration is OPEN' : 'Registration is CLOSED';

    const openedAt = data.opened_at ? `Opened at: ${data.opened_at}` : '';
    const closedAt = data.closed_at ? `Closed at: ${data.closed_at}` : '';
    const closeAt = data.close_at ? `Auto close at: ${data.close_at}` : '';
    statusMeta.textContent = [distributionWindowOpen ? openedAt : closedAt, closeAt].filter(Boolean).join(' | ');

    if (closeInput && data.close_at) {
      closeInput.value = String(data.close_at).replace(' ', 'T').slice(0, 16);
    }

    btn.textContent = distributionWindowOpen ? 'Close Registration' : 'Open Registration';
    btn.className = distributionWindowOpen ? 'btn btn-outline' : 'btn btn-primary';
    if (msg) msg.textContent = '';
  } catch (err) {
    statusText.textContent = 'Failed to load window status';
    statusMeta.textContent = '';
    btn.textContent = 'Unavailable';
    if (msg) msg.textContent = err.message;
  }
}

async function toggleDistributionWindow() {
  const btn = document.getElementById('toggleWindowBtn');
  const msg = document.getElementById('windowMsg');
  const closeInput = document.getElementById('registrationCloseAt');
  if (!btn) return;

  const opening = !distributionWindowOpen;
  const closeAt = closeInput ? closeInput.value : '';

  if (opening && !closeAt) {
    if (msg) {
      msg.style.color = '#c62828';
      msg.textContent = 'Please choose an automatic close date before opening registration.';
    }
    alert('Please choose an automatic close date before opening registration.');
    return;
  }

  try {
    btn.disabled = true;
    if (msg) {
      msg.style.color = '#444';
      msg.textContent = 'Saving...';
    }

    const res = await fetch('/api/coordinator/distribution-window', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_open: opening, close_at: closeAt })
    });

    const data = await readApiJson(res);
    if (!res.ok) throw new Error(data.error || 'Failed to update registration window.');

    if (msg) {
      msg.style.color = 'green';
      msg.textContent = data.message || 'Updated successfully.';
    }
    await loadDistributionWindow();
  } catch (err) {
    if (msg) {
      msg.style.color = '#c62828';
      msg.textContent = err.message || 'Something went wrong.';
    }
  } finally {
    btn.disabled = false;
  }
}

function renderStats(stats) {
  const total = document.getElementById('statTotal');
  const assigned = document.getElementById('statAssigned');
  const waiting = document.getElementById('statWaiting');
  const groups = document.getElementById('statGroups');
  if (total) total.textContent = stats.total_registered_students || 0;
  if (assigned) assigned.textContent = stats.assigned || 0;
  if (waiting) waiting.textContent = stats.waiting || 0;
  if (groups) groups.textContent = stats.active_groups || 0;
}

function renderSupervisorOptions(professors) {
  const select = document.getElementById('sectionSupervisor');
  if (!select) return;
  select.innerHTML = '<option value="">Select supervisor...</option>';
  professors.forEach(prof => {
    const opt = document.createElement('option');
    opt.value = prof.faculty_id;
    opt.textContent = `${prof.full_name} (${prof.assigned_projects} assigned groups)`;
    select.appendChild(opt);
  });
}

function renderForms(forms, professors) {
  const tableBody = document.getElementById('distributionFormsBody');
  if (!tableBody) return;

  if (!forms.length) {
    tableBody.innerHTML = '<tr><td colspan="7">No submissions yet.</td></tr>';
    return;
  }

  tableBody.innerHTML = forms.map(form => {
    const preferredDoctors = [form.preferred_1, form.preferred_2, form.preferred_3].filter(Boolean);
    const currentSupervisorId = form.supervisor_id || '';
    const currentSupervisorName = form.final_supervisor || 'Not assigned';
    const selectId = `groupSupervisor_${form.project_id}`;

    const supervisorOptions = [
      '<option value="">Select supervisor...</option>',
      ...professors.map(prof => {
        const selected = String(prof.faculty_id) === String(currentSupervisorId) ? 'selected' : '';
        return `<option value="${prof.faculty_id}" ${selected}>${escapeHtml(prof.full_name)}</option>`;
      })
    ].join('');

    return `
      <tr>
        <td>${escapeHtml(form.group_name || '—')}</td>
        <td>${escapeHtml(form.team_members || '—')}</td>
        <td>${preferredDoctors.length ? preferredDoctors.map(escapeHtml).join('<br>') : '—'}</td>
        <td>${escapeHtml(form.title || '—')}</td>
        <td>
          <select class="field-select" id="${selectId}">
            ${supervisorOptions}
          </select>
          <div style="font-size:12px;color:#667587;margin-top:6px">
            Current: ${escapeHtml(currentSupervisorName)}
          </div>
        </td>
        <td>
          <button class="btn btn-primary" type="button" onclick="assignGroupSupervisor(${form.project_id})">Save</button>
        </td>
        <td>${statusBadge(form.status)}</td>
      </tr>
    `;
  }).join('');
}

function renderUnassignedStudents(students) {
  const unassignedBox = document.getElementById('unassignedStudentsBox');
  if (!unassignedBox) return;

  if (!students.length) {
    unassignedBox.innerHTML = '<div>No unassigned students.</div>';
    updateSelectedStudentsCount();
    return;
  }

  unassignedBox.innerHTML = students.map(student => `
    <label style="display:flex;align-items:center;gap:10px;padding:10px;border-bottom:1px solid #e8e8e8;cursor:pointer;">
      <input type="checkbox" class="unassigned-student-checkbox" value="${student.student_id}" onchange="handleStudentCheckboxChange(this)" />
      <div class="member-avatar u-01ebd179">${escapeHtml((student.full_name || '').split(' ').map(x => x[0]).slice(0, 2).join('') || '--')}</div>
      <div style="flex:1">
        <div><b>${escapeHtml(student.full_name || '-')}</b></div>
        <div style="font-size:12px;color:#666">${escapeHtml(student.university_id || '')}</div>
      </div>
    </label>
  `).join('');

  updateSelectedStudentsCount();
}

function renderSections(sections) {
  const sectionsList = document.getElementById('sectionsList');
  if (!sectionsList) return;

  if (!sections.length) {
    sectionsList.innerHTML = '<div>No sections entered yet.</div>';
    return;
  }

  sectionsList.innerHTML = sections.map(section => `
    <div class="u-e83423b7">
      <span class="u-adf67d91">${escapeHtml(section.section_name || '—')} — ${escapeHtml(section.supervisor_name || '—')}</span>
      <span class="pill p-accepted u-49f06467">Entered ✓</span>
    </div>
  `).join('');
}

async function loadDistributionData() {
  const tableBody = document.getElementById('distributionFormsBody');
  const unassignedBox = document.getElementById('unassignedStudentsBox');
  const sectionsList = document.getElementById('sectionsList');
  const sectionSupervisor = document.getElementById('sectionSupervisor');
  const sectionMsg = document.getElementById('sectionMsg');

  if (!tableBody && !unassignedBox && !sectionsList) return;

  try {
    const res = await fetch('/api/coordinator/distribution-data');
    const data = await readApiJson(res);
    if (!res.ok) throw new Error(data.error || 'Failed to load distribution data.');

    professorsCache = data.professors || [];
    formsCache = data.forms || [];
    unassignedCache = data.unassigned_students || [];

    renderForms(formsCache, professorsCache);
    renderUnassignedStudents(unassignedCache);
    renderSupervisorOptions(professorsCache);
    renderSections(data.sections || []);
    renderStats(data.stats || {});
    updateSelectedStudentsCount();

    if (sectionMsg) sectionMsg.textContent = '';
    if (sectionSupervisor && !sectionSupervisor.value) {
      sectionSupervisor.value = '';
    }
  } catch (err) {
    if (tableBody) tableBody.innerHTML = `<tr><td colspan="7">${escapeHtml(err.message)}</td></tr>`;
    if (unassignedBox) unassignedBox.innerHTML = `<div>${escapeHtml(err.message)}</div>`;
    if (sectionsList) sectionsList.innerHTML = `<div>${escapeHtml(err.message)}</div>`;
    const sectionSupervisor = document.getElementById('sectionSupervisor');
    if (sectionSupervisor) sectionSupervisor.innerHTML = '<option value="">Select supervisor...</option>';
    const sectionMsg = document.getElementById('sectionMsg');
    if (sectionMsg) sectionMsg.textContent = err.message;
  }
}

async function assignGroupSupervisor(projectId) {
  const msg = document.getElementById('sectionMsg');
  const select = document.getElementById(`groupSupervisor_${projectId}`);
  const supervisorId = select ? select.value : '';

  if (!supervisorId) {
    if (msg) {
      msg.style.color = '#c62828';
      msg.style.fontWeight = '600';
      msg.textContent = 'Please choose a supervisor before saving.';
    }
    alert('Please choose a supervisor before saving.');
    return;
  }

  try {
    if (msg) {
      msg.style.color = '#444';
      msg.style.fontWeight = '600';
      msg.textContent = 'Saving group supervisor...';
    }

    const res = await fetch('/api/coordinator/assign-group-supervisor', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: projectId,
        supervisor_id: supervisorId
      })
    });

    const data = await readApiJson(res);

    if (!res.ok) {
      throw new Error(data.error || 'Failed to assign supervisor.');
    }

    if (msg) {
      msg.style.color = 'green';
      msg.style.fontWeight = '600';
      msg.textContent = data.message || 'Supervisor assigned successfully.';
    }

    await loadDistributionData();
  } catch (err) {
    if (msg) {
      msg.style.color = '#c62828';
      msg.style.fontWeight = '700';
      msg.textContent = err.message || 'Something went wrong while assigning the supervisor.';
    }
    alert(err.message || 'Something went wrong while assigning the supervisor.');
  }
}

async function addSectionEntry() {
  const sectionName = document.getElementById('sectionName')?.value.trim();
  const supervisorId = document.getElementById('sectionSupervisor')?.value;
  const selectedStudents = getSelectedStudentIds();
  const msg = document.getElementById('sectionMsg');
  const addBtn = document.querySelector('button[onclick="addSectionEntry()"]');

  if (!sectionName || !supervisorId) {
    if (msg) {
      msg.style.color = '#c62828';
      msg.style.fontWeight = '600';
      msg.textContent = 'Please enter the section name and choose a supervisor.';
    }
    alert('Please enter the section name and choose a supervisor.');
    return;
  }

  if (!selectedStudents.length) {
    if (msg) {
      msg.style.color = '#c62828';
      msg.style.fontWeight = '600';
      msg.textContent = 'Please choose at least one unassigned student.';
    }
    alert('Please choose at least one unassigned student.');
    return;
  }

  if (selectedStudents.length > 3) {
    if (msg) {
      msg.style.color = '#c62828';
      msg.style.fontWeight = '600';
      msg.textContent = 'You can choose at most 3 students.';
    }
    alert('You can choose at most 3 students.');
    return;
  }

  try {
    if (addBtn) addBtn.disabled = true;
    if (msg) {
      msg.style.color = '#444';
      msg.style.fontWeight = '600';
      msg.textContent = 'Saving...';
    }

    const res = await fetch('/api/coordinator/add-section', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        section_name: sectionName,
        supervisor_id: supervisorId,
        student_ids: selectedStudents
      })
    });

    const data = await readApiJson(res);

    if (!res.ok) {
      throw new Error(data.error || 'Failed to add section.');
    }

    if (msg) {
      msg.style.color = 'green';
      msg.style.fontWeight = '600';
      msg.textContent = data.message || 'Section added successfully.';
    }

    const sectionNameInput = document.getElementById('sectionName');
    const sectionSupervisor = document.getElementById('sectionSupervisor');
    if (sectionNameInput) sectionNameInput.value = '';
    if (sectionSupervisor) sectionSupervisor.value = '';

    await loadDistributionData();
  } catch (err) {
    if (msg) {
      msg.style.color = '#c62828';
      msg.style.fontWeight = '700';
      msg.textContent = err.message || 'Something went wrong while adding the section.';
    }
    alert(err.message || 'Something went wrong while adding the section.');
  } finally {
    if (addBtn) addBtn.disabled = false;
  }
}

function initRegistrationPage() {
  if (!document.getElementById('pg-registration')) return;
  loadDistributionWindow();
  loadDistributionData();
}

/* =========================
   COMMITTEE SCHEDULER
========================= */
function setCommitteeMessage(text, isError = false) {
  const msg = document.getElementById('committeeMsg');
  if (!msg) return;
  msg.style.color = isError ? '#c62828' : '#1b5e20';
  msg.style.fontWeight = '600';
  msg.textContent = text || '';
}

function renderEligibleProjects(projects) {
  const box = document.getElementById('eligibleProjectsBox');
  if (!box) return;

  if (!projects || !projects.length) {
    box.innerHTML = '<div>No eligible projects waiting for committee discussion.</div>';
    return;
  }

  box.innerHTML = projects.map(project => `
    <div class="u-e83423b7" style="display:block">
      <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap">
        <div>
          <div class="u-2e61148f">${committeeEscapeHtml(project.title || '—')}</div>
          <div class="u-7d16b22c">${committeeEscapeHtml(project.team_members || 'No team members')}</div>
        </div>
        <span class="pill p-review">${committeeEscapeHtml(project.status || 'submitted')}</span>
      </div>
    </div>
  `).join('');
}

function renderCommitteeStats(stats) {
  const formed = document.getElementById('statCommitteesFormed');
  const avg = document.getElementById('statAverageScores');
  const ongoing = document.getElementById('statOngoing');
  const scheduled = document.getElementById('statScheduled');

  if (formed) formed.textContent = stats?.formed ?? 0;
  if (avg) avg.textContent = stats?.average_score ?? 0;
  if (ongoing) ongoing.textContent = stats?.ongoing ?? 0;
  if (scheduled) scheduled.textContent = stats?.scheduled ?? 0;
}

function renderCurrentCommittees(committees) {
  const box = document.getElementById('currentCommitteesBox');
  if (!box) return;

  if (!committees || !committees.length) {
    box.innerHTML = '<div>No committees created yet.</div>';
    return;
  }

  box.innerHTML = committees.map(item => `
    <div class="u-2b587ae7">
      <div class="u-11730a65">
        <div class="u-2e61148f">${committeeEscapeHtml(item.committee_name || 'Committee')}</div>
        ${committeeStatusBadge(item.status)}
      </div>
      <div class="u-7d16b22c">
        ${committeeEscapeHtml(item.discussion_date || '—')}
        ${item.start_time ? '· ' + committeeEscapeHtml(item.start_time) : ''}
        ${item.room_name ? '· ' + committeeEscapeHtml(item.room_name) : ''}
      </div>
      <div class="u-99556c5c">
        ${committeeEscapeHtml(item.projects_count || 0)} project(s)
        ${item.responsible_name ? ' · Responsible: ' + committeeEscapeHtml(item.responsible_name) : ''}
      </div>
    </div>
  `).join('');
}

function renderCommitteePlans(plans) {
  const box = document.getElementById('committeePlansBox');
  if (!box) return;

  if (!plans || !plans.length) {
    box.innerHTML = '<div>No generated committees yet.</div>';
    return;
  }

  box.innerHTML = plans.map(plan => {
    const responsibleOptions = [
      '<option value="">Choose responsible doctor...</option>',
      ...plan.members.map(member => {
        const selected = String(member.faculty_id) === String(plan.responsible_faculty_id || '') ? 'selected' : '';
        return `<option value="${member.faculty_id}" ${selected}>${committeeEscapeHtml(member.full_name)} — ${committeeEscapeHtml(member.specialization)}</option>`;
      })
    ].join('');

    const membersHtml = plan.members.map(member => `
      <div class="member-row" style="margin-bottom:8px">
        <div class="member-avatar">${committeeEscapeHtml((member.full_name || '').split(' ').map(x => x[0]).slice(0, 2).join('') || '--')}</div>
        <div style="flex:1">
          <div class="u-2e61148f">${committeeEscapeHtml(member.full_name)}</div>
          <div class="u-7d16b22c">${committeeEscapeHtml(member.specialization)} · ${committeeEscapeHtml(member.years_experience)} yrs</div>
        </div>
        <span class="pill ${member.role === 'responsible' ? 'p-accepted' : 'p-review'}">
          ${member.role === 'responsible' ? 'Responsible' : 'Member'}
        </span>
      </div>
    `).join('');

    const projectsHtml = (plan.projects || []).map(project => `
      <tr>
        <td>${committeeEscapeHtml(project.slot_order)}</td>
        <td>${committeeEscapeHtml(project.slot_start)} - ${committeeEscapeHtml(project.slot_end)}</td>
        <td>${committeeEscapeHtml(project.title)}</td>
        <td>${committeeEscapeHtml(project.team_members || '—')}</td>
      </tr>
    `).join('');

    return `
      <div class="card" style="margin-bottom:14px;border:1px solid #e3e8ef">
        <div class="card-hd">
          <span class="card-title">${committeeEscapeHtml(plan.committee_name)}</span>
          ${committeeStatusBadge(plan.status)}
        </div>

        <div style="font-size:13px;color:#667587;margin-bottom:10px">
          <b>Date:</b> ${committeeEscapeHtml(plan.discussion_date)} |
          <b>Time:</b> ${committeeEscapeHtml(plan.start_time)} - ${committeeEscapeHtml(plan.end_time)} |
          <b>Room:</b> ${committeeEscapeHtml(plan.room_name)}
        </div>

        <div style="margin-bottom:12px">
          <div class="field-label">Responsible Doctor</div>
          <div style="display:flex;gap:10px;flex-wrap:wrap">
            <select class="field-select" id="responsible_${plan.plan_id}" style="flex:1;min-width:260px">
              ${responsibleOptions}
            </select>
            <button class="btn btn-primary" type="button" onclick="saveResponsibleDoctor(${plan.plan_id})">Save Responsible</button>
          </div>
        </div>

        <div class="field-label" style="margin-bottom:8px">Committee Members</div>
        <div class="u-e47f6ecd" style="margin-bottom:12px">
          ${membersHtml}
        </div>

        <div class="field-label" style="margin-bottom:8px">Projects In This Committee</div>
        <div class="u-77c8140b">
          <table class="reg-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Slot</th>
                <th>Project</th>
                <th>Team Members</th>
              </tr>
            </thead>
            <tbody>
              ${projectsHtml || '<tr><td colspan="4">No projects assigned.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }).join('');
}

async function loadCommitteeDashboard() {
  if (!document.getElementById('pg-committee')) return;

  try {
    const res = await fetch('/api/coordinator/committee-dashboard', { credentials: 'same-origin' });
    const data = await readJsonResponse(res);

    if (!res.ok) {
      throw new Error(data.error || 'Failed to load committee dashboard.');
    }

    committeeDashboardCache = data;
    renderEligibleProjects(data.eligible_projects || []);
    renderCommitteePlans(data.plans || []);
    renderCurrentCommittees(data.current_committees || []);
    renderCommitteeStats(data.stats || {});

    const dateInput = document.getElementById('committeeDate');
    if (dateInput && !dateInput.value) {
      dateInput.value = new Date().toISOString().slice(0, 10);
    }
  } catch (err) {
    setCommitteeMessage(err.message || 'Failed to load committee dashboard.', true);
    const eligible = document.getElementById('eligibleProjectsBox');
    const plans = document.getElementById('committeePlansBox');
    const current = document.getElementById('currentCommitteesBox');
    if (eligible) eligible.innerHTML = `<div>${committeeEscapeHtml(err.message)}</div>`;
    if (plans) plans.innerHTML = `<div>${committeeEscapeHtml(err.message)}</div>`;
    if (current) current.innerHTML = `<div>${committeeEscapeHtml(err.message)}</div>`;
  }
}

async function generateCommittees() {
  const discussionDate = document.getElementById('committeeDate')?.value;
  const startTime = document.getElementById('committeeStartTime')?.value;
  const projectsPerCommittee = document.getElementById('projectsPerCommittee')?.value;

  if (!discussionDate || !startTime || !projectsPerCommittee) {
    setCommitteeMessage('Please fill discussion date, start time, and projects per committee.', true);
    alert('Please fill discussion date, start time, and projects per committee.');
    return;
  }

  try {
    setCommitteeMessage('Generating committees...', false);

    const res = await fetch('/api/coordinator/committee-generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        discussion_date: discussionDate,
        start_time: startTime,
        projects_per_committee: parseInt(projectsPerCommittee, 10)
      })
    });

    const data = await readApiJson(res);

    if (!res.ok) {
      throw new Error(data.error || 'Failed to generate committees.');
    }

    setCommitteeMessage(data.message || 'Committees generated successfully.');
    renderCommitteePlans(data.plans || []);
    await loadCommitteeDashboard();
  } catch (err) {
    setCommitteeMessage(err.message || 'Failed to generate committees.', true);
    alert(err.message || 'Failed to generate committees.');
  }
}

async function saveResponsibleDoctor(planId) {
  const select = document.getElementById(`responsible_${planId}`);
  const facultyId = select ? select.value : '';

  if (!facultyId) {
    setCommitteeMessage('Please choose the responsible doctor first.', true);
    alert('Please choose the responsible doctor first.');
    return;
  }

  try {
    const res = await fetch(`/api/coordinator/committee/${planId}/responsible`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ faculty_id: facultyId })
    });

    const data = await readApiJson(res);

    if (!res.ok) {
      throw new Error(data.error || 'Failed to save the responsible doctor.');
    }

    setCommitteeMessage(data.message || 'Responsible doctor saved successfully.');
    renderCommitteePlans(data.plans || []);
    await loadCommitteeDashboard();
  } catch (err) {
    setCommitteeMessage(err.message || 'Failed to save the responsible doctor.', true);
    alert(err.message || 'Failed to save the responsible doctor.');
  }
}

function initCommitteePage() {
  if (!document.getElementById('pg-committee')) return;
  loadCommitteeDashboard();
}

async function resetAndRedistributeCommittees() {
  const discussionDate = document.getElementById('committeeDate')?.value;
  const startTime = document.getElementById('committeeStartTime')?.value;
  const projectsPerCommittee = document.getElementById('projectsPerCommittee')?.value;

  if (!discussionDate || !startTime || !projectsPerCommittee) {
    setCommitteeMessage('Please fill discussion date, start time, and projects per committee.', true);
    alert('Please fill discussion date, start time, and projects per committee.');
    return;
  }

  const confirmed = confirm('This will delete the current scheduled committees and redistribute the projects again. Continue?');
  if (!confirmed) return;

  try {
    setCommitteeMessage('Resetting and redistributing committees...', false);

    const res = await fetch('/api/coordinator/committee-reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        discussion_date: discussionDate,
        start_time: startTime,
        projects_per_committee: parseInt(projectsPerCommittee, 10)
      })
    });

    const data = await readApiJson(res);

    if (!res.ok) {
      throw new Error(data.error || 'Failed to reset and redistribute committees.');
    }

    setCommitteeMessage(data.message || 'Committees were reset and redistributed successfully.');
    renderCommitteePlans(data.plans || []);
    await loadCommitteeDashboard();
  } catch (err) {
    setCommitteeMessage(err.message || 'Failed to reset and redistribute committees.', true);
    alert(err.message || 'Failed to reset and redistribute committees.');
  }
}



async function readJsonResponse(res) {
  const contentType = res.headers.get('content-type') || '';
  const text = await res.text();
  if (!contentType.includes('application/json')) {
    if (text.toLowerCase().includes('<!doctype') || text.toLowerCase().includes('<html')) {
      throw new Error('The server returned an HTML page instead of JSON. Log in again as coordinator, then refresh. If you are already logged in, check the Flask terminal for the real error.');
    }
    throw new Error(text || 'The server did not return JSON.');
  }
  try {
    return JSON.parse(text);
  } catch (e) {
    throw new Error('Invalid JSON returned by the server.');
  }
}

/* =========================
   DASHBOARD
========================= */
function dashSet(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value ?? 0;
}

function renderDashList(id, rows, labelKey, valueKey) {
  const box = document.getElementById(id);
  if (!box) return;
  if (!rows || !rows.length) {
    box.innerHTML = '<div>No data found.</div>';
    return;
  }
  const total = rows.reduce((sum, row) => sum + (parseInt(row[valueKey] ?? row.count ?? 0, 10) || 0), 0) || 1;
  box.innerHTML = rows.map(row => {
    const label = row[labelKey] || row.status || row.project_type || 'Unknown';
    const count = parseInt(row[valueKey] ?? row.count ?? 0, 10) || 0;
    const percent = Math.round((count / total) * 100);
    return `
      <div style="margin-bottom:12px">
        <div style="display:flex;justify-content:space-between;gap:10px;font-size:13px;margin-bottom:6px">
          <span>${escapeHtml(label)}</span><b>${count}</b>
        </div>
        <div style="height:8px;background:#edf2f7;border-radius:999px;overflow:hidden">
          <div style="height:100%;width:${percent}%;background:#0f6e56;border-radius:999px"></div>
        </div>
      </div>
    `;
  }).join('');
}

function renderDashboardLatest(projects) {
  const box = document.getElementById('dashLatestProjects');
  if (!box) return;
  if (!projects || !projects.length) {
    box.innerHTML = '<div>No projects found.</div>';
    return;
  }
  box.innerHTML = projects.map(project => `
    <div class="review-card new-proj">
      <div class="u-e8f8c28c">
        <div class="u-2e61148f">${escapeHtml(project.title || 'Untitled Project')}</div>
        ${statusBadge(project.status)}
      </div>
      <div class="u-6aa10742">
        ${escapeHtml(project.team_members || 'No team members')} · ${escapeHtml(project.supervisor_name || 'No supervisor yet')}
      </div>
      <div class="btn-row">
        <button class="btn btn-outline u-d59a4528" data-go="review" type="button">Detailed Review</button>
      </div>
    </div>
  `).join('');
}

function renderDashboardProgress(stats) {
  const box = document.getElementById('dashWorkflowProgress');
  if (!box) return;
  const total = Math.max(parseInt(stats.total_projects || 0, 10), 1);
  const items = [
    ['Submitted / Review', stats.awaiting_review || 0],
    ['Committee Evaluation', stats.under_evaluation || 0],
    ['Accepted / Archived', stats.accepted || 0],
    ['Rejected', stats.rejected || 0],
  ];
  box.innerHTML = items.map(([label, count]) => {
    const percent = Math.round((count / total) * 100);
    return `
      <div class="prog-wrap">
        <div class="prog-label"><span>${escapeHtml(label)}</span><span class="u-44265a69">${percent}%</span></div>
        <div class="prog-bg"><div class="prog-fill" style="width:${percent}%"></div></div>
      </div>
    `;
  }).join('');
}



async function readApiJson(res) {
  const contentType = (res.headers.get('content-type') || '').toLowerCase();
  const bodyText = await res.text();

  if (!contentType.includes('application/json')) {
    if (bodyText.trim().startsWith('<')) {
      throw new Error('The server returned an HTML page instead of JSON. This means the API route is missing, you are not logged in as coordinator, or Flask has an error. Check the Flask terminal.');
    }
    throw new Error(bodyText || 'The server did not return JSON.');
  }

  try {
    return JSON.parse(bodyText || '{}');
  } catch (e) {
    throw new Error('Invalid JSON returned from server. Check the Flask terminal.');
  }
}

async function loadDashboardData() {
  if (!document.getElementById('pg-dashboard')) return;
  try {
    const res = await fetch('/api/coordinator/dashboard-data', { credentials: 'same-origin' });
    const data = await readJsonResponse(res);
    if (!res.ok) throw new Error(data.error || 'Failed to load dashboard.');
    const stats = data.stats || {};
    dashSet('dashTotalProjects', stats.total_projects || 0);
    dashSet('dashAwaitingReview', stats.awaiting_review || 0);
    dashSet('dashUnderEvaluation', stats.under_evaluation || 0);
    dashSet('dashAccepted', stats.accepted || 0);
    dashSet('dashRejected', stats.rejected || 0);
    dashSet('dashCommitteesCount', stats.committees || 0);
    const status = document.getElementById('dashDistributionStatus');
    if (status) status.textContent = data.distribution_open ? 'Open' : 'Closed';
    renderDashboardLatest(data.latest_projects || []);
    renderDashboardProgress(stats);
    renderDashList('dashStatusDistribution', data.by_status || [], 'status', 'count');
    renderDashList('dashTypeDistribution', data.by_type || [], 'project_type', 'count');
  } catch (err) {
    const box = document.getElementById('dashLatestProjects');
    if (box) box.innerHTML = `<div>${escapeHtml(err.message)}</div>`;
  }
}

/* =========================
   REVIEW PROJECTS
========================= */
let reviewProjectsCache = [];
let reviewFilter = 'all';

function reviewBadge(status) {
  const s = normalizeText(status);
  if (s === 'accepted') return '<span class="pill p-accepted">Accepted</span>';
  if (s === 'rejected') return '<span class="pill p-pending">Rejected</span>';
  if (s === 'committee_evaluation') return '<span class="pill p-review">Committee</span>';
  if (s === 'needs_revision') return '<span class="pill p-pending">Needs Revision</span>';
  if (s === 'under_review') return '<span class="pill p-review">In Review</span>';
  return '<span class="pill p-new">New</span>';
}

function filterReviewProjects(status, btn) {
  reviewFilter = status;
  document.querySelectorAll('#pg-review .tab-bar .tab').forEach(tab => tab.classList.remove('on'));
  if (btn) btn.classList.add('on');
  renderReviewProjects();
}

function renderReviewProjects() {
  const box = document.getElementById('reviewProjectsBox');
  if (!box) return;
  const rows = reviewFilter === 'all'
    ? reviewProjectsCache
    : reviewProjectsCache.filter(project => normalizeText(project.status) === normalizeText(reviewFilter));

  if (!rows.length) {
    box.innerHTML = '<div>No projects in this filter.</div>';
    return;
  }

  box.innerHTML = rows.map(project => `
    <div class="eval-proj-card u-540daf2c" style="margin-bottom:14px">
      <div class="u-3670a192">
        <div>
          <div class="u-4b40f770">${escapeHtml(project.title || 'Untitled Project')}</div>
          <div class="u-7d16b22c">${escapeHtml(project.team_members || 'No team members')} · ${escapeHtml(project.supervisor_name || 'No supervisor yet')}</div>
        </div>
        ${reviewBadge(project.status)}
      </div>
      <div class="u-63e9554f">${escapeHtml(project.abstract || 'No abstract provided.')}</div>
      <div class="u-1c86650a">
        <span class="u-9ca6aa56">${escapeHtml(project.project_type || 'other')}</span>
        <span class="u-d5dc922a">Files: ${escapeHtml(project.files_count || 0)}</span>
      </div>
      <div class="field-wrap">
        <div class="field-label">Reviewer Notes</div>
        <textarea class="field-textarea u-f9368ae0" id="reviewNotes_${project.project_id}" placeholder="Add notes...">${escapeHtml(project.coordinator_notes || '')}</textarea>
      </div>
      <div class="btn-row">
        <button class="btn btn-success" type="button" onclick="saveReviewDecision(${project.project_id}, 'accepted')">✓ Accept</button>
        <button class="btn btn-danger" type="button" onclick="saveReviewDecision(${project.project_id}, 'rejected')">✗ Reject</button>
        <button class="btn btn-outline" type="button" onclick="saveReviewDecision(${project.project_id}, 'needs_revision')">Request Revision</button>
        <button class="btn btn-primary" type="button" onclick="saveReviewDecision(${project.project_id}, 'send_to_committee')">Send to Committee</button>
      </div>
    </div>
  `).join('');
}

async function loadReviewProjects() {
  if (!document.getElementById('pg-review')) return;
  const msg = document.getElementById('reviewMsg');
  try {
    if (msg) msg.textContent = 'Loading...';
    const res = await fetch('/api/coordinator/review-projects');
    const data = await readApiJson(res);
    if (!res.ok) throw new Error(data.error || 'Failed to load projects.');
    reviewProjectsCache = data.projects || [];
    if (msg) msg.textContent = '';
    renderReviewProjects();
  } catch (err) {
    if (msg) {
      msg.style.color = '#c62828';
      msg.textContent = err.message;
    }
    const box = document.getElementById('reviewProjectsBox');
    if (box) box.innerHTML = `<div>${escapeHtml(err.message)}</div>`;
  }
}

async function saveReviewDecision(projectId, decision) {
  const notes = document.getElementById(`reviewNotes_${projectId}`)?.value || '';
  const msg = document.getElementById('reviewMsg');
  try {
    if (msg) {
      msg.style.color = '#444';
      msg.textContent = 'Saving decision...';
    }
    const res = await fetch(`/api/coordinator/review-project/${projectId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, notes })
    });
    const data = await readApiJson(res);
    if (!res.ok) throw new Error(data.error || 'Failed to save decision.');
    if (msg) {
      msg.style.color = 'green';
      msg.textContent = data.message || 'Saved successfully.';
    }
    await loadReviewProjects();
  } catch (err) {
    if (msg) {
      msg.style.color = '#c62828';
      msg.textContent = err.message;
    }
    alert(err.message);
  }
}


/* =========================
   DASHBOARD / INTERNAL PAGE BUTTONS
   Fix for buttons that use data-go="review", data-go="registration", data-go="committee", etc.
========================= */
function bindCoordinatorPageButtons() {
  document.querySelectorAll('[data-go]').forEach(btn => {
    if (btn.dataset.navBound === '1') return;
    btn.dataset.navBound = '1';

    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const page = (btn.dataset.go || '').trim();
      if (!page) return;

      const urls = {
        dashboard: '/coordinator/dashboard',
        registration: '/coordinator/registration',
        hours: '/coordinator/hours',
        review: '/coordinator/review',
        committee: '/coordinator/committee',
        evaluation: '/coordinator/evaluation',
        lectures: '/coordinator/lectures',
        search: '/coordinator/search',
        notifs: '/coordinator/notifs',
        ai: '/coordinator/ai',
        profile: '/coordinator/profile'
      };

      window.location.href = urls[page] || `/coordinator/${encodeURIComponent(page)}`;
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  applySidebarState();
  bindSidebarHover();
  bindTabs();
  bindCoordinatorPageButtons();
  bindAI();
  initRegistrationPage();
  initCommitteePage();
  loadDashboardData();
  loadReviewProjects();
});
