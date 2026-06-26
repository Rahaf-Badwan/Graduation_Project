document.addEventListener('DOMContentLoaded', function(){
  document.getElementById('ann-modal-link').textContent =
    window.location.origin + '/activate';
    loadCurrentAnn();
});

function escapeAnnHtml(value){
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function renderCurrentAnn(ann){
  var box = document.getElementById('ann-current-info');
  if(!box || !ann) return;

  var daysLeft = Number(ann.days_left || 0);
  box.style.display = 'block';
  box.innerHTML =
    '<strong>Active announcement:</strong> ' + escapeAnnHtml(ann.message) + '<br>' +
    '<span style="opacity:.8;">' +
    '<span class="material-symbols-outlined icon-inline">hourglass_bottom</span> ' +
    daysLeft + ' day' + (daysLeft !== 1 ? 's' : '') +
    ' remaining - expires on ' + escapeAnnHtml(ann.expires_at) +
    '</span>';
}

async function loadCurrentAnn(){
  try{
    var res = await fetch('/head/api/announcements/active');
    var data = await res.json();
    if(data.announcement){
      renderCurrentAnn(data.announcement);
    }
  }catch(e){}
}

function copyLink(){
  var link = window.location.origin + '/activate';

  if(navigator.clipboard && window.isSecureContext){
    navigator.clipboard.writeText(link).then(function(){
      showFeedback_ann('Link copied!', 'success');
    });
  }else{
    var el = document.createElement('textarea');
    el.value = link;
    document.body.appendChild(el);
    el.select();
    document.execCommand('copy');
    document.body.removeChild(el);
    showFeedback_ann('Link copied!', 'success');
  }
}
function openAnnModal(){
  document.getElementById('ann-overlay').classList.add('open');
}

function closeAnnModal(e){
  if(e && e.target !== document.getElementById('ann-overlay')) return;
  document.getElementById('ann-overlay').classList.remove('open');
  hideFeedback_ann();
}



async function createAnnModal(){
  hideFeedback_ann();
  var msg = document.getElementById('ann-msg').value.trim();
  var days = parseInt(document.getElementById('ann-days').value, 10);
  if(!msg){
    showFeedback_ann('Please write the announcement message before publishing.', 'warn');
    return;
  }
  if(!Number.isFinite(days) || days < 1 || days > 90){
    showFeedback_ann('Choose a duration between 1 and 90 days.', 'warn');
    return;
  }

  var btn = document.querySelector('#ann-overlay .btn.btn-primary');
  btn.disabled = true;
  btn.textContent = 'Publishing...';
  
  try{
    var res = await fetch('/head/api/announcements/create', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: msg, days: days})
    });
    var data = await res.json().catch(function(){ return {}; });

    if(res.ok){
      showFeedback_ann(
        'Announcement published successfully. It will expire on ' + data.expires_at + ' after ' + data.days + ' day' + (data.days !== 1 ? 's' : '') + '.',
        'success'
      );

      renderCurrentAnn({
        message: msg,
        days_left: data.days,
        expires_at: data.expires_at
      });

      document.getElementById('ann-msg').value = '';
    }else{
      showFeedback_ann(data.error || 'The announcement could not be published. Please review the details and try again.', 'error');
    }
  }catch(e){
    showFeedback_ann('Unable to publish the announcement right now. Please check your connection and try again.', 'error');
  }finally{
    btn.disabled = false; 
    btn.innerHTML = 'Publish &#x2197;';
  }
}

function showFeedback_ann(msg, type){
  var el = document.getElementById('ann-feedback');

  var s ={
    success: {color:'var(--color-text-success)', bg:'var(--color-background-success)', border:'var(--color-border-success)'},
    error: {color:'var(--color-text-danger)', bg:'var(--color-background-danger)', border:'var(--color-border-danger)'},
    warn: {color:'var(--color-text-warning)', bg:'var(--color-background-warning)', border:'var(--color-border-warning)'},
  }[type] || {};

  el.removeAttribute('style');
  el.style.display ='block';
  el.style.padding = '10px 14px';
  el.style.borderRadius ='8px';
  el.style.fontSize ='13px';
  el.style.color = s.color;
  el.style.background = s.bg;
  el.style.border = '0.5px solid ' + s.border;
  el.textContent = msg;
  clearTimeout(el._t);
  el._t = setTimeout(hideFeedback_ann, 5000);
}

function hideFeedback_ann(){
  var el = document.getElementById('ann-feedback');
  if (el) el.style.display = 'none';
}
