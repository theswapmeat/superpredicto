import os
import requests
from flask import current_app
from itsdangerous import URLSafeTimedSerializer

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

# --- Send Password Reset Email ---
def send_password_reset_email(to_email, reset_url):
    _send_email(
        to_email,
        subject="Reset Your SuperPredicto Password",
        html=f"""
            <p>Hello,</p>
            <p>We received a request to reset your SuperPredicto password.</p>
            <p><a href="{reset_url}">Click here to reset your password</a></p>
            <p>This link will expire in 24 hours. If you didn't request this, just ignore this email.</p>
        """
    )

# --- Send Admin Invite Email ---
def send_invite_email(to_email, reset_url):
    _send_email(
        to_email,
        subject="You're Invited to Join SuperPredicto",
        html=f"""
            <p>Hello,</p>
            <p>You’ve been invited to create your SuperPredicto account.</p>
            <p><a href="{reset_url}">Click here to set your password</a></p>
            <p>This link will expire in 24 hours.</p>
        """
    )

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
    api_key = current_app.config['RESEND_API_KEY']
    sender = "SuperPredicto <no-reply@superpredicto.com>"

    payload = {
        "from": sender,
        "to": [to_email],
        "subject": subject,
        "html": html
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    response = requests.post("https://api.resend.com/emails", json=payload, headers=headers)

    if response.status_code != 200:
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
