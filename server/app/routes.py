from flask import (
    current_app,
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    abort,
)
from datetime import datetime, timedelta
from pytz import timezone
from .models import db, User, Game, UserPrediction
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, desc
from .utils import (
    generate_reset_token,
    confirm_reset_token,
    send_password_reset_email,
    send_invite_email,
    verify_paypal_payment,
    send_payment_receipt_email,
)
import os

main = Blueprint("main", __name__)


# --- Home Page ---
@main.route("/")
def index():
    user = None
    needs_profile = False
    if "user_id" in session:
        user = User.query.get(session["user_id"])
        if user:
            needs_profile = not user.first_name or not user.last_name
        else:
            # User ID in session doesn't exist in DB; clear session
            session.pop("user_id", None)


    # Fetch users excluding admin, and order based on leaderboard ranking rules
    leaderboard_users = (
        User.query.filter(User.email != "admin@superpredicto.com")
        .filter(User.first_name.isnot(None), User.first_name != "")
        .filter(User.last_name.isnot(None), User.last_name != "")
        .filter(User.display_name.isnot(None), User.display_name != "")
        .order_by(
            desc(User.perfect_picks),
            desc(User.picks_scoring_two),
            desc(User.picks_scoring_one),
        )
        .all()
    )

    # Prepare dicts for the template
    leaderboard_dicts = [
        {
            "name": user.display_name
            or f"{user.first_name or ''} {user.last_name or ''}".strip()
            or "-",
            "points": sum(
                filter(
                    None,
                    [
                        (user.perfect_picks or 0) * 4,
                        (user.picks_scoring_two or 0) * 2,
                        (user.picks_scoring_one or 0) * 1,
                    ],
                )
            ),
            "perfect_picks": user.perfect_picks or 0,
            "picks_scoring_two": user.picks_scoring_two or 0,
            "picks_scoring_one": user.picks_scoring_one or 0,
            "picks_scoring_zero": user.picks_scoring_zero or 0,
            "invalid_picks": user.invalid_picks or 0,
        }
        for user in leaderboard_users
    ]

    return render_template(
        "index.html",
        user=user,
        needs_profile=needs_profile,
        leaderboard=leaderboard_dicts,
    )


# --- Keep Alive Route ---
keepalive_bp = Blueprint("keepalive", __name__)


@keepalive_bp.route("/keepalive", methods=["GET"])
def keep_alive():
    return jsonify({"status": "ok"}), 200


# --- Login Required Decorator ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            next_url = request.url
            return redirect(
                url_for("main.login", next=next_url, reason="login_required")
            )
        return f(*args, **kwargs)

    return decorated_function


# --- Login ---
@main.route("/login", methods=["GET", "POST"])
def login():
    # Flash only if user was redirected here due to being unauthenticated
    reason = request.args.get("reason")
    if request.method == "GET" and reason == "login_required":
        flash("You must be logged in to access this page.", "warning")

    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        remember = "remember" in request.form  # Get checkbox state

        user = User.query.filter_by(email=email).first()

        if (
            not user
            or not user.password_hash
            or not check_password_hash(user.password_hash, password)
        ):
            flash("Invalid email or password.", "danger")
            return render_template("login.html")

        session["user_id"] = user.id
        session["user_email"] = user.email
        session.permanent = remember  # Extend session if 'Remember Me' checked

        if not user.first_name or not user.last_name:
            flash("Please complete your profile before continuing.", "warning")
            return redirect(url_for("main.profile"))

        flash("Login successful.", "success")

        # Redirect to next page if provided, otherwise home
        next_page = request.args.get("next")
        return redirect(next_page or url_for("main.index"))

    return render_template("login.html")


# --- Logout ---
@main.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("user_email", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))


# --- Forgot Password ---
@main.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        user = User.query.filter_by(email=email).first()

        if user:
            token = generate_reset_token(user.email)
            reset_url = url_for(
                "main.reset_password_token", token=token, _external=True
            )
            send_password_reset_email(user.email, reset_url)

        flash("If that email exists, a reset link has been sent.", "info")
        return redirect(url_for("main.login"))

    return render_template("forgot_password.html")


# --- Reset Password ---
@main.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password_token(token):
    mode = request.args.get("mode", "reset")
    email = confirm_reset_token(token)
    if not email:
        flash("Reset link is invalid or has expired.", "danger")
        return redirect(url_for("main.forgot_password"))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("main.login"))

    if request.method == "POST":
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        if new_password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("reset_password.html")

        user.password_hash = generate_password_hash(new_password)
        user.must_change_password = False
        db.session.commit()
        flash("Your password has been set. You may now log in.", "success")
        return redirect(url_for("main.login"))

    return render_template("reset_password.html", mode=mode)


# --- Submit Picks (Protected) ---
@main.route("/submit-picks", methods=["GET", "POST"])
@login_required
def submit_picks():
    user_id = session["user_id"]
    user = User.query.get(user_id)

    if not user.first_name or not user.last_name:
        flash("Please complete your profile before submitting picks.", "warning")
        return redirect(url_for("main.profile"))

    if not user.is_paid:
        flash("Please complete payment to submit picks.", "warning")
        return redirect(url_for("main.payment"))

    games = Game.query.order_by(Game.date_of_game, Game.time_of_game).all()
    uae = timezone("Asia/Dubai")
    now_uae = datetime.now(uae)

    existing_predictions = {
        pred.game_id: pred
        for pred in UserPrediction.query.filter_by(user_id=user_id).all()
    }

    if request.method == "POST":
        error_found = False
        form_data = request.form
        changes_made = False

        for game in games:
            game_datetime = datetime.combine(game.date_of_game, game.time_of_game)
            game_datetime_uae = timezone("UTC").localize(game_datetime).astimezone(uae)

            if game_datetime_uae <= now_uae:
                continue  # Game is in the past

            home_key = f"home_score_{game.id}"
            away_key = f"away_score_{game.id}"

            home_val = form_data.get(home_key, "").strip()
            away_val = form_data.get(away_key, "").strip()

            existing = existing_predictions.get(game.id)

            # Case: One score filled but not the other
            if (home_val and not away_val) or (away_val and not home_val):
                flash(
                    f"Both scores must be entered for Game #{game.game_number}.",
                    "danger",
                )
                error_found = True
                continue

            # Case: both blank — remove prediction if it exists
            if not home_val and not away_val:
                if existing:
                    db.session.delete(existing)
                    changes_made = True
                continue

            # Validate that both are integers
            if not home_val.isdigit() or not away_val.isdigit():
                flash(
                    f"Scores for Game #{game.game_number} must be whole numbers.",
                    "danger",
                )
                error_found = True
                continue

            home_score = int(home_val)
            away_score = int(away_val)

            # Update or create prediction
            if not existing:
                new_pred = UserPrediction(
                    user_id=user_id,
                    game_id=game.id,
                    home_score_prediction=home_score,
                    away_score_prediction=away_score,
                )
                db.session.add(new_pred)
                changes_made = True
            elif (
                existing.home_score_prediction != home_score
                or existing.away_score_prediction != away_score
            ):
                existing.home_score_prediction = home_score
                existing.away_score_prediction = away_score
                changes_made = True

        if error_found:
            return render_template(
                "submit_picks.html",
                games=games,
                pred_dict=existing_predictions,
                uae_now=now_uae,
                form_data=form_data,
            )

        if not changes_made:
            flash("No changes made to your picks.", "info")
            return redirect(url_for("main.submit_picks"))

        db.session.commit()
        flash("Your picks have been saved.", "success")
        return redirect(url_for("main.submit_picks"))

    return render_template(
        "submit_picks.html",
        games=games,
        pred_dict=existing_predictions,
        uae_now=now_uae,
        form_data={},
    )


# --- All Predictions (Protected) ---
@main.route("/predictions")
@login_required
def predictions():
    user_id = request.args.get("user_id", type=int)
    game_id = request.args.get("game_id", type=int)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    query = UserPrediction.query.join(UserPrediction.user).join(UserPrediction.game)

    # Exclude predictions made by admin
    query = query.filter(User.email != "admin@superpredicto.com")

    if user_id:
        query = query.filter(UserPrediction.user_id == user_id)
    if game_id:
        query = query.filter(UserPrediction.game_id == game_id)

    query = query.order_by(Game.game_number.asc())

    paginated_preds = query.paginate(page=page, per_page=per_page)

    # Exclude admin from user filter dropdown
    all_users = (
    User.query
    .filter(
        User.email != "admin@superpredicto.com",
        User.is_paid == True,
        User.is_active == True,
        User.first_name.isnot(None),
        User.last_name.isnot(None),
        User.display_name.isnot(None),
        User.first_name != "",
        User.last_name != "",
        User.display_name != ""
    )
    .order_by(User.first_name, User.last_name)
    .all()
)

    all_games = Game.query.order_by(Game.date_of_game, Game.time_of_game).all()

    return render_template(
        "predictions.html",
        predictions=paginated_preds,
        users=all_users,
        games=all_games,
        per_page=per_page,
    )



# --- Predictions Filter ---
@main.route("/predictions/filter")
@login_required
def predictions_filter():
    user_id = request.args.get("user_id", type=int)
    game_id = request.args.get("game_id", type=int)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    query = UserPrediction.query.options(
        joinedload(UserPrediction.user), joinedload(UserPrediction.game)
    ).join(
        UserPrediction.user
    ).join(
        UserPrediction.game
    ).filter(
        User.email != "admin@superpredicto.com"
    )

    if user_id:
        query = query.filter(UserPrediction.user_id == user_id)
    if game_id:
        query = query.filter(UserPrediction.game_id == game_id)

    query = query.order_by(Game.game_number.asc())

    predictions = query.paginate(page=page, per_page=per_page)

    return render_template("partials/_predictions_table.html", predictions=predictions)



# --- Scoring Guidelines ---
@main.route("/guidelines")
def guidelines():
    return render_template("guidelines.html")


# --- Dashboard (Admin Only) ---
@main.route("/dashboard")
@login_required
def dashboard():
    if session.get("user_email") != "admin@superpredicto.com":
        flash("Access denied.", "danger")
        return redirect(url_for("main.index"))

    users = User.query.filter(User.email != "admin@superpredicto.com").all()
    return render_template("dashboard.html", users=users)



# --- Invite User (Admin Only) ---
@main.route("/invite-user", methods=["POST"])
@login_required
def invite_user():
    if session.get("user_email") != "admin@superpredicto.com":
        flash("Access denied.", "danger")
        return redirect(url_for("main.index"))

    email = request.form["invite_email"].strip().lower()
    existing_user = User.query.filter_by(email=email).first()

    if existing_user:
        flash("This email is already registered.", "warning")
        return redirect(url_for("main.dashboard"))

    # Create user with must_change_password=True
    new_user = User(email=email, must_change_password=True)
    db.session.add(new_user)
    db.session.commit()

    # Generate and send invite email
    token = generate_reset_token(email)
    reset_url = url_for(
        "main.reset_password_token", token=token, mode="invite", _external=True
    )

    try:
        send_invite_email(email, reset_url)
        flash(f"Invitation sent to {email}.", "success")
    except Exception as e:
        flash(f"User created, but email failed: {str(e)}", "danger")

    return redirect(url_for("main.dashboard"))

# --- Update User Payment Status (Admin Only) ---
@main.route("/admin/update-payments", methods=["POST"])
@login_required
def update_payments():
    if session.get("user_email") != "admin@superpredicto.com":
        flash("Unauthorized access.", "danger")
        return redirect(url_for("main.index"))

    users = User.query.filter(User.email != "admin@superpredicto.com").all()
    changes_made = False

    for user in users:
        paid_checkbox = f"paid_{user.id}"
        active_checkbox = f"active_{user.id}"

        is_paid_checked = paid_checkbox in request.form
        is_active_checked = active_checkbox in request.form

        if user.is_paid != is_paid_checked:
            user.is_paid = is_paid_checked
            changes_made = True

        if user.is_active != is_active_checked:
            user.is_active = is_active_checked
            changes_made = True

    if changes_made:
        db.session.commit()
        flash("User statuses updated successfully.", "success")
    else:
        flash("No changes detected.", "info")

    return redirect(url_for("main.dashboard"))


# --- Test User Creation ---
@main.route("/test", methods=["GET", "POST"])
def test_create_user():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        first_name = request.form["first_name"]
        last_name = request.form["last_name"]
        password = request.form["password"]

        if User.query.filter_by(email=email).first():
            flash("Email already exists.", "danger")
            return render_template("test.html")

        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            password_hash=generate_password_hash(password),
            must_change_password=True,
        )
        db.session.add(user)
        db.session.commit()
        flash("User created successfully!", "success")
        return redirect(url_for("main.test_create_user"))

    return render_template("test.html")


# --- Profile Page ---
@main.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = User.query.get(session["user_id"])

    if request.method == "GET" and request.args.get("from_picks"):
        flash("Please complete your profile before submitting picks.", "warning")

    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        display_name = request.form.get("display_name", "").strip()

        if not first_name or not last_name:
            flash("First name and last name are required.", "danger")
            return render_template("profile.html", user=user)

        if not display_name:
            error = "Display name is required."
            return render_template("profile.html", user=user, error=error)

        if " " in display_name or len(display_name) > 10:
            error = "Display name must be a single word under 10 characters."
            return render_template("profile.html", user=user, error=error)

        # Check if any changes were made
        if (
            first_name == (user.first_name or "") and
            last_name == (user.last_name or "") and
            display_name == (user.display_name or "")
        ):
            flash("No changes detected.", "info")
            return redirect(url_for("main.profile"))

        # Apply changes
        user.first_name = first_name
        user.last_name = last_name
        user.display_name = display_name

        try:
            db.session.commit()
            flash("Profile updated successfully.", "success")
            return redirect(url_for("main.index"))
        except IntegrityError:
            db.session.rollback()
            error = "That display name is already taken."
            return render_template("profile.html", user=user, error=error)

    return render_template("profile.html", user=user)


# --- Payment ---
@main.route("/payment", methods=["GET", "POST"])
@login_required
def payment():
    user = User.query.get(session["user_id"])

    if request.method == "GET" and request.args.get("from_picks"):
        flash("Please complete your payment to submit picks.", "warning")

    if not user.first_name or not user.last_name:
        flash("Please complete your profile before making a payment.", "warning")
        return redirect(url_for("main.profile"))

    if user.is_paid:
        flash("You're already paid up!", "info")
        return redirect(url_for("main.index"))

    if request.method == "POST":
        # Simulate successful payment
        user.is_paid = True
        db.session.commit()
        flash("Payment successful! You can now submit your picks.", "success")
        return redirect(url_for("main.submit_picks"))

    return render_template("payment.html")


# --- Payment Success ---
@main.route("/payment-success", methods=["GET", "POST"])
@login_required
def payment_success():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "User session invalid"}), 401

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    if request.method == "POST":
        data = request.get_json()
        order_id = data.get("orderID")

        if not order_id:
            return jsonify({"error": "Missing orderID"}), 400

        try:
            order_info = verify_paypal_payment(order_id)
            if order_info.get("status") != "COMPLETED":
                return jsonify({"error": "Payment not confirmed by PayPal"}), 400

            if not user.is_paid:
                user.is_paid = True
                db.session.commit()
                send_payment_receipt_email(
                    user.email, order_info["purchase_units"][0]["amount"]["value"]
                )

            # Set session flag to allow redirect
            session["payment_successful"] = True

            return jsonify({"message": "Payment confirmed"}), 200

        except Exception as e:
            return jsonify({"error": f"Payment verification failed: {str(e)}"}), 500

    if request.method == "GET":
        if not session.get("payment_successful"):
            return redirect(url_for("main.index"))  # or abort(403)

        # Clear the flag for one-time access
        session.pop("payment_successful", None)
        flash("Payment completed. You may now submit your picks.", "success")
        return redirect(url_for("main.submit_picks"))



# --- Schedule ---
@main.route("/schedule")
def schedule():
    games = Game.query.order_by(Game.game_number).all()
    return render_template("schedule.html", games=games)


from tasks.scoring import run_prediction_scoring


# --- Admin Scoring ---
@main.route("/admin/run-scoring")
@login_required
def admin_run_scoring():
    if session.get("user_email") != "admin@superpredicto.com":
        abort(403)
    run_prediction_scoring()
    flash("Scoring successfully run.", "success")
    return redirect(url_for("main.dashboard"))
