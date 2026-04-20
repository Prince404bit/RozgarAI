# KaamMitr — AI-Powered Rural Employment Platform

> *"Har insaan — aaj se kama sakta hai"* (Every person can earn — starting today)

A conversational AI platform that connects rural workers with jobs and employers with workers — via **web chat**, **voice input**, and **phone (IVR/SMS)**. No literacy required. No forms. Just talk.

---

## Problem Statement

Over 300 million rural workers in India lack access to formal employment channels. Barriers include:

- Low digital literacy — can't navigate job portals
- Language barriers — most platforms are English-only
- No smartphones or internet — rely on basic phones
- No verifiable work history — employers don't trust them

KaamMitr solves all four with a voice-first, Hindi/English/Telugu conversational AI.

---

## Solution Overview

Workers simply **say or type** what they want — in Hindi or English — and the AI:

1. Detects intent (find work / post job / get help)
2. Matches skill level via a short Q&A
3. Shows relevant jobs instantly
4. Handles application end-to-end
5. Builds a verifiable trust score over time

Employers post jobs in under 60 seconds via conversation — no forms, no dashboards needed.

---

## Key Features

- **Voice-first UI** — Web Speech API + Twilio IVR (no typing required)
- **Zero-form flow** — entire interaction via natural conversation
- **Multilingual** — auto-detects Hindi / English / Telugu
- **Dual job modes** — Instant gigs (hourly) + Skilled jobs (monthly)
- **AI skill assessment** — Gemini-powered Q&A to verify skill level
- **Trust score system** — built from job completions + employer ratings
- **IVR/SMS support** — works on basic phones via Twilio
- **Graceful fallback** — rule-based AI when Gemini key is absent
- **AI resume generator** — auto-generates worker profile for employers

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, Flask 3.0 |
| Database | SQLite (dev) / PostgreSQL (prod) via SQLAlchemy |
| AI | Google Gemini 1.5 Flash |
| Voice/SMS | Twilio IVR + SMS |
| Frontend | Jinja2 templates, Vanilla JS, Web Speech API |
| Deployment | Gunicorn + any cloud (Render, Railway, Fly.io) |

---

## How to Run

### 1. Clone the repository
```bash
git clone https://github.com/your-username/kaammitr.git
cd kaammitr
```

### 2. Create a virtual environment
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set up environment variables
```bash
cp .env.example .env
# Edit .env — add GEMINI_API_KEY at minimum
```

### 5. Run the app
```bash
python app.py
# → Open http://localhost:5000
```

> **Note:** The app works without a Gemini key using the built-in rule-based fallback. All conversation flows remain functional.

### Production (Gunicorn)
```bash
gunicorn -c gunicorn.conf.py "app:create_app()"
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Flask session secret |
| `GEMINI_API_KEY` | Recommended | Google AI Studio key — [get free](https://aistudio.google.com/) |
| `TWILIO_ACCOUNT_SID` | Optional | For IVR/SMS features |
| `TWILIO_AUTH_TOKEN` | Optional | Twilio auth token |
| `TWILIO_PHONE` | Optional | Your Twilio phone number |
| `BASE_URL` | Optional | Public URL for Twilio webhooks (use ngrok locally) |
| `DATABASE_URL` | Optional | Defaults to SQLite; set PostgreSQL URL for production |

---

## Folder Structure

```
project/
├── app.py                    # Flask app factory + entry point
├── config.py                 # Config & conversation state constants
├── requirements.txt
├── gunicorn.conf.py          # Production server config
├── .env.example              # Environment variable template
│
├── models/
│   └── database.py           # SQLAlchemy models (User, Job, WorkHistory) + seed data
│
├── services/
│   ├── ai_service.py         # Gemini AI + rule-based fallback
│   ├── conversation_service.py  # Message orchestration + context memory
│   └── job_service.py        # Job CRUD + smart matching
│
├── routes/
│   ├── api_routes.py         # /api/* — JSON REST API
│   ├── twilio_routes.py      # /twilio/* — IVR + SMS webhooks
│   └── web_routes.py         # Web page routes
│
├── utils/
│   └── helpers.py            # Language detection, phone utils
│
├── templates/                # Jinja2 HTML templates
└── static/                   # CSS + JS assets
```

---

## API Reference

### Core AI Endpoint
```
POST /api/ai/process
Body: { "phone": "919876543210", "text": "kaam chahiye", "location": "Jaipur" }
Response: { success, data: { response_text, jobs[], state, intent, language, user } }
```

### Jobs
```
GET  /api/jobs?type=instant|skilled&skill=electrician&location=Jaipur
POST /api/jobs/:id/apply  { phone }
GET  /api/health
```

Full API docs available in [`routes/api_routes.py`](routes/api_routes.py).

---

## Twilio IVR Setup

1. In Twilio console → Phone Numbers → your number
2. Set **Voice webhook**: `POST https://your-domain.com/twilio/voice`
3. Set **SMS webhook**: `POST https://your-domain.com/twilio/sms`
4. For local dev: `ngrok http 5000` → use ngrok URL as `BASE_URL` in `.env`

---

## Conversation Flow

```
User Input
    │
    ├── "kaam chahiye"     → Instant Jobs (hourly gigs)
    ├── "electrician hoon" → Skill Q&A → Skilled Jobs
    ├── "worker chahiye"   → Job Posting Flow (employer)
    └── unknown            → Greeting + Options
```

Every state is persisted per user — conversation resumes across sessions and channels (web, IVR, SMS).

---

## Future Improvements

- [ ] Map integration for job location proximity
- [ ] Push notifications via WhatsApp Business API
- [ ] Worker photo ID verification
- [ ] React/Vue SPA frontend
- [ ] Multi-city expansion beyond Jaipur
- [ ] Employer subscription tiers

---

## License

MIT License — see [LICENSE](LICENSE) for details.
