/*------Add Student------------------------*/

const API_BASE = '/head';
var currentCourse = 'COMP4200';
var allStudents = [];

document.addEventListener('DOMContentLoaded', function() {
    loadStudents();
    setInterval(loadStudents, 30000);
});

/* --- Tabs ---*/

function selectTab(course, btn){
  currentCourse = course;
  document.querySelectorAll('.tab').forEach(function(b){
    b.classList.remove('active');
  });
  btn.classList.add('active');
  loadStudents();
}

async function loadStudents(){
  var list = document.getElementById('studentList');
  list.innerHTML = '<div style="padding:24px; color:var(--color-text-tertiary); font-size:13px;">Loading...</div>';


  try{
    /*await mean that can get ddata from api or server or database without stop the program */
    var res = await fetch(API_BASE + '/api/students/active?course=' + currentCourse);
    var data = await res.json();
    allStudents = data.students || [];
    renderStudents(allStudents);
  }catch (e){
    list.innerHTML = '<div style="padding:24px; color:var(--color-text-secondary); font-size:13px;">Could not connect to server.</div>';
    
  }
}

/* show the student */
function renderStudents(students){
  var list = document.getElementById('studentList');
  
  if(!students.length){
    list.innerHTML = 
       '<div style="paddding:32px; text-align:center; color:var(--color-text-tertiart); font-size:13px;">' +
          'No active students in ' + currentCourse +
        '</div>';
    return;    
  }
  list.innerHTML = students.map(function (s) {
    var initials = s.avatar_initials ||
       s.full_name.split(' ').map(function (w) { return w[0]; }).join('').slice(0, 2).toUpperCase();
    return(
      '<div class="student-row" style="'+
        'display:flex; align-items:center; gap:12px;' +
        'padding:12px 16px;' +
        'border-bottom:0.5px solid var(--color-border-tertiary);">' +
      
        '<div style="'+ 
          'width:34px; height:34px; border-radius:50%; flex-shrink:0;' +
          'background:var(--color-background-info);' + 
          'display: grid; place-items:center;' +
          'font-size:12px font-weight:600; color:var(--color-text-info);">' +
         initials +
        '</div>' +

        '<div style="flex:1; min-width:0;">' +
            '<div style="font-size:14px; font-weight:500; color:var(--color-var-primary);">' +
                s.full_name +
            '</div>' +
            '<div style="font-size:12px; color:var(--color-text-secondary); margin-top:2px;' +
                'white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">' +
                s.university_id + ' &middot; ' + s.email +
            '</div>'+
        '</div>'+
        '<span style="' + 
          'font-size:11px; font-weight:500; flex-shrink:0;' +
          'padding:3px 10px; border-radius:20px;' +
          'background:var(--color-background-success);' +
          'color:var(--color-text-success);' +
          'border:0.5px solid var(--color-border-success);">' +
          'Active' +
        '</span>' +
      '</div>'
    );
  }).join('');
}

/*--add student with is-active=0 and course=COMP4200 */
async function addStudent(){
  var name = document.getElementById('fullName').value.trim();
  var uid = document.getElementById('universityId').value.trim();

   hideFeedback();

  if(!name || !uid){
    showFeedback('Please fill in Name and University ID.', 'warn');
    return;
  }

  var addBtn = document.querySelector('.btn.btn-primary');
  addBtn.disabled = true;
  addBtn.textContent = 'Adding...';

  try{
    var res = await fetch(API_BASE + '/api/students/add', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({full_name: name, university_id: uid})
    });
    var data = await res.json();

    if(res.ok){
      clearForm(false);
      showFeedback(data.message || 'تم إضافة الطالب بنجاح. حالة الحساب: بانتظار التفعيل.', 'success');
      loadStudents();
    }else{
      showFeedback(data.error || 'Something went wrong.', 'error');
    }
  }catch(e){
    showFeedback('Could not reach the server.', 'error');
  }finally{
    addBtn.disabled = false;
    addBtn.innerHTML = 'Confirm New Student &#x2197;';
  }
}

/*clear the form */
function clearForm(hideMessage){
  if(hideMessage === undefined) hideMessage = true;

  ['fullName', 'universityId'].forEach(function(id){
    var el = document.getElementById(id);
    if(el) el.value = '';
  });

  var textarea = document.querySelector('.field-textarea');
  if(textarea) textarea.value = '';
  if(hideMessage) hideFeedback();
}

/*feedback to head of department to know if the student add or any something happen */
function showFeedback(msg, type){
  var feedback = document.getElementById('add-feedback');
  if(!feedback) return;

  feedback.style.display = 'block';

  var styles = {
   success: {
    color: 'var(--color-text-success)',
    background: 'var(--color-background-success)',
    border: 'var(--color-border-success)'
   },
   error: {
    color: 'var(--color-text-danger)',
    background: 'var(--color-background-danger)',
    border: 'var(--color-border-danger)'
   },
   warn: {
    color: 'var(--color-text-warning)',
    background: 'var(--color-background-warning)',
    border: 'var(--color-border-warning)'
   }

  };

  var s = styles[type] || styles.warn;
  feedback.removeAttribute('style');
  feedback.style.display = 'block';
  feedback.style.padding = '10px 14px';
  feedback.style.borderRadius = 'var(--border-radius-md, 8px)';
  feedback.style.fontSize = '13px';
  feedback.style.marginTop = '12px';
  feedback.style.color = s.color;
  feedback.style.background = s.background;
  feedback.style.border = '0.5px solid ' + s.border;
  feedback.textContent = msg;

  clearTimeout(feedback._timer);
  feedback._timer = setTimeout(hideFeedback, 5000);
}


/*hide feedbacke */
function hideFeedback(){
  var feedback = document.getElementById("add-feedback");
  if(feedback) feedback.style.display = 'none';
}


/*  Promote and Archive Modal  */

function escapeText(value){
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function openPromoteModal(){
  document.getElementById('promote-overlay').classList.add('open');
  loadPassedStudents();
  loadComp4300Students();
}

function closePromoteModal(e){
  if(e && e.target !== document.getElementById('promote-overlay')) return;
  document.getElementById('promote-overlay').classList.remove('open');
}

function renderGroupRow(group, badgeText, badgeColor){
  var name = group.group_name || group.title || ('Project ' + group.project_id);
  var title = group.title && group.title !== name ? group.title : '';
  var students = group.students || '-';
  var supervisor = group.supervisor_name || 'Not assigned';
  var count = group.student_count || 0;

  return '<div style="padding:10px 12px; border-bottom:0.5px solid var(--color-border-tertiary);">' +
    '<div style="display:flex; justify-content:space-between; gap:10px; align-items:flex-start;">' +
      '<div style="min-width:0; flex:1;">' +
        '<div style="font-size:13px; font-weight:700; color:var(--color-text-primary);">' + escapeText(name) + '</div>' +
        (title ? '<div style="font-size:11px; color:var(--color-text-secondary); margin-top:2px;">' + escapeText(title) + '</div>' : '') +
      '</div>' +
      '<span style="font-size:11px; padding:2px 8px; border-radius:20px; background:var(--color-background-tertiary); color:' + badgeColor + '; border:0.5px solid var(--color-border-tertiary); white-space:nowrap;">' + escapeText(badgeText) + '</span>' +
    '</div>' +
    '<div style="font-size:11px; color:var(--color-text-secondary); margin-top:6px; line-height:1.5;">' +
      '<b>Students (' + escapeText(count) + '):</b> ' + escapeText(students) + '<br>' +
      '<b>Supervisor:</b> ' + escapeText(supervisor) +
    '</div>' +
  '</div>';
}

function renderArchiveProjectRow(project){
  var name = project.group_name || project.title || ('Project ' + project.project_id);
  var title = project.title && project.title !== name ? project.title : '';
  var students = project.students || '-';
  var supervisor = project.supervisor_name || 'Not assigned';
  var count = project.student_count || 0;
  var visibility = project.archive_visibility === 'private' ? 'private' : 'public';

  return '<div style="padding:10px 12px; border-bottom:0.5px solid var(--color-border-tertiary);">' +
    '<div style="display:flex; justify-content:space-between; gap:10px; align-items:flex-start;">' +
      '<div style="min-width:0; flex:1;">' +
        '<div style="font-size:13px; font-weight:700; color:var(--color-text-primary);">' + escapeText(name) + '</div>' +
        (title ? '<div style="font-size:11px; color:var(--color-text-secondary); margin-top:2px;">' + escapeText(title) + '</div>' : '') +
      '</div>' +
      '<span style="font-size:11px; padding:2px 8px; border-radius:20px; background:var(--color-background-tertiary); color:#dc2626; border:0.5px solid var(--color-border-tertiary); white-space:nowrap;">Ready for Archive</span>' +
    '</div>' +
    '<div style="font-size:11px; color:var(--color-text-secondary); margin-top:6px; line-height:1.5;">' +
      '<b>Students (' + escapeText(count) + '):</b> ' + escapeText(students) + '<br>' +
      '<b>Supervisor:</b> ' + escapeText(supervisor) +
    '</div>' +
    '<label style="display:flex; align-items:center; justify-content:space-between; gap:10px; margin-top:10px; font-size:11px; color:var(--color-text-secondary);">' +
      '<span>Archive visibility</span>' +
      '<select class="archive-visibility-select" data-project-id="' + escapeText(project.project_id) + '" style="border:0.5px solid var(--color-border-secondary); border-radius:8px; padding:6px 8px; font-size:11px; color:var(--color-text-primary); background:var(--color-background-primary);">' +
        '<option value="public"' + (visibility === 'public' ? ' selected' : '') + '>Public</option>' +
        '<option value="private"' + (visibility === 'private' ? ' selected' : '') + '>Private</option>' +
      '</select>' +
    '</label>' +
  '</div>';
}

async function loadPassedStudents(){
  var list = document.getElementById('passed-students-list');
  list.innerHTML = '<div style="padding:12px; color:var(--color-text-tertiary);">Loading...</div>';

  try{
    var res = await fetch('/head/api/students/passes');
    var data = await res.json();

    if(!res.ok || data.error){
      throw new Error(data.error || 'Could not load promoted groups.');
    }

    var groups = data.groups || [];

    if(!groups.length){
      list.innerHTML = '<div style="padding:12px; color:var(--color-text-tertiary);">No succeeded COMP4200 groups waiting for promotion.</div>';
      return;
    }

    list.innerHTML = groups.map(function(g){
      return renderGroupRow(g, 'Ready for COMP4300', 'var(--green)');
    }).join('');
  }catch(e){
    list.innerHTML = '<div style="padding:12px; color:var(--color-text-danger);">' + escapeText(e.message || 'Could not load groups.') + '</div>';
  }
}

async function loadComp4300Students(){
  var list = document.getElementById('comp4300-students-list');
  list.innerHTML = '<div style="padding:12px; color:var(--color-text-tertiary);">Loading...</div>';

  try{
    var res = await fetch('/head/api/students/comp4300');
    var data = await res.json();

    if(!res.ok || data.error){
      throw new Error(data.error || 'Could not load COMP4300 projects.');
    }

    var projects = data.projects || [];

    if(!projects.length){
      list.innerHTML = '<div style="padding:12px; color:var(--color-text-tertiary);">No succeeded COMP4300 projects waiting for archive.</div>';
      return;
    }

    list.innerHTML = projects.map(renderArchiveProjectRow).join('');
  }catch(e){
    list.innerHTML = '<div style="padding:12px; color:var(--color-text-danger);">' + escapeText(e.message || 'Could not load projects.') + '</div>';
  }
}

async function promoteAll(){
  var btn = document.getElementById('promoteBtn');
  btn.disabled = true;
  btn.textContent = 'Promoting...';

  try{
    var res = await fetch('/head/api/students/promote-all', {method: 'POST'});
    var data = await res.json();

    if(res.ok){
      showFeedback_promote('promote-feedback', data.message, 'success');
      loadPassedStudents();
      loadComp4300Students();
      loadStudents();
    }else{
      showFeedback_promote('promote-feedback', data.error || 'Something went wrong.', 'error');
    }
  }catch(e){
    showFeedback_promote('promote-feedback', 'Could not reach the server.', 'error');
  }finally{
    btn.disabled = false;
    btn.innerHTML = '<span class="material-symbols-outlined icon-inline">upgrade</span> Promote All to COMP4300';
  }
}

async function archiveAll(){
  var btn = document.getElementById('archiveBtn');
  btn.disabled = true;
  btn.textContent = 'Archiving...';
  var projectVisibilities = {};

  document.querySelectorAll('.archive-visibility-select').forEach(function(select){
    if(select.dataset.projectId){
      projectVisibilities[select.dataset.projectId] = select.value === 'private' ? 'private' : 'public';
    }
  });

  try{
    var res = await fetch('/head/api/students/archive-all', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({project_visibilities: projectVisibilities})
    });
    var data = await res.json();

    if(res.ok){
      showFeedback_promote('archive-feedback', data.message, 'success');
      loadComp4300Students();
      loadStudents();
    }else{
      showFeedback_promote('archive-feedback', data.error || 'Something went wrong.', 'error');
    }
  }catch(e){
    showFeedback_promote('archive-feedback', 'Could not reach the server.', 'error');
  }finally{
    btn.disabled = false;
    btn.innerHTML = '<span class="material-symbols-outlined icon-inline">archive</span> Archive All COMP4300 Projects';
  }
}

function showFeedback_promote(id, message, type){
  var el = document.getElementById(id);
  var s = {
    success: {color:'var(--color-text-success)', bg:'var(--color-background-success)', border:'var(--color-border-success)'},
    error: {color:'var(--color-text-danger)', bg:'var(--color-background-danger)', border:'var(--color-border-danger)'}
  }[type] || {};
  el.removeAttribute('style');
  el.style.display = 'block';
  el.style.padding = '10px 14px';
  el.style.borderRadius = '8px';
  el.style.fontSize = '12px';
  el.style.color = s.color;
  el.style.background = s.bg;
  el.style.border = '0.5px solid ' + s.border;
  el.textContent = message;
}
