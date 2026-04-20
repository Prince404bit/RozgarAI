"""
API Routes — KaamMitr backend endpoints.
All endpoints return: { success, data, message }
"""

import time
import uuid
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, g
from models.database import db, User, Job, WorkHistory
from services.conversation_service import handle_message, apply_to_job, complete_job
from services.ai_service import generate_resume, generate_job_questions
from services.job_service import (
    get_all_jobs, get_job_by_id, create_job,
    get_user_applications, get_employer_jobs, smart_job_search,
    get_job_with_distance
)

logger = logging.getLogger(__name__)
api    = Blueprint("api", __name__, url_prefix="/api")

_last_call: dict = {}
_RATE_LIMIT_SEC  = 2


def ok(data=None, message="Success"):
    return jsonify({"success": True,  "data": data, "message": message})

def err(message="Error", code=400):
    return jsonify({"success": False, "data": None, "message": message}), code


@api.before_request
def _attach_request_id():
    g.request_id = str(uuid.uuid4())[:8]
    g.start_time = time.time()

@api.after_request
def _log_request(response):
    elapsed = round((time.time() - g.start_time) * 1000)
    logger.info(f"[{g.request_id}] {request.method} {request.path} → {response.status_code} ({elapsed}ms)")
    return response

@api.errorhandler(Exception)
def _handle_error(e):
    logger.error(f"[{getattr(g, 'request_id', '?')}] Unhandled error: {e}", exc_info=True)
    return jsonify({"success": False, "data": None,
                    "message": "Server error. Please try again."}), 500


# ── Auth ──────────────────────────────────────────────────────────────────────

@api.route("/auth/login", methods=["POST"])
def auth_login():
    body     = request.get_json(force=True) or {}
    phone    = body.get("phone", "").strip().replace(" ", "")
    name     = body.get("name", "").strip()
    location = body.get("location", "").strip()

    if not phone or len(phone) < 10:
        return err("Valid phone number required")

    user = User.query.filter_by(phone=phone).first()
    if not user:
        user = User(phone=phone, location=location)
        if name:
            user.name = name
        db.session.add(user)
        db.session.commit()
    else:
        if name and not user.name:
            user.name = name
        if location and not user.location:
            user.location = location
        db.session.commit()

    return ok(user.to_dict(), "Login successful")


@api.route("/auth/employer-login", methods=["POST"])
def employer_login():
    body     = request.get_json(force=True) or {}
    phone    = body.get("phone", "").strip().replace(" ", "")
    name     = body.get("name", "").strip()
    company  = body.get("company", "").strip()
    location = body.get("location", "").strip()

    if not phone or len(phone) < 10:
        return err("Valid phone number required")

    user = User.query.filter_by(phone=phone).first()
    if not user:
        user = User(phone=phone, location=location, role="employer")
        if name:    user.name = name
        if company: user.skill = company
        db.session.add(user)
    else:
        if name:    user.name = name
        if company: user.skill = company
        if location and not user.location: user.location = location
        user.role = "employer"
    db.session.commit()
    return ok(user.to_dict(), "Employer login successful")


# ── Core AI endpoint ──────────────────────────────────────────────────────────

@api.route("/ai/process", methods=["POST"])
def ai_process():
    body     = request.get_json(force=True) or {}
    phone    = body.get("phone", "").strip()
    text     = body.get("text", "").strip()
    location = body.get("location", "").strip()

    if not phone:
        return err("Phone number is required")
    if not text:
        return err("Message text is required")

    now = time.time()
    if phone in _last_call and now - _last_call[phone] < _RATE_LIMIT_SEC:
        return err("Please wait a moment before sending again"), 429
    _last_call[phone] = now

    for attempt in range(2):
        try:
            result = handle_message(phone, text, location)
            return ok(result)
        except Exception as e:
            logger.warning(f"[{g.request_id}] AI attempt {attempt+1} failed: {e}")
            if attempt == 1:
                return err("AI service temporarily unavailable. Please try again.")
            time.sleep(0.5)


# ── User endpoints ────────────────────────────────────────────────────────────

@api.route("/user/profile", methods=["GET"])
def get_profile():
    phone = request.args.get("phone", "").strip()
    if not phone:
        return err("Phone required")
    user = User.query.filter_by(phone=phone).first()
    if not user:
        user = User(phone=phone)
        db.session.add(user)
        db.session.commit()
    return ok(user.to_dict())


@api.route("/user/profile", methods=["PUT"])
def update_profile():
    body  = request.get_json(force=True) or {}
    phone = body.get("phone", "").strip()
    user  = User.query.filter_by(phone=phone).first()
    if not user:
        user = User(phone=phone)
        db.session.add(user)
        db.session.commit()
    for field in ("name", "skill", "language", "location"):
        if field in body:
            setattr(user, field, body[field])
    db.session.commit()
    return ok(user.to_dict())


@api.route("/user/applications", methods=["GET"])
def user_applications():
    phone = request.args.get("phone", "").strip()
    user  = User.query.filter_by(phone=phone).first()
    if not user:
        return ok([])
    return ok(get_user_applications(user.id))


@api.route("/user/jobs-posted", methods=["GET"])
def employer_jobs():
    phone = request.args.get("phone", "").strip()
    user  = User.query.filter_by(phone=phone).first()
    if not user:
        return ok([])
    return ok(get_employer_jobs(user.id))


@api.route("/user/recommended-jobs", methods=["GET"])
def recommended_jobs():
    phone = request.args.get("phone", "").strip()
    user  = User.query.filter_by(phone=phone).first()
    if not user:
        return ok([])
    return ok(smart_job_search(user))


# ── Worker trust profile ──────────────────────────────────────────────────────

@api.route("/user/trust-profile", methods=["GET"])
def trust_profile():
    phone = request.args.get("phone", "").strip()
    user  = User.query.filter_by(phone=phone).first()
    if not user:
        return err("User not found", 404)

    history   = WorkHistory.query.filter_by(user_id=user.id).all()
    completed = [h for h in history if h.status == "completed"]
    ratings   = [h.rating for h in completed if h.rating > 0]
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0.0
    verified   = user.trust_score >= 70 and len(completed) >= 3

    # Star display: e.g. "⭐ 4.5"
    stars = "⭐" * round(avg_rating) if avg_rating > 0 else "—"

    return ok({
        "name":           user.name or "Worker",
        "skill":          user.skill or "",
        "skill_level":    user.skill_level or "beginner",
        "trust_score":    round(user.trust_score or 50),
        "avg_rating":     avg_rating,
        "stars":          stars,
        "jobs_completed": len(completed),
        "jobs_applied":   len(history),
        "total_earnings": user.earnings or 0,
        "verified":       verified,
        "badge":          "✅ Verified" if verified else "🔄 Building Trust",
        "location":       user.location or "",
        "display":        f"{user.name or 'Worker'} ({KM_cap(user.skill or 'General')})\n"
                          f"{stars} {avg_rating} | {len(completed)} jobs | "
                          f"{'✅ Verified' if verified else '🔄 Building Trust'}",
    })


def KM_cap(s):
    return s.capitalize() if s else ""


# ── Job endpoints ─────────────────────────────────────────────────────────────

@api.route("/jobs", methods=["GET"])
def list_jobs():
    job_type = request.args.get("type")
    skill    = request.args.get("skill")
    location = request.args.get("location")
    return ok(get_all_jobs(job_type=job_type, skill=skill, location=location))


@api.route("/jobs/<int:job_id>", methods=["GET"])
def get_job(job_id):
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    job = get_job_with_distance(job_id, lat, lng)
    if not job:
        return err("Job not found", 404)
    return ok(job)


@api.route("/jobs/instant", methods=["GET"])
def instant_jobs():
    jobs = Job.query.filter(
        Job.job_type == "instant", Job.status == "open", Job.salary_unit == "hour"
    ).order_by(Job.salary.desc()).all()
    return ok([j.to_dict() for j in jobs])


@api.route("/jobs/skilled", methods=["GET"])
def skilled_jobs():
    jobs = Job.query.filter(
        Job.job_type == "skilled", Job.status == "open",
        Job.salary_unit == "month", Job.salary >= 4000, Job.salary <= 9000
    ).order_by(Job.salary.desc()).all()
    return ok([j.to_dict() for j in jobs])


@api.route("/jobs", methods=["POST"])
def post_job():
    body    = request.get_json(force=True) or {}
    phone   = body.pop("phone", "")
    user    = User.query.filter_by(phone=phone).first()
    user_id = user.id if user else None
    job     = create_job(body, user_id)
    return ok(job, "Job posted successfully")


@api.route("/jobs/<int:job_id>/apply", methods=["POST"])
def apply_job(job_id):
    body   = request.get_json(force=True) or {}
    phone  = body.get("phone", "")
    result = apply_to_job(phone, job_id)
    if result["success"]:
        return ok(result)
    return err(result["message"])


@api.route("/jobs/<int:job_id>/complete", methods=["POST"])
def complete_job_route(job_id):
    body      = request.get_json(force=True) or {}
    wh_id     = body.get("work_history_id")
    rating    = float(body.get("rating", 5))
    proof_url = body.get("proof_url", "")
    result    = complete_job(wh_id, rating, proof_url)
    if result["success"]:
        return ok(result)
    return err("Could not complete job")


# ── Application status update ─────────────────────────────────────────────────

@api.route("/applications/<int:wh_id>/status", methods=["POST"])
def update_application_status(wh_id):
    body   = request.get_json(force=True) or {}
    status = body.get("status", "").strip()
    allowed = {"accepted", "rejected", "in_progress", "completed"}
    if status not in allowed:
        return err(f"Status must be one of: {', '.join(allowed)}")
    wh = WorkHistory.query.get(wh_id)
    if not wh:
        return err("Application not found", 404)
    wh.status = status
    if status == "accepted":
        wh.accepted_at = datetime.utcnow()
    elif status == "completed":
        wh.completed_at = datetime.utcnow()
    db.session.commit()
    return ok(wh.to_dict(), f"Status updated to {status}")


# ── Reset conversation ────────────────────────────────────────────────────────

@api.route("/user/reset-conversation", methods=["POST"])
def reset_conversation():
    body  = request.get_json(force=True) or {}
    phone = body.get("phone", "").strip()
    user  = User.query.filter_by(phone=phone).first()
    if not user:
        return ok(message="Nothing to reset")
    user.last_state   = "IDLE"
    user.context_json = "{}"
    db.session.commit()
    return ok(message="Conversation reset")


# ── Post job (navbar form) ────────────────────────────────────────────────────

@api.route("/jobs/post", methods=["POST"])
def post_job_form():
    body     = request.get_json(force=True) or {}
    phone    = body.get("phone", "").strip()
    title    = body.get("title", "").strip()
    location = body.get("location", "").strip()
    duration = body.get("duration", "").strip()
    salary   = body.get("salary", 0)

    if not phone:
        return err("Login required", 401)
    if not title or not location or not duration or not salary:
        return err("Title, location, duration and salary are required")

    employer = User.query.filter_by(phone=phone).first()
    if not employer:
        return err("User not found", 404)

    job = Job(
        title       = title,
        description = body.get("description", ""),
        job_type    = body.get("job_type", "instant"),
        status      = body.get("status", "open"),
        salary      = float(salary),
        salary_unit = body.get("salary_unit", "day"),
        location    = location,
        duration    = duration,
        created_by  = employer.id,
        employer_fee_paid = False,
    )
    db.session.add(job)
    employer.role = "employer"
    db.session.commit()
    return ok(job.to_dict(), f"Job '{job.title}' posted successfully!")


# ── AI Resume ─────────────────────────────────────────────────────────────────

@api.route("/user/resume", methods=["GET"])
def get_resume():
    phone = request.args.get("phone", "").strip()
    lang  = request.args.get("lang", "hi")
    user  = User.query.filter_by(phone=phone).first()
    if not user:
        return err("User not found", 404)

    history = WorkHistory.query.filter_by(user_id=user.id).all()
    work_data = []
    for wh in history:
        job = Job.query.get(wh.job_id)
        if job:
            work_data.append({
                "title":     job.title,
                "location":  job.location,
                "salary":    job.salary,
                "unit":      job.salary_unit,
                "duration":  job.duration,
                "status":    wh.status,
                "rating":    wh.rating,
                "applied_at": wh.applied_at.strftime("%d %b %Y") if wh.applied_at else ""
            })

    completed  = [w for w in work_data if w["status"] == "completed"]
    rated      = [w["rating"] for w in completed if w["rating"] > 0]
    avg_rating = round(sum(rated) / len(rated), 1) if rated else 0.0

    user_data = {
        "name":           user.name or "Worker",
        "phone":          user.phone,
        "location":       user.location or "Not specified",
        "skill":          user.skill or "General Labour",
        "skill_level":    user.skill_level or "beginner",
        "skill_score":    round(user.skill_score or 0),
        "trust_score":    round(user.trust_score or 50),
        "earnings":       user.earnings or 0,
        "jobs_applied":   len(work_data),
        "jobs_completed": len(completed),
        "avg_rating":     avg_rating,
        "work_history":   work_data,
    }

    resume = generate_resume(user_data, lang)
    return ok({"resume": resume, "user": user_data})


# ── Employer: get applicants ──────────────────────────────────────────────────

@api.route("/employer/applicants/<int:job_id>", methods=["GET"])
def get_applicants(job_id):
    phone    = request.args.get("phone", "").strip()
    employer = User.query.filter_by(phone=phone).first()
    if not employer:
        return err("Login required", 401)

    job = Job.query.get(job_id)
    if not job:
        return err("Job not found", 404)
    if job.created_by != employer.id:
        return err("Access denied", 403)

    applications = WorkHistory.query.filter_by(job_id=job_id).all()
    result = []
    for wh in applications:
        worker = User.query.get(wh.user_id)
        if not worker:
            continue

        all_wh    = WorkHistory.query.filter_by(user_id=worker.id).all()
        completed = [w for w in all_wh if w.status == "completed"]
        ratings   = [w.rating for w in completed if w.rating > 0]
        avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0.0
        verified   = worker.trust_score >= 70 and len(completed) >= 3
        stars      = "⭐" * round(avg_rating) if avg_rating > 0 else "—"

        past_jobs = []
        for pw in completed[-3:]:
            pj = Job.query.get(pw.job_id)
            if pj:
                past_jobs.append({
                    "title":    pj.title,
                    "location": pj.location,
                    "salary":   pj.salary,
                    "unit":     pj.salary_unit,
                    "rating":   pw.rating,
                })

        result.append({
            "application_id":  f"KM-{wh.id:04d}",
            "wh_id":           wh.id,
            "status":          wh.status,
            "applied_at":      wh.applied_at.strftime("%d %b %Y, %I:%M %p") if wh.applied_at else "",
            "accepted_at":     wh.accepted_at.strftime("%d %b %Y") if wh.accepted_at else "",
            "worker_id":       worker.id,
            "name":            worker.name or "Worker",
            "phone":           worker.phone,
            "location":        worker.location or "",
            "skill":           worker.skill or "",
            "skill_level":     worker.skill_level or "beginner",
            "skill_score":     round(worker.skill_score or 0),
            "trust_score":     round(worker.trust_score or 50),
            "avg_rating":      avg_rating,
            "stars":           stars,
            "jobs_completed":  len(completed),
            "total_earnings":  worker.earnings or 0,
            "verified":        verified,
            "badge":           "✅ Verified" if verified else "🔄 Building Trust",
            "trust_display":   f"{worker.name or 'Worker'} ({KM_cap(worker.skill or 'General')})\n"
                               f"{stars} {avg_rating} | {len(completed)} jobs | "
                               f"{'✅ Verified' if verified else '🔄 Building Trust'}",
            "past_jobs":       past_jobs,
        })

    return ok(result)


# ── Monetization stats ────────────────────────────────────────────────────────

@api.route("/monetization/stats", methods=["GET"])
def monetization_stats():
    """Platform-level monetization overview (admin/demo use)."""
    total_commission = db.session.query(
        db.func.sum(WorkHistory.commission_amount)
    ).scalar() or 0.0

    total_jobs_posted = Job.query.count()
    employer_fees     = Job.query.filter_by(employer_fee_paid=True).count() * 50.0
    premium_users     = User.query.filter_by(is_premium=True).count()
    total_workers     = User.query.filter_by(role="worker").count()
    total_employers   = User.query.filter_by(role="employer").count()

    return ok({
        "total_commission_earned": round(total_commission, 2),
        "employer_post_fees":      round(employer_fees, 2),
        "total_revenue":           round(total_commission + employer_fees, 2),
        "total_jobs_posted":       total_jobs_posted,
        "premium_users":           premium_users,
        "total_workers":           total_workers,
        "total_employers":         total_employers,
        "commission_rate":         "5% per completed job",
        "employer_post_fee":       "₹50 per job post",
    })


# ── Job Q&A questions ────────────────────────────────────────────────────────

@api.route("/jobs/<int:job_id>/questions", methods=["GET"])
def get_job_questions(job_id):
    job = Job.query.get(job_id)
    if not job:
        return err("Job not found", 404)
    questions = generate_job_questions(job.to_dict())
    return ok(questions)


# ── Health check ──────────────────────────────────────────────────────────────

@api.route("/health", methods=["GET"])
def health():
    return ok({
        "jobs":   Job.query.count(),
        "users":  User.query.count(),
        "status": "ok"
    })
