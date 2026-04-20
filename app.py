"""
KaamMitr — AI-Powered Rural Employment Platform
Entry point: Flask application factory.
"""

import os
import logging
from flask import Flask, jsonify, request
from config import Config
from models.database import db, seed_demo_jobs
from routes.api_routes import api
from routes.twilio_routes import twilio_bp
from routes.web_routes import web

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def create_app(config_class=Config) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_class)

    db.init_app(app)

    app.register_blueprint(api)
    app.register_blueprint(twilio_bp)
    app.register_blueprint(web)

    # ── DB init ────────────────────────────────────────────────────────────────
    with app.app_context():
        try:
            db.create_all()
            try:
                from sqlalchemy import text
                with db.engine.connect() as conn:
                    conn.execute(text("PRAGMA journal_mode=WAL;"))
                    conn.execute(text("PRAGMA synchronous=NORMAL;"))
            except Exception:
                pass
            seed_demo_jobs()
            logger.info("✅ Database ready")
        except Exception as e:
            logger.warning(f"DB init failed ({e}), rebuilding schema...")
            try:
                db.drop_all()
            except Exception:
                pass
            db.create_all()
            try:
                from sqlalchemy import text
                with db.engine.connect() as conn:
                    conn.execute(text("PRAGMA journal_mode=WAL;"))
                    conn.execute(text("PRAGMA synchronous=NORMAL;"))
            except Exception:
                pass
            seed_demo_jobs()
            logger.info("✅ Database rebuilt and ready")

    # ── CORS ───────────────────────────────────────────────────────────────────
    @app.after_request
    def add_cors(response):
        response.headers["Access-Control-Allow-Origin"]  = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        return response

    # ── Global error handlers ──────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "message": "Endpoint not found"}), 404
        return "Page not found", 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"success": False, "message": "Method not allowed"}), 405

    @app.errorhandler(500)
    def server_error(e):
        logger.error(f"500 error on {request.path}: {e}")
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "message": "Internal server error"}), 500
        return "Server error", 500

    @app.errorhandler(Exception)
    def unhandled(e):
        logger.error(f"Unhandled exception on {request.path}: {e}", exc_info=True)
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "message": "Unexpected error. Please try again."}), 500
        return "Unexpected error", 500

    logger.info("🚀 KaamMitr app created successfully")
    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info(f"🌐 Starting dev server on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=Config.DEBUG)
