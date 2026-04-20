"""
Web Routes — serve Flask templates for the web demo UI.
"""

from flask import Blueprint, render_template, request, redirect, url_for, session
from models.database import User, Job, db
from services.job_service import get_all_jobs

web = Blueprint("web", __name__)


@web.route("/")
def index():
    """Always redirect to language selection — forces language pick on every fresh visit."""
    return redirect(url_for("web.language"))


@web.route("/home")
def home():
    """Actual home page — reached after language is selected."""
    return render_template("index.html")


@web.route("/language")
def language():
    """Language selection page."""
    return render_template("language.html")


@web.route("/lang")
def lang_select():
    """Alias for /language."""
    return render_template("language.html")


@web.route("/login")
def login():
    return render_template("login.html")


@web.route("/chat")
def chat():
    """Main chat interface."""
    phone = request.args.get("phone") or session.get("phone", "")
    if not phone:
        return redirect(url_for("web.home"))
    session["phone"] = phone
    user = User.query.filter_by(phone=phone).first()
    return render_template("chat.html", phone=phone, user=user)


@web.route("/job-apply/<int:job_id>")
def job_apply(job_id):
    """Job application Q&A page."""
    job = Job.query.get_or_404(job_id)
    return render_template("job_apply.html", job=job)


@web.route("/job-confirm")
def job_confirm():
    """Job application confirmation page."""
    return render_template("job_confirm.html")


@web.route("/jobs")
def jobs_page():
    """Browse all open jobs."""
    job_type = request.args.get("type", "")
    jobs = get_all_jobs(job_type=job_type or None, limit=30)
    return render_template("jobs.html", jobs=jobs, filter_type=job_type)


@web.route("/profile")
def profile():
    """User profile & history."""
    phone = request.args.get("phone") or session.get("phone", "")
    if not phone:
        return redirect(url_for("web.home"))
    user = User.query.filter_by(phone=phone).first()
    return render_template("profile.html", phone=phone, user=user)


@web.route("/employer-login")
def employer_login_page():
    """Separate employer login/signup page."""
    return render_template("employer_login.html")


@web.route("/employer")
def employer():
    """Employer dashboard — login required."""
    phone = request.args.get("phone") or session.get("phone", "")
    # If no phone, redirect to login then back here
    if not phone:
        return redirect(url_for("web.login") + "?next=/employer")
    session["phone"] = phone
    user = User.query.filter_by(phone=phone).first()
    return render_template("employer.html", phone=phone, user=user)


@web.route("/dashboard")
def dashboard():
    """Analytics dashboard."""
    return render_template("dashboard.html")
