const SIDEBAR_PIN_KEY = 'coordSidebarPinned';
let sidebarPinned = false;

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

function statusBadge(status) {
  const value = (status || '').toLowerCase();
  if (value === 'accepted' || value === 'under_review' || value === 'committee_evaluation') return '<span class="pill p-accepted">Assigned ✓</span>';
  if (value === 'submitted') return '<span class="pill p-review">Being Assigned</span>';
  return `<span class="pill p-pending">${status || 'Pending'}</span>`;
}

function buildProfessorOptions(professors) {
  return ['<option value="">Select a professor...</option>'].concat(
    professors.map(p => `<option value="${p.faculty_id}">${p.full_name} (${p.assigned_projects} projects)</option>`)
  ).join('');
}

async function loadDistributionData() {
  const tableBody = document.getElementById('distributionFormsBody');
  const unassignedBox = document.getElementById('unassignedStudentsBox');
  const sectionsList = document.getElementById('sectionsList');
  const sectionSupervisor = document.getElementById('sectionSupervisor');
  if (!tableBody && !unassignedBox && !sectionsList) return;

  try {
    const res = await fetch('/api/coordinator/distribution-data');
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to load distribution data.');

    if (tableBody) {
      tableBody.innerHTML = data.forms.length ? data.forms.map(form => `
        <tr>
          <td>${form.group_name || '—'}</td>
          <td>${form.team_members || '—'}</td>
          <td>${form.preferred_1 || '—'}</td>
          <td>${form.preferred_2 || '—'}</td>
          <td>${form.preferred_3 || '—'}</td>
          <td>${form.title || '—'}</td>
          <td>${statusBadge(form.status)}</td>
        </tr>
      `).join('') : '<tr><td colspan="7">No submissions yet.</td></tr>';
    }

    if (unassignedBox) {
      const opts = buildProfessorOptions(data.professors || []);
      unassignedBox.innerHTML = data.unassigned_students.length ? data.unassigned_students.map(student => `
        <div class="u-2a06ea22">
          <div class="member-avatar u-01ebd179">${student.full_name.split(' ').map(x => x[0]).slice(0,2).join('')}</div>
          <div class="u-d5e8c5f3">
            <div class="u-0e49e1b3">${student.full_name}</div>
            <div class="u-7d16b22c">${student.university_id}</div>
          </div>
          <select class="field-select u-b103e901" id="faculty-${student.student_id}">${opts}</select>
          <button class="btn btn-primary u-d59a4528" type="button" onclick="assignStudent(${student.student_id})">Assign</button>
        </div>
      `).join('') : '<div>All students are already assigned.</div>';
    }

    if (sectionSupervisor) sectionSupervisor.innerHTML = buildProfessorOptions(data.professors || []);

    if (sectionsList) {
      sectionsList.innerHTML = data.sections.length ? data.sections.map(section => `
        <div class="u-e83423b7">
          <span class="u-adf67d91">${section.section_name} — ${section.supervisor_name}</span>
          <span class="pill p-accepted u-49f06467">Entered ✓</span>
        </div>
      `).join('') : '<div>No sections entered yet.</div>';
    }

    document.getElementById('statTotal').textContent = data.stats.total_registered_students || 0;
    document.getElementById('statAssigned').textContent = data.stats.assigned || 0;
    document.getElementById('statWaiting').textContent = data.stats.waiting || 0;
    document.getElementById('statGroups').textContent = data.stats.active_groups || 0;
  } catch (err) {
    if (tableBody) tableBody.innerHTML = `<tr><td colspan="7">${err.message}</td></tr>`;
  }
}

async function assignStudent(studentId) {
  const facultyId = document.getElementById(`faculty-${studentId}`)?.value;
  if (!facultyId) return alert('Select a professor first.');
  const res = await fetch('/api/coordinator/assign-student', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ student_id: studentId, faculty_id: facultyId })
  });
  const data = await res.json();
  alert(data.message || data.error || 'Done.');
  if (res.ok) loadDistributionData();
}

async function addSectionEntry() {
  const section_name = document.getElementById('sectionName')?.value.trim();
  const supervisor_id = document.getElementById('sectionSupervisor')?.value;
  const box = document.getElementById('sectionMsg');
  const res = await fetch('/api/coordinator/add-section', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ section_name, supervisor_id })
  });
  const data = await res.json();
  box.textContent = data.message || data.error || 'Done.';
  box.style.color = res.ok ? 'green' : 'crimson';
  if (res.ok) {
    document.getElementById('sectionName').value = '';
    document.getElementById('sectionSupervisor').value = '';
    loadDistributionData();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  applySidebarState();
  bindSidebarHover();
  bindTabs();
  bindAI();
  loadDistributionData();
});
