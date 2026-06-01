import os
import requests
from flask import current_app, url_for
from itsdangerous import URLSafeTimedSerializer

# Public, absolute URL to the email logo. Emails are read in an inbox, so the
# image needs a fully-qualified URL; url_for(_external) gives the right host in
# each environment, and we fall back to the prod domain outside a request.
def _logo_url():
    try:
        return url_for("static", filename="brand/superpredicto-ondark.png", _external=True)
    except Exception:
        return "https://superpredicto.com/static/brand/superpredicto-ondark.png"

# --- Token Management ---
def generate_reset_token(email):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return serializer.dumps(email, salt=current_app.config['SECURITY_PASSWORD_SALT'])

def confirm_reset_token(token, expiration=86400):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = serializer.loads(token, salt=current_app.config['SECURITY_PASSWORD_SALT'], max_age=expiration)
    except Exception:
        return None
    return email

# --- Shared branded email layout -------------------------------------------
# A light, table-based template with inline styles so it renders reliably across
# Gmail / Outlook / Apple Mail. Keep new emails going through this for consistency.
def _email_layout(heading, body_html, cta_text=None, cta_url=None, footer_note=None):
    button = ""
    if cta_text and cta_url:
        button = f"""
        <table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0 6px;">
          <tr>
            <td align="center" bgcolor="#00D17A" style="border-radius:10px;">
              <a href="{cta_url}" target="_blank"
                 style="display:inline-block;padding:14px 30px;font-family:Arial,Helvetica,sans-serif;font-size:15px;font-weight:bold;color:#06210F;text-decoration:none;border-radius:10px;">
                {cta_text}</a>
            </td>
          </tr>
        </table>"""

    fallback = ""
    if cta_url:
        fallback = f"""
        <p style="margin:14px 0 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#8a94a6;">Or paste this link into your browser:</p>
        <p style="margin:4px 0 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;word-break:break-all;"><a href="{cta_url}" style="color:#0a9d5e;">{cta_url}</a></p>"""

    note = ""
    if footer_note:
        note = f'<p style="margin:18px 0 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:1.5;color:#8a94a6;">{footer_note}</p>'

    return f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f4f6fb;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6fb;padding:28px 12px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#ffffff;border:1px solid #e6e9f0;border-radius:16px;overflow:hidden;">
        <tr><td bgcolor="#0B1020" style="background:#0B1020;padding:22px 32px;">
          <img src="{_logo_url()}" width="190" height="60" alt="SuperPredicto"
               style="display:block;border:0;width:190px;height:60px;color:#ffffff;font-family:Arial,Helvetica,sans-serif;font-weight:bold;font-size:20px;" />
        </td></tr>
        <tr><td style="padding:22px 32px 0;">
          <h1 style="margin:0 0 12px;font-family:Arial,Helvetica,sans-serif;font-size:23px;line-height:1.25;color:#0B1020;">{heading}</h1>
          <div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.6;color:#3d4759;">{body_html}</div>
          {button}
          {fallback}
          {note}
        </td></tr>
        <tr><td style="padding:24px 32px 28px;">
          <div style="border-top:1px solid #eef1f6;padding-top:16px;">
            <p style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9aa3b2;">© 2026 SuperPredicto</p>
          </div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


# --- Email content builders -------------------------------------------------
# Each returns (subject, html). Kept separate from sending so the content can be
# previewed in a browser without dispatching a real email (see /dev/email-preview).
def build_password_reset_email(reset_url):
    return (
        "Reset your SuperPredicto password",
        _email_layout(
            heading="Reset your password",
            body_html=(
                "<p style='margin:0;'>We received a request to reset your SuperPredicto "
                "password. Click below to choose a new one — it only takes a moment.</p>"
            ),
            cta_text="Reset password →",
            cta_url=reset_url,
            footer_note="This link expires in 24 hours. If you didn't request this, you can safely ignore this email — your password won't change.",
        ),
    )


def build_invite_email(reset_url):
    return (
        "You're invited to SuperPredicto — World Cup 2026",
        _email_layout(
            heading="You're invited to play ⚽",
            body_html=(
                "<p style='margin:0 0 12px;'>You've been invited to join the "
                "<b>FIFA World Cup 2026 Prediction League</b> on SuperPredicto.</p>"
                "<p style='margin:0;'>Predict the scorelines, bank points for every correct call, "
                "and battle your friends up the leaderboard. Set your password to create your "
                "account and get started.</p>"
            ),
            cta_text="Set your password →",
            cta_url=reset_url,
            footer_note="This link expires in 7 days. If you weren't expecting this invite, you can safely ignore this email.",
        ),
    )


def build_tournament_invite_email(set_password_url, year=2026):
    return (
        f"You're in — World Cup {year} on SuperPredicto",
        _email_layout(
            heading=f"You're in for World Cup {year} ⚽",
            body_html=(
                f"<p style='margin:0 0 12px;'>Good news — you've been added to the "
                f"<b>FIFA World Cup {year} Prediction League</b> on SuperPredicto.</p>"
                "<p style='margin:0;'>To keep your account secure, set a fresh password before "
                "you start. Then make your first pick before kickoff and climb the leaderboard.</p>"
            ),
            cta_text="Set your password →",
            cta_url=set_password_url,
            footer_note="This link expires in 7 days. If you'd rather sit this one out, just ignore this email.",
        ),
    )


def build_signup_reminder_email(set_password_url, hours=24):
    return (
        f"Kickoff in {hours} hours — finish signing up for World Cup 2026",
        _email_layout(
            heading=f"⚽ The World Cup kicks off in {hours} hours",
            body_html=(
                f"<p style='margin:0 0 12px;'>The <b>FIFA World Cup 2026</b> starts in about "
                f"<b>{hours} hours</b> — and you haven't finished signing up yet.</p>"
                "<p style='margin:0;'>Set your password below to activate your account. Make sure "
                "your entry is paid (by bank transfer to the organiser) and you'll be all set to "
                "make your first picks before kickoff.</p>"
            ),
            cta_text="Set your password →",
            cta_url=set_password_url,
            footer_note="This link expires in 7 days. If you weren't expecting this, you can safely ignore this email.",
        ),
    )


def build_pick_reminder_email(games, picks_url):
    """`games`: list of {"label": "Mexico vs South Africa", "kickoff": "Wed 11 Jun, 19:00 (Dubai)"}."""
    rows = "".join(
        f"<tr><td style='padding:8px 0;border-bottom:1px solid #eef1f6;font-family:Arial,Helvetica,sans-serif;font-size:15px;color:#0B1020;'>"
        f"<b>{g['label']}</b><br><span style='font-size:13px;color:#8a94a6;'>Kicks off {g['kickoff']}</span></td></tr>"
        for g in games
    )
    plural = "games" if len(games) != 1 else "game"
    return (
        "⏰ Kickoff soon — you haven't picked yet",
        _email_layout(
            heading="⏰ Your pick closes soon",
            body_html=(
                f"<p style='margin:0 0 12px;'>You haven't made a prediction for the following {plural}, "
                "kicking off within the next couple of hours:</p>"
                f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='margin:0 0 4px;'>{rows}</table>"
                "<p style='margin:14px 0 0;'>Get your picks in before kickoff — picks lock the moment the match starts.</p>"
            ),
            cta_text="Make your pick →",
            cta_url=picks_url,
            footer_note="You're receiving this because you're a paid entrant in the FIFA World Cup 2026 league.",
        ),
    )


# --- Senders ---------------------------------------------------------------
def send_password_reset_email(to_email, reset_url):
    subject, html = build_password_reset_email(reset_url)
    _send_email(to_email, subject=subject, html=html)


def send_invite_email(to_email, reset_url):
    subject, html = build_invite_email(reset_url)
    _send_email(to_email, subject=subject, html=html)


def send_tournament_invite_email(to_email, set_password_url, year=2026):
    subject, html = build_tournament_invite_email(set_password_url, year)
    _send_email(to_email, subject=subject, html=html)


def send_signup_reminder_email(to_email, set_password_url, hours=24):
    subject, html = build_signup_reminder_email(set_password_url, hours)
    _send_email(to_email, subject=subject, html=html)


def send_pick_reminder_email(to_email, games, picks_url):
    subject, html = build_pick_reminder_email(games, picks_url)
    _send_email(to_email, subject=subject, html=html)

# --- Verify Paypal ---
def verify_paypal_payment(order_id):
    client_id = os.getenv('PAYPAL_CLIENT_ID')
    client_secret = os.getenv('PAYPAL_CLIENT_SECRET')

    headers = {
        "Accept": "application/json",
        "Accept-Language": "en_US",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    # Step 1: Get access token
    auth_response = requests.post(
        "https://api-m.sandbox.paypal.com/v1/oauth2/token",
        auth=(client_id, client_secret),
        headers=headers,
        data={"grant_type": "client_credentials"},
    )
    auth_response.raise_for_status()
    access_token = auth_response.json()['access_token']

    # Step 2: Verify order
    verify_response = requests.get(
        f"https://api-m.sandbox.paypal.com/v2/checkout/orders/{order_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    verify_response.raise_for_status()
    return verify_response.json()

# --- Core Email Sender ---
def _send_email(to_email, subject, html):
    api_key = current_app.config["MAILEROO_API_KEY"]

    payload = {
        "from": {
            "address": current_app.config["MAIL_FROM_ADDRESS"],
            "display_name": current_app.config["MAIL_FROM_NAME"],
        },
        "to": {"address": to_email},
        "subject": subject,
        "html": html,
    }

    headers = {
        "X-Api-Key": api_key,
        "Content-Type": "application/json",
    }

    response = requests.post(
        "https://smtp.maileroo.com/api/v2/emails", json=payload, headers=headers
    )

    # Maileroo returns HTTP 200 with {"success": true, ...} on success.
    if response.status_code != 200:
        raise Exception(f"Email send failed ({response.status_code}): {response.text}")
    try:
        ok = response.json().get("success", False)
    except ValueError:
        ok = False
    if not ok:
        raise Exception(f"Email send failed: {response.text}")

# --- Payment Confirmation Email ---
def send_payment_receipt_email(to_email, amount):
    _send_email(
        to_email,
        subject="SuperPredicto Payment Receipt",
        html=f"""
            <p>Thank you for your payment!</p>
            <p>We received AED {amount} for your SuperPredicto account.</p>
            <p>You can now access all features.</p>
        """
    )
