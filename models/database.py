"""
Database models for the Rural Employment Platform.
SQLite via SQLAlchemy — simple, portable, hackathon-ready.
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    phone         = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name          = db.Column(db.String(100), default="")
    language      = db.Column(db.String(10), default="hi")
    role          = db.Column(db.String(20), default="worker")
    skill         = db.Column(db.String(100), default="")
    skill_level   = db.Column(db.String(20), default="")
    skill_score   = db.Column(db.Float, default=0.0)
    trust_score   = db.Column(db.Float, default=50.0)
    earnings      = db.Column(db.Float, default=0.0)
    location      = db.Column(db.String(200), default="")
    last_state    = db.Column(db.String(50), default="IDLE")
    context_json  = db.Column(db.Text, default="{}")
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    last_active   = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Monetization fields
    commission_earned = db.Column(db.Float, default=0.0)
    is_premium        = db.Column(db.Boolean, default=False)

    work_history  = db.relationship("WorkHistory", backref="user", lazy=True)

    def to_dict(self):
        history   = WorkHistory.query.filter_by(user_id=self.id).all()
        completed = [h for h in history if h.status == "completed"]
        ratings   = [h.rating for h in completed if h.rating > 0]
        avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0.0
        verified   = self.trust_score >= 70 and len(completed) >= 3
        return {
            "id":             self.id,
            "phone":          self.phone,
            "name":           self.name,
            "language":       self.language,
            "role":           self.role,
            "skill":          self.skill,
            "skill_level":    self.skill_level,
            "skill_score":    self.skill_score,
            "trust_score":    self.trust_score,
            "earnings":       self.earnings,
            "location":       self.location,
            "last_state":     self.last_state,
            "avg_rating":     avg_rating,
            "jobs_completed": len(completed),
            "jobs_applied":   len(history),
            "verified":       verified,
            "badge":          "✅ Verified" if verified else "🔄 Building Trust",
        }


class Job(db.Model):
    __tablename__ = "jobs"

    id              = db.Column(db.Integer, primary_key=True)
    title           = db.Column(db.String(200), nullable=False)
    description     = db.Column(db.Text, default="")
    job_type        = db.Column(db.String(20), default="instant")
    skill_required  = db.Column(db.String(100), default="")
    skill_level_min = db.Column(db.String(20), default="beginner")
    salary          = db.Column(db.Float, default=300.0)
    salary_unit     = db.Column(db.String(20), default="day")
    location        = db.Column(db.String(200), default="")
    duration        = db.Column(db.String(100), default="1 day")
    created_by      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    status          = db.Column(db.String(20), default="open")
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    # Monetization
    employer_fee_paid = db.Column(db.Boolean, default=False)
    commission_rate   = db.Column(db.Float, default=0.05)

    work_history    = db.relationship("WorkHistory", backref="job", lazy=True)

    def to_dict(self):
        return {
            "id":              self.id,
            "title":           self.title,
            "description":     self.description,
            "job_type":        self.job_type,
            "skill_required":  self.skill_required,
            "skill_level_min": self.skill_level_min,
            "salary":          self.salary,
            "salary_unit":     self.salary_unit,
            "location":        self.location,
            "duration":        self.duration,
            "status":          self.status,
            "created_by":      self.created_by,
            "commission_rate": self.commission_rate,
        }


class WorkHistory(db.Model):
    __tablename__ = "work_history"

    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    job_id          = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=False)
    status          = db.Column(db.String(20), default="applied")
    proof_url       = db.Column(db.String(500), default="")
    rating          = db.Column(db.Float, default=0.0)
    employer_rating = db.Column(db.Float, default=0.0)
    notes           = db.Column(db.Text, default="")
    applied_at      = db.Column(db.DateTime, default=datetime.utcnow)
    accepted_at     = db.Column(db.DateTime, nullable=True)
    completed_at    = db.Column(db.DateTime, nullable=True)

    # Monetization
    commission_amount = db.Column(db.Float, default=0.0)

    def to_dict(self):
        app_id = f"KM-{self.id:04d}"
        return {
            "id":               self.id,
            "application_id":   app_id,
            "user_id":          self.user_id,
            "job_id":           self.job_id,
            "status":           self.status,
            "rating":           self.rating,
            "employer_rating":  self.employer_rating,
            "notes":            self.notes,
            "commission_amount":self.commission_amount,
            "applied_at":       self.applied_at.strftime("%d %b %Y, %I:%M %p") if self.applied_at else "",
            "accepted_at":      self.accepted_at.strftime("%d %b %Y, %I:%M %p") if self.accepted_at else "",
            "completed_at":     self.completed_at.strftime("%d %b %Y, %I:%M %p") if self.completed_at else "",
        }


def seed_demo_jobs():
    try:
        if Job.query.count() > 0:
            return
    except Exception:
        return

    demo_jobs = [
        {"title": "Safai Kaamgar (Cleaning Helper)", "job_type": "instant",
         "salary": 60, "salary_unit": "hour", "location": "Jaipur",
         "duration": "2 ghante", "skill_required": "",
         "description": "Ghar ya daftar ki safai karna, 2 ghante ka kaam"},
        {"title": "Loading / Unloading Helper", "job_type": "instant",
         "salary": 80, "salary_unit": "hour", "location": "Jaipur",
         "duration": "4 ghante", "skill_required": "",
         "description": "Saman uthana aur pahunchana, 4 ghante ka kaam"},
        {"title": "Khet Mazdoor (Farm Labour)", "job_type": "instant",
         "salary": 70, "salary_unit": "hour", "location": "Jaipur",
         "duration": "6 ghante", "skill_required": "",
         "description": "Khet mein paidal kaam, 6 ghante"},
        {"title": "Paint Helper", "job_type": "instant",
         "salary": 65, "salary_unit": "hour", "location": "Jaipur",
         "duration": "3 ghante", "skill_required": "",
         "description": "Painter ke saath kaam, 3 ghante"},
        {"title": "Delivery Helper (Local)", "job_type": "instant",
         "salary": 75, "salary_unit": "hour", "location": "Jaipur",
         "duration": "5 ghante", "skill_required": "",
         "description": "Local area mein saman pahunchana, 5 ghante"},
        {"title": "Event Setup Helper", "job_type": "instant",
         "salary": 70, "salary_unit": "hour", "location": "Jaipur",
         "duration": "8 ghante", "skill_required": "",
         "description": "Shaadi ya event mein setup karna, 8 ghante"},
        {"title": "Car Washing Helper", "job_type": "instant",
         "salary": 55, "salary_unit": "hour", "location": "Jaipur",
         "duration": "2 ghante", "skill_required": "",
         "description": "Gaadi dhona aur saaf karna, 2 ghante"},
        {"title": "Kitchen Helper (Hotel)", "job_type": "instant",
         "salary": 65, "salary_unit": "hour", "location": "Jaipur",
         "duration": "4 ghante", "skill_required": "",
         "description": "Hotel kitchen mein madad karna, 4 ghante"},
        {"title": "Security Guard (Chowkidar)", "job_type": "skilled",
         "salary": 7500, "salary_unit": "month", "location": "Jaipur",
         "duration": "Permanent", "skill_required": "security", "skill_level_min": "beginner",
         "description": "Office ya colony ki chowkidari, raat ki duty"},
        {"title": "House Helper / Bai", "job_type": "skilled",
         "salary": 4500, "salary_unit": "month", "location": "Jaipur",
         "duration": "Permanent", "skill_required": "cleaning", "skill_level_min": "beginner",
         "description": "Ghar ki safai, bartan, kapde dhona"},
        {"title": "Cook / Rasoia", "job_type": "skilled",
         "salary": 6000, "salary_unit": "month", "location": "Jaipur",
         "duration": "Permanent", "skill_required": "cook", "skill_level_min": "beginner",
         "description": "Ghar mein roz khana banana, 2 waqt ka"},
        {"title": "Office Peon / Helper", "job_type": "skilled",
         "salary": 5500, "salary_unit": "month", "location": "Jaipur",
         "duration": "Permanent", "skill_required": "", "skill_level_min": "beginner",
         "description": "Office mein chai, photocopy, delivery kaam"},
        {"title": "Delivery Boy (Two-Wheeler)", "job_type": "skilled",
         "salary": 8500, "salary_unit": "month", "location": "Jaipur",
         "duration": "Permanent", "skill_required": "driver", "skill_level_min": "beginner",
         "description": "Local delivery, khud ki bike chahiye"},
        {"title": "Watchman (Apartment)", "job_type": "skilled",
         "salary": 8000, "salary_unit": "month", "location": "Jaipur",
         "duration": "Permanent", "skill_required": "security", "skill_level_min": "beginner",
         "description": "Apartment complex mein gate duty, 12 hour shift"},
        {"title": "Shop Assistant", "job_type": "skilled",
         "salary": 5000, "salary_unit": "month", "location": "Jaipur",
         "duration": "Permanent", "skill_required": "", "skill_level_min": "beginner",
         "description": "Dukaan mein saman rakhna, billing mein madad karna"},
        {"title": "Gardener (Mali)", "job_type": "skilled",
         "salary": 4000, "salary_unit": "month", "location": "Jaipur",
         "duration": "Permanent", "skill_required": "gardening", "skill_level_min": "beginner",
         "description": "Bungalow ya society ka garden maintain karna"},
        {"title": "Driver (Car / Auto)", "job_type": "skilled",
         "salary": 9000, "salary_unit": "month", "location": "Jaipur",
         "duration": "Permanent", "skill_required": "driver", "skill_level_min": "intermediate",
         "description": "Family ya office ke liye regular driving"},
        {"title": "Electrician Helper (Workshop)", "job_type": "skilled",
         "salary": 7000, "salary_unit": "month", "location": "Jaipur",
         "duration": "Permanent", "skill_required": "electrician", "skill_level_min": "beginner",
         "description": "Workshop mein electrician ke saath kaam karna"},
    ]

    for j in demo_jobs:
        job = Job(**j)
        db.session.add(job)
    db.session.commit()
    print("✅ Demo jobs seeded.")
