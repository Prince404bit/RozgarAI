"""Shared utility functions."""

import re
import logging

logger = logging.getLogger(__name__)


def detect_language(text: str) -> str:
    """
    Simple heuristic language detector.
    Returns 'hi' for Hindi-dominant text, 'en' otherwise.
    Falls back to langdetect if available.
    """
    hindi_chars = re.findall(r'[\u0900-\u097F]', text)
    if len(hindi_chars) > 2:
        return "hi"

    hindi_words = {
        "kaam", "chahiye", "mujhe", "hai", "hain", "nahin", "nahi",
        "aur", "ek", "do", "teen", "kya", "kyun", "kaun", "kahan",
        "kab", "aata", "paise", "naukri", "worker", "mazdoor", "karo",
        "karein", "bolo", "dekho", "accha", "theek", "haan", "nahi",
        "shukriya", "namaste", "ji", "bhai", "didi",
    }
    words = set(text.lower().split())
    if words & hindi_words:
        return "hi"

    try:
        from langdetect import detect
        lang = detect(text)
        return "hi" if lang in ("hi", "ur") else "en"
    except Exception:
        pass

    return "en"


def sanitize_phone(phone: str) -> str:
    """Normalise phone number to digits only (with country code)."""
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 10:
        digits = "91" + digits
    return digits


def format_currency(amount: float) -> str:
    """Format as Indian Rupees."""
    return f"₹{int(amount):,}"


def truncate(text: str, max_len: int = 200) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"
