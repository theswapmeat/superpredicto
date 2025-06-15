from dotenv import load_dotenv
import os

load_dotenv()  # Loads .env file

from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS oklahoma (
                id SERIAL PRIMARY KEY,
                message TEXT NOT NULL
            );
        """))
        print("✅ Connected to:", db.engine.url)
