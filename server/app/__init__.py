import os
from dotenv import load_dotenv

# --- Environment loading (MUST happen before Config is imported) ---
# Config reads os.getenv(...) at import time, so the correct env files must be
# loaded first. Shared secrets live in `.env`; the active database URL lives in
# `.env.<APP_ENV>` (.env.dev = local Postgres, .env.prod = Supabase).
# APP_ENV defaults to "dev" so a local run never accidentally connects to production.
_SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP_ENV = os.getenv("APP_ENV", "dev")
load_dotenv(os.path.join(_SERVER_DIR, ".env"))  # shared/base secrets
load_dotenv(os.path.join(_SERVER_DIR, f".env.{_APP_ENV}"), override=True)  # env-specific DB URL

from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from .config import Config

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()


def create_app():
    app = Flask(
        __name__,
        static_folder=os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../client/static")
        ),
        template_folder=os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../client/templates")
        ),
    )

    # Load configuration
    app.config.from_object(Config)

    # Fail loud rather than silently falling back to the weak, source-committed
    # defaults for these secrets. SECRET_KEY signs session cookies (a forged one
    # = an admin session) and SECURITY_PASSWORD_SALT salts reset tokens (a forged
    # one = account takeover). Outside local dev, a missing/typo'd env var would
    # otherwise downgrade both to a publicly-known value with no signal — so crash
    # the boot instead, turning a silent hole into an obvious deploy-time error.
    if _APP_ENV != "dev":
        for _key, _weak in (
            ("SECRET_KEY", "supersecretkey"),
            ("SECURITY_PASSWORD_SALT", "another-secret"),
        ):
            _val = app.config.get(_key)
            if not _val or _val == _weak:
                raise RuntimeError(
                    f"{_key} is unset or using the insecure built-in default "
                    f"(APP_ENV={_APP_ENV}). Set a strong, random {_key} environment "
                    "variable before starting the app."
                )

    # Initialize extensions with app
    db.init_app(app)
    migrate.init_app(app, db)

    # Register blueprints
    from .routes import main, keepalive_bp

    app.register_blueprint(main)
    app.register_blueprint(keepalive_bp)

    # Error Handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        return render_template("500.html"), 500

    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template("403.html"), 403

    @app.errorhandler(401)
    def unauthorized_error(error):
        return render_template("401.html"), 401

    return app
