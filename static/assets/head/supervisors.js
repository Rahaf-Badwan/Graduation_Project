/* ============================================================
   supervisors.js  —  APMS Supervisors Page
   Handles: active list, stats, inactive list for activation,
            Hours sidebar panel, send-hours-to-coordinator
   ============================================================ */

(function () {
  "use strict";

  /* ── State ─────────────────────────────────────── */
  let inactiveSupervisors = [];
  let hoursSupervisors    = [];
  let selectedUserId      = null;

  /* ── Specialization display map ────────────────── */
  const SPEC_LABELS = {
    software_engineering:  "Software Engineering",
    artificial_intelligence: "AI",
    web_development:       "Web Development",
    mobile:                "Mobile",
    security_networks:     "Security & Networks",
    databases:             "Databases",
    other:                 "Other",
  };

  /* ── Avatar colour pairs (bg / text) ───────────── */
  const AVATAR_COLOURS = [
    ["var(--blue-light)",  "var(--blue)"],
    ["#FBEAF0",            "#993556"],
    ["var(--teal-light)",  "var(--teal)"],
    ["#FEF3C7",            "#92400E"],
    ["#EDE9FE",            "#5B21B6"],
    ["#DCFCE7",            "#15803D"],
  ];
  function avatarColour(index) {
    return AVATAR_COLOURS[index % AVATAR_COLOURS.length];
  }

  /* ── Init ───────────────────────────────────────── */
  document.addEventListener("DOMContentLoaded", () => {
    loadSupervisors();
    loadStats();
    loadInactive();
    loadHours();
    bindHoursSend();
  });

  /* ════════════════════════════════════════════════
     ACTIVE SUPERVISORS LIST
  ════════════════════════════════════════════════ */
  async function loadSupervisors() {
    const container = document.getElementById("supervisors-list");
    if (!container) return;

    try {
      const res  = await fetch("/head/api/supervisors");
      const data = await res.json();

      if (!res.ok || !data.supervisors?.length) {
        container.innerHTML = `<div class="empty-state">No active supervisors found.</div>`;
        return;
      }

      container.innerHTML = data.supervisors
        .map((s, i) => buildSupervisorCard(s, i))
        .join("");
    } catch (e) {
      container.innerHTML = `<div class="empty-state" style="color:var(--red)">Failed to load supervisors.</div>`;
    }
  }

  function buildSupervisorCard(s, index) {
    const [bg, color] = avatarColour(index);
    const initials    = s.avatar_initials || initFrom(s.full_name);
    const spec        = SPEC_LABELS[s.specialization] || s.specialization || "—";
    const yrs         = s.years_experience ? `${s.years_experience} years experience` : "";
    const avg         = parseFloat(s.average_score || 0).toFixed(1);

    return `
    <div class="supervisor-card" style="border:0.5px solid var(--color-border-tertiary);border-radius:var(--rm);padding:12px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <div class="person-avatar"
             style="background:${bg};color:${color};width:40px;height:40px;font-size:13px">
          ${initials}
        </div>
        <div style="flex:1">
          <div class="person-name" style="font-size:14px">${escHtml(s.full_name)}</div>
          <div class="person-info">Specialization: ${spec}${yrs ? ` · ${yrs}` : ""}</div>
        </div>
        <span class="pill p-active">Active</span>
      </div>
      <div style="display:flex;gap:10px;font-size:12px">
        <div style="flex:1;text-align:center;background:var(--color-background-secondary);padding:6px;border-radius:var(--rm)">
          <div style="font-weight:700;color:var(--blue)">${s.this_semester || 0}</div>
          <div style="color:var(--color-text-secondary)">This Semester</div>
        </div>
        <div style="flex:1;text-align:center;background:var(--color-background-secondary);padding:6px;border-radius:var(--rm)">
          <div style="font-weight:700;color:var(--green)">${avg}</div>
          <div style="color:var(--color-text-secondary)">Average</div>
        </div>
        <div style="flex:1;text-align:center;background:var(--color-background-secondary);padding:6px;border-radius:var(--rm)">
          <div style="font-weight:700;color:var(--teal)">${s.total_projects || 0}</div>
          <div style="color:var(--color-text-secondary)">Total</div>
        </div>
      </div>
    </div>`;
  }

  /* ════════════════════════════════════════════════
     STATS SUMMARY (right panel top card)
  ════════════════════════════════════════════════ */
  async function loadStats() {
    try {
      const res  = await fetch("/head/api/supervisors/stats");
      const data = await res.json();
      if (!res.ok || !data.stats) return;

      const st = data.stats;
      setInner("stat-active-supervisors",      st.active_supervisors    ?? "—");
      setInner("stat-avg-projects",            st.avg_projects_per_supervisor ?? "—");
      setInner("stat-highest-avg",             st.highest_average        ?? "—");
      setInner("stat-lowest-avg",              st.lowest_average         ?? "—");

      const maxLoad = st.max_load ?? 0;
      const banner  = document.getElementById("distribution-banner");
      if (banner) {
        if (maxLoad <= 7) {
          banner.textContent = `✓ Distribution is fair — max load per supervisor: ${maxLoad} projects (within acceptable limit)`;
          banner.style.background = "var(--teal-light)";
          banner.style.color      = "var(--teal)";
        } else {
          banner.textContent = `⚠ Overloaded — max load per supervisor: ${maxLoad} projects (exceeds limit)`;
          banner.style.background = "#FEF3C7";
          banner.style.color      = "#92400E";
        }
      }
    } catch (_) {}
  }

  /* ════════════════════════════════════════════════
     INACTIVE SUPERVISORS TABLE (Add panel)
  ════════════════════════════════════════════════ */
  async function loadInactive() {
    const tbody = document.getElementById("inactive-supervisor-tbody");
    const empty = document.getElementById("inactive-empty");
    if (!tbody) return;

    try {
      const res  = await fetch("/head/api/supervisors/inactive");
      const data = await res.json();

      inactiveSupervisors = data.supervisors || [];

      if (!inactiveSupervisors.length) {
        tbody.innerHTML = "";
        if (empty) empty.style.display = "block";
        return;
      }

      if (empty) empty.style.display = "none";

      tbody.innerHTML = inactiveSupervisors.map((s, i) => {
        const [bg, color] = avatarColour(i);
        const spec  = SPEC_LABELS[s.specialization] || s.specialization || "—";
        const init  = s.avatar_initials || initFrom(s.full_name);
        return `
        <tr data-user-id="${s.user_id}">
          <td>
            <div style="display:flex;align-items:center;gap:8px">
              <div class="person-avatar"
                   style="background:${bg};color:${color};width:32px;height:32px;font-size:11px;flex-shrink:0">
                ${init}
              </div>
              <div>
                <div style="font-weight:600;font-size:13px">${escHtml(s.full_name)}</div>
                <div style="font-size:11px;color:var(--color-text-secondary)">${escHtml(s.email || "")}</div>
              </div>
            </div>
          </td>
          <td style="font-size:12px;color:var(--color-text-secondary)">${spec}</td>
          <td style="font-size:12px">${s.years_experience || 0} yrs</td>
          <td>
            <button class="btn btn-sm btn-primary activate-btn"
                    data-user-id="${s.user_id}"
                    data-name="${escAttr(s.full_name)}">
              Activate ↗
            </button>
          </td>
        </tr>`;
      }).join("");

      // Bind activate buttons
      tbody.querySelectorAll(".activate-btn").forEach(btn => {
        btn.addEventListener("click", () => openActivateModal(
          parseInt(btn.dataset.userId),
          btn.dataset.name
        ));
      });
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="4" style="color:var(--red);font-size:12px;text-align:center">Failed to load inactive supervisors.</td></tr>`;
    }
  }

  /* ── Activate Modal ─────────────────────────── */
  function openActivateModal(userId, name) {
    selectedUserId = userId;
    setInner("activate-modal-name", escHtml(name));
    clearField("activate-hours");
    clearField("activate-password");
    clearField("activate-confirm");
    setInner("activate-modal-error", "");
    showEl("supervisor-activate-modal");
  }

  window.closeActivateModal = function () {
    hideEl("supervisor-activate-modal");
    selectedUserId = null;
  };

  window.submitActivateSupervisor = async function () {
    const hours   = document.getElementById("activate-hours")?.value?.trim();
    const pass    = document.getElementById("activate-password")?.value || "";
    const confirm = document.getElementById("activate-confirm")?.value  || "";
    const errEl   = document.getElementById("activate-modal-error");

    if (!hours || !pass || !confirm) {
      if (errEl) errEl.textContent = "Please fill in all fields.";
      return;
    }
    if (parseFloat(hours) < 0) {
      if (errEl) errEl.textContent = "Hours cannot be negative.";
      return;
    }

    try {
      const res  = await fetch("/head/api/supervisors/activate", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id:                   selectedUserId,
          graduation_project_hours:  parseFloat(hours),
          password:                  pass,
          confirm_password:          confirm,
        }),
      });
      const data = await res.json();

      if (!res.ok) {
        if (errEl) errEl.textContent = data.error || "Activation failed.";
        return;
      }

      closeActivateModal();
      showToast("Supervisor activated successfully ✓", "success");
      // Refresh all panels
      loadSupervisors();
      loadStats();
      loadInactive();
      loadHours();
    } catch (_) {
      if (errEl) errEl.textContent = "Network error. Please try again.";
    }
  };

  /* ════════════════════════════════════════════════
     HOURS SIDEBAR PANEL
  ════════════════════════════════════════════════ */
  async function loadHours() {
    const container = document.getElementById("hours-list");
    if (!container) return;

    try {
      const res  = await fetch("/head/api/supervisors/hours");
      const data = await res.json();

      hoursSupervisors = data.supervisors || [];

      if (!hoursSupervisors.length) {
        container.innerHTML = `<div class="empty-state" style="font-size:12px">No data yet.</div>`;
        setInner("hours-total", "0 hrs");
        return;
      }

      container.innerHTML = hoursSupervisors.map((s, i) => {
        const [bg, color] = avatarColour(i);
        const init  = s.avatar_initials || initFrom(s.full_name);
        const hrs   = parseFloat(s.hours || 0);
        return `
        <div style="display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:0.5px solid var(--color-border-tertiary)">
          <div class="person-avatar"
               style="background:${bg};color:${color};width:30px;height:30px;font-size:10px;flex-shrink:0">
            ${init}
          </div>
          <div style="flex:1;min-width:0">
            <div style="font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
              ${escHtml(s.full_name)}
            </div>
            <div style="font-size:11px;color:var(--color-text-secondary)">
              ${SPEC_LABELS[s.specialization] || "—"}
            </div>
          </div>
          <div style="font-size:13px;font-weight:700;color:var(--teal);white-space:nowrap">
            ${hrs % 1 === 0 ? hrs : hrs.toFixed(1)} hrs
          </div>
        </div>`;
      }).join("");

      const total = hoursSupervisors.reduce((acc, s) => acc + parseFloat(s.hours || 0), 0);
      setInner("hours-total", `${total % 1 === 0 ? total : total.toFixed(1)} hrs`);
    } catch (_) {}
  }

  function bindHoursSend() {
    const btn = document.getElementById("send-hours-btn");
    if (!btn) return;

    btn.addEventListener("click", async () => {
      btn.disabled = true;
      btn.textContent = "Sending…";

      try {
        // Try to get current user id from page meta or default
        const senderMeta = document.querySelector('meta[name="current-user-id"]');
        const senderId   = senderMeta ? parseInt(senderMeta.content) : null;

        const res  = await fetch("/head/api/supervisors/hours/send", {
          method:  "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sender_user_id: senderId }),
        });
        const data = await res.json();

        if (!res.ok) {
          showToast(data.error || "Failed to send.", "error");
        } else {
          showToast("Hours summary sent to coordinator ✓", "success");
        }
      } catch (_) {
        showToast("Network error.", "error");
      } finally {
        btn.disabled    = false;
        btn.textContent = "Send to Coordinator ↗";
      }
    });
  }

  /* ── Helpers ────────────────────────────────── */
  function initFrom(name) {
    return (name || "?")
      .split(" ")
      .filter(Boolean)
      .slice(0, 2)
      .map(w => w[0].toUpperCase())
      .join("");
  }

  function escHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escAttr(str) {
    return String(str || "").replace(/"/g, "&quot;");
  }

  function setInner(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
  }

  function clearField(id) {
    const el = document.getElementById(id);
    if (el) el.value = "";
  }

  function showEl(id) {
    const el = document.getElementById(id);
    if (el) el.style.display = "";
  }

  function hideEl(id) {
    const el = document.getElementById(id);
    if (el) el.style.display = "none";
  }

  function showToast(msg, type) {
    if (typeof window.showNotification === "function") {
      window.showNotification(msg, type);
      return;
    }
    // Fallback simple toast
    const t = document.createElement("div");
    t.style.cssText = `
      position:fixed;bottom:24px;right:24px;z-index:9999;
      background:${type === "success" ? "var(--green, #16a34a)" : "var(--red, #dc2626)"};
      color:#fff;padding:10px 18px;border-radius:8px;font-size:13px;
      box-shadow:0 4px 16px rgba(0,0,0,.2);transition:opacity .4s;`;
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => { t.style.opacity = "0"; }, 2800);
    setTimeout(() => t.remove(), 3200);
  }
})();
