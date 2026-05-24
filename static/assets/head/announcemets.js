document.addEventListener('DOMContentLoaded', function(){
  document.getElementById('ann-modal-link').textContent =
    window.location.origin + '/activate';
    loadCurrentAnn();
});

async function loadCurrentAnn(){
  try{
    var res = await fetch('/api/announcements/active');
    var data = await res.json();
    if(data.announcement){
      var ann = data.announcement;
      var box = document.getElementById('ann-current-info');
      box.style.display = 'block';
      box.innerHTML = 
      '<strong>Active:</strong> ' + ann.message + '<br>' + 
      '<span style="opacity:.8;"> <span class="material-symbols-outlined">hourglass_bottom</span> ' + ann.days_left +
      ' day' + (ann.days_left !== 1 ? 's' : '') + ' remaining-expires ' +
      ann.expires_at + '</span>';
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
  var days = parseInt(document.getElementById('ann-days').value) || 20;
  if(!msg){
    showFeedback_ann('Please write a message first.', 'warn');
    return;
  }

  var btn = document.querySelector('#ann-overlay .btn.btn-primary');
  btn.disabled = true; btn.textContent = 'Publishing...';
  
  try{
    var res = await fetch('/head/api/announcements/create', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: msg, days: days})
    });
    var data = await res.json();

    if(res.ok){
      showFeedback_ann(
        'Published! Expires on' + data.expires_at + '(' + data.days + 'days).',
        'success'
      );

      //update box
      var box = document.getElementById('ann-current-info');
      box.style.display = 'block';
      box.innerHTML =
      '<strong>Active:</strong' + ann.msg + '<br>' +
      '<span style="opacity:.8;"> <span class="material-symbols-outlined icon-inline">hourglass_bottom</span> ' + ann.days_left +
      'day' + (ann.days_left !== 1 ? 's' : '') + 'remaining-expires' +
      ann.expires_at + '</span>';

      document.getElementById('ann-msg').value = '';
    }else{
      showFeedback_ann(data.error || 'Something went wrong.', 'error');
    }
  }catch(e){
    showFeedback_ann('Could not reach the server.', 'error');
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
  el.style.border = '0.5px solid' + s.border;
  el.textContent = msg;
  clearTimeout(el._t);
  el._t = setTimeout(hideFeedback_ann, 5000);
}

function hideFeedback_ann(){
  var el = document.getElementById('ann-feedback');
  if (el) el.style.display = 'none';
}
