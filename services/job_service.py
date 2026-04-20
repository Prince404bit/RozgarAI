"""
Job Service — CRUD and smart search for jobs.
All business logic lives here; routes just call these functions.
"""

import math
from models.database import db, Job, User, WorkHistory


def _haversine(lat1, lon1, lat2, lon2) -> float:
    """Return distance in km between two coordinates."""
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_job_with_distance(job_id: int, user_lat: float = None, user_lng: float = None) -> dict:
    """Return job detail with distance if user coords provided."""
    job = Job.query.get(job_id)
    if not job:
        return None
    d = job.to_dict()
    d["distance_km"] = None
    if user_lat is not None and user_lng is not None:
        job_lat = getattr(job, "lat", None)
        job_lng = getattr(job, "lng", None)
        if job_lat and job_lng:
            try:
                d["distance_km"] = round(_haversine(user_lat, user_lng, float(job_lat), float(job_lng)), 1)
            except Exception:
                pass
    d["process_steps"] = [
        "Apply via chat or Jobs page",
        "Employer contacts you",
        "Complete work",
        "Rate & get paid",
    ]
    return d


def get_all_jobs(job_type=None, skill=None, location=None, limit=50):
    q = Job.query  # show all statuses so user-posted jobs appear
    if job_type:
        q = q.filter_by(job_type=job_type)
    if skill:
        q = q.filter(Job.skill_required.ilike(f"%{skill}%"))
    if location:
        q = q.filter(Job.location.ilike(f"%{location}%"))
    return [j.to_dict() for j in q.order_by(Job.created_at.desc()).limit(limit).all()]


def get_job_by_id(job_id):
    job = Job.query.get(job_id)
    return job.to_dict() if job else None


def create_job(data: dict, user_id: int = None):
    job = Job(
        title           = data.get("title", ""),
        description     = data.get("description", ""),
        job_type        = data.get("job_type", "instant"),
        skill_required  = data.get("skill_required", ""),
        skill_level_min = data.get("skill_level_min", "beginner"),
        salary          = float(data.get("salary", 300)),
        salary_unit     = data.get("salary_unit", "day"),
        location        = data.get("location", ""),
        duration        = data.get("duration", "1 day"),
        created_by      = user_id,
    )
    db.session.add(job)
    db.session.commit()
    return job.to_dict()


def get_user_applications(user_id: int):
    rows = WorkHistory.query.filter_by(user_id=user_id).order_by(WorkHistory.applied_at.desc()).all()
    result = []
    for wh in rows:
        job = Job.query.get(wh.job_id)
        d = wh.to_dict()
        d["job_title"]    = job.title    if job else ""
        d["job_salary"]   = job.salary   if job else 0
        d["job_salary_unit"] = job.salary_unit if job else "day"
        d["job_location"] = job.location if job else ""
        d["job_duration"] = job.duration if job else ""
        d["job_type"]     = job.job_type if job else ""
        result.append(d)
    return result


def get_employer_jobs(user_id: int):
    jobs = Job.query.filter_by(created_by=user_id).all()
    result = []
    for j in jobs:
        applicants = WorkHistory.query.filter_by(job_id=j.id).count()
        d = j.to_dict()
        d["applicants"] = applicants
        result.append(d)
    return result


def smart_job_search(user: User):
    """Return best matching jobs for a given user."""
    level_order = {"beginner": 0, "intermediate": 1, "expert": 2}
    user_lvl = level_order.get(user.skill_level or "beginner", 0)
    skill = (user.skill or "").lower()

    all_jobs = Job.query.filter_by(status="open").all()
    scored = []
    for j in all_jobs:
        score = 0
        j_skill = (j.skill_required or "").lower()
        j_min   = level_order.get(j.skill_level_min or "beginner", 0)

        # Skill match
        if skill and (j_skill in skill or skill in j_skill):
            score += 50
        # Level match
        if user_lvl >= j_min:
            score += 30
        # Higher pay bonus
        score += min(20, j.salary / 50)

        scored.append((score, j))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [j.to_dict() for _, j in scored[:6]]
