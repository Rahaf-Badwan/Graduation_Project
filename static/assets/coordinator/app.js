const SIDEBAR_PIN_KEY = 'coordSidebarPinned';
let sidebarPinned = false;
let distributionWindowOpen = false;
let professorsCache = [];
let formsCache = [];
let unassignedCache = [];

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
    const data = await res.json();
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

function statusBadge(status) {
  const value = (status || '').toLowerCase();
  if (value === 'accepted' || value === 'under_review' || value === 'committee_evaluation') return '<span class="pill p-accepted">Assigned ✓</span>';
  if (value === 'submitted') return '<span class="pill p-review">Being Assigned</span>';
  return `<span class="pill p-pending">${escapeHtml(status || 'Pending')}</span>`;
}

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
  if (!statusText || !statusMeta || !btn) return;

  try {
    const res = await fetch('/api/coordinator/distribution-window');
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to load window status.');

    distributionWindowOpen = !!data.is_open;
    statusText.textContent = distributionWindowOpen ? 'Registration is OPEN' : 'Registration is CLOSED';

    const openedAt = data.opened_at ? `Opened at: ${data.opened_at}` : '';
    const closedAt = data.closed_at ? `Closed at: ${data.closed_at}` : '';
    statusMeta.textContent = distributionWindowOpen ? openedAt : closedAt;

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
  if (!btn) return;

  try {
    btn.disabled = true;
    if (msg) msg.textContent = 'Saving...';

    const res = await fetch('/api/coordinator/distribution-window', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_open: !distributionWindowOpen })
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to update registration window.');

    if (msg) msg.textContent = data.message || 'Updated successfully.';
    await loadDistributionWindow();
  } catch (err) {
    if (msg) msg.textContent = err.message || 'Something went wrong.';
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
    const data = await res.json();
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
    if (msg) msg.textContent = 'Please choose a supervisor before saving.';
    return;
  }

  try {
    if (msg) msg.textContent = 'Saving group supervisor...';

    const res = await fetch('/api/coordinator/assign-group-supervisor', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: projectId,
        supervisor_id: supervisorId
      })
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to assign supervisor.');

    if (msg) msg.textContent = data.message || 'Supervisor assigned successfully.';
    await loadDistributionData();
  } catch (err) {
    if (msg) msg.textContent = err.message || 'Something went wrong while assigning the supervisor.';
  }
}

async function addSectionEntry() {
  const sectionName = document.getElementById('sectionName')?.value.trim();
  const supervisorId = document.getElementById('sectionSupervisor')?.value;
  const selectedStudents = getSelectedStudentIds();
  const msg = document.getElementById('sectionMsg');
  const addBtn = document.querySelector('button[onclick="addSectionEntry()"]');

  if (!sectionName || !supervisorId) {
    if (msg) msg.textContent = 'Please enter the section name and choose a supervisor.';
    return;
  }

  if (!selectedStudents.length) {
    if (msg) msg.textContent = 'Please choose at least one unassigned student.';
    return;
  }

  if (selectedStudents.length > 3) {
    if (msg) msg.textContent = 'You can choose at most 3 students.';
    return;
  }

  try {
    if (addBtn) addBtn.disabled = true;
    if (msg) msg.textContent = 'Saving...';

    const res = await fetch('/api/coordinator/add-section', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        section_name: sectionName,
        supervisor_id: supervisorId,
        student_ids: selectedStudents
      })
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to add section.');

    if (msg) msg.textContent = data.message || 'Section added successfully.';
    const sectionNameInput = document.getElementById('sectionName');
    const sectionSupervisor = document.getElementById('sectionSupervisor');
    if (sectionNameInput) sectionNameInput.value = '';
    if (sectionSupervisor) sectionSupervisor.value = '';
    await loadDistributionData();
  } catch (err) {
    if (msg) msg.textContent = err.message || 'Something went wrong while adding the section.';
  } finally {
    if (addBtn) addBtn.disabled = false;
  }
}

function initRegistrationPage() {
  if (!document.getElementById('pg-registration')) return;
  loadDistributionWindow();
  loadDistributionData();
}

document.addEventListener('DOMContentLoaded', () => {
  applySidebarState();
  bindSidebarHover();
  bindTabs();
  bindAI();
  initRegistrationPage();
});