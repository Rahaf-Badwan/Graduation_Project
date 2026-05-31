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

function isStudentShell() {
  return document.body?.dataset.appRole === 'student';
}

function navigateStudent(href) {
  if (!href) return;
  const nextUrl = new URL(href, window.location.href);
  if (nextUrl.href === window.location.href) return;
  document.body.classList.add('student-nav-leaving');
  window.location.assign(nextUrl.href);
}

function isStudentPageUrl(href) {
  try {
    const url = new URL(href, window.location.href);
    return (
      url.origin === window.location.origin &&
      url.pathname.startsWith('/student/') &&
      !url.pathname.startsWith('/student/api/')
    );
  } catch (e) {
    return false;
  }
}

function bindStudentNavigation() {
  if (!isStudentShell()) return;

  const currentPage = document.body.dataset.page || 'dashboard';
  document.querySelectorAll('.sb-item[data-page]').forEach(link => {
    link.classList.toggle('on', link.dataset.page === currentPage);
    if (!link.dataset.tip) {
      link.dataset.tip = link.querySelector('.sb-label')?.textContent.trim() || '';
    }
  });

  document.addEventListener('click', event => {
    const link = event.target.closest?.('a[href]');
    if (
      !link ||
      !isStudentPageUrl(link.href) ||
      link.hasAttribute('download') ||
      event.defaultPrevented ||
      event.button !== 0 ||
      event.ctrlKey ||
      event.metaKey ||
      event.shiftKey ||
      event.altKey ||
      link.target === '_blank'
    ) {
      return;
    }
    event.preventDefault();
    navigateStudent(link.href);
  });

  document.querySelectorAll('[data-student-href]').forEach(control => {
    const go = () => navigateStudent(control.dataset.studentHref);
    control.addEventListener('click', go);
    control.addEventListener('keydown', event => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      go();
    });
  });
}

function setStudentNotificationBadge(badge, count) {
  if (!badge) return;
  badge.textContent = count > 99 ? '99+' : count;
  badge.style.display = count > 0 ? '' : 'none';
}

async function refreshStudentNotificationBadges() {
  if (!isStudentShell()) return;
  try {
    const res = await fetch('/student/api/notifications/unread-count');
    const data = await res.json();
    const count = Number(data.unread || 0);
    setStudentNotificationBadge(document.getElementById('notif-badge'), count);
    setStudentNotificationBadge(document.getElementById('sbNotifBadge'), count);
  } catch (e) {}
}

async function loadStudentTopbarInfo() {
  if (!isStudentShell()) return;
  const subtitle = document.getElementById('tbSub');
  const profileCourseBadge = document.getElementById('profileCourseBadge');
  try {
    const res = await fetch('/student/api/topbar-info');
    const data = await res.json();
    const year = data.academic_year ? ' · Semester ' + data.academic_year : '';
    const courseCode = data.course_code || 'COMP4200';
    if (subtitle) subtitle.textContent = courseCode + year;
    if (profileCourseBadge) profileCourseBadge.textContent = courseCode;
  } catch (e) {
    if (subtitle) subtitle.textContent = 'COMP4200';
    if (profileCourseBadge) profileCourseBadge.textContent = 'COMP4200';
  }
}

function initializeStudentShell() {
  if (!isStudentShell()) return;
  bindStudentNavigation();
  refreshStudentNotificationBadges();
  loadStudentTopbarInfo();
  window.setInterval(refreshStudentNotificationBadges, 60000);
}

window.addEventListener('pageshow', () => {
  document.body?.classList.remove('student-nav-leaving');
});

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
    const res = await fetch('/student/api/distribution-submit', {
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
  initializeStudentShell();
  document.getElementById('chatIn')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') askAI();
  });
  loadSupervisorsForStudentDistribution();
});
