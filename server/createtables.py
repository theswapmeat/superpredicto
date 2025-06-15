from dotenv import load_dotenv
load_dotenv()

from app import create_app, db

app = create_app()

with app.app_context():
    db.create_all()
    print("✅ All tables created in the test database.")
