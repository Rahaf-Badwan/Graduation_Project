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
  var email = document.getElementById('email').value.trim();

   hideFeedback();

  if(!name || !uid || !email){
    showFeedback('Please fill in Name, University ID, and Email.', 'warn');
    return;
  }

  var addBtn = document.querySelector('.btn.btn-primary');
  addBtn.disabled = true;
  addBtn.textContent = 'Adding...';

  try{
    var res = await fetch(API_BASE + '/api/students/add', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({full_name: name, university_id: uid, email: email})
    });
    var data = await res.json();

    if(res.ok){
      showFeedback('Student added successfully. Status: Pending', 'success');
      clearForm();
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
function clearForm(){
  ['fullName', 'universityId', 'email'].forEach(function(id){
    var el = document.getElementById(id);
    if(el) el.value = '';
  });

  var textarea = document.querySelector('.field-textarea');
  if(textarea) textarea.value = '';
  hideFeedback();
}

/*feedback to head of department to know if the student add or any something happen */
function showFeedback(msg, type){
  var feedback = document.getElementById('add-feedback');

  feedback.style.display = 'block';

  var colors = {
    success: 'var(--color-text-success)',
    error: 'var(--color-text-danger)',
    warn: 'var(--color-text-warning)'
  };

  var backgrounds = {
    success: 'var(--color-background-success)',
    error: 'var(--color-background-danger)',
    warn: 'var(--color-background-warning)'
  };

  var borders = {
    success: 'var(--color-text-success)',
    error: 'var(--color-text-danger)',
    warn: 'var(--color-text-warning)'
  };
  feedback.style.cssText = 
    'display:block; padding:10px 14px; border-radius:var(--border-radius-md);' +
    'font-size:13px; margin-top:12px;' +
    'color:'    + (colors[type] || colors.warn) + ';' +
    'background:' + (backgrounds[type] || backgrounds.warn) + ';' +
    'border:0.5px solid ' +(borders[type] || borders.warn) + ';' ;
  feedback.textContent = msg;
}


/*hide feedbacke */
function hideFeedback(){
  var feedback = document.getElementById("add-feedback");
  if(feedback) feedback.style.display = 'none';
}