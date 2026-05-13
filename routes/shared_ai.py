from flask import Blueprint, render_template, request

from auth import login_required

shared_ai_bp = Blueprint("shared_ai", __name__)


ROLE_BASE_TEMPLATES = {
    "student": "student/base.html",
    "coordinator": "coordinator/base.html",
    "supervisor": "supervisor/base.html",
    "head": "head/base.html",
    "head_of_department": "head/base.html",
}


@shared_ai_bp.route("/student/ai")
@shared_ai_bp.route("/coordinator/ai")
@shared_ai_bp.route("/supervisor/ai")
@shared_ai_bp.route("/head/ai")
@login_required()
def shared_ai_page():
    role_path = request.path.strip("/").split("/", 1)[0]
    return render_template(
        "shared/ai.html",
        base_template=ROLE_BASE_TEMPLATES.get(role_path),
    )
