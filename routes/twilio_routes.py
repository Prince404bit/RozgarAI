"""
Twilio IVR — KaamMitr voice system.
Flow: greet → detect skill/intent → show jobs → apply → connect employer
"""

import re
import logging
from flask import Blueprint, request, Response, url_for
from services.conversation_service import handle_message, apply_to_job
from config import Config

logger     = logging.getLogger(__name__)
twilio_bp  = Blueprint("twilio", __name__, url_prefix="/twilio")


# ── TwiML helpers ─────────────────────────────────────────────────────────────

def _twiml(content: str) -> Response:
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<Response>\n{content}\n</Response>'
    return Response(xml, mimetype="text/xml")

def _say(text: str, lang: str = "hi") -> str:
    voice = "Polly.Aditi" if lang == "hi" else ("Polly.Raveena" if lang == "te" else "Polly.Raveena")
    safe  = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")[:1800]
    return f'  <Say voice="{voice}">{safe}</Say>'

def _gather(action_url: str, lang: str = "hi", timeout: int = 6) -> tuple:
    code = {"hi": "hi-IN", "en": "en-IN", "te": "te-IN"}.get(lang, "hi-IN")
    open_tag = (
        f'  <Gather input="speech" action="{action_url}" '
        f'method="POST" language="{code}" '
        f'speechTimeout="auto" timeout="{timeout}">'
    )
    return open_tag, "  </Gather>"

def _redirect(url: str) -> str:
    return f'  <Redirect method="POST">{url}</Redirect>'

def _pause(n: int = 1) -> str:
    return f'  <Pause length="{n}"/>'

def _hangup() -> str:
    return "  <Hangup/>"


# ── Entry point ───────────────────────────────────────────────────────────────

@twilio_bp.route("/voice", methods=["GET", "POST"])
def voice_entry():
    """Greet caller in Hindi + English, start listening."""
    greeting = (
        "Namaskar! KaamMitr mein aapka swagat hai. "
        "Aaj aap kaam dhundh rahe hain ya worker chahiye? "
        "Boliye — jaise 'kaam chahiye' ya 'painter chahiye'."
    )
    process_url = url_for("twilio.process_speech", _external=True)
    g_open, g_close = _gather(process_url, "hi", timeout=8)

    body = (
        f"{g_open}\n"
        f"{_say(greeting, 'hi')}\n"
        f"{_pause(1)}\n"
        f"{_say('Hello! Say need work or tell your skill.', 'en')}\n"
        f"{g_close}\n"
        f"{_say('Koi awaaz nahi aayi. Dobara try karein.', 'hi')}\n"
        f"{_redirect(url_for('twilio.voice_entry', _external=True))}"
    )
    return _twiml(body)


# ── Process speech ────────────────────────────────────────────────────────────

@twilio_bp.route("/process", methods=["POST"])
def process_speech():
    speech     = request.form.get("SpeechResult", "").strip()
    phone      = request.form.get("From", "unknown").replace("whatsapp:", "").strip()
    confidence = float(request.form.get("Confidence", 0.5))

    logger.info(f"IVR | {phone} | '{speech}' | conf={confidence:.2f}")

    if not speech or confidence < 0.25:
        return _silent_fallback(phone)

    # Run through AI engine
    try:
        result = handle_message(phone, speech)
    except Exception as e:
        logger.error(f"IVR AI error for {phone}: {e}")
        result = {"response_text": "Thodi problem aayi. Dobara bolein.",
                  "language": "hi", "state": "IDLE", "jobs": []}

    response = result.get("response_text", "")
    language = result.get("language", "hi")
    state    = result.get("state", "IDLE")
    jobs     = result.get("jobs", [])

    spoken = _build_spoken(response, jobs, language)

    process_url = url_for("twilio.process_speech", _external=True)
    g_open, g_close = _gather(process_url, language, timeout=8)

    terminal = {"JOB_POSTED", "HELPING"}
    if state in terminal:
        body = (
            f"{_say(spoken, language)}\n"
            f"{_pause(1)}\n"
            f"{_say(_goodbye(language), language)}\n"
            f"{_hangup()}"
        )
    elif state in {"INSTANT_JOBS", "SHOWING_JOBS"} and jobs:
        # Offer to apply to first job via keypress
        apply_url = url_for("twilio.ivr_apply", _external=True)
        first_job = jobs[0]
        job_id    = first_job.get("id", 0)
        confirm   = _confirm_job_msg(first_job, language)
        body = (
            f"  <Gather input='speech dtmf' action='{apply_url}?phone={phone}&job_id={job_id}' "
            f"method='POST' language='{'hi-IN' if language=='hi' else 'en-IN'}' timeout='8'>\n"
            f"{_say(spoken, language)}\n"
            f"{_pause(1)}\n"
            f"{_say(confirm, language)}\n"
            f"  </Gather>\n"
            f"{_say(_no_input_fallback(language), language)}\n"
            f"{_redirect(url_for('twilio.voice_entry', _external=True))}"
        )
    else:
        body = (
            f"{g_open}\n"
            f"{_say(spoken, language)}\n"
            f"{g_close}\n"
            f"{_say(_no_input_fallback(language), language)}\n"
            f"{_redirect(url_for('twilio.voice_entry', _external=True))}"
        )

    return _twiml(body)


# ── IVR Apply ─────────────────────────────────────────────────────────────────

@twilio_bp.route("/apply", methods=["POST"])
def ivr_apply():
    """Handle voice/keypress confirmation to apply for a job."""
    phone   = request.args.get("phone", "")
    job_id  = int(request.args.get("job_id", 0))
    speech  = request.form.get("SpeechResult", "").lower()
    digits  = request.form.get("Digits", "")

    yes_words = {"haan", "yes", "ha", "ok", "theek", "1", "apply"}
    confirmed = any(w in speech for w in yes_words) or digits == "1"

    if confirmed and job_id:
        result = apply_to_job(phone, job_id)
        if result["success"]:
            app_id = result.get("application_id", "")
            lang   = "hi"
            msg = (f"Bahut achha! Aapki application submit ho gayi. "
                   f"Application ID {app_id}. "
                   f"Employer jald hi aapse contact karega. Dhanyavaad!")
        else:
            msg = result.get("message", "Apply nahi ho saka. Dobara try karein.")
            lang = "hi"
        return _twiml(f"{_say(msg, lang)}\n{_pause(1)}\n{_hangup()}")

    # User said no — offer more jobs
    process_url = url_for("twilio.voice_entry", _external=True)
    lang = "hi"
    msg  = "Theek hai. Koi aur kaam dekhna chahte hain? Boliye."
    g_open, g_close = _gather(url_for("twilio.process_speech", _external=True), lang)
    return _twiml(f"{g_open}\n{_say(msg, lang)}\n{g_close}\n{_redirect(process_url)}")


# ── SMS handler ───────────────────────────────────────────────────────────────

@twilio_bp.route("/sms", methods=["POST"])
def handle_sms():
    body  = request.form.get("Body", "").strip()
    phone = request.form.get("From", "").replace("whatsapp:", "").strip()

    if not body or not phone:
        return _twiml("<Message>Kuch samajh nahi aaya. Dobara try karein.</Message>")

    try:
        result = handle_message(phone, body)
    except Exception as e:
        logger.error(f"SMS error for {phone}: {e}")
        return _twiml("<Message>Thodi problem aayi. Dobara try karein.</Message>")

    response = result.get("response_text", "")
    jobs     = result.get("jobs", [])
    language = result.get("language", "hi")

    sms = response
    if jobs:
        lines = []
        for j in jobs[:3]:
            lines.append(f"• {j['title']} | ₹{j['salary']}/{j['salary_unit']} | {j['location']}")
        sms += "\n\n" + "\n".join(lines)

    sms  = sms[:1600]
    safe = sms.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return _twiml(f"<Message>{safe}</Message>")


# ── Status callback ───────────────────────────────────────────────────────────

@twilio_bp.route("/status", methods=["POST"])
def call_status():
    sid    = request.form.get("CallSid", "")
    status = request.form.get("CallStatus", "")
    logger.info(f"Call {sid} → {status}")
    return _twiml("")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_spoken(text: str, jobs: list, lang: str) -> str:
    clean = re.sub(r'[🎉✅💰📍⏱🔍👇💪🙏👋📋🆘😊🧑💼🧾⭐🔘🆔]', '', text)
    clean = re.sub(r'\*{1,2}', '', clean)
    clean = re.sub(r'#{1,6}\s?', '', clean)
    clean = re.sub(r'\n+', '. ', clean).strip()

    if jobs:
        if lang == "hi":
            clean += f". Maine {len(jobs)} kaam dhundhe hain. "
            for i, j in enumerate(jobs[:2], 1):
                clean += f"Option {i}: {j['title']}, {j['salary']} rupaye per {j['salary_unit']}. "
        else:
            clean += f". I found {len(jobs)} jobs. "
            for i, j in enumerate(jobs[:2], 1):
                clean += f"Option {i}: {j['title']}, {j['salary']} rupees per {j['salary_unit']}. "
    return clean[:1800]


def _confirm_job_msg(job: dict, lang: str) -> str:
    title  = job.get("title", "")
    salary = job.get("salary", 0)
    unit   = job.get("salary_unit", "hour")
    if lang == "hi":
        return (f"Kya aap {title} ke liye apply karna chahte hain? "
                f"Payment: {salary} rupaye per {unit}. "
                f"Haan bolein ya 1 dabayein.")
    return (f"Do you want to apply for {title}? "
            f"Payment: {salary} rupees per {unit}. "
            f"Say yes or press 1.")


def _silent_fallback(phone: str) -> Response:
    try:
        result = handle_message(phone, "kaam chahiye")
        lang   = result.get("language", "hi")
    except Exception:
        lang = "hi"

    msg = ("Mujhe kuch samajh nahi aaya. "
           "Kya aap kaam dhundh rahe hain? 'Kaam chahiye' bolein."
           if lang == "hi" else
           "I didn't catch that. Say 'need work' to find jobs.")

    process_url = url_for("twilio.process_speech", _external=True)
    g_open, g_close = _gather(process_url, lang, timeout=8)
    return _twiml(f"{g_open}\n{_say(msg, lang)}\n{g_close}")


def _goodbye(lang: str) -> str:
    if lang == "hi":
        return "Shukriya! KaamMitr use karne ke liye dhanyavaad. Aapka din shubh ho!"
    return "Thank you for using KaamMitr. Have a great day!"


def _no_input_fallback(lang: str) -> str:
    if lang == "hi":
        return "Koi awaaz nahi aayi. Dobara bolein."
    return "No response detected. Please try again."
