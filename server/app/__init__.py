import os
from flask import Flask
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
            os.path.join(os.path.dirname(__file__), '../../client/static')
        ),
        template_folder=os.path.abspath(
            os.path.join(os.path.dirname(__file__), '../../client/templates')
        )
    )

    # Load configuration
    app.config.from_object(Config)

    # Initialize extensions with app
    db.init_app(app)
    migrate.init_app(app, db)

    # Register blueprints
    from .routes import main
    app.register_blueprint(main)

    return app
