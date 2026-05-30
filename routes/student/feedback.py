from flask import (
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
import bcrypt
from werkzeug.utils import secure_filename

from auth import login_required
from db import get_db
from .blueprint import student_bp
from .common import *

@student_bp.route("/feedback")
@login_required(role="student")
def feedback():
    return render_template("student/feedback.html")
