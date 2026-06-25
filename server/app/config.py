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
    # Session-cookie hardening. HttpOnly keeps JS from reading the cookie (XSS
    # can't steal the session); SameSite=Lax blunts CSRF; Secure restricts it to
    # HTTPS in prod (left off in local dev, which is plain HTTP).
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("APP_ENV", "dev") != "dev"
    # Public domain used to build absolute links/images in EMAILS. url_for(_external)
    # would otherwise stamp the host of whatever triggered the send — and cron-fired
    # reminders hit the DigitalOcean ingress (…ondigitalocean.app), not the custom
    # domain. This keeps every email pointing at superpredicto.com regardless.
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://superpredicto.com")
    # Bump (or set the env var) to cache-bust static CSS/JS via ?v=ASSET_VERSION.
    ASSET_VERSION = os.getenv("ASSET_VERSION", "4")
    # Live scores (football-data.org) + the secret that guards the cron sync endpoint.
    FOOTBALL_DATA_API_KEY = os.getenv("FOOTBALL_DATA_API_KEY")
    INTERNAL_SYNC_TOKEN = os.getenv("INTERNAL_SYNC_TOKEN")
    # Entry fee + bank-transfer details — single source of truth for BOTH the
    # /payment page and the payment-reminder email. Change these in one place only.
    ENTRY_FEE_LABEL = os.getenv("ENTRY_FEE_LABEL", "AED 275")
    BANK_DETAILS = [
        ("Name", "Anup Paul Chackunny"),
        ("Bank", "Emirates NBD"),
        ("Account", "1014040525401"),
        ("IBAN", "AE270260001014040525401"),
    ]
    # WhatsApp contact — single source for the /support page and reminder emails.
    SUPPORT_WHATSAPP_URL = os.getenv("SUPPORT_WHATSAPP_URL", "https://wa.me/971529012505")