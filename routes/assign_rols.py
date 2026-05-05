from datetime import timedelta
import datetime
from flask import Blueprint, jsonify, request
from db import get_db

assign_rols_bp = Blueprint("assign_rols_bp", __name__)

#get the course info
@assign_rols_bp.route("/api/course/<course_code>")
def get_course(course_code):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    #get semesters
    cursor.execute("""
                  SELECT semester_id, academic_year, semester_number
                  FROM  semesters 
                  WHERE course_code = %s             
                           """, (course_code,))
    semesters = cursor.fetchall()
    
    #the current coordinator of this course
    cursor.execute("""
                        SELECT u.full_name,
                               f.title,
                               ca.assigned_at
                        FROM coordinator_assignments ca
                        JOIN faculty f ON ca.faculty_id = f.faculty_id
                        JOIN users u ON u.user_id = f.user_id
                        JOIN semesters s ON s.semester_id = ca.semester_id
                        WHERE s.course_code = %s
                        ORDER BY ca.assigned_at DESC
                        LIMIT 1
                             """, (course_code,))
    coordinator = cursor.fetchone()
    
    #the doctors 
    cursor.execute("""
                    SELECT 
                         f.faculty_id,
                          u.full_name,
                          f.specialization,
                         COUNT(p.project_id) AS project_count
                    FROM faculty f
                    JOIN users u ON u.user_id = f.user_id
                    JOIN projects p ON p.supervisor_id = f.faculty_id
                    JOIN semesters s ON s.semester_id = p.semester_id
                        AND s.course_code = %s
                    GROUP BY f.faculty_id, u.full_name, f.specialization
                         """, (course_code,))
    doctors = cursor.fetchall()
    
    return jsonify({
        "semesters": [dict(row) for row in semesters],
        "coordinator": dict(coordinator) if coordinator else None,
        "doctors" : [dict(row) for row in doctors]
    })

#assign & update coordinator
@assign_rols_bp.route("/api/assign-coordinator", methods=["POST"])
def assign_coordinator():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    faculty_id = request.form["faculty_id"]
    semester_id = request.form["semester_id"]
    assigned_by = request.form.get("assigned_by", 1)

    #check if already exists
    cursor.execute("""
                        SELECT * FROM coordinator_assignments
                        WHERE semester_id = %s
                        """, (semester_id,))
    existing = cursor.fetchone()
    
    if existing:
        now = datetime.datetime.now()
        last_assigned = existing["assigned_at"]
        days_diff = (now - last_assigned).days
        if days_diff > 20 :
            return jsonify({"error": "Cannot change coordinator after 20 days "})
        
    #update coordinator
        cursor.execute("""
        UPDATE coordinator_assignments
        SET faculty_id = %s, assigned_at = NOW(), assigned_by = %s
        WHERE semester_id = %s
               """, (faculty_id, assigned_by, semester_id))
    else:
        #insert first time
        cursor.execute("""
            INSERT INTO coordinator_assignments
                   (faculty_id, semester_id, assigned_by)
                   VALUES (%s, %s, %s)
                   """, (faculty_id, semester_id, assigned_by))
    cursor.close()
    conn.close()
    return jsonify({"success": True})