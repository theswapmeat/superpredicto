import os
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv
from .config import Config

# Load environment variables from .env file
load_dotenv()

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
