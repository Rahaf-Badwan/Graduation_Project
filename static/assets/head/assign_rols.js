const API_BASE = '/head';

let assignState = {
  academicYears: [],
  coordinatorsByYear: {},
  doctors: [],
  projectCountsByYear: {},
};

window.addEventListener('DOMContentLoaded', () => loadAssignCoordinatorPage());

async function loadAssignCoordinatorPage(preferredYear) {
  try {
    const res = await fetch(API_BASE + '/api/assign-coordinator-data', {
      headers: { 'Accept': 'application/json' },
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to load coordinator data.');

    assignState = {
      academicYears: data.academic_years || [],
      coordinatorsByYear: data.coordinators_by_year || {},
      doctors: data.doctors || [],
      projectCountsByYear: data.project_counts_by_year || {},
    };

    renderAcademicYears(preferredYear);
    renderDoctorSelect();
    renderSelectedYear();
  } catch (err) {
    showToast(err.message || 'Could not load coordinator data.', 'error');
  }
}

function renderAcademicYears(preferredYear) {
  const select = document.getElementById('semesterSelect');
  select.innerHTML = '';

  const years = assignState.academicYears;
  if (!years.length) {
    select.innerHTML = '<option value="">No academic years available</option>';
    return;
  }

  years.forEach(year => {
    const option = document.createElement('option');
    option.value = year.academic_year;
    option.textContent = year.academic_year + (year.is_new ? ' (new)' : '');
    if (preferredYear ? year.academic_year === preferredYear : year.is_active) option.selected = true;
    select.appendChild(option);
  });

  if (!select.value) select.value = years[0].academic_year;
  select.onchange = renderSelectedYear;
}

function renderDoctorSelect() {
  const select = document.getElementById('doctorSelect');
  select.innerHTML = '<option value="" disabled selected>Select Coordinator</option>';

  assignState.doctors.forEach(doctor => {
    const option = document.createElement('option');
    option.value = doctor.faculty_id;
    option.textContent = doctor.full_name;
    select.appendChild(option);
  });
}

function renderSelectedYear() {
  const year = document.getElementById('semesterSelect').value;
  const coordinator = assignState.coordinatorsByYear[year] || null;
  updateCoordinatorUI(coordinator);
  renderDoctorList(year, coordinator);

  const select = document.getElementById('doctorSelect');
  select.value = coordinator && coordinator.faculty_id ? String(coordinator.faculty_id) : '';
}

function renderDoctorList(year, coordinator) {
  const doctorList = document.getElementById('doctorList');
  const counts = assignState.projectCountsByYear[year] || {};
  doctorList.innerHTML = '';

  if (!assignState.doctors.length) {
    doctorList.innerHTML = '<div style="color:var(--color-text-secondary);font-size:13px;padding:12px 0">No doctors found.</div>';
    return;
  }

  assignState.doctors.forEach(doctor => {
    const name = cleanDoctorName(doctor.full_name);
    const initials = initialsFor(name);
    const color = colorForDoctor(doctor.faculty_id);
    const projectCount = Number(counts[String(doctor.faculty_id)] || 0);
    const isCoordinator = coordinator && Number(doctor.faculty_id) === Number(coordinator.faculty_id);
    const coordTag = isCoordinator
      ? '<span class="role-badge role-badge--coord">Coordinator</span>'
      : '';
    const badgeHTML = projectCount > 0
      ? `<div class="badge">${projectCount}<span class="label">${projectCount === 1 ? 'Project' : 'Projects'}</span></div>`
      : '';

    doctorList.insertAdjacentHTML('beforeend', `
      <div class="doctor-card ${isCoordinator ? 'doctor-card--coord' : ''}">
        <div class="left">
          <div class="avatar" style="background:${color}">${escapeHtml(initials)}</div>
          <div class="doctor-info">
            <div class="name">${escapeHtml(doctor.full_name)} ${coordTag}</div>
            <div class="spec">${escapeHtml(doctor.specialization || 'No specialization')}</div>
          </div>
        </div>
        <div class="right">${badgeHTML}</div>
      </div>
    `);
  });
}

function cleanDoctorName(fullName) {
  return String(fullName || '')
    .replace(/Dr\.?/g, '')
    .replace(/Prof\.?/g, '')
    .trim();
}

function initialsFor(name) {
  const initials = String(name || '?')
    .split(/\s+/)
    .filter(Boolean)
    .map(part => part[0])
    .join('')
    .substring(0, 2)
    .toUpperCase();
  return initials || '?';
}

function colorForDoctor(id) {
  const colors = ['#d1fae5', '#dbeafe', '#fef3c7', '#fce7f3', '#e0e7ff'];
  return colors[Math.abs(Number(id) || 0) % colors.length];
}

function assignCoordinator(facultyId) {
  if (!facultyId) {
    showToast('Please select a coordinator.', 'error');
    return;
  }

  const academicYear = document.getElementById('semesterSelect').value;
  if (!academicYear) {
    showToast('Please select an academic year.', 'error');
    return;
  }

  const notes = document.getElementById('assignNotes').value.trim();
  const btn = document.querySelector('.btn-primary');

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Assigning...';

  const resetBtn = () => {
    btn.disabled = false;
    btn.innerHTML = 'Confirm New Coordinator &#x2197;';
  };

  const body = new URLSearchParams({
    faculty_id: facultyId,
    academic_year: academicYear,
    notes,
  });

  fetch(API_BASE + '/api/assign-coordinator', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  })
    .then(res => res.json().then(data => ({ ok: res.ok, data })))
    .then(({ ok, data }) => {
      if (!ok || data.error) {
        showToast(data.error || 'Coordinator assignment failed.', 'error');
        return;
      }
      showToast('Coordinator assigned to COMP4200 and COMP4300 successfully.', 'success');
      return loadAssignCoordinatorPage(academicYear);
    })
    .catch(() => showToast('Something went wrong.', 'error'))
    .finally(resetBtn);
}

function updateCoordinatorUI(coordinator) {
  document.getElementById('coordinator').innerText =
    coordinator ? coordinator.full_name : 'None';
}

function showToast(message, type = 'success') {
  document.querySelector('.toast')?.remove();

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span class="toast-icone">${type === 'success'
      ? '<span class="material-symbols-outlined">check</span>'
      : '<span class="material-symbols-outlined">close</span>'}
    </span>
    <span>${escapeHtml(message)}</span>
  `;
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('hide');
    setTimeout(() => toast.remove(), 400);
  }, 3000);
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Academic Year Modal ─────────────────────────────────
function openAcademicYearModal() {
  const modal = document.getElementById('academicYearModal');
  modal.style.display = 'flex';
  document.getElementById('newAcademicYear').value = '';
  document.getElementById('semesterStart').value = '';
  document.getElementById('semesterEnd').value = '';
  document.getElementById('setActiveYear').checked = false;
  document.getElementById('academicYearError').textContent = '';
}

function closeAcademicYearModal() {
  document.getElementById('academicYearModal').style.display = 'none';
}

async function createAcademicYear() {
  const errorEl = document.getElementById('academicYearError');
  const btn = document.getElementById('createAcademicYearBtn');
  errorEl.textContent = '';

  const payload = {
    academic_year: document.getElementById('newAcademicYear').value.trim(),
    semester_start: document.getElementById('semesterStart').value,
    semester_end: document.getElementById('semesterEnd').value,
    set_active: document.getElementById('setActiveYear').checked,
  };

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Creating...';

  try {
    const res = await fetch(API_BASE + '/api/academic-years', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok || data.error) {
      errorEl.textContent = data.error || 'Failed to create academic year.';
      return;
    }

    closeAcademicYearModal();
    showToast(`Academic year ${data.academic_year} created successfully.`, 'success');
    await loadAssignCoordinatorPage(data.academic_year);

  } catch (err) {
    errorEl.textContent = 'Something went wrong.';
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Create Academic Year &#x2197;';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const modal = document.getElementById('academicYearModal');
  if (modal) {
    modal.addEventListener('click', function (e) {
      if (e.target === this) closeAcademicYearModal();
    });
  }
});