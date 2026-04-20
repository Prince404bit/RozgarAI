"""
Conversation Service — brain of KaamMitr.
Handles: voice flow, skill detection, job matching, context memory, trust score.
"""

import json
import logging
from datetime import datetime
from models.database import db, User, Job, WorkHistory
from services.ai_service import process_user_input, generate_first_question
from config import Config

logger = logging.getLogger(__name__)

COMMISSION_RATE   = 0.05
EMPLOYER_POST_FEE = 50.0


def _load_context(user: User) -> dict:
    try:
        ctx = json.loads(user.context_json or "{}")
    except Exception:
        ctx = {}
    ctx["last_state"]  = user.last_state or "IDLE"
    ctx["language"]    = user.language or "hi"
    ctx["skill"]       = user.skill or ""
    ctx["skill_level"] = user.skill_level or ""
    ctx.setdefault("last_job_id",    None)
    ctx.setdefault("last_job_title", "")
    ctx.setdefault("session_count",  0)
    return ctx


def _save_context(user: User, ctx: dict, next_state: str):
    user.last_state = next_state
    ctx["session_count"] = ctx.get("session_count", 0) + 1
    ctx_json = json.dumps(ctx, ensure_ascii=False)
    if len(ctx_json) > 10240:
        keep = {"last_state", "language", "skill", "skill_level",
                "skill_score", "last_job_id", "last_job_title", "session_count"}
        ctx = {k: v for k, v in ctx.items() if k in keep}
        ctx_json = json.dumps(ctx, ensure_ascii=False)
    user.context_json = ctx_json
    db.session.commit()


def _smart_greeting(user: User, ctx: dict) -> str:
    lang     = ctx.get("language", "hi")
    skill    = ctx.get("skill", "")
    sessions = ctx.get("session_count", 0)

    if sessions > 0 and skill:
        if lang == "hi":
            return (f"Wapas aaye! 🙏 Kal aapne {skill} ka kaam kiya tha.\n"
                    f"Kya aaj bhi {skill} ka kaam chahiye? Ya kuch aur?")
        elif lang == "te":
            return f"తిరిగి వచ్చారు! 🙏 మీరు {skill} పని చేశారు. ఈరోజు కూడా అదే కావాలా?"
        else:
            return (f"Welcome back! 🙏 Last time you worked as {skill}.\n"
                    f"Want the same type of work today?")

    if lang == "hi":
        return ("Namaste! 🙏 Main aapka KaamMitr hun.\n\n"
                "🎤 Bolo ya likho:\n"
                "• 'Kaam chahiye' — aaj hi paise kamao\n"
                "• Apni skill batao — electrician, driver, cook...\n"
                "• 'Worker chahiye' — agar aap employer hain")
    elif lang == "te":
        return ("నమస్కారం! 🙏 నేను మీ KaamMitr.\n\n"
                "• 'పని కావాలి' — ఈరోజే సంపాదించండి\n"
                "• మీ నైపుణ్యం చెప్పండి\n"
                "• 'కార్మికుడు కావాలి' — employer అయితే")
    return ("Hello! 🙏 I'm your KaamMitr.\n\n"
            "🎤 Say or type:\n"
            "• 'Need work' — earn today\n"
            "• Tell your skill — electrician, driver, cook...\n"
            "• 'Need a worker' — if you're an employer")


def _earning_estimate(jobs: list, lang: str) -> str:
    if not jobs:
        return ""
    top    = jobs[0]
    salary = top.get("salary", 0) if isinstance(top, dict) else top.salary
    unit   = top.get("salary_unit", "hour") if isinstance(top, dict) else top.salary_unit
    dur    = top.get("duration", "") if isinstance(top, dict) else top.duration

    hours = 4
    dur_lower = str(dur).lower()
    for n in range(8, 0, -1):
        if str(n) in dur_lower:
            hours = n
            break

    est = salary * hours if unit == "hour" else salary

    if lang == "hi":
        return f"\n\n💰 Aaj ki kamai estimate: ₹{int(est)} tak!"
    elif lang == "te":
        return f"\n\n💰 ఈరోజు సంపాదన అంచనా: ₹{int(est)} వరకు!"
    return f"\n\n💰 Today's earning estimate: up to ₹{int(est)}!"


def handle_message(phone: str, text: str, location: str = "") -> dict:
    text = (text or "").strip()
    if not text:
        text = "help"

    user = User.query.filter_by(phone=phone).first()
    if not user:
        user = User(phone=phone, location=location or "")
        db.session.add(user)
        db.session.commit()

    ctx = _load_context(user)

    # Smart context: repeat last skill on affirmative
    last_skill = ctx.get("skill", "")
    text_lower = text.lower()
    repeat_kw  = ["haan", "yes", "same", "wahi", "phir se", "again", "ha "]
    if any(k in text_lower for k in repeat_kw) and last_skill and ctx.get("last_state") in ("IDLE", "ASKING_MODE"):
        text = f"mujhe {last_skill} ka kaam chahiye"

    try:
        ai_result = process_user_input(text, ctx)
    except Exception as e:
        logger.error(f"AI processing failed for {phone}: {e}")
        ai_result = {
            "intent": "find_work",
            "next_state": "INSTANT_JOBS",
            "response_text": _smart_greeting(user, ctx),
            "language": ctx.get("language", "hi"),
            "extracted_data": {},
        }

    intent     = ai_result.get("intent", "unknown")
    next_state = ai_result.get("next_state", "ASKING_MODE")
    language   = ai_result.get("language", ctx.get("language", "hi"))
    response   = ai_result.get("response_text", "")
    extracted  = ai_result.get("extracted_data", {})

    if language:
        user.language = language
        ctx["language"] = language

    if extracted.get("skill"):
        user.skill = extracted["skill"]
        ctx["skill"] = extracted["skill"]

    if extracted.get("skill_level"):
        user.skill_level = extracted["skill_level"]
        ctx["skill_level"] = extracted["skill_level"]

    if extracted.get("temp_job"):
        ctx["temp_job"] = extracted["temp_job"]

    for field in ("qa_round", "qa_score", "current_question", "correct_keywords"):
        if field in extracted:
            ctx[field] = extracted[field]

    if "skill_score" in ai_result:
        user.skill_score = ai_result["skill_score"]
        ctx["skill_score"] = ai_result["skill_score"]
    elif extracted.get("skill_score"):
        user.skill_score = extracted["skill_score"]
        ctx["skill_score"] = extracted["skill_score"]

    if extracted.get("has_skill") and extracted.get("skill"):
        ctx["skill"] = extracted["skill"]
        user.skill = extracted["skill"]

    if intent in ("find_work", "skill_based_job", "help", "unknown"):
        ctx["temp_job"] = {}

    jobs         = []
    show_instant = False
    show_skilled = False

    if next_state == "INSTANT_JOBS":
        jobs = _get_instant_jobs(user, location)
        show_instant = True
        if jobs:
            response += _earning_estimate(jobs, language)

    elif next_state == "SHOWING_JOBS":
        jobs = _get_skilled_jobs(user)
        show_skilled = True
        if not jobs:
            jobs = _get_instant_jobs(user, location)
            show_instant = True
            response += "\n\n" + _no_skilled_jobs_msg(language)
        if jobs:
            response += _earning_estimate(jobs, language)

    elif next_state == "SKILL_QA" and ctx.get("qa_round", 0) == 0:
        q_data   = generate_first_question(ctx.get("skill", ""), ctx.get("skill_level", "intermediate"), language)
        question = q_data.get("question", "")
        keywords = q_data.get("correct_keywords", [])
        ctx["current_question"] = question
        ctx["correct_keywords"] = keywords
        ctx["qa_round"]         = 0
        ctx["qa_score"]         = 0
        response = response + ("\n\n" if response else "") + question

    elif next_state == "JOB_POSTED":
        temp_job = ctx.get("temp_job", {})
        _save_posted_job(temp_job, user)
        ctx["temp_job"] = {}

    elif next_state == "HELPING":
        response = _help_message(language)

    elif next_state == "ASKING_MODE" and not response:
        response = _smart_greeting(user, ctx)

    if jobs:
        first = jobs[0]
        ctx["last_job_id"]    = first.id if hasattr(first, "id") else first.get("id")
        ctx["last_job_title"] = first.title if hasattr(first, "title") else first.get("title", "")

    _save_context(user, ctx, next_state)

    return {
        "response_text": response,
        "jobs":          [j.to_dict() if hasattr(j, "to_dict") else j for j in jobs],
        "state":         next_state,
        "user":          user.to_dict(),
        "intent":        intent,
        "show_instant":  show_instant,
        "show_skilled":  show_skilled,
        "language":      language,
    }


def _get_instant_jobs(user: User, location: str = "") -> list:
    q = Job.query.filter(Job.job_type == "instant", Job.status == "open", Job.salary_unit == "hour")
    if location or user.location:
        loc = (location or user.location).split(',')[0].strip()[:10]
        q = q.filter(Job.location.ilike(f"%{loc}%"))
    jobs = q.order_by(Job.salary.desc()).limit(8).all()
    if not jobs:
        jobs = Job.query.filter_by(job_type="instant", status="open").limit(8).all()
    return jobs


def _get_skilled_jobs(user: User) -> list:
    return Job.query.filter(
        Job.job_type == "skilled", Job.status == "open",
        Job.salary_unit == "month", Job.salary >= 4000, Job.salary <= 9000
    ).order_by(Job.salary.desc()).limit(8).all()


def _save_posted_job(temp_job: dict, user: User):
    if not temp_job.get("title"):
        return
    job = Job(
        title           = temp_job.get("title", "Job Opening"),
        description     = temp_job.get("description", ""),
        job_type        = temp_job.get("job_type", "skilled"),
        skill_required  = temp_job.get("skill_required", ""),
        skill_level_min = temp_job.get("skill_level_min", "beginner"),
        salary          = float(temp_job.get("salary", 300)),
        location        = temp_job.get("location", user.location or ""),
        duration        = temp_job.get("duration", "1 day"),
        created_by      = user.id,
        status          = "open",
        employer_fee_paid = False,
    )
    user.role = "employer"
    db.session.add(job)
    db.session.commit()
    logger.info(f"Job posted: {job.title} by user {user.id} | fee: ₹{EMPLOYER_POST_FEE}")


def apply_to_job(phone: str, job_id: int) -> dict:
    user = User.query.filter_by(phone=phone).first()
    if not user:
        return {"success": False, "message": "User not found"}

    job = Job.query.get(job_id)
    if not job or job.status != "open":
        return {"success": False, "message": "Job not available"}

    existing = WorkHistory.query.filter_by(user_id=user.id, job_id=job_id).first()
    if existing:
        lang = user.language or "hi"
        msgs = {
            "hi": f"Aap pehle se '{job.title}' ke liye apply kar chuke hain. ID: KM-{existing.id:04d}",
            "en": f"Already applied to '{job.title}'. ID: KM-{existing.id:04d}",
            "te": f"'{job.title}' కి ఇంకా apply చేసారు. ID: KM-{existing.id:04d}"
        }
        return {"success": False, "message": msgs.get(lang, msgs["en"]),
                "already_applied": True, "work_history_id": existing.id}

    commission = round(job.salary * job.commission_rate, 2)
    wh = WorkHistory(user_id=user.id, job_id=job_id, status="applied", commission_amount=commission)
    db.session.add(wh)
    db.session.commit()

    lang   = user.language or "hi"
    app_id = f"KM-{wh.id:04d}"
    logger.info(f"Application {app_id} | job={job.title} | commission=₹{commission}")

    msgs = {
        "hi": (f"✅ Application submit ho gayi!\n\n"
               f"📋 Job: {job.title}\n📍 Location: {job.location}\n"
               f"💰 Payment: ₹{job.salary}/{job.salary_unit}\n"
               f"⏱ Duration: {job.duration}\n🆔 ID: {app_id}\n\n"
               f"Employer jald hi contact karega."),
        "en": (f"✅ Application submitted!\n\n"
               f"📋 Job: {job.title}\n📍 Location: {job.location}\n"
               f"💰 Payment: ₹{job.salary}/{job.salary_unit}\n"
               f"⏱ Duration: {job.duration}\n🆔 ID: {app_id}\n\n"
               f"Employer will contact you soon."),
        "te": (f"✅ Application submit అయింది!\n\n"
               f"📋 Job: {job.title}\n📍 Location: {job.location}\n"
               f"💰 Payment: ₹{job.salary}/{job.salary_unit}\n"
               f"⏱ Duration: {job.duration}\n🆔 ID: {app_id}\n\n"
               f"Employer మీకు contact చేస్తారు.")
    }

    return {
        "success":         True,
        "message":         msgs.get(lang, msgs["en"]),
        "work_history_id": wh.id,
        "application_id":  app_id,
        "job_title":       job.title,
        "job_location":    job.location,
        "job_salary":      job.salary,
        "job_salary_unit": job.salary_unit,
        "job_duration":    job.duration,
        "status":          "applied",
        "commission":      commission,
    }


def complete_job(work_history_id: int, rating: float, proof_url: str = "") -> dict:
    wh = WorkHistory.query.get(work_history_id)
    if not wh:
        return {"success": False}

    wh.status       = "completed"
    wh.rating       = rating
    wh.proof_url    = proof_url
    wh.completed_at = datetime.utcnow()

    user = User.query.get(wh.user_id)
    if user:
        user.trust_score = min(100, user.trust_score * 0.8 + rating * 20 * 0.2)
        if proof_url:
            user.trust_score = min(100, user.trust_score + 2)
        job = Job.query.get(wh.job_id)
        if job:
            user.earnings += job.salary
            commission = round(job.salary * job.commission_rate, 2)
            user.commission_earned = (user.commission_earned or 0) + commission
            wh.commission_amount = commission
            logger.info(f"Job completed | user={user.id} | commission=₹{commission}")

    db.session.commit()
    return {"success": True, "trust_score": user.trust_score if user else 0}


def _no_skilled_jobs_msg(lang):
    if lang == "hi":
        return "Abhi aapki skill ke liye koi job nahi hai, par instant kaam se aaj hi shuru kar sakte hain! 💪"
    return "No skilled jobs right now, but you can start earning today with instant work! 💪"


def _help_message(lang):
    if lang == "hi":
        return ("🆘 Help:\n\n"
                "• Instant kaam: 'Kaam chahiye' bolo\n"
                "• Skill job: Apni skill batao\n"
                "• Job post: 'Worker chahiye' bolo\n"
                "• Profile: Menu mein 'Profile' dabao\n\n"
                "Koi bhi sawaal ho — poochh sakte hain! 😊")
    elif lang == "te":
        return ("🆘 సహాయం:\n\n"
                "• తక్షణ పని: 'పని కావాలి' అనండి\n"
                "• నైపుణ్య ఉద్యోగం: మీ నైపుణ్యం చెప్పండి\n"
                "• ఉద్యోగం పోస్ట్: 'కార్మికుడు కావాలి' అనండి\n"
                "• ప్రొఫైల్: Menu లో 'Profile' నొక్కండి\n\n"
                "ఏదైనా అడగండి — సహాయం చేస్తాను! 😊")
    return ("🆘 Help:\n\n"
            "• Instant work: Say 'Need work'\n"
            "• Skill job: Tell your skill\n"
            "• Post a job: Say 'Need a worker'\n"
            "• Profile: Tap 'Profile' in menu\n\n"
            "Ask me anything! 😊")
