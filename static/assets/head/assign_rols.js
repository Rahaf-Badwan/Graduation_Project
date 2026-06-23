// ─── Head of Department — page-specific JS ────────────────────────────────
// toggleSidebar / applySidebarState / bindSidebarHover / askAI / setQ
// are all provided by the shared assets/js/app.js — do NOT redeclare here.
/*---------Assign rols ---------------*/
const API_BASE = '/head';
let currentCourse = "COMP4200";
let currentAssignedAt="null";

window.onload = function () {
  loadCourse(currentCourse);
};
// ─── Tab bar (Overview page) ──────────────────────────────────────────────
function selectTab(courseCode, el) {
  currentCourse = courseCode;
  document.querySelectorAll('.tab').forEach(t =>
     t.classList.remove('active')
    );
  el.classList.add('active');
  loadCourse(courseCode);
}


function loadCourse(courseCode){
    fetch(API_BASE + `/api/course/${courseCode}`)
        .then(res => res.json())
        .then(data => {
          //coordinator
          currentAssignedAt = 
          data.coordinator ? data.coordinator.assigned_at : null;
          updateCoordinatorUI(data.coordinator);

          //semesters
          let sem = document.getElementById("semesterSelect");
          sem.innerHTML = "";

          data.semesters.forEach(s => {
            sem.innerHTML += `
            <option value="${s.semester_id}">
            ${s.academic_year}
            </option>
            `;
          });
          //doctors list
          let doctorList = document.getElementById("doctorList");
          let doctorSelect = document.getElementById("doctorSelect");

          doctorList.innerHTML = "";
          doctorSelect.innerHTML = '<option value="" disabled selected>Select Coordinator</option>';

          data.doctors.forEach(d => {
            if(d.role === "head_of_department") return;
            let name = d.full_name
            .replace(/Dr\.?/g, "")
            .replace(/Prof\.?/g, "")
            .trim();
            let initials = name
                .split(" ")
                .map(n => n[0])
                .join("")
                .substring(0, 2)
                .toUpperCase();
            const colors = ["#d1fae5", "#dbeafe"
              ,"#fef3c7", "#fce7f3", "#e0e7ff"
              ];

            let color = colors[Math.floor(Math.random() * colors.length)];
            //have projects
            let badgeHTML = "";
            if(d.project_count > 0){
              badgeHTML = `
              <div class="badge">
                 ${d.project_count}
                <span class="label">
                  ${d.project_count == 1 ? "Project" : "Projects"}
                </span>

              </div>
              `;
          }

          let hourHTML = "";
          if(d.weekly_hours != null){
            hourHTML = `
            <span class="hours-tag">
              <span class="matirial-symbols-outlined icons-inline" syle="font-size:13px; vertical-align:-2px;">schedule</span>
              ${d.weekly_hours}h/week
              </span>`;
          }



          if(d.role === "head_of_department"){
            doctorList.innerHTML += `
              <div class="doctor-card doctor-card--head">
                <div class="left">
                  <div class="avatar avatar--head" style="background:${color}">${initials}</div>
                  <div class="doctor-info">
                    <div class="name">
                      ${d.full_name}
                      <span class="role-badge role-badge--head"> Head Of Dept.</span>
                    </div>
                    <div class="spec">${d.specialization} ${hourHTML}</div>}
                  </div>
                </div>
                <div class="right">${badgeHTML}</div>
              </div>`;
              doctorSelect.innerHTML += `<option value="${d.faculty_id}">${d.full_name}</option>`;
          }

          let isCoordiantor = data.coordinator && d.faculty_id === data.coordinator.faculty_id;
          let coordTag = isCoordiantor
             ? `<span class="role-badge role-badge--coord">Coordinator</span>`
             : "";

          doctorList.innerHTML += `
            <div class="doctor-card ${isCoordiantor ? 'doctor-card--coord' : ''}">
                <div class="left">
                  <div class="avatar" style="background: ${color}">${initials}</div>
                  <div class="doctor-info">
                    <div class="name">${d.full_name} ${coordTag}</div>
                    <div class="spec">${d.specialization} ${hourHTML}</div>
                  </div>
                </div>
                <div class="right">
                 ${badgeHTML}
                </div>
            </div>
          `;
          //select
          doctorSelect.innerHTML +=`
            <option value="${d.faculty_id}">
            ${d.full_name}
            </option>
          `;
        });
        if (data.coordinator && data.coordinator.faculty_id) {
          doctorSelect.value = String(data.coordinator.faculty_id);
        } else {
          doctorSelect.value = "";
        }

      })
      .catch(err => console.error(err));
  }

      


// assign coordinator
function assignCoordinator(facultyId){
  if (!facultyId) {
    showToast("Please select a supervisor.", "error");
    return;
  }

  let semesterId = document.getElementById("semesterSelect").value;
  let btn = document.querySelector(".btn-primary");

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Assigning...'

  const resetBtn = () => {
    btn.disabled = false;
    btn.innerHTML = `Confirm New Coordinator &#x2197;`;
  };

  fetch(API_BASE + '/api/assign-coordinator', {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded"
    },
    body: `faculty_id=${encodeURIComponent(facultyId)}&semester_id=${encodeURIComponent(semesterId)}&assigned_by=2`
  })
  .then(res => res.json())
  .then(data => {
    setTimeout(() =>{
    if(data.error){
      showToast(data.error, "error");
    }else{
      showToast("Coordinator assigned successfully!", "success");
      loadCourse(currentCourse);
    }
      resetBtn();
    }, 1500); 
  })
  .catch(() => {
    showToast("Something went wrong.", "error");
    resetBtn();
  })
 
}


function updateCoordinatorUI(coordinator){
  document.getElementById("coordinator").innerText = 
  coordinator ? coordinator.full_name : "None";

}

function showToast(message,  type = "success"){
  document.querySelector(".toast")?.remove();

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
  <span class="toast-icone">${type === "success" 
    ? '<span class="material-symbols-outlined">check</span>' 
    : '<span class="material-symbols-outlined">close</span>'}
  </span>
  <span>${message}</span>
  `;
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.classList.add("hide");
    setTimeout(() => toast.remove(), 400);
  }, 3000);
}

