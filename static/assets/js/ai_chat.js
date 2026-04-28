// APMS AI chat client
// Shared by student, coordinator, and head AI pages.
let currentSessionId = makeSessionId();
let replyToText = null;
const ARCHIVE_PREF_KEY = 'apms-ai-archive-open';
const AI_API_TIMEOUT_MS = 70000;

function makeSessionId() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  return 'chat_' + Date.now() + '_' + Math.random().toString(36).slice(2, 12);
}

function scrollBottom() {
  const scroller = document.querySelector('.content-area');
  requestAnimationFrame(() => {
    if (scroller) scroller.scrollTop = scroller.scrollHeight;
    else window.scrollTo(0, document.documentElement.scrollHeight);
  });
}

function escapeHtml(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

async function readJsonResponse(res) {
  try {
    return await res.json();
  } catch (err) {
    return { error: `Server returned a non-JSON response (HTTP ${res.status}). Please check Flask terminal errors.` };
  }
}

async function fetchJson(url, options = {}, timeoutMs = AI_API_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    const data = await readJsonResponse(res);
    return { res, data };
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new Error('Request timed out. The server or AI service is taking too long to respond.');
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

// ── Reply feature ──
function hasReplyUi() {
  return Boolean(document.getElementById('replyBar') && document.getElementById('replyBarText'));
}

function setReply(text) {
  if (!hasReplyUi()) return;
  replyToText = text;
  const bar  = document.getElementById('replyBar');
  const span = document.getElementById('replyBarText');
  const preview = String(text || '').length > 80 ? String(text).slice(0, 80) + '…' : String(text || '');
  span.textContent = preview;
  bar.style.display = 'flex';
  document.getElementById('chatIn')?.focus();
}

function cancelReply() {
  replyToText = null;
  const bar = document.getElementById('replyBar');
  if (bar) bar.style.display = 'none';
}

// ── Message builder ──
function applyInline(text) {
  let s = escapeHtml(text);
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/`([^`]+)`/g, '<code style="background:#eef;padding:1px 4px;border-radius:3px;font-size:12px">$1</code>');
  return s;
}

function formatResponse(text) {
  let sourceHtml = '';
  let body = String(text || '');

  if (body.startsWith('Based on uploaded PDFs:')) {
    sourceHtml = '<span class="msg-source pdf">📄 From uploaded PDFs</span>';
    body = body.replace('Based on uploaded PDFs:', '').trim();
  } else if (body.startsWith('Based on APMS data:')) {
    sourceHtml = '<span class="msg-source db">🗄 From APMS database</span>';
    body = body.replace('Based on APMS data:', '').trim();
  } else if (body.startsWith('General AI answer:')) {
    sourceHtml = '<span class="msg-source ai">🤖 General AI</span>';
    body = body.replace('General AI answer:', '').trim();
  }

  const lines = body.split('\n');
  let html = '';
  let inList = false;

  for (let line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      if (inList) { html += '</ul>'; inList = false; }
      html += '<div style="height:6px"></div>';
      continue;
    }

    const isBullet = /^[-•*]\s/.test(trimmed) || /^\d+\.\s/.test(trimmed);
    if (isBullet) {
      if (!inList) { html += '<ul class="bot-list">'; inList = true; }
      const ct = trimmed.replace(/^[-•*\d\.]+\s*/, '');
      html += '<li dir="auto">' + applyInline(ct) + '</li>';
    } else {
      if (inList) { html += '</ul>'; inList = false; }
      html += '<p style="margin:0 0 6px 0" dir="auto">' + applyInline(trimmed) + '</p>';
    }
  }

  if (inList) html += '</ul>';
  return (sourceHtml ? '<div style="margin-bottom:10px">' + sourceHtml + '</div>' : '') + html;
}

function addMessage(content, kind, quotedText) {
  const body = document.getElementById('chatBody');
  if (!body) return null;

  const wrap = document.createElement('div');
  wrap.className = 'chat-msg-wrap ' + (kind === 'user' ? 'user-wrap' : 'bot-wrap');

  const bubble = document.createElement('div');
  bubble.className = 'chat-msg ' + (kind === 'user' ? 'chat-user' : 'chat-bot');
  bubble.setAttribute('dir', 'auto');

  if (quotedText) {
    const q = document.createElement('div');
    q.className = 'reply-quote';
    q.textContent = String(quotedText).length > 90 ? String(quotedText).slice(0, 90) + '…' : String(quotedText);
    bubble.appendChild(q);
  }

  const msgContent = document.createElement('div');
  if (kind === 'user') msgContent.textContent = content;
  else msgContent.innerHTML = content;
  bubble.appendChild(msgContent);
  wrap.appendChild(bubble);

  if (kind === 'bot' && hasReplyUi()) {
    const replyBtn = document.createElement('button');
    replyBtn.className = 'reply-btn';
    replyBtn.innerHTML = '↩ Reply';
    replyBtn.onclick = () => setReply((bubble.innerText || bubble.textContent || '').trim().slice(0, 200));
    wrap.appendChild(replyBtn);
  }

  body.appendChild(wrap);
  scrollBottom();
  return wrap;
}

function showLoading() {
  const body = document.getElementById('chatBody');
  if (!body) return;
  hideLoading();
  const div  = document.createElement('div');
  div.id = 'loadingBubble';
  div.className = 'chat-loading';
  div.innerHTML = '<span></span><span></span><span></span>';
  body.appendChild(div);
  scrollBottom();
}

function hideLoading() {
  const el = document.getElementById('loadingBubble');
  if (el) el.remove();
}

// ── Archive ──
function formatArchiveDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function syncArchiveUi() {
  const wrap = document.getElementById('aiWrap');
  const btn = document.getElementById('archiveToggleBtn');
  const backdrop = document.getElementById('archiveBackdrop');
  const isOpen = wrap ? !wrap.classList.contains('archive-collapsed') : true;
  if (btn) {
    btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    btn.setAttribute('title', isOpen ? 'Hide archive' : 'Show archive');
  }
  if (backdrop) backdrop.classList.toggle('show', isOpen && window.innerWidth <= 900);
}

function setArchiveOpen(open, remember = true) {
  const wrap = document.getElementById('aiWrap');
  if (!wrap) return;
  wrap.classList.toggle('archive-collapsed', !open);
  syncArchiveUi();
  if (remember) localStorage.setItem(ARCHIVE_PREF_KEY, open ? '1' : '0');
}

function toggleArchive() {
  const wrap = document.getElementById('aiWrap');
  if (!wrap) return;
  setArchiveOpen(wrap.classList.contains('archive-collapsed'));
}

function resetWelcome() {
  const body = document.getElementById('chatBody');
  if (!body) return;
  const firstName = escapeHtml(window.APMS_AI_FIRST_NAME || 'there');
  body.innerHTML = `
    <div class="chat-msg-wrap bot-wrap">
      <div class="chat-msg chat-bot">Hello ${firstName}! I can provide you with comprehensive reports and analyses on projects, supervisor performance, and comparisons with previous years.</div>
    </div>
    <div class="chat-msg-wrap bot-wrap">
      <div class="chat-msg chat-bot">Try for example: "Compare AI vs web projects over 3 years" or "Who is the top supervisor this semester?"</div>
    </div>
    <div class="suggested-wrap" id="suggestedWrap">
      <div class="suggested-label">Suggested Questions</div>
      <div class="suggested-grid">
        <button class="suggested-btn" onclick="sendSuggested('Compare the performance of AI projects vs web development over the last 3 years')">📊 Compare discipline performance</button>
        <button class="suggested-btn" onclick="sendSuggested('Who is the top-performing supervisor this semester?')">🏆 Top-performing supervisor</button>
        <button class="suggested-btn" onclick="sendSuggested('What is the trend in project grades over the last five years?')">📈 Grade trend — 5 years</button>
        <button class="suggested-btn" onclick="sendSuggested('How many projects were rejected this semester and what were the reasons?')">⚠ Analysis of rejected projects</button>
        <button class="suggested-btn" onclick="sendSuggested('Which students are still without a supervisor?')">👥 Students without supervisors</button>
        <button class="suggested-btn" onclick="sendSuggested('What projects scored above 90 this semester?')">⭐ Top-scored projects</button>
      </div>
    </div>`;
}

async function loadArchive(activeId = currentSessionId) {
  const list = document.getElementById('archiveList');
  if (!list) return;
  list.innerHTML = '<div class="archive-empty">Loading archive...</div>';

  try {
    const { res, data } = await fetchJson('/api/ai/archive', {}, 30000);
    if (!res.ok) throw new Error(data.error || 'Failed to load archive.');

    const conversations = data.conversations || [];
    if (!conversations.length) {
      list.innerHTML = '<div class="archive-empty">No archived chats yet. Start a conversation and it will appear here.</div>';
      return;
    }

    list.innerHTML = conversations.map(item => {
      const sessionId = escapeHtml(item.session_id);
      return `
      <div class="archive-item ${item.session_id === activeId ? 'active' : ''}" onclick="openArchivedChat('${sessionId}')">
        <div class="archive-item-title">${escapeHtml(item.title)}</div>
        <div class="archive-meta">
          <span>${formatArchiveDate(item.updated_at)} · ${Number(item.days_left || 0)} days left</span>
          <button class="archive-delete" type="button" onclick="deleteArchivedChat(event,'${sessionId}')">Delete</button>
        </div>
      </div>`;
    }).join('');
  } catch (err) {
    console.error('[AI archive]', err);
    list.innerHTML = `<div class="archive-error">Archive could not be loaded.<br><small>${escapeHtml(err.message)}</small></div>`;
  }
}

async function openArchivedChat(sessionId) {
  currentSessionId = sessionId;
  cancelReply();
  const body = document.getElementById('chatBody');
  if (!body) return;
  body.innerHTML = '';
  showLoading();

  try {
    const { res, data } = await fetchJson('/api/ai/archive/' + encodeURIComponent(sessionId), {}, 30000);
    hideLoading();
    if (!res.ok) throw new Error(data.error || 'Failed to open conversation.');

    if (!data.messages || !data.messages.length) {
      resetWelcome();
      return;
    }

    for (const msg of data.messages) {
      if (msg.role === 'user') addMessage(msg.text, 'user', msg.reply_to || null);
      else addMessage(formatResponse(msg.text), 'bot');
    }
    await loadArchive(sessionId);
    if (window.innerWidth <= 900) setArchiveOpen(false);
  } catch (err) {
    hideLoading();
    addMessage(formatResponse('⚠️ **Could not open this archived conversation.**\n- ' + err.message), 'bot');
  }
}

async function deleteArchivedChat(event, sessionId) {
  event.stopPropagation();
  if (!confirm('Delete this archived conversation?')) return;

  try {
    const { res, data } = await fetchJson('/api/ai/archive/' + encodeURIComponent(sessionId), { method: 'DELETE' }, 30000);
    if (!res.ok) throw new Error(data.error || 'Could not delete this conversation.');
    if (sessionId === currentSessionId) startNewChat(false);
    await loadArchive(currentSessionId);
  } catch (err) {
    alert('Could not delete this conversation: ' + err.message);
  }
}

function startNewChat(refreshArchive = true) {
  currentSessionId = makeSessionId();
  cancelReply();
  resetWelcome();
  const inp = document.getElementById('chatIn');
  if (inp) inp.focus();
  if (refreshArchive) loadArchive(currentSessionId);
  if (window.innerWidth <= 900) setArchiveOpen(false);
}

async function askAI() {
  const inp = document.getElementById('chatIn');
  const btn = document.getElementById('sendBtn');
  if (!inp || !inp.value.trim()) return;

  const question = inp.value.trim();
  const currentReply = replyToText;
  inp.value = '';
  cancelReply();

  const suggested = document.getElementById('suggestedWrap');
  if (suggested) suggested.remove();

  addMessage(question, 'user', currentReply);
  showLoading();
  if (btn) btn.disabled = true;
  if (inp) inp.disabled = true;

  try {
    const payload = { question, session_id: currentSessionId };
    if (currentReply) payload.reply_to = currentReply;

    const { res, data } = await fetchJson('/api/ai/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (data.session_id) currentSessionId = data.session_id;
    hideLoading();

    if (!res.ok) {
      addMessage(formatResponse('⚠️ **Error:** ' + (data.error || 'Unknown server error.')), 'bot');
    } else {
      addMessage(formatResponse(data.answer || data.error || 'No response returned.'), 'bot');
    }

    loadArchive(currentSessionId);
  } catch (err) {
    hideLoading();
    addMessage(formatResponse('⚠️ **Could not reach the server** — make sure `app.py` is running.\n- Error: ' + err.message), 'bot');
  } finally {
    if (btn) btn.disabled = false;
    if (inp) { inp.disabled = false; inp.focus(); }
  }
}

function sendSuggested(question) {
  const suggested = document.getElementById('suggestedWrap');
  if (suggested) suggested.remove();
  const inp = document.getElementById('chatIn');
  if (inp) inp.value = question;
  askAI();
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('chatIn')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') askAI();
  });

  const storedPref = localStorage.getItem(ARCHIVE_PREF_KEY);
  const defaultOpen = storedPref === null ? window.innerWidth > 900 : storedPref === '1';
  setArchiveOpen(defaultOpen, false);
  window.addEventListener('resize', () => syncArchiveUi());
  loadArchive();
});

window.setReply = setReply;
window.cancelReply = cancelReply;
window.setArchiveOpen = setArchiveOpen;
window.toggleArchive = toggleArchive;
window.startNewChat = startNewChat;
window.askAI = askAI;
window.sendSuggested = sendSuggested;
window.openArchivedChat = openArchivedChat;
window.deleteArchivedChat = deleteArchivedChat;
