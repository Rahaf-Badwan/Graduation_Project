import hashlib
import secrets
from flask import Blueprint, jsonify, render_template, request, redirect, url_for, session
import bcrypt
from db import get_db
from auth import login_required

head_bp = Blueprint("head", __name__, url_prefix="/head")


# ─── Dashboard ──────────────────────────────────────────────
@head_bp.route("/")
@head_bp.route("/dashboard")
@login_required(role="head_of_department")
def dashboard():
    return render_template("head/index.html")


# ─── Assign Roles ───────────────────────────────────────────
@head_bp.route("/assign")
@login_required(role="head_of_department")
def assign():
    return render_template("head/assign.html")


# ─── Department Overview ────────────────────────────────────
@head_bp.route("/overview")
@login_required(role="head_of_department")
def overview():
    return render_template("head/overview.html")


# ─── Supervisors ────────────────────────────────────────────
@head_bp.route("/supervisors")
@login_required(role="head_of_department")
def supervisors():
    return render_template("head/supervisors.html")


# ─── Search ─────────────────────────────────────────────────
@head_bp.route("/search")
@login_required(role="head_of_department")
def search():
    return render_template("head/search.html")


# ─── Notifications ──────────────────────────────────────────
@head_bp.route("/notifs")
@login_required(role="head_of_department")
def notifs():
    return render_template("head/notifs.html")


# ─── AI Assistant ───────────────────────────────────────────
@head_bp.route("/ai")
@login_required(role="head_of_department")
def ai():
    return render_template("head/ai.html")


# ─── Profile ────────────────────────────────────────────────
@head_bp.route("/profile")
@login_required(role="head_of_department")
def profile():
    user_id = session["user_id"]
    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT user_id, university_id, full_name, email, avatar_initials FROM users WHERE user_id = %s",
            (user_id,)
        )
        user = cursor.fetchone()
        cursor.close()
        db.close()
    except Exception:
        user = None
    return render_template("head/profile.html", user=user, pwd_error=None, pwd_success=None)


# ─── Change Password ─────────────────────────────────────────
@head_bp.route("/profile/change-password", methods=["POST"])
@login_required(role="head_of_department")
def change_password():
    user_id     = session["user_id"]
    current_pwd = request.form.get("current_password", "").strip()
    new_pwd     = request.form.get("new_password", "").strip()
    confirm_pwd = request.form.get("confirm_password", "").strip()

    def get_user():
        try:
            db     = get_db()
            cursor = db.cursor(dictionary=True)
            cursor.execute(
                "SELECT user_id, university_id, full_name, email, avatar_initials, password_hash FROM users WHERE user_id = %s",
                (user_id,)
            )
            u = cursor.fetchone()
            cursor.close()
            db.close()
            return u
        except Exception:
            return None

    user = get_user()

    if not current_pwd or not new_pwd or not confirm_pwd:
        return render_template("head/profile.html", user=user, pwd_error="Please fill in all fields.", pwd_success=None)
    if len(new_pwd) < 8:
        return render_template("head/profile.html", user=user, pwd_error="New password must be at least 8 characters.", pwd_success=None)
    if new_pwd != confirm_pwd:
        return render_template("head/profile.html", user=user, pwd_error="Passwords do not match.", pwd_success=None)
    if not user or not bcrypt.checkpw(current_pwd.encode(), user["password_hash"].encode()):
        return render_template("head/profile.html", user=user, pwd_error="Current password is incorrect.", pwd_success=None)

    try:
        hashed = bcrypt.hashpw(new_pwd.encode(), bcrypt.gensalt()).decode()
        db     = get_db()
        cursor = db.cursor()
        cursor.execute("UPDATE users SET password_hash = %s WHERE user_id = %s", (hashed, user_id))
        db.commit()
        cursor.close()
        db.close()
        return render_template("head/profile.html", user=user, pwd_error=None, pwd_success="Password updated successfully!")
    except Exception as e:
        return render_template("head/profile.html", user=user, pwd_error=f"Error: {e}", pwd_success=None)
# ─── Add student ────────────────────────────────────────────────
@head_bp.route('/addStudent')
@login_required(role="head_of_department")
def add_student():
    return render_template('/head/addStudent.html')

@head_bp.route("/api/active-student")
@login_required(role="head_of_department")
def active_students():
    course_code = request.args.get("course_code")
    print(course_code)
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT DISTINCT
                   u.user_id,
                   u.full_name,
                   u.university_id,
                   u.email
                   FROM users u
                   JOIN students st
                    ON st.user_id = u.user_id
                   JOIN student_courses sc
                    ON sc.student_id = st.student_id
                   WHERE u.role = 'student'
                   AND sc.status = 'active'
                   AND sc.course_code = %s
                   
        """, (course_code,))
    
    students = cursor.fetchall()

    print("COURSE:", course_code)
    print(students)
    cursor.close()
    db.close()
    return jsonify(students)

@head_bp.route("/api/add-student", methods=["POST"])
@login_required(role="head_of_department")
def api_add_student():
    full_name = request.form.get("full_name")
    university_id = request.form.get("university_id")
    email = request.form.get("email")
    course_code = request.form.get("course_code")

    import uuid
    from datetime import datetime, timedelta

    token = str(uuid.uuid4())
    expiry = datetime.now() + timedelta(days=20)
    
    db = get_db()
    cursor = db.cursor()

    #check if the student already exist
    cursor.execute("""
            SELECT * FROM users
            WHERE university_id = %s 
        """, (university_id,))
    existing = cursor.fetchone()
    if existing:
        cursor.close()
        db.close()
        return jsonify({
            "success": False,
            "error": "Student already exists"
        })
    temp_pass = secrets.token_hex(4)
    password_hash = bcrypt.hashpw(temp_pass.encode(), bcrypt.gensalt()).decode()
    
   
   #add user
    cursor.execute("""
            INSERT INTO users
                    (university_id, full_name, email, password_hash, role, account_status
                   , activation_token, activation_expiry)
                    VALUES (%s, %s, %s, %s, 'student', 'pending', %s, %s)                
                """, (university_id, full_name, email, password_hash, token, expiry))
    user_id = cursor.lastrowid

#add user to student
    cursor.execute("""
            INSERT INTO students (user_id)
            VALUES(%s)   
    """, (user_id,))

    student_id = cursor.lastrowid

#add the student in COMP4200 by default
    cursor.execute("""
        SELECT semester_id FROM semesters WHERE course_code = 'COMP4200'
    """)

    semester = cursor.fetchone()

    cursor.execute("""
            INSERT INTO student_courses (student_id, semester_id, status)
            VALUES(%s, %s, 'pending')
    """, (student_id, semester["semester_id"]))
    
    db.commit()
    cursor.close()
    db.close()

    activation_link = url_for('auth.activate', token=token, _external=True)

    return jsonify({
        "success": True,
        "message": "Student added successfully",
        "link": activation_link
    })
     