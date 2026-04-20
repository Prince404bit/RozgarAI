"""
AI Service — Gemini as the Central Decision Engine.

Single entry point:  process_user_input(text, context) → AIResult dict
All intents, skill detection, Q&A, job matching suggestions go through here.
"""

import json
import re
import logging
from config import Config

logger = logging.getLogger(__name__)

# ── Try importing Gemini SDK ────────────────────────────────────────────────
try:
    import google.generativeai as genai
    genai.configure(api_key=Config.GEMINI_API_KEY)
    _model = genai.GenerativeModel(Config.GEMINI_MODEL)
    GEMINI_AVAILABLE = bool(Config.GEMINI_API_KEY)
except Exception as e:
    logger.warning(f"Gemini SDK not available: {e}")
    GEMINI_AVAILABLE = False
    _model = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call_gemini(prompt: str, json_mode: bool = True) -> str:
    """Low-level Gemini call with retry + JSON stripping."""
    if not GEMINI_AVAILABLE or not _model:
        raise RuntimeError("Gemini not configured")

    response = _model.generate_content(prompt)
    text = response.text.strip()

    if json_mode:
        # Strip markdown code fences if present
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)

    return text.strip()


def _safe_json(text: str) -> dict:
    """Parse JSON safely; return empty dict on failure."""
    try:
        return json.loads(text)
    except Exception:
        # Try to extract JSON object from larger text
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return {}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def process_user_input(user_text: str, context: dict) -> dict:
    """
    Unified AI processor for ALL user inputs.

    context keys used:
        last_state  – current conversation state
        language    – "hi" or "en"
        skill       – current skill if known
        skill_level – current level if known
        qa_round    – question round index (int)
        qa_score    – running score (int)
        qa_questions – list of questions asked so far
        temp_job    – partial employer job dict

    Returns dict:
        intent          – find_work | skill_based_job | post_job | help | unknown | apply_job
        user_type       – worker | employer | unknown
        next_state      – new conversation state
        response_text   – what to say back to user (in detected language)
        extracted_data  – skill, level, answers, etc.
        language        – detected language
        jobs_to_show    – list of job ids (optional)
        skill_score     – evaluated score (optional)
    """

    language = context.get("language", "hi")
    last_state = context.get("last_state", "IDLE")

    if GEMINI_AVAILABLE:
        return _gemini_process(user_text, context, language, last_state)
    else:
        return _rule_based_fallback(user_text, context, language, last_state)


# ---------------------------------------------------------------------------
# Gemini-powered processing
# ---------------------------------------------------------------------------

SYSTEM_PERSONA = """
You are a helpful employment assistant for rural India.
You help low-literacy, low-income workers find jobs and help employers find workers.
Always respond in the SAME language as the user (Hindi or English).
Be friendly, simple, and encouraging.
Never use complex words.
"""

def _gemini_process(user_text, context, language, last_state):
    """Route to correct Gemini prompt based on state."""

    # State-aware routing
    if last_state in ("IDLE", "ASKING_MODE"):
        return _detect_intent(user_text, context, language)

    elif last_state == "ASKING_SKILL":
        return _extract_skill(user_text, context, language)

    elif last_state == "ASKING_LEVEL":
        return _extract_level(user_text, context, language)

    elif last_state == "SKILL_QA":
        return _evaluate_answer(user_text, context, language)

    elif last_state in ("POST_JOB_ROLE", "POST_JOB_SALARY", "POST_JOB_LOC", "POST_JOB_DUR"):
        return _collect_job_info(user_text, context, language, last_state)

    else:
        return _detect_intent(user_text, context, language)


def _detect_intent(user_text, context, language):
    """Step 1 — Understand what user wants."""
    prompt = f"""
{SYSTEM_PERSONA}

User message: "{user_text}"

Analyze and return ONLY valid JSON (no markdown, no explanation):
{{
  "intent": "<find_work | skill_based_job | post_job | help | unknown>",
  "user_type": "<worker | employer | unknown>",
  "language": "<hi | en>",
  "has_skill_mentioned": <true|false>,
  "skill_mentioned": "<skill or empty string>",
  "response_text": "<short, warm reply in the user's language asking next step>"
}}

Rules:
- If user says kaam chahiye / need work / naukri → intent = find_work
- If user mentions a skill (electrician, plumber, driver etc) → intent = skill_based_job
- If user says worker chahiye / need worker / hire → intent = post_job, user_type = employer
- If ambiguous → intent = unknown, ask clarifying question
- response_text must be in the same language as the user (detect from message)
"""

    raw = _call_gemini(prompt)
    data = _safe_json(raw)

    intent = data.get("intent", "unknown")
    user_type = data.get("user_type", "worker")
    lang = data.get("language", language)
    has_skill = data.get("has_skill_mentioned", False)
    skill = data.get("skill_mentioned", "")
    response_text = data.get("response_text", _default_greeting(lang))

    # Decide next state
    if intent == "find_work":
        next_state = "INSTANT_JOBS"
    elif intent == "skill_based_job":
        if has_skill and skill:
            next_state = "ASKING_LEVEL"
        else:
            next_state = "ASKING_SKILL"
    elif intent == "post_job":
        next_state = "POST_JOB_ROLE"
    elif intent == "help":
        next_state = "HELPING"
    else:
        next_state = "ASKING_MODE"

    return {
        "intent": intent,
        "user_type": user_type,
        "next_state": next_state,
        "response_text": response_text,
        "language": lang,
        "extracted_data": {"skill": skill, "has_skill": has_skill},
    }


def _extract_skill(user_text, context, language):
    """Extract skill name from user message."""
    prompt = f"""
{SYSTEM_PERSONA}

User said: "{user_text}"

Extract skill and return ONLY valid JSON:
{{
  "skill_found": <true|false>,
  "skill": "<normalised skill name in English, lowercase, e.g. electrician, plumber, mason, carpenter, driver, welder, painter, tailor, cook>",
  "response_text": "<reply in user's language confirming skill or asking again>"
}}

If no clear skill is mentioned, set skill_found=false and ask again in simple language.
Language for response: {language}
"""
    raw = _call_gemini(prompt)
    data = _safe_json(raw)

    skill_found = data.get("skill_found", False)
    skill = data.get("skill", "")
    response_text = data.get("response_text", "Aapki skill kya hai? (e.g. electrician, plumber)")

    if skill_found and skill:
        next_state = "ASKING_LEVEL"
    else:
        next_state = "ASKING_SKILL"

    return {
        "intent": "skill_based_job",
        "user_type": "worker",
        "next_state": next_state,
        "response_text": response_text,
        "language": language,
        "extracted_data": {"skill": skill},
    }


def _extract_level(user_text, context, language):
    """Determine beginner/intermediate/expert from user message."""
    prompt = f"""
{SYSTEM_PERSONA}

User said: "{user_text}"
Context — known skill: {context.get('skill', 'unknown')}

Determine skill level and return ONLY valid JSON:
{{
  "skill_level": "<beginner | intermediate | expert>",
  "response_text": "<reply in {language} confirming level and explaining next step>"
}}

Mapping hints:
- naya/abhi seekha/helper/thoda → beginner
- kuch saal kaam kiya / 1-2 saal / thik hai → intermediate
- expert / experienced / bahut saal / professional → expert
- numbers: 0-1yr = beginner, 1-4yr = intermediate, 4+yr = expert
"""
    raw = _call_gemini(prompt)
    data = _safe_json(raw)

    level = data.get("skill_level", "beginner")
    response_text = data.get("response_text", "")

    # Beginners go straight to jobs; intermediate/expert do Q&A
    if level == "beginner":
        next_state = "SHOWING_JOBS"
    else:
        next_state = "SKILL_QA"

    return {
        "intent": "skill_based_job",
        "user_type": "worker",
        "next_state": next_state,
        "response_text": response_text,
        "language": language,
        "extracted_data": {"skill_level": level},
    }


def _generate_skill_question(skill, level, round_num, language):
    """Generate one skill assessment question."""
    prompt = f"""
You are assessing a {level}-level {skill} worker in India.
Generate question #{round_num + 1} (practical, simple, relevant to Indian rural context).

Return ONLY valid JSON:
{{
  "question": "<question in {language} — simple words>",
  "correct_keywords": ["<keyword1>", "<keyword2>", "<keyword3>"]
}}

Rules:
- intermediate: basic practical questions
- expert: scenario-based / troubleshooting
- Keep language very simple
- Max 1 sentence question
"""
    raw = _call_gemini(prompt)
    return _safe_json(raw)


def _evaluate_answer(user_text, context, language):
    """Evaluate one Q&A answer and decide next step."""
    skill = context.get("skill", "")
    level = context.get("skill_level", "intermediate")
    qa_round = int(context.get("qa_round", 0))
    qa_score = int(context.get("qa_score", 0))
    current_question = context.get("current_question", "")
    correct_keywords = context.get("correct_keywords", [])

    # Score the answer
    prompt = f"""
Skill: {skill}, Level: {level}
Question: "{current_question}"
Expected keywords: {correct_keywords}
User's answer: "{user_text}"

Return ONLY valid JSON:
{{
  "score": <0-10>,
  "correct": <true|false>,
  "feedback": "<1 line feedback in {language}>"
}}
"""
    raw = _call_gemini(prompt)
    eval_data = _safe_json(raw)
    score = eval_data.get("score", 5)
    feedback = eval_data.get("feedback", "")

    new_score = qa_score + score
    new_round = qa_round + 1

    # Max 3 questions for intermediate, 4 for expert
    max_rounds = 3 if level == "intermediate" else 4

    if new_round >= max_rounds:
        # Final evaluation
        final_score = (new_score / (max_rounds * 10)) * 100
        if final_score >= 60:
            msg = _skill_pass_message(skill, level, round(final_score), language)
            next_state = "SHOWING_JOBS"
        else:
            msg = _skill_low_message(language) + f"\n\n{feedback}"
            next_state = "INSTANT_JOBS"

        return {
            "intent": "skill_based_job",
            "user_type": "worker",
            "next_state": next_state,
            "response_text": msg,
            "language": language,
            "extracted_data": {"qa_round": new_round, "qa_score": new_score},
            "skill_score": round(final_score),
        }
    else:
        # Generate next question
        q_data = _generate_skill_question(skill, level, new_round, language)
        question_text = q_data.get("question", _fallback_question(skill, language))
        new_keywords = q_data.get("correct_keywords", [])

        return {
            "intent": "skill_based_job",
            "user_type": "worker",
            "next_state": "SKILL_QA",
            "response_text": f"{feedback}\n\n{question_text}",
            "language": language,
            "extracted_data": {
                "qa_round": new_round,
                "qa_score": new_score,
                "current_question": question_text,
                "correct_keywords": new_keywords,
            },
        }


def _collect_job_info(user_text, context, language, last_state):
    """Step-by-step employer job posting (one field at a time)."""
    temp_job = context.get("temp_job", {})

    if last_state == "POST_JOB_ROLE":
        temp_job["title"] = user_text.strip()
        response = _salary_question(language)
        next_state = "POST_JOB_SALARY"

    elif last_state == "POST_JOB_SALARY":
        # Extract salary number
        nums = re.findall(r'\d+', user_text)
        salary = int(nums[0]) if nums else 300
        temp_job["salary"] = salary
        response = _location_question(language)
        next_state = "POST_JOB_LOC"

    elif last_state == "POST_JOB_LOC":
        temp_job["location"] = user_text.strip()
        response = _duration_question(language)
        next_state = "POST_JOB_DUR"

    elif last_state == "POST_JOB_DUR":
        temp_job["duration"] = user_text.strip()
        # Refine with Gemini if available, else heuristic fallback
        try:
            if GEMINI_AVAILABLE:
                refined = _refine_job_with_gemini(temp_job, language)
                temp_job.update(refined)
        except Exception:
            pass
        # Heuristic defaults
        title_lower = (temp_job.get('title') or '').lower()
        skilled_words = ['electrician','plumber','carpenter','mason','welder','driver','tailor','painter']
        temp_job.setdefault('job_type', 'skilled' if any(w in title_lower for w in skilled_words) else 'instant')
        temp_job.setdefault('skill_required', next((w for w in skilled_words if w in title_lower), ''))
        temp_job.setdefault('skill_level_min', 'beginner')
        temp_job.setdefault('description', temp_job.get('title',''))
        summary = _job_summary(temp_job, language)
        response = summary
        next_state = "JOB_POSTED"

    else:
        response = _role_question(language)
        next_state = "POST_JOB_ROLE"

    return {
        "intent": "post_job",
        "user_type": "employer",
        "next_state": next_state,
        "response_text": response,
        "language": language,
        "extracted_data": {"temp_job": temp_job},
    }


def _refine_job_with_gemini(job: dict, language: str) -> dict:
    """Let Gemini add skill_required, skill_level_min, job_type etc."""
    prompt = f"""
Job details collected from employer:
{json.dumps(job, ensure_ascii=False)}

Return ONLY valid JSON with these added/improved fields:
{{
  "skill_required": "<skill name if specific, else empty>",
  "skill_level_min": "<beginner|intermediate|expert>",
  "job_type": "<instant|skilled>",
  "description": "<2 line job description in {language}>"
}}
"""
    raw = _call_gemini(prompt)
    return _safe_json(raw)


# ---------------------------------------------------------------------------
# Rule-based fallback (when Gemini is not configured)
# ---------------------------------------------------------------------------

INSTANT_KEYWORDS = [
    "kaam", "kama", "paise", "earning", "work", "job", "naukri",
    "instant", "turant", "aaj", "today",
]
SKILL_KEYWORDS = [
    "electrician", "plumber", "carpenter", "mason", "driver",
    "welder", "painter", "tailor", "cook", "mistri", "bijli",
    "paani", "lohar", "darzi", "electrical", "plumbing",
]
EMPLOYER_KEYWORDS = [
    "worker chahiye", "worker chaiye", "mujhe worker", "mujhe mazdoor",
    "labour chahiye", "mazdoor chahiye", "hire karna", "kaam dena hai",
    "need worker", "need labour", "rakna hai",
]


HELP_KEYWORDS = ["help", "madad", "samajh", "kya kare", "?", "bataao", "batao", "kaise"]

def _rule_based_fallback(user_text, context, language, last_state):
    """
    State-aware rule-based fallback used when Gemini is not configured.
    Mirrors the same routing logic as _gemini_process().
    """
    text_lower = user_text.lower().strip()

    # ── State-specific handling (mirrors Gemini branch) ──────────────────
    if last_state == "ASKING_SKILL":
        return _extract_skill_rules(user_text, context, language)

    if last_state == "ASKING_LEVEL":
        return _extract_level_rules(user_text, context, language)

    if last_state == "SKILL_QA":
        # Simple pass — score 5/10 and advance round
        qa_round = int(context.get("qa_round", 0)) + 1
        qa_score = int(context.get("qa_score", 0)) + 5
        max_rounds = 3 if context.get("skill_level") == "intermediate" else 4
        if qa_round >= max_rounds:
            final = (qa_score / (max_rounds * 10)) * 100
            if final >= 50:
                msg = _skill_pass_message(context.get("skill",""), context.get("skill_level",""), round(final), language)
                ns  = "SHOWING_JOBS"
            else:
                msg = _skill_low_message(language)
                ns  = "INSTANT_JOBS"
            return {"intent":"skill_based_job","user_type":"worker","next_state":ns,
                    "response_text":msg,"language":language,
                    "extracted_data":{"qa_round":qa_round,"qa_score":qa_score},
                    "skill_score": round(final)}
        else:
            q = _fallback_question(context.get("skill",""), language)
            return {"intent":"skill_based_job","user_type":"worker","next_state":"SKILL_QA",
                    "response_text": q, "language":language,
                    "extracted_data":{"qa_round":qa_round,"qa_score":qa_score,
                                      "current_question":q,"correct_keywords":[]}}

    if last_state in ("POST_JOB_ROLE","POST_JOB_SALARY","POST_JOB_LOC","POST_JOB_DUR"):
        return _collect_job_info(user_text, context, language, last_state)

    # ── Detect language ──────────────────────────────────────────────────
    from utils.helpers import detect_language
    detected_lang = detect_language(user_text)
    if detected_lang != language:
        language = detected_lang

    # ── Fresh intent detection ────────────────────────────────────────────
    detected_skill = next((k for k in SKILL_KEYWORDS if k in text_lower), None)
    is_employer    = any(k in text_lower for k in EMPLOYER_KEYWORDS)
    is_worker      = any(k in text_lower for k in INSTANT_KEYWORDS)
    is_help        = any(k in text_lower for k in HELP_KEYWORDS)

    if is_employer:
        return {"intent":"post_job","user_type":"employer","next_state":"POST_JOB_ROLE",
                "response_text":_role_question(language),"language":language,"extracted_data":{}}

    if detected_skill:
        return {"intent":"skill_based_job","user_type":"worker","next_state":"ASKING_LEVEL",
                "response_text":_level_question(detected_skill, language),
                "language":language,"extracted_data":{"skill":detected_skill}}

    if is_worker and not is_help:
        return {"intent":"find_work","user_type":"worker","next_state":"INSTANT_JOBS",
                "response_text":_instant_jobs_message(language),"language":language,"extracted_data":{}}

    if is_help:
        return {"intent":"help","user_type":"unknown","next_state":"HELPING",
                "response_text":"","language":language,"extracted_data":{}}

    return {"intent":"unknown","user_type":"unknown","next_state":"ASKING_MODE",
            "response_text":_default_greeting(language),"language":language,"extracted_data":{}}


def _extract_skill_rules(user_text, context, language):
    text_lower = user_text.lower()
    detected = next((k for k in SKILL_KEYWORDS if k in text_lower), None)
    if detected:
        return {"intent":"skill_based_job","user_type":"worker","next_state":"ASKING_LEVEL",
                "response_text":_level_question(detected, language),
                "language":language,"extracted_data":{"skill":detected}}
    return {"intent":"skill_based_job","user_type":"worker","next_state":"ASKING_SKILL",
            "response_text":"Apni skill batao — jaise electrician, plumber, driver...",
            "language":language,"extracted_data":{}}


def _extract_level_rules(user_text, context, language):
    text_lower = user_text.lower()
    expert_kw  = ["expert","experienced","professional","5","6","7","8","9","10","bahut"]
    inter_kw   = ["intermediate","2","3","4","thik","kuch saal","saal"]
    if any(k in text_lower for k in expert_kw):
        level = "expert"
    elif any(k in text_lower for k in inter_kw):
        level = "intermediate"
    else:
        level = "beginner"
    skill = context.get("skill","")
    if level == "beginner":
        msg = _skill_pass_message(skill, level, 60, language)
        ns  = "SHOWING_JOBS"
    else:
        q   = _fallback_question(skill, language)
        msg = f"Theek hai! Ab ek sawaal:\n\n{q}"
        ns  = "SKILL_QA"
    return {"intent":"skill_based_job","user_type":"worker","next_state":ns,
            "response_text":msg,"language":language,
            "extracted_data":{"skill_level":level,"qa_round":0,"qa_score":0,
                              "current_question":q if ns=="SKILL_QA" else "",
                              "correct_keywords":[]}}


def generate_resume(user_data: dict, language: str = "hi") -> dict:
    """
    Generate an AI resume for a rural worker.
    Uses Gemini if available, else builds a structured fallback resume.
    Returns a dict with sections: summary, skills, experience, strengths, recommendation
    """
    if GEMINI_AVAILABLE:
        return _gemini_resume(user_data, language)
    return _fallback_resume(user_data, language)


def _gemini_resume(user_data: dict, language: str) -> dict:
    name        = user_data.get("name", "Worker")
    skill       = user_data.get("skill", "General Labour")
    level       = user_data.get("skill_level", "beginner")
    score       = user_data.get("skill_score", 0)
    trust       = user_data.get("trust_score", 50)
    location    = user_data.get("location", "")
    completed   = user_data.get("jobs_completed", 0)
    applied     = user_data.get("jobs_applied", 0)
    earnings    = user_data.get("earnings", 0)
    avg_rating  = user_data.get("avg_rating", 0)
    history     = user_data.get("work_history", [])

    history_text = ""
    for w in history[:5]:
        history_text += f"- {w['title']} at {w['location']}, {w['salary']}/{w['unit']}, Status: {w['status']}, Rating: {w['rating']}/5\n"

    lang_instruction = {
        "hi": "Respond in simple Hindi (Hinglish is fine). Use simple words a rural worker can understand.",
        "en": "Respond in simple English.",
        "te": "Respond in simple Telugu."
    }.get(language, "Respond in simple Hindi.")

    prompt = f"""
You are an AI resume generator for rural workers in India.
{lang_instruction}

Worker Data:
- Name: {name}
- Skill: {skill} ({level} level, score: {score}%)
- Location: {location}
- Trust Score: {trust}/100
- Jobs Applied: {applied}
- Jobs Completed: {completed}
- Total Earnings: Rs {earnings}
- Average Rating: {avg_rating}/5
- Work History:
{history_text if history_text else 'No work history yet'}

Generate a professional resume and return ONLY valid JSON:
{{
  "summary": "<2-3 line professional summary about this worker in {language}>",
  "skills": ["<skill 1>", "<skill 2>", "<skill 3>"],
  "experience": "<describe their work experience based on history, 2-3 lines>",
  "strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "attendance": "<comment on their job completion rate and reliability>",
  "feedback_summary": "<summary of ratings and employer feedback>",
  "recommendation": "<1 line strong recommendation for employers>",
  "overall_grade": "<A+ | A | B+ | B | C based on trust score and completion rate>"
}}

Rules:
- Be positive and encouraging
- Base everything on actual data provided
- Keep language simple
- If no history, still write a good summary based on skill and trust score
"""
    try:
        raw  = _call_gemini(prompt)
        data = _safe_json(raw)
        if data:
            return data
    except Exception as e:
        logger.warning(f"Gemini resume generation failed: {e}")
    return _fallback_resume(user_data, language)


def _fallback_resume(user_data: dict, language: str) -> dict:
    """Rule-based resume when Gemini is not available."""
    name      = user_data.get("name", "Worker")
    skill     = user_data.get("skill", "General Labour")
    level     = user_data.get("skill_level", "beginner")
    score     = user_data.get("skill_score", 0)
    trust     = user_data.get("trust_score", 50)
    location  = user_data.get("location", "")
    completed = user_data.get("jobs_completed", 0)
    applied   = user_data.get("jobs_applied", 0)
    earnings  = user_data.get("earnings", 0)
    avg_rating = user_data.get("avg_rating", 0)

    grade = "A+" if trust >= 85 else "A" if trust >= 70 else "B+" if trust >= 55 else "B" if trust >= 40 else "C"
    completion_rate = round((completed / applied * 100) if applied > 0 else 0)

    if language == "hi":
        return {
            "summary": f"{name} ek mehnat kash worker hain jo {location} mein rehte hain. Inhe {skill} ka {level} level ka anubhav hai aur inki trust rating {trust}/100 hai.",
            "skills": [skill.capitalize(), "Mehnat aur lagan", "Samay par kaam karna"],
            "experience": f"Inhone {applied} jobs ke liye apply kiya aur {completed} jobs successfully complete ki hain. Kul kamai: Rs {earnings}.",
            "strengths": ["Vishwasneey (Reliable)", "Samay par kaam", "Mehnat kash"],
            "attendance": f"Job completion rate: {completion_rate}%. {'Bahut achha record hai!' if completion_rate >= 70 else 'Kaam mein sudhar ho raha hai.'}",
            "feedback_summary": f"Average employer rating: {avg_rating}/5. {'Employers bahut khush hain!' if avg_rating >= 4 else 'Achha feedback mila hai.' if avg_rating >= 3 else 'Abhi tak koi rating nahi mili.'}",
            "recommendation": f"{name} ek bharosemand worker hain. Inhe kaam dene ki sifarish ki jaati hai.",
            "overall_grade": grade
        }
    elif language == "te":
        return {
            "summary": f"{name} {location} లో నివసించే కష్టపడే కార్మికుడు. వారికి {skill} లో {level} స్థాయి అనుభవం ఉంది. ట్రస్ట్ స్కోర్: {trust}/100.",
            "skills": [skill.capitalize(), "కష్టపడటం", "సమయపాలన"],
            "experience": f"{applied} ఉద్యోగాలకు దరఖాస్తు చేసి {completed} పూర్తి చేశారు. మొత్తం సంపాదన: Rs {earnings}.",
            "strengths": ["నమ్మకమైనవారు", "సమయపాలన", "కష్టపడతారు"],
            "attendance": f"పని పూర్తి రేటు: {completion_rate}%.",
            "feedback_summary": f"సగటు రేటింగ్: {avg_rating}/5.",
            "recommendation": f"{name} నమ్మకమైన కార్మికుడు. పని ఇవ్వడం సిఫార్సు చేయబడింది.",
            "overall_grade": grade
        }
    else:
        return {
            "summary": f"{name} is a hardworking worker based in {location} with {level}-level experience in {skill}. Trust score: {trust}/100.",
            "skills": [skill.capitalize(), "Hard working", "Punctual"],
            "experience": f"Applied to {applied} jobs and completed {completed} successfully. Total earnings: Rs {earnings}.",
            "strengths": ["Reliable", "Punctual", "Hardworking"],
            "attendance": f"Job completion rate: {completion_rate}%. {'Excellent record!' if completion_rate >= 70 else 'Improving steadily.'}",
            "feedback_summary": f"Average employer rating: {avg_rating}/5. {'Employers are very happy!' if avg_rating >= 4 else 'Good feedback received.' if avg_rating >= 3 else 'No ratings yet.'}",
            "recommendation": f"{name} is a trustworthy worker. Highly recommended for employment.",
            "overall_grade": grade
        }


# ---------------------------------------------------------------------------
# Job application Q&A — generate questions for a specific job
# ---------------------------------------------------------------------------

def generate_job_questions(job: dict) -> list:
    """
    Generate 3 simple screening questions for a job application.
    Returns list of {question, options} dicts.
    """
    if GEMINI_AVAILABLE:
        try:
            prompt = f"""
You are a job screening assistant for rural India workers.
Job: {job.get('title')}
Description: {job.get('description', '')}
Skill required: {job.get('skill_required', 'none')}

Generate exactly 3 simple screening questions for this job.
Return ONLY valid JSON array (no markdown):
[
  {{"question": "<question in Hindi/English>", "options": ["<opt1>", "<opt2>", "<opt3>", "<opt4>"]}},
  {{"question": "...", "options": [...]}},
  {{"question": "...", "options": [...]}}
]
Rules:
- Questions must be simple, practical, relevant to the job
- Each question has exactly 4 options
- Mix Hindi and English naturally
- First option should be the best answer
"""
            raw = _call_gemini(prompt)
            # Strip markdown fences
            raw = re.sub(r'^```[a-z]*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)
            data = json.loads(raw.strip())
            if isinstance(data, list) and len(data) >= 1:
                return data[:3]
        except Exception as e:
            logger.warning(f"Gemini job questions failed: {e}")

    # Fallback generic questions
    title = job.get('title', 'this job')
    skill = job.get('skill_required', '')
    return [
        {
            "question": f"Kya aapne pehle {title} ka kaam kiya hai?",
            "options": ["Haan, bahut baar", "Haan, thoda", "Nahi, par seekhna chahta hoon", "Bilkul nahi"]
        },
        {
            "question": "Aap kab se kaam shuru kar sakte hain?",
            "options": ["Aaj se", "Kal se", "Is hafte mein", "Agle hafte"]
        },
        {
            "question": "Aap din mein kitne ghante kaam kar sakte hain?",
            "options": ["8+ ghante", "6-8 ghante", "4-6 ghante", "4 ghante se kam"]
        },
    ]


# ---------------------------------------------------------------------------
# Skill Q&A — generate first question (called from conversation_service)
# ---------------------------------------------------------------------------

def generate_first_question(skill: str, level: str, language: str) -> dict:
    """Generate the opening Q&A question."""
    if GEMINI_AVAILABLE:
        return _generate_skill_question(skill, level, 0, language)
    return {
        "question": _fallback_question(skill, language),
        "correct_keywords": [],
    }


# ---------------------------------------------------------------------------
# Static response helpers (Hindi + English)
# ---------------------------------------------------------------------------

def _default_greeting(lang):
    if lang == "hi":
        return ("Namaste! 🙏\n\n"
                "Aap kya karna chahte ho?\n\n"
                "1️⃣ Turant kaam karke paise kamana\n"
                "2️⃣ Apni skill ke hisab se job dhundna\n"
                "3️⃣ Worker rakna (employer ho?)\n\n"
                "Bolo ya likho!")
    return ("Hello! 👋\n\n"
            "What would you like to do?\n\n"
            "1️⃣ Start earning today (instant work)\n"
            "2️⃣ Find a job matching your skill\n"
            "3️⃣ Post a job (employer?)\n\n"
            "Just tell me!")


def _instant_jobs_message(lang):
    if lang == "hi":
        return "Bilkul! Aapke paas kai instant kaam ke options hain. Neeche dekhein 👇"
    return "Great! There are instant jobs available near you. See below 👇"


def _level_question(skill, lang):
    if lang == "hi":
        return (f"Acha! {skill.capitalize()} aata hai 👍\n\n"
                f"Aapka experience kitna hai?\n"
                f"• Beginner (naya seekha)\n"
                f"• Intermediate (kuch saal kaam kiya)\n"
                f"• Expert (bahut experience)")
    return (f"Great! You know {skill} 👍\n\n"
            f"What's your experience level?\n"
            f"• Beginner (just started)\n"
            f"• Intermediate (few years)\n"
            f"• Expert (many years)")


def _skill_pass_message(skill, level, score, lang):
    if lang == "hi":
        return (f"Shabash! 🎉 Aapka {skill.capitalize()} score {score}% hai!\n\n"
                f"Aap {level} level ke skilled worker ho.\n"
                f"Aapke liye jobs dhundh raha hoon... 🔍")
    return (f"Excellent! 🎉 Your {skill} score is {score}%!\n\n"
            f"You're a {level} level worker.\n"
            f"Finding matching jobs... 🔍")


def _skill_low_message(lang):
    if lang == "hi":
        return ("Koi baat nahi! Aap abhi instant kaam karke paise kama sakte hain. 💪\n"
                "Aur saath mein apni skill bhi badhao!\n\n"
                "Yeh instant jobs hain jo aaj hi shuru kar sakte hain:")
    return ("No worries! You can start earning today with instant work 💪\n"
            "While you keep improving your skills!\n\n"
            "Here are instant jobs you can start today:")


def _role_question(lang):
    if lang == "hi":
        return "Theek hai! Kaun sa kaam chahiye? (e.g. Electrician, Driver, Safai wala)"
    return "Sure! What kind of worker do you need? (e.g. Electrician, Driver, Cleaner)"


def _salary_question(lang):
    if lang == "hi":
        return "Aap per din kitna denge? (₹ mein likhein, e.g. 400)"
    return "What will you pay per day? (write in ₹, e.g. 400)"


def _location_question(lang):
    if lang == "hi":
        return "Kaam kaahan hoga? (Sheher ya area ka naam likhein)"
    return "Where is the work located? (City or area name)"


def _duration_question(lang):
    if lang == "hi":
        return "Kaam kitne din ka hai? (e.g. 1 din, 1 hafte, 1 mahina)"
    return "How long is the job? (e.g. 1 day, 1 week, 1 month)"


def _job_summary(job, lang):
    if lang == "hi":
        return (f"✅ Job post ho gaya!\n\n"
                f"📋 Kaam: {job.get('title', '')}\n"
                f"💰 Salary: ₹{job.get('salary', 0)}/din\n"
                f"📍 Location: {job.get('location', '')}\n"
                f"⏱ Duration: {job.get('duration', '')}\n\n"
                f"Hum aapko suitable workers bhejenge!")
    return (f"✅ Job posted successfully!\n\n"
            f"📋 Role: {job.get('title', '')}\n"
            f"💰 Salary: ₹{job.get('salary', 0)}/day\n"
            f"📍 Location: {job.get('location', '')}\n"
            f"⏱ Duration: {job.get('duration', '')}\n\n"
            f"We'll send you suitable workers!")


def _fallback_question(skill, lang):
    questions = {
        "electrician": {
            "hi": "Switch mein live wire kaunsa rang hota hai?",
            "en": "What color is the live wire in a switch?"
        },
        "plumber": {
            "hi": "Pipe mein leak hone par pehle kya karte ho?",
            "en": "What do you do first when a pipe is leaking?"
        },
        "mason": {
            "hi": "Cement aur ret ka ratio kya hota hai?",
            "en": "What is the cement to sand ratio for plastering?"
        },
    }
    default = {
        "hi": f"{skill.capitalize()} mein sabse pehle kya karte hain?",
        "en": f"What is the first step in {skill} work?"
    }
    q = questions.get(skill, default)
    return q.get(lang, q.get("hi"))
