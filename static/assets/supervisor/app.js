// ─── Supervisor — page-specific JS ─────────────────────────────────────────
// toggleSidebar / applySidebarState / bindSidebarHover / askAI / setQ
// are all provided by the shared assets/js/app.js and assets/js/ai_chat.js
// Do NOT redeclare them here.

// ─── Tab bar ───────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.tab').forEach(function (tab) {
    tab.addEventListener('click', function () {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('on'));
      this.classList.add('on');
    });
  });
});
