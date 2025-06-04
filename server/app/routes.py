from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from .models import db, User, Game, UserPrediction
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from .utils import (
    generate_reset_token,
    confirm_reset_token,
    send_password_reset_email,
    send_invite_email,
    verify_paypal_payment,
    send_payment_receipt_email
)


main = Blueprint('main', __name__)

# --- Login Required Decorator ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("You must be logged in to access this page.", "warning")
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Home Page ---
@main.route('/')
def index():
    user = None
    needs_profile = False
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        needs_profile = not user.first_name or not user.last_name
    return render_template('index.html', user=user, needs_profile=needs_profile)

# --- Login ---
@main.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        user = User.query.filter_by(email=email).first()

        if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
            flash("Invalid email or password.", "danger")
            return render_template('login.html')

        session['user_id'] = user.id
        session['user_email'] = user.email

        if not user.first_name or not user.last_name:
            flash("Please complete your profile before continuing.", "warning")
            return redirect(url_for('main.profile'))

        flash("Login successful.", "success")
        return redirect(url_for('main.index'))

    return render_template('login.html')

# --- Logout ---
@main.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('user_email', None)
    flash("You have been logged out.", "info")
    return redirect(url_for('main.index'))

# --- Forgot Password ---
@main.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        user = User.query.filter_by(email=email).first()

        if user:
            token = generate_reset_token(user.email)
            reset_url = url_for('main.reset_password_token', token=token, _external=True)
            send_password_reset_email(user.email, reset_url)

        flash("If that email exists, a reset link has been sent.", "info")
        return redirect(url_for('main.login'))

    return render_template('forgot_password.html')

# --- Reset Password ---
@main.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password_token(token):
    email = confirm_reset_token(token)
    if not email:
        flash("Reset link is invalid or has expired.", "danger")
        return redirect(url_for('main.forgot_password'))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('main.login'))

    if request.method == 'POST':
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        if new_password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template('reset_password.html')

        user.password_hash = generate_password_hash(new_password)
        user.must_change_password = False
        db.session.commit()
        flash("Your password has been set. You may now log in.", "success")
        return redirect(url_for('main.login'))

    return render_template('reset_password.html')

# --- Submit Picks (Protected) ---
@main.route('/submit-picks', methods=['GET', 'POST'])
@login_required
def submit_picks():
    user = User.query.get(session['user_id'])

    if not user.first_name or not user.last_name:
        # flash("Please complete your profile before submitting picks.", "warning")
        return redirect(url_for('main.profile'))

    if not user.is_paid:
        flash("Please complete payment to access picks.", "warning")
        return redirect(url_for('main.payment'))

    games = Game.query.order_by(Game.date_of_game, Game.time_of_game).all()

    if request.method == 'POST':
        for game in games:
            home_score = request.form.get(f'home_score_{game.id}')
            away_score = request.form.get(f'away_score_{game.id}')
            if home_score and away_score:
                prediction = UserPrediction.query.filter_by(user_id=user.id, game_id=game.id).first()
                if not prediction:
                    prediction = UserPrediction(user_id=user.id, game_id=game.id)
                prediction.home_score_prediction = int(home_score)
                prediction.away_score_prediction = int(away_score)
                db.session.add(prediction)
        db.session.commit()
        flash("Picks submitted successfully.", "success")
        return redirect(url_for('main.submit_picks'))

    return render_template('submit_picks.html', games=games)

# --- All Predictions (Protected) ---
@main.route('/predictions')
@login_required
def predictions():
    all_predictions = UserPrediction.query.all()
    return render_template('predictions.html', predictions=all_predictions)

# --- Scoring Guidelines ---
@main.route('/guidelines')
def guidelines():
    return render_template('guidelines.html')

# --- Dashboard (Admin Only) ---
@main.route('/dashboard')
@login_required
def dashboard():
    if session.get('user_email') != 'admin@superpredicto.com':
        flash("Access denied.", "danger")
        return redirect(url_for('main.index'))
    return render_template('dashboard.html')

# --- Invite User (Admin Only) ---
@main.route('/invite-user', methods=['POST'])
@login_required
def invite_user():
    if session.get('user_email') != 'admin@superpredicto.com':
        flash("Access denied.", "danger")
        return redirect(url_for('main.index'))

    email = request.form['invite_email'].strip().lower()
    existing_user = User.query.filter_by(email=email).first()

    if existing_user:
        flash("This email is already registered.", "warning")
        return redirect(url_for('main.dashboard'))

    # Create user with must_change_password=True
    new_user = User(email=email, must_change_password=True)
    db.session.add(new_user)
    db.session.commit()

    # Generate and send invite email
    token = generate_reset_token(email)
    reset_url = url_for('main.reset_password_token', token=token, _external=True)

    try:
        send_invite_email(email, reset_url)
        flash(f"Invitation sent to {email}.", "success")
    except Exception as e:
        flash(f"User created, but email failed: {str(e)}", "danger")

    return redirect(url_for('main.dashboard'))

# --- Test User Creation ---
@main.route('/test', methods=['GET', 'POST'])
def test_create_user():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        password = request.form['password']

        if User.query.filter_by(email=email).first():
            flash("Email already exists.", "danger")
            return render_template('test.html')

        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            password_hash=generate_password_hash(password),
            must_change_password=True
        )
        db.session.add(user)
        db.session.commit()
        flash("User created successfully!", "success")
        return redirect(url_for('main.test_create_user'))

    return render_template('test.html')

# --- Profile Page ---
@main.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()

        if not first_name or not last_name:
            flash("First name and last name are required.", "danger")
            return render_template('profile.html', user=user)

        user.first_name = first_name
        user.last_name = last_name
        db.session.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for('main.index'))

    return render_template('profile.html', user=user)

# --- Payment ---
@main.route('/payment', methods=['GET', 'POST'])
@login_required
def payment():
    user = User.query.get(session['user_id'])

    if not user.first_name or not user.last_name:
        flash("Please complete your profile before making a payment.", "warning")
        return redirect(url_for('main.profile'))

    if user.is_paid:
        flash("You're already paid up!", "info")
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        # Simulate successful payment
        user.is_paid = True
        db.session.commit()
        flash("Payment successful! You can now submit your picks.", "success")
        return redirect(url_for('main.submit_picks'))

    return render_template('payment.html')

# --- Payment Success ---
@main.route('/payment-success', methods=['GET', 'POST'])
@login_required
def payment_success():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'User session invalid'}), 401

    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    if request.method == 'POST':
        data = request.get_json()
        order_id = data.get('orderID')

        if not order_id:
            return jsonify({'error': 'Missing orderID'}), 400

        try:
            order_info = verify_paypal_payment(order_id)
            if order_info.get('status') != 'COMPLETED':
                return jsonify({'error': 'Payment not confirmed by PayPal'}), 400

            if not user.is_paid:
                user.is_paid = True
                db.session.commit()
                send_payment_receipt_email(
                    user.email,
                    order_info['purchase_units'][0]['amount']['value']
                )

            return jsonify({'message': 'Payment confirmed'}), 200

        except Exception as e:
            return jsonify({'error': f'Payment verification failed: {str(e)}'}), 500

    if request.method == 'GET':
        flash("Payment completed. You may now submit your picks.", "success")
        return redirect(url_for('main.submit_picks'))



