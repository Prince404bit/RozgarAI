import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Config:
    # --- App ---
    SECRET_KEY = os.getenv("SECRET_KEY", "")
    if not SECRET_KEY:
        SECRET_KEY = os.urandom(32).hex()
        logger.warning("SECRET_KEY not set — using a random key. Sessions will reset on restart.")
    DEBUG = os.getenv("DEBUG", "False") == "True"

    # --- Database ---
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///rural_employment.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Gemini AI ---
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = "gemini-1.5-flash"          # fast + cost-effective

    # --- Twilio ---
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_PHONE       = os.getenv("TWILIO_PHONE", "")

    # --- Public base URL (for Twilio callbacks) ---
    BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")

    # --- Languages ---
    SUPPORTED_LANGUAGES = ["hi", "en", "te"]

    # --- Conversation states ---
    STATE_IDLE           = "IDLE"
    STATE_ASKING_MODE    = "ASKING_MODE"
    STATE_ASKING_SKILL   = "ASKING_SKILL"
    STATE_ASKING_LEVEL   = "ASKING_LEVEL"
    STATE_SKILL_QA       = "SKILL_QA"
    STATE_SHOWING_JOBS   = "SHOWING_JOBS"
    STATE_INSTANT_JOBS   = "INSTANT_JOBS"
    STATE_POST_JOB_ROLE  = "POST_JOB_ROLE"
    STATE_POST_JOB_SALARY = "POST_JOB_SALARY"
    STATE_POST_JOB_LOC   = "POST_JOB_LOC"
    STATE_POST_JOB_DUR   = "POST_JOB_DUR"
    STATE_JOB_POSTED     = "JOB_POSTED"
    STATE_APPLYING       = "APPLYING"
    STATE_HELPING        = "HELPING"
