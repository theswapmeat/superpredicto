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
from sqlalchemy import func, desc, cast, String, Interval, or_
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
    from sqlalchemy import or_

    user = None
    needs_profile = False
    completed_games_count = Game.query.filter_by(is_completed=True).count()

    user_id = session.get("user_id")
    if user_id:
        user = User.query.get(user_id)
        if not user:
            session.pop("user_id", None)
            session.pop("user_email", None)
        else:
            needs_profile = not user.first_name or not user.last_name

    # Fetch all relevant users
    raw_users = (
        User.query.filter(User.email != "admin@superpredicto.com")
        .filter(User.first_name.isnot(None), User.first_name != "")
        .filter(User.last_name.isnot(None), User.last_name != "")
        .filter(User.display_name.isnot(None), User.display_name != "")
        .all()
    )

    # Build leaderboard dicts with calculated points
    leaderboard_dicts = []
    for u in raw_users:
        perfect = u.perfect_picks or 0
        two = u.picks_scoring_two or 0
        one = u.picks_scoring_one or 0

        points = perfect * 4 + two * 2 + one * 1

        leaderboard_dicts.append(
            {
                "name": u.display_name
                or f"{u.first_name or ''} {u.last_name or ''}".strip()
                or "-",
                "points": points,
                "perfect_picks": perfect,
                "picks_scoring_two": two,
                "picks_scoring_one": one,
                "picks_scoring_zero": u.picks_scoring_zero or 0,
                "invalid_picks": u.invalid_picks or 0,
            }
        )

    # Sort by ranking logic
    leaderboard_dicts.sort(
        key=lambda x: (
            -x["points"],
            -x["perfect_picks"],
            -x["picks_scoring_two"],
            -x["picks_scoring_one"],
        )
    )

    return render_template(
        "index.html",
        user=user,
        needs_profile=needs_profile,
        leaderboard=leaderboard_dicts,
        completed_games_count=completed_games_count,
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
    # ✅ Redirect already-logged-in users to home
    if "user_id" in session:
        return redirect(url_for("main.index"))

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

    # ✅ Prevent reuse of invite link
    if user.password_hash and mode == "invite":
        flash("This invite link has already been used. Please log in.", "warning")
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
# @main.route("/submit-picks", methods=["GET", "POST"])
# @login_required
# def submit_picks():
#     return render_template("maintenance.html", message="This page is under maintenance. Please check back in a few hours.")


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

    existing_predictions = {
        pred.game_id: pred
        for pred in UserPrediction.query.filter_by(user_id=user_id).all()
    }

    if request.method == "POST":
        now_uae = datetime.now(uae)
        error_found = False
        form_data = request.form
        changes_made = False
        deletion_attempted = False

        for game in games:
            game_datetime_local = uae.localize(
                datetime.combine(game.date_of_game, game.time_of_game)
            )

            home_key = f"home_score_{game.id}"
            away_key = f"away_score_{game.id}"

            home_val = form_data.get(home_key, "").strip()
            away_val = form_data.get(away_key, "").strip()

            existing = existing_predictions.get(game.id)

            # Skip empty inputs, but do NOT delete existing predictions
            if not home_val and not away_val:
                # if existing:
                #     flash(
                #         f"Once predictions have been made, deletion is not allowed. You can amend them.",
                #         "warning",
                #     )
                #     deletion_attempted = True
                continue

            # Handle incomplete input
            if (home_val and not away_val) or (away_val and not home_val):
                flash(
                    f"Both scores must be entered for Game #{game.game_number}.",
                    "danger",
                )
                error_found = True
                continue

            # Validate inputs are digits
            if not home_val.isdigit() or not away_val.isdigit():
                flash(
                    f"Scores for Game #{game.game_number} must be whole numbers.",
                    "danger",
                )
                error_found = True
                continue

            # Reject picks if game has already started
            if game_datetime_local <= now_uae:
                flash(
                    f"Game #{game.game_number} has already started. Picks not accepted.",
                    "danger",
                )
                error_found = True
                continue

            home_score = int(home_val)
            away_score = int(away_val)

            if not existing:
                db.session.add(
                    UserPrediction(
                        user_id=user_id,
                        game_id=game.id,
                        home_score_prediction=home_score,
                        away_score_prediction=away_score,
                    )
                )
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
            flash(
                "No changes made to your picks. Reminder - you cannot delete predictions once they have been made.",
                "info",
            )
            return redirect(url_for("main.submit_picks"))

        db.session.commit()
        flash("Your picks have been saved.", "success")
        return redirect(url_for("main.submit_picks"))

    now_uae = datetime.now(uae)
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

    uae = timezone("Asia/Dubai")
    now_uae = datetime.now(uae)

    query = UserPrediction.query.join(UserPrediction.user).join(UserPrediction.game)

    query = query.filter(User.email != "admin@superpredicto.com")

    # ✅ Only include predictions for games that have already started
    query = query.filter((Game.date_of_game + Game.time_of_game) <= now_uae)

    if user_id:
        query = query.filter(UserPrediction.user_id == user_id)
    if game_id:
        query = query.filter(UserPrediction.game_id == game_id)

    query = query.order_by(Game.game_number.asc())

    paginated_preds = query.paginate(page=page, per_page=per_page)

    # User & game filter dropdowns
    all_users = (
        User.query.filter(
            User.email != "admin@superpredicto.com",
            User.is_paid == True,
            User.is_active == True,
            User.first_name.isnot(None),
            User.last_name.isnot(None),
            User.display_name.isnot(None),
            User.first_name != "",
            User.last_name != "",
            User.display_name != "",
        )
        .order_by(User.display_name)
        .all()
    )

    all_games = Game.query.order_by(Game.date_of_game, Game.time_of_game).all()

    # Only keep games that are completed or already started
    visible_games = [
        g
        for g in all_games
        if g.is_completed
        or uae.localize(datetime.combine(g.date_of_game, g.time_of_game)) <= now_uae
    ]

    return render_template(
        "predictions.html",
        predictions=paginated_preds,
        users=all_users,
        games=visible_games,
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

    uae = timezone("Asia/Dubai")
    now_uae = datetime.now(uae)

    # Load all predictions with joins
    all_predictions = (
        UserPrediction.query.options(
            joinedload(UserPrediction.user), joinedload(UserPrediction.game)
        )
        .join(UserPrediction.user)
        .join(UserPrediction.game)
        .filter(User.email != "admin@superpredicto.com")
        .all()
    )

    # Filter in Python: only include predictions for games that are completed or already started
    filtered_preds = [
        p
        for p in all_predictions
        if p.game
        and (
            p.game.is_completed
            or uae.localize(datetime.combine(p.game.date_of_game, p.game.time_of_game))
            <= now_uae
        )
        and (not user_id or p.user_id == user_id)
        and (not game_id or p.game_id == game_id)
    ]

    filtered_preds.sort(
        key=lambda p: (
            p.game.game_number if p.game and p.game.game_number is not None else 0
        )
    )

    # Manual pagination
    start = (page - 1) * per_page
    end = start + per_page
    paginated_preds = filtered_preds[start:end]

    class SimplePagination:
        def __init__(self, items, total, page, per_page):
            self.items = items
            self.total = total
            self.page = page
            self.per_page = per_page
            self.pages = (total + per_page - 1) // per_page  # total pages
            self.has_prev = page > 1
            self.has_next = page < self.pages
            self.prev_num = page - 1 if self.has_prev else None
            self.next_num = page + 1 if self.has_next else None

    print(f"[DEBUG] {len(filtered_preds)} predictions returned to template.")
    return render_template(
        "partials/_predictions_table.html",
        predictions=SimplePagination(
            paginated_preds, len(filtered_preds), page, per_page
        ),
    )


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
    games = Game.query.order_by(Game.game_number).all()
    return render_template("dashboard.html", users=users, games=games)


# --- Dashboard (Admin Only / Update Games) ---
@main.route("/dashboard/update-games", methods=["POST"])
@login_required
def update_games():
    if session.get("user_email") != "admin@superpredicto.com":
        flash("Access denied.", "danger")
        return redirect(url_for("main.index"))

    games = Game.query.order_by(Game.game_number).all()

    for game in games:
        # ✅ Update team names (for games 49–63)
        if game.game_number >= 49:
            home_team = request.form.get(f"home_team_{game.id}")
            away_team = request.form.get(f"away_team_{game.id}")
            if home_team is not None:
                game.home_team = home_team.strip()
            if away_team is not None:
                game.away_team = away_team.strip()

        # ✅ Update scores (always editable)
        home_score = request.form.get(f"home_{game.id}")
        away_score = request.form.get(f"away_{game.id}")

        try:
            game.home_team_score = int(home_score) if home_score != "" else None
            game.away_team_score = int(away_score) if away_score != "" else None
        except ValueError:
            flash(f"Invalid score entered for Game #{game.game_number}.", "danger")
            continue

        # ✅ Determine whether to mark as completed
        checkbox_checked = request.form.get(f"completed_{game.id}") == "on"
        if checkbox_checked:
            if game.home_team_score is not None and game.away_team_score is not None:
                game.is_completed = True
            else:
                flash(
                    f"Game #{game.game_number} cannot be marked as completed without both scores.",
                    "warning",
                )
        else:
            # ✅ Uncheck completed if box not checked
            game.is_completed = False

    db.session.commit()
    flash("Games updated successfully.", "success")
    return redirect(url_for("main.dashboard"))


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
            first_name == (user.first_name or "")
            and last_name == (user.last_name or "")
            and display_name == (user.display_name or "")
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


# --- Support ---
@main.route("/support")
def support():
    return render_template("support.html")


##############################
##  DEBUG
##############################


@main.route("/debug/game-timestamps")
@login_required
def debug_game_timestamps():
    if session.get("user_email") != "admin@superpredicto.com":
        abort(403)

    uae = timezone("Asia/Dubai")
    now_uae = datetime.now(uae)

    games = Game.query.order_by(Game.game_number).all()

    output = f"<h3>Current Dubai time: {now_uae}</h3><ul>"
    for game in games:
        try:
            start_dt = datetime.combine(game.date_of_game, game.time_of_game)
            output += f"<li>Game #{game.game_number} — {game.home_team} vs {game.away_team} | Starts at: {start_dt} | Completed: {game.is_completed}</li>"
        except Exception as e:
            output += f"<li>Error in game #{game.id}: {e}</li>"
    output += "</ul>"
    return output


@main.route("/debug/prediction-check")
@login_required
def prediction_check():
    if session.get("user_email") != "admin@superpredicto.com":
        abort(403)
    uae = timezone("Asia/Dubai")
    now_uae = datetime.now(uae)

    try:
        query = UserPrediction.query.join(UserPrediction.game).filter(
            or_(
                Game.is_completed == True,
                (Game.date_of_game + cast(Game.time_of_game, Interval)) <= now_uae,
            )
        )
        count = query.count()
        return f"<h3>{count} predictions found for started or completed games</h3>"
    except Exception as e:
        return f"<h3>Error occurred: {e}</h3>", 500
