const SIDEBAR_PIN_KEY = 'apmsSidebarPinned';
let sidebarPinned = false;

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

function toggleSidebar() {
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

function appendStudentChatMessage(text, kind) {
  const body = document.getElementById('chatBody');
  if (!body) return;
  const msg = document.createElement('div');
  msg.className = 'chat-msg ' + (kind === 'user' ? 'chat-user' : 'chat-bot');
  msg.textContent = text;
  body.appendChild(msg);
  body.scrollTop = body.scrollHeight;
}

async function askAI() {
  const inp = document.getElementById('chatIn');
  if (!inp || !inp.value.trim()) return;
  const question = inp.value.trim();
  appendStudentChatMessage(question, 'user');
  inp.value = '';
  try {
    const res = await fetch('/api/ai/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question })
    });
    const data = await res.json();
    appendStudentChatMessage(data.answer || data.error || 'No response returned.', 'bot');
  } catch (err) {
    appendStudentChatMessage('Could not connect to the AI service.', 'bot');
  }
}

function setQ(q) {
  const inp = document.getElementById('chatIn');
  if (inp) { inp.value = q; inp.focus(); }
}

async function loadSupervisorsForStudentDistribution() {
  const selects = [document.getElementById('pref1'), document.getElementById('pref2'), document.getElementById('pref3')].filter(Boolean);
  if (!selects.length) return;
  try {
    const res = await fetch('/api/coordinator/distribution-data');
    const data = await res.json();
    if (!data.professors) return;
    for (const select of selects) {
      data.professors.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.faculty_id;
        opt.textContent = p.full_name;
        select.appendChild(opt);
      });
    }
  } catch (e) {}
}

async function submitDistributionProject() {
  const messageBox = document.getElementById('distMsg');
  const payload = {
    title: document.getElementById('distTitle')?.value || '',
    group_name: document.getElementById('distGroup')?.value || '',
    abstract: document.getElementById('distAbstract')?.value || '',
    keywords: document.getElementById('distKeywords')?.value || '',
    preferred_supervisors: [
      document.getElementById('pref1')?.value,
      document.getElementById('pref2')?.value,
      document.getElementById('pref3')?.value,
    ].filter(Boolean),
    member_ids: Array.from(document.querySelectorAll('.member-id')).map(i => i.value.trim()).filter(Boolean),
  };
  try {
    const res = await fetch('/api/student/distribution-submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    messageBox.textContent = data.message || data.error || 'Done.';
    messageBox.style.color = res.ok ? 'green' : 'crimson';
  } catch (err) {
    messageBox.textContent = 'Could not submit the project.';
    messageBox.style.color = 'crimson';
  }
}

function clearDistributionForm() {
  ['distTitle', 'distGroup', 'distAbstract', 'distKeywords', 'pref1', 'pref2', 'pref3'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  document.querySelectorAll('.member-id').forEach(el => el.value = '');
  const box = document.getElementById('distMsg');
  if (box) box.textContent = '';
}

document.addEventListener('DOMContentLoaded', () => {
  applySidebarState();
  bindSidebarHover();
  document.getElementById('chatIn')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') askAI();
  });
  loadSupervisorsForStudentDistribution();
});
