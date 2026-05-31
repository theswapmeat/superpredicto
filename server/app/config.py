import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")
    SQLALCHEMY_DATABASE_URI = os.getenv("SUPABASE_URL", "sqlite:///superpredicto.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECURITY_PASSWORD_SALT = os.getenv("SECURITY_PASSWORD_SALT", "another-secret")
    # Email (Maileroo). MAILEROO_API_KEY is a per-domain "Sending Key" from the
    # Maileroo dashboard; the from-address domain must be verified in Maileroo.
    MAILEROO_API_KEY = os.getenv("MAILEROO_API_KEY")
    MAIL_FROM_ADDRESS = os.getenv("MAIL_FROM_ADDRESS", "no-reply@superpredicto.com")
    MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "SuperPredicto")
    PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
    PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")
    PERMANENT_SESSION_LIFETIME = timedelta(days=14)
    # Bump (or set the env var) to cache-bust static CSS/JS via ?v=ASSET_VERSION.
    ASSET_VERSION = os.getenv("ASSET_VERSION", "1")
    # Live scores (football-data.org) + the secret that guards the cron sync endpoint.
    FOOTBALL_DATA_API_KEY = os.getenv("FOOTBALL_DATA_API_KEY")
    INTERNAL_SYNC_TOKEN = os.getenv("INTERNAL_SYNC_TOKEN")