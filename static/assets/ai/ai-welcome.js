/**
 * Welcome + project prompt cards (archived catalog only)
 */
const TYPE_LABEL = {
  ai: 'AI',
  web: 'Web',
  mobile: 'Mobile',
  security: 'Security',
  other: 'Other',
};

const TYPE_ICON = {
  ai: '🧠',
  web: '🌐',
  mobile: '📱',
  security: '🔒',
  other: '📦',
};

function escapeHtml(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escapeAttr(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/</g, '&lt;');
}

function projectQuestion(title) {
  return (
    `Provide a professional summary of the archived graduation project "${title}" based on the final PDF report: ` +
    `1) the project idea and problem it solves, 2) technologies and tools, 3) key results and recommendations. ` +
    `If the report text is not available, use only the catalog data and mention that clearly.`
  );
}

function buildWelcomeHtml(projects) {
  const name = (window.APMS_AI_FIRST_NAME || 'Guest').replace(/[<>&"']/g, '');
  const list = Array.isArray(projects) ? projects : [];
  const count = list.length;

  const sorted = [...list].sort((a, b) => Number(b.final_score || 0) - Number(a.final_score || 0));

  const cards = sorted
    .map((p) => {
      const title = escapeHtml(p.title);
      const type = p.project_type || 'other';
      const typeLabel = TYPE_LABEL[type] || type;
      const icon = TYPE_ICON[type] || '📄';
      const score = p.final_score != null ? p.final_score : '—';
      const q = projectQuestion(p.title);
      const label = p.title;
      return `
      <button type="button" class="prompt-card" data-type="${type}"
        data-label="${escapeAttr(label)}"
        data-question="${escapeAttr(q)}"
        aria-label="Ask about ${title}">
        <span class="prompt-card-icon">${icon}</span>
        <span class="prompt-card-body">
          <span class="prompt-card-title">${title}</span>
          <span class="prompt-card-meta">
            <span class="prompt-type">${typeLabel}</span>
            <span class="prompt-score">${score}</span>
          </span>
        </span>
      </button>`;
    })
    .join('');

  return `
    <div class="welcome-screen">
      <div class="welcome-brand">
        <div class="welcome-logo" aria-hidden="true">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M12 3L4 9v6l8 6 8-6V9l-8-6z"/>
          </svg>
        </div>
        <h1 class="welcome-heading">Hello ${name}</h1>
        <p class="welcome-sub">Choose one of <strong>${count}</strong> archived projects. Answers are based on the PDF report.</p>
      </div>
      <div class="projects-panel">
        <div class="projects-panel-head">
          <span>Archived Projects</span>
          <span class="projects-count">${count}</span>
        </div>
        <div class="prompt-grid prompt-grid--projects" id="suggestedWrap">
          ${cards || '<p class="welcome-empty">No archived projects are available right now.</p>'}
        </div>
      </div>
    </div>`;
}

window.buildApmsWelcome = function buildApmsWelcome() {
  return buildWelcomeHtml(window.APMS_ARCHIVED_PROJECTS || []);
};

window.loadApmsWelcome = async function loadApmsWelcome() {
  const body = document.getElementById('chatBody');
  if (!body) return;

  body.innerHTML = `<div class="welcome-screen welcome-loading"><div class="loading-dots"><span></span><span></span><span></span></div><p>Loading projects...</p></div>`;

  try {
    const res = await fetch('/api/ai/archived-projects');
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to load projects');

    window.APMS_ARCHIVED_PROJECTS = data.projects || [];
    window.APMS_ARCHIVED_COUNT = window.APMS_ARCHIVED_PROJECTS.length;
    body.innerHTML = buildWelcomeHtml(window.APMS_ARCHIVED_PROJECTS);

    const sub = document.querySelector('.sidebar-foot-sub');
    if (sub) sub.textContent = `${window.APMS_ARCHIVED_COUNT} archived projects`;
  } catch (err) {
    body.innerHTML = `<div class="welcome-screen"><p class="welcome-empty">${escapeHtml(err.message)}</p></div>`;
  }
};
