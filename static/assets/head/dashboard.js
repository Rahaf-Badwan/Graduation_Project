const NOTIF_ICONS = {
  urgent_alert:        { icon: "flag",         bg: "var(--amber-light)"        },
  file_uploaded:       { icon: "description",  bg: "var(--teal-light)"         },
  committee_assigned:  { icon: "groups",        bg: "var(--blue-light)"         },
  deadline_reminder:   { icon: "schedule",      bg: "var(--coral-light)"        },
  feedback_received:   { icon: "rate_review",   bg: "var(--green-light)"        },
  status_changed:      { icon: "sync",          bg: "var(--purple-light)"       },
  supervisor_assigned: { icon: "person_add",    bg: "var(--teal-light)"         },
  project_reviewed:    { icon: "task_alt",      bg: "var(--green-light)"        },
  system:              { icon: "info",          bg: "var(--color-surface-alt)"  },
};

async function loadDashboard() {
  setLoadingState();

  try {
    const res = await fetch(`/head/api/dashboard-data`, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json();
    renderDashboard(data);

  } catch (err) {
    console.error("[Dashboard] fetch failed:", err);
    showError();
  }
}

function setLoadingState() {
  ["stat-projects", "stat-supervisors", "stat-acceptance", "stat-avg"]
    .forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = "…";
    });

  const coordEl = document.getElementById("coordinator-line");
  if (coordEl) coordEl.textContent = "Loading…";

  const notifEl = document.getElementById("notifications-list");
  if (notifEl) notifEl.innerHTML = loadingHTML();

  const specEl = document.getElementById("spec-list");
  if (specEl) specEl.innerHTML = loadingHTML();
}

function loadingHTML() {
  return `<div style="color:var(--color-text-secondary);font-size:13px;padding:8px 0">
            Loading…
          </div>`;
}

function renderDashboard(data) {

  // ── Stats ────────────────────────────────────────────────
  setText("stat-projects",    data.total_projects     ?? "—");
  setText("stat-supervisors", data.active_supervisors  ?? "—");
  setText("stat-acceptance",
    data.acceptance_rate != null ? `${data.acceptance_rate}%` : "—");
  setText("stat-avg",
    data.avg_grade ? data.avg_grade : "—");

  // ── Coordinator ──────────────────────────────────────────
  const coord = data.coordinator || {};
  setText("coordinator-line",
    coord.coordinator_name
      ? `Coordinator: ${coord.coordinator_name} — ${coord.coordinator_email}`
      : "No coordinator assigned for this semester."
  );

  // ── Notifications ────────────────────────────────────────
  const notifEl = document.getElementById("notifications-list");
  if (notifEl) {
    notifEl.innerHTML = (data.notifications && data.notifications.length)
      ? data.notifications.map(renderNotif).join("")
      : `<div style="color:var(--color-text-secondary);font-size:13px;padding:8px 0">
           No notifications yet.
         </div>`;
  }

  // ── Specializations ──────────────────────────────────────
  const specEl = document.getElementById("spec-list");
  if (specEl) {
    specEl.innerHTML = (data.specializations && data.specializations.length)
      ? data.specializations.map(renderSpecBar).join("")
      : `<div style="color:var(--color-text-secondary);font-size:13px;padding:8px 0">
           No grade data available yet.
         </div>`;
  }
}

function renderNotif(n) {
  const cfg  = NOTIF_ICONS[n.notification_type] || NOTIF_ICONS["system"];
  const dot  = n.is_read ? "" : `<div class="notif-dot-red"></div>`;
  const when = n.created_at ? `&middot; ${timeAgo(n.created_at)}` : "";

  return `
    <div class="notif-item ${n.is_read ? "" : "unread"}">
      <div class="notif-icon-wrap" style="background:${cfg.bg}">
        <span class="material-symbols-outlined icon-inline" style="font-size:15px">
          ${cfg.icon}
        </span>
      </div>
      <div style="flex:1">
        <div class="notif-title">${escHtml(n.title)}</div>
        <div class="notif-meta">${escHtml(n.message)} ${when}</div>
      </div>
      ${dot}
    </div>`;
}

function renderSpecBar(s) {
  return `
    <div class="prog-wrap">
      <div class="prog-label">
        <span>${escHtml(s.label)}</span>
        <span>${s.avg} avg</span>
      </div>
      <div class="prog-bg">
        <div class="prog-fill"
             style="width:${s.width}%; background:${s.color}; transition:width .4s ease">
        </div>
      </div>
    </div>`;
}

function showError() {
  const msg = `<div style="color:var(--coral);font-size:13px;padding:8px 0">
                 Failed to load data. Please refresh the page.
               </div>`;
  const notifEl = document.getElementById("notifications-list");
  const specEl  = document.getElementById("spec-list");
  if (notifEl) notifEl.innerHTML = msg;
  if (specEl)  specEl.innerHTML  = msg;
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function escHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function timeAgo(dateStr) {
  const diff = Math.floor((Date.now() - new Date(dateStr)) / 1000);
  if (diff <    60) return "just now";
  if (diff <  3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} hr ago`;
  return `${Math.floor(diff / 86400)} days ago`;
}

document.addEventListener("DOMContentLoaded", () => {
  loadDashboard();
});

function switchRole() {
  fetch('/head/api/switch-role', { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
  .then(r => r.json())
  .then(d => { if (d.success) window.location.href = '/supervisor/dashboard'; });
}