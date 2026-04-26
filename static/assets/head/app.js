// ─── Head of Department — page-specific JS ────────────────────────────────
// toggleSidebar / applySidebarState / bindSidebarHover / askAI / setQ
// are all provided by the shared assets/js/app.js — do NOT redeclare here.

// ─── Tab bar (Overview page) ──────────────────────────────────────────────
function selectTab(id, el) {
  document.querySelectorAll('.tab-bar .tab').forEach(t => t.classList.remove('on', 'active'));
  if (el) { el.classList.add('on'); el.classList.add('active'); }
}
