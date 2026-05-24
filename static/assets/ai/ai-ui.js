/**
 * Confirm dialog used by the AI archive delete action.
 */

/** @returns {Promise<boolean>} */
function apmsConfirm({ title, message, confirmText = 'Delete', cancelText = 'Cancel' }) {
  return new Promise((resolve) => {
    const overlay = document.getElementById('confirmModal');
    if (!overlay) {
      resolve(window.confirm(message || title));
      return;
    }

    const titleEl = document.getElementById('confirmModalTitle');
    const msgEl = document.getElementById('confirmModalMessage');
    const btnOk = document.getElementById('confirmModalOk');
    const btnCancel = document.getElementById('confirmModalCancel');

    if (titleEl) titleEl.textContent = title || 'Confirm';
    if (msgEl) msgEl.textContent = message || '';
    if (btnOk) btnOk.textContent = confirmText;
    if (btnCancel) btnCancel.textContent = cancelText;

    const done = (value) => {
      overlay.classList.remove('is-open');
      overlay.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('modal-open');
      resolve(value);
    };

    const cleanup = () => {
      overlay.onclick = null;
      btnOk.onclick = null;
      btnCancel.onclick = null;
    };

    const onOk = () => { cleanup(); done(true); };
    const onCancel = () => { cleanup(); done(false); };
    const onBackdrop = (e) => {
      if (e.target === overlay) onCancel();
    };
    const onKey = (e) => {
      if (e.key === 'Escape') onCancel();
    };

    btnOk.onclick = onOk;
    btnCancel.onclick = onCancel;
    overlay.onclick = onBackdrop;
    document.addEventListener('keydown', onKey, { once: true });

    overlay.classList.add('is-open');
    overlay.setAttribute('aria-hidden', 'false');
    document.body.classList.add('modal-open');
    btnCancel.focus();
  });
}

function initApmsUi() {}

window.apmsConfirm = apmsConfirm;
window.initApmsUi = initApmsUi;
