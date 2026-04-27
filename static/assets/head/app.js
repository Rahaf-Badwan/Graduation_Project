// ─── Head of Department — page-specific JS ────────────────────────────────
// toggleSidebar / applySidebarState / bindSidebarHover / askAI / setQ
// are all provided by the shared assets/js/app.js — do NOT redeclare here.
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
    fetch(`/api/course/${courseCode}`)
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
          doctorSelect.innerHTML = "";

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
          doctorList.innerHTML += `
            <div class="doctor-card">
                <div class="left">
                  <div class="avatar">${initials}</div>
                  <div class="doctor-info">
                    <div class="name">${d.full_name}</div>
                    <div class="spec">${d.specialization}</div>
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

      })
      .catch(err => console.error(err));
  }

      


// assign coordinator
function assignCoordinator(facultyId){
  let semesterId = document.getElementById("semesterSelect").value;

  fetch("/api/assign-coordinator", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded"
    },
    body: `faculty_id=${facultyId}&semester_id=${semesterId}&assigned_by=2`
  })
  .then(res => res.json())
  .then(data => {
    if(data.error){
      alert(data.error);
    }else{
      alert("Coordinator Assigned successfully");
      loadCourse(currentCourse);
    }
  });
}
function updateCoordinatorUI(coordinator){
  document.getElementById("coordinator").innerText = 
  coordinator ? coordinator.full_name : "None";

}
