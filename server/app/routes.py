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
from .models import db, User, Game, UserPrediction, Tournament, Participant
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
    send_tournament_invite_email,
    verify_paypal_payment,
    send_payment_receipt_email,
)
import os

main = Blueprint("main", __name__)


def assign_leaderboard_ranks(entries):
    """Sort leaderboard entries by the ranking cascade and assign competition ranks.

    Cascade: total points desc -> perfect picks desc -> picks scoring 2 desc ->
    picks scoring 1 desc -> invalid picks ASC (fewer is better).

    Ties on every criterion share a rank (competition ranking: 1, 2, 2, 4).
    Players with 0 points are unranked (rank = None, shown as "-"). Mutates and
    returns `entries`.
    """
    entries.sort(
        key=lambda d: (
            -d["points"],
            -d["perfect_picks"],
            -d["picks_scoring_two"],
            -d["picks_scoring_one"],
            d["invalid_picks"],
        )
    )
    prev_key = None
    rank = 0
    for i, d in enumerate(entries, start=1):
        if d["points"] <= 0:
            d["rank"] = None
            continue
        key = (
            d["points"],
            d["perfect_picks"],
            d["picks_scoring_two"],
            d["picks_scoring_one"],
            d["invalid_picks"],
        )
        if key != prev_key:
            rank = i
            prev_key = key
        d["rank"] = rank
    return entries


def _user_initials(u):
    fn = (u.first_name or "").strip()
    ln = (u.last_name or "").strip()
    if fn and ln:
        return (fn[0] + ln[0]).upper()
    base = (u.display_name or fn or u.email or "?").strip()
    return base[:2].upper()


def earliest_open_game(tournament_id):
    """The earliest game of a tournament whose kickoff is still in the future."""
    now_utc = datetime.now(timezone("UTC"))
    games = (
        Game.query.filter_by(tournament_id=tournament_id)
        .order_by(Game.date_of_game, Game.time_of_game)
        .all()
    )
    for g in games:
        if g.kickoff_utc() > now_utc:
            return g
    return None


def earliest_live_game(tournament_id):
    """The in-play game with the earliest kickoff (i.e. closest to finishing).

    Several group-stage games can be live at once; the homepage card features
    just one, so we pick the one that started first.
    """
    return (
        Game.query.filter(
            Game.tournament_id == tournament_id,
            Game.status.in_(("IN_PLAY", "PAUSED")),
        )
        .order_by(Game.date_of_game, Game.time_of_game)
        .first()
    )


def build_leaderboard(tournament, current_user_id=None):
    """Ranked leaderboard entries for one tournament (active, named participants).

    Each entry carries user_id so rows can link to that user's predictions.
    """
    if not tournament:
        return []
    participants = (
        Participant.query.filter_by(tournament_id=tournament.id, is_active=True)
        .join(Participant.user)
        .filter(
            User.email != "admin@superpredicto.com",
            User.first_name.isnot(None),
            User.first_name != "",
            User.last_name.isnot(None),
            User.last_name != "",
            User.display_name.isnot(None),
            User.display_name != "",
        )
        .all()
    )
    entries = [
        {
            "user_id": p.user_id,
            "name": p.user.display_name
            or f"{p.user.first_name or ''} {p.user.last_name or ''}".strip()
            or "-",
            "initials": _user_initials(p.user),
            "is_you": p.user_id == current_user_id,
            "points": (p.perfect_picks or 0) * 4
            + (p.picks_scoring_two or 0) * 2
            + (p.picks_scoring_one or 0) * 1,
            "perfect_picks": p.perfect_picks or 0,
            "picks_scoring_two": p.picks_scoring_two or 0,
            "picks_scoring_one": p.picks_scoring_one or 0,
            "picks_scoring_zero": p.picks_scoring_zero or 0,
            "invalid_picks": p.invalid_picks or 0,
        }
        for p in participants
    ]
    assign_leaderboard_ranks(entries)
    return entries


@main.app_context_processor
def inject_nav_context():
    """Expose the current user to every template for the shared dark navbar."""
    uid = session.get("user_id")
    nav_user = User.query.get(uid) if uid else None
    return {
        "current_user": nav_user,
        "is_admin_user": session.get("user_email") == "admin@superpredicto.com",
        "current_initials": _user_initials(nav_user) if nav_user else "",
    }


# --- Home Page ---
@main.route("/")
def index():
    user = None
    needs_profile = False

    user_id = session.get("user_id")
    if user_id:
        user = User.query.get(user_id)
        if not user:
            session.pop("user_id", None)
            session.pop("user_email", None)
        else:
            needs_profile = not user.first_name or not user.last_name

    # Leaderboard view: defaults to the active tournament, but a season switcher
    # lets anyone view a past tournament's final leaderboard (read-only — inactive
    # seasons expose ONLY the leaderboard, no schedule/picks/predictions).
    tournaments = Tournament.query.order_by(Tournament.year.desc()).all()
    selected = None
    sel_id = request.args.get("tournament_id", type=int)
    if sel_id:
        selected = Tournament.query.get(sel_id)
    if not selected:
        selected = active_tournament() or (tournaments[0] if tournaments else None)

    # Homepage shows only the top 3 (ranks 1-3, ties included); the full table
    # lives on /leaderboard.
    all_entries = build_leaderboard(selected, user_id)
    leaderboard_dicts = [
        e for e in all_entries if e["rank"] is not None and e["rank"] <= 3
    ]

    # Hero + live pick card only for the active tournament; archived tournaments
    # are leaderboard-only.
    show_hero = bool(selected and selected.is_active)
    open_game = None
    live_game = None
    user_pick = None
    is_eligible = False
    match_count = (
        Game.query.filter_by(tournament_id=selected.id).count() if selected else 0
    )
    if show_hero:
        # A live game takes over the hero card; otherwise show the next pickable one.
        live_game = earliest_live_game(selected.id)
        open_game = earliest_open_game(selected.id)
        if user_id:
            part = Participant.query.filter_by(
                user_id=user_id, tournament_id=selected.id
            ).first()
            is_eligible = bool(part and part.is_active and part.is_paid)
            if open_game:
                user_pick = UserPrediction.query.filter_by(
                    user_id=user_id, game_id=open_game.id
                ).first()

    return render_template(
        "index.html",
        user=user,
        logged_in=bool(user),
        user_initials=_user_initials(user) if user else "",
        needs_profile=needs_profile,
        leaderboard=leaderboard_dicts,
        tournament=selected,
        tournaments=tournaments,
        show_hero=show_hero,
        open_game=open_game,
        live_game=live_game,
        any_live=bool(live_game),
        user_pick=user_pick,
        is_eligible=is_eligible,
        match_count=match_count,
        team_count=48,
        perfect_pts=4,
    )


# --- Tournaments (card grid) ---
@main.route("/tournaments")
def tournaments():
    all_tournaments = Tournament.query.order_by(Tournament.year.desc()).all()
    return render_template("tournaments.html", tournaments=all_tournaments)


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
@main.route("/submit-picks", methods=["GET", "POST"])
@login_required
def submit_picks():
    user_id = session["user_id"]
    user = User.query.get(user_id)

    if not user.first_name or not user.last_name:
        flash("Please complete your profile before submitting picks.", "warning")
        return redirect(url_for("main.profile"))

    active = active_tournament()
    if not active:
        flash("There is no active tournament right now.", "warning")
        return redirect(url_for("main.index"))

    part = Participant.query.filter_by(
        user_id=user_id, tournament_id=active.id
    ).first()
    if not part or not part.is_active:
        flash(
            f"You're not enrolled in {active.name}. Please contact the admin to join.",
            "warning",
        )
        return redirect(url_for("main.index"))

    if not part.is_paid:
        flash("Please complete payment to submit picks.", "warning")
        return redirect(url_for("main.payment"))

    games = (
        Game.query.filter_by(tournament_id=active.id)
        .order_by(Game.date_of_game, Game.time_of_game)
        .all()
    )
    uae = timezone("Asia/Dubai")

    game_ids = [g.id for g in games]
    existing_predictions = (
        {
            pred.game_id: pred
            for pred in UserPrediction.query.filter(
                UserPrediction.user_id == user_id,
                UserPrediction.game_id.in_(game_ids),
            ).all()
        }
        if game_ids
        else {}
    )

    if request.method == "POST":
        now_uae = datetime.now(uae)
        error_found = False
        form_data = request.form
        changes_made = False
        locked_attempts = []  # game numbers the user tried to change after kickoff

        for game in games:
            # Locked games (already kicked off) are never modified — their saved
            # pick stays exactly as it is. But if the user actually tried to change
            # one (submitted a complete score that differs from the saved pick),
            # record it so we can tell them clearly that the change was rejected.
            game_datetime_local = uae.localize(
                datetime.combine(game.date_of_game, game.time_of_game)
            )
            if game_datetime_local <= now_uae:
                hv = form_data.get(f"home_score_{game.id}", "").strip()
                av = form_data.get(f"away_score_{game.id}", "").strip()
                if hv.isdigit() and av.isdigit():
                    ex = existing_predictions.get(game.id)
                    ex_h = ex.home_score_prediction if ex else None
                    ex_a = ex.away_score_prediction if ex else None
                    if int(hv) != ex_h or int(av) != ex_a:
                        locked_attempts.append(game.game_number)
                continue

            home_key = f"home_score_{game.id}"
            away_key = f"away_score_{game.id}"

            home_val = form_data.get(home_key, "").strip()
            away_val = form_data.get(away_key, "").strip()

            existing = existing_predictions.get(game.id)

            # Skip empty inputs — but do NOT delete an existing prediction. Once a
            # pick has been made it can only be amended, never removed (upstream fix
            # for "scores being deleted").
            if not home_val and not away_val:
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
                tournament=active,
            )

        if locked_attempts:
            if len(locked_attempts) == 1:
                flash(
                    f"Game #{locked_attempts[0]} had already kicked off, so your change "
                    "to it was NOT saved — predictions lock the moment a match starts.",
                    "warning",
                )
            else:
                nums = ", ".join(f"#{n}" for n in locked_attempts)
                flash(
                    f"Games {nums} had already kicked off, so your changes to them were "
                    "NOT saved — predictions lock the moment a match starts.",
                    "warning",
                )

        if changes_made:
            db.session.commit()
            flash("Your picks have been saved.", "success")
        elif not locked_attempts:
            flash("No changes made to your picks.", "info")
        return redirect(url_for("main.submit_picks"))

    now_uae = datetime.now(uae)
    return render_template(
        "submit_picks.html",
        games=games,
        pred_dict=existing_predictions,
        uae_now=now_uae,
        form_data={},
        tournament=active,
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

    active = active_tournament()
    if not active:
        flash("There is no active tournament right now.", "warning")
        return redirect(url_for("main.index"))

    query = (
        UserPrediction.query.join(UserPrediction.user)
        .join(UserPrediction.game)
        .filter(User.email != "admin@superpredicto.com")
        .filter(Game.tournament_id == active.id)
        # Only predictions for games that have already started
        .filter((Game.date_of_game + cast(Game.time_of_game, Interval)) <= now_uae)
    )

    if user_id:
        query = query.filter(UserPrediction.user_id == user_id)
    if game_id:
        query = query.filter(UserPrediction.game_id == game_id)

    query = query.order_by(Game.game_number.asc())

    paginated_preds = query.paginate(page=page, per_page=per_page)

    # Dropdowns: participants of the active tournament + its started games
    all_users = (
        User.query.join(Participant, Participant.user_id == User.id)
        .filter(
            Participant.tournament_id == active.id,
            Participant.is_active == True,
            User.email != "admin@superpredicto.com",
            User.first_name.isnot(None),
            User.first_name != "",
            User.last_name.isnot(None),
            User.last_name != "",
            User.display_name.isnot(None),
            User.display_name != "",
        )
        .order_by(User.first_name, User.last_name)
        .all()
    )

    all_games = (
        Game.query.filter(
            Game.tournament_id == active.id,
            (Game.date_of_game + cast(Game.time_of_game, Interval)) <= now_uae,
        )
        .order_by(Game.date_of_game, Game.time_of_game)
        .all()
    )

    return render_template(
        "predictions.html",
        predictions=paginated_preds,
        users=all_users,
        games=all_games,
        per_page=per_page,
        tournament=active,
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

    active = active_tournament()
    active_id = active.id if active else -1

    query = (
        UserPrediction.query.options(
            joinedload(UserPrediction.user), joinedload(UserPrediction.game)
        )
        .join(UserPrediction.user)
        .join(UserPrediction.game)
        .filter(User.email != "admin@superpredicto.com")
        .filter(Game.tournament_id == active_id)
    )

    # Only predictions for games that have started or completed
    query = query.filter(
        or_(
            Game.is_completed == True,
            (Game.date_of_game + cast(Game.time_of_game, Interval)) <= now_uae,
        )
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


# --- Full Leaderboard ---
@main.route("/leaderboard")
@login_required
def leaderboard():
    tournaments = Tournament.query.order_by(Tournament.year.desc()).all()
    selected = None
    sel_id = request.args.get("tournament_id", type=int)
    if sel_id:
        selected = Tournament.query.get(sel_id)
    if not selected:
        selected = active_tournament() or (tournaments[0] if tournaments else None)

    entries = build_leaderboard(selected, session.get("user_id"))
    any_live = bool(
        selected
        and selected.is_active
        and Game.query.filter(
            Game.tournament_id == selected.id,
            Game.status.in_(("IN_PLAY", "PAUSED")),
        ).first()
    )
    return render_template(
        "leaderboard.html",
        leaderboard=entries,
        tournament=selected,
        any_live=any_live,
    )


# --- Lock a single pick from the landing page ---
@main.route("/lock-pick", methods=["POST"])
@login_required
def lock_pick():
    user_id = session["user_id"]
    active = active_tournament()
    if not active:
        flash("There is no active tournament right now.", "warning")
        return redirect(url_for("main.index"))

    # Must be a paid, active participant of the current tournament.
    part = Participant.query.filter_by(
        user_id=user_id, tournament_id=active.id
    ).first()
    if not part or not part.is_active:
        flash(f"You're not enrolled in {active.name}.", "warning")
        return redirect(url_for("main.index"))
    if not part.is_paid:
        flash("Please complete payment to submit picks.", "warning")
        return redirect(url_for("main.payment"))

    game = Game.query.filter_by(
        id=request.form.get("game_id", type=int), tournament_id=active.id
    ).first()
    if not game:
        flash("That match is no longer available.", "danger")
        return redirect(url_for("main.index"))

    # Reject if the game has already kicked off.
    if game.kickoff_utc() <= datetime.now(timezone("UTC")):
        flash(f"Game #{game.game_number} has already started.", "danger")
        return redirect(url_for("main.index"))

    home_val = (request.form.get("home_score") or "").strip()
    away_val = (request.form.get("away_score") or "").strip()
    if not home_val.isdigit() or not away_val.isdigit():
        flash("Scores must be whole numbers.", "danger")
        return redirect(url_for("main.index"))

    home_score, away_score = int(home_val), int(away_val)
    existing = UserPrediction.query.filter_by(
        user_id=user_id, game_id=game.id
    ).first()
    if existing:
        existing.home_score_prediction = home_score
        existing.away_score_prediction = away_score
    else:
        db.session.add(
            UserPrediction(
                user_id=user_id,
                game_id=game.id,
                home_score_prediction=home_score,
                away_score_prediction=away_score,
            )
        )
    db.session.commit()
    flash("Pick saved.", "success")
    return redirect(url_for("main.submit_picks", focus=game.id))


# --- Admin helpers ---
ADMIN_EMAIL = "admin@superpredicto.com"


def is_admin():
    return session.get("user_email") == ADMIN_EMAIL


def get_selected_tournament():
    """Resolve which tournament the admin is managing.

    Prefers ?tournament_id= / form tournament_id, then the active tournament,
    then the most recent one.
    """
    tid = request.values.get("tournament_id", type=int)
    if tid:
        t = Tournament.query.get(tid)
        if t:
            return t
    return (
        Tournament.query.filter_by(is_active=True).first()
        or Tournament.query.order_by(Tournament.year.desc()).first()
    )


def active_tournament():
    """The current/active tournament shown to players (the public-facing one)."""
    return Tournament.query.filter_by(is_active=True).first()


def is_archived(tournament):
    """Archived (non-active) tournaments are read-only — no scoring or edits."""
    return bool(tournament) and not tournament.is_active


# --- Dashboard (Admin Only) ---
@main.route("/dashboard")
@login_required
def dashboard():
    if not is_admin():
        flash("Access denied.", "danger")
        return redirect(url_for("main.index"))

    tournaments = Tournament.query.order_by(Tournament.year.desc()).all()
    selected = get_selected_tournament()

    participants = (
        Participant.query.filter_by(tournament_id=selected.id)
        .join(Participant.user)
        .order_by(User.display_name, User.first_name)
        .all()
    )
    enrolled_ids = {p.user_id for p in participants}

    addable_q = User.query.filter(User.email != ADMIN_EMAIL)
    if enrolled_ids:
        addable_q = addable_q.filter(~User.id.in_(enrolled_ids))
    addable_users = addable_q.order_by(User.display_name, User.first_name).all()

    return render_template(
        "dashboard.html",
        tournaments=tournaments,
        selected_tournament=selected,
        participants=participants,
        addable_users=addable_users,
        invite_feedback=session.pop("invite_feedback", None),
    )


# --- Match Scores (Admin Only) — enter results / knockout teams ---
@main.route("/scores")
@login_required
def match_scores():
    if not is_admin():
        flash("Access denied.", "danger")
        return redirect(url_for("main.index"))

    tournaments = Tournament.query.order_by(Tournament.year.desc()).all()
    selected = get_selected_tournament()
    games = (
        Game.query.filter_by(tournament_id=selected.id)
        .order_by(Game.game_number)
        .all()
    )
    return render_template(
        "match_scores.html",
        tournaments=tournaments,
        selected_tournament=selected,
        games=games,
    )


# --- Dashboard (Admin Only / Update Games) ---
@main.route("/dashboard/update-games", methods=["POST"])
@login_required
def update_games():
    if not is_admin():
        flash("Access denied.", "danger")
        return redirect(url_for("main.index"))

    selected = get_selected_tournament()
    if is_archived(selected):
        flash("This tournament is archived and can't be modified.", "warning")
        return redirect(url_for("main.match_scores", tournament_id=selected.id))

    games = (
        Game.query.filter_by(tournament_id=selected.id)
        .order_by(Game.game_number)
        .all()
    )

    for game in games:
        # Update team names only for knockout games (teams are TBD placeholders).
        if game.stage == "knockout":
            home_team = request.form.get(f"home_team_{game.id}")
            away_team = request.form.get(f"away_team_{game.id}")
            if home_team is not None:
                game.home_team = home_team.strip()
            if away_team is not None:
                game.away_team = away_team.strip()

        # ✅ Update scores (always editable)
        home_score = request.form.get(f"home_{game.id}")
        away_score = request.form.get(f"away_{game.id}")

        old_h, old_a = game.home_team_score, game.away_team_score
        try:
            game.home_team_score = int(home_score) if home_score != "" else None
            game.away_team_score = int(away_score) if away_score != "" else None
        except ValueError:
            flash(f"Invalid score entered for Game #{game.game_number}.", "danger")
            continue

        # An admin hand-edit pins the score: the live-score auto-sync won't overwrite it.
        if (game.home_team_score, game.away_team_score) != (old_h, old_a):
            game.manual_override = True

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
    flash("Match results saved.", "success")
    return redirect(url_for("main.match_scores", tournament_id=selected.id))


# --- Invite User / Enroll in Tournament (Admin Only) ---
@main.route("/invite-user", methods=["POST"])
@login_required
def invite_user():
    if not is_admin():
        flash("Access denied.", "danger")
        return redirect(url_for("main.index"))

    selected = get_selected_tournament()
    if is_archived(selected):
        flash("This tournament is archived and can't be modified.", "warning")
        return redirect(url_for("main.dashboard", tournament_id=selected.id))

    email = request.form.get("invite_email", "").strip().lower()

    # Feedback for the invite form is shown inline (under the field), not as a
    # top-of-page flash. Stash {category, message} in the session for the next
    # dashboard render to pick up.
    def _invite_feedback(category, message):
        session["invite_feedback"] = {"category": category, "message": message}
        return redirect(url_for("main.dashboard", tournament_id=selected.id))

    if not email:
        return _invite_feedback("err", "Please enter an email address.")

    existing_user = User.query.filter_by(email=email).first()

    if existing_user:
        # Account already exists — just enroll them in this tournament.
        already = Participant.query.filter_by(
            user_id=existing_user.id, tournament_id=selected.id
        ).first()
        if already:
            message, category = f"{email} is already in {selected.year}.", "info"
        else:
            db.session.add(
                Participant(user_id=existing_user.id, tournament_id=selected.id)
            )
            db.session.commit()
            message, category = f"{email} enrolled in {selected.year}.", "ok"

        # If they never finished signup, re-send the invite link.
        if not existing_user.password_hash:
            token = generate_reset_token(email)
            reset_url = url_for(
                "main.reset_password_token", token=token, mode="invite", _external=True
            )
            try:
                send_invite_email(email, reset_url)
                message += f" Invite link re-sent to {email}."
            except Exception as e:
                message += f" Enrolled, but invite email failed: {str(e)}"
                category = "warn"
        return _invite_feedback(category, message)

    # New account: create, enroll, and invite.
    new_user = User(email=email, must_change_password=True)
    db.session.add(new_user)
    db.session.flush()  # assign new_user.id before creating the Participant
    db.session.add(Participant(user_id=new_user.id, tournament_id=selected.id))
    db.session.commit()

    token = generate_reset_token(email)
    reset_url = url_for(
        "main.reset_password_token", token=token, mode="invite", _external=True
    )
    try:
        send_invite_email(email, reset_url)
        return _invite_feedback(
            "ok", f"Invitation sent to {email} and enrolled in {selected.year}."
        )
    except Exception as e:
        return _invite_feedback(
            "err", f"User created & enrolled, but email failed: {str(e)}"
        )


# --- Add Existing Users to a Tournament (Admin Only) ---
@main.route("/dashboard/add-participants", methods=["POST"])
@login_required
def add_participants():
    if not is_admin():
        flash("Access denied.", "danger")
        return redirect(url_for("main.index"))

    selected = get_selected_tournament()
    if is_archived(selected):
        flash("This tournament is archived and can't be modified.", "warning")
        return redirect(url_for("main.dashboard", tournament_id=selected.id))

    user_ids = request.form.getlist("add_user_ids", type=int)
    if not user_ids:
        flash("No users selected.", "info")
        return redirect(url_for("main.dashboard", tournament_id=selected.id))

    already_in = {
        p.user_id
        for p in Participant.query.filter_by(tournament_id=selected.id)
        .filter(Participant.user_id.in_(user_ids))
        .all()
    }
    added = 0
    emailed = 0
    email_failed = []
    for uid in user_ids:
        if uid in already_in:
            continue
        user = User.query.get(uid)
        if not user or user.email == ADMIN_EMAIL:
            continue
        db.session.add(Participant(user_id=uid, tournament_id=selected.id))
        added += 1

        # Email them a one-time "set your password" link. We discard their old
        # password ONLY if the email actually sends, so a send failure never
        # locks them out. With password_hash = None they must use the link
        # (login is blocked until they set a new password).
        token = generate_reset_token(user.email)
        set_url = url_for(
            "main.reset_password_token", token=token, mode="invite", _external=True
        )
        try:
            send_tournament_invite_email(user.email, set_url, selected.year)
            user.password_hash = None
            user.must_change_password = True
            emailed += 1
        except Exception:
            email_failed.append(user.email)

    if added:
        db.session.commit()
        msg = f"Added {added} player(s) to {selected.year}; emailed {emailed} a set-password link."
        if email_failed:
            flash(msg + f" Email failed for: {', '.join(email_failed)}.", "warning")
        else:
            flash(msg, "success")
    else:
        flash("No new players added.", "info")
    return redirect(url_for("main.dashboard", tournament_id=selected.id))


# --- Update Participant Paid/Active Status (Admin Only) ---
@main.route("/dashboard/update-participants", methods=["POST"])
@login_required
def update_participants():
    if not is_admin():
        flash("Unauthorized access.", "danger")
        return redirect(url_for("main.index"))

    selected = get_selected_tournament()
    if is_archived(selected):
        flash("This tournament is archived and can't be modified.", "warning")
        return redirect(url_for("main.dashboard", tournament_id=selected.id))

    participants = Participant.query.filter_by(tournament_id=selected.id).all()
    changes_made = False

    for p in participants:
        is_paid_checked = f"paid_{p.id}" in request.form
        is_active_checked = f"active_{p.id}" in request.form

        if p.is_paid != is_paid_checked:
            p.is_paid = is_paid_checked
            changes_made = True
        if p.is_active != is_active_checked:
            p.is_active = is_active_checked
            changes_made = True

    if changes_made:
        db.session.commit()
        flash("Participant statuses updated.", "success")
    else:
        flash("No changes detected.", "info")
    return redirect(url_for("main.dashboard", tournament_id=selected.id))


# --- Remove a Participant from a Tournament (Admin Only) ---
@main.route("/dashboard/remove-participant", methods=["POST"])
@login_required
def remove_participant():
    if not is_admin():
        flash("Access denied.", "danger")
        return redirect(url_for("main.index"))

    selected = get_selected_tournament()
    if is_archived(selected):
        flash("This tournament is archived and can't be modified.", "warning")
        return redirect(url_for("main.dashboard", tournament_id=selected.id))

    participant_id = request.form.get("participant_id", type=int)
    p = Participant.query.filter_by(
        id=participant_id, tournament_id=selected.id
    ).first()
    if p:
        name = p.user.display_name or p.user.email
        db.session.delete(p)
        db.session.commit()
        flash(f"Removed {name} from {selected.year}.", "success")
    else:
        flash("Participant not found.", "warning")
    return redirect(url_for("main.dashboard", tournament_id=selected.id))


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

    active = active_tournament()
    if not active:
        flash("There is no active tournament right now.", "warning")
        return redirect(url_for("main.index"))

    part = Participant.query.filter_by(
        user_id=user.id, tournament_id=active.id
    ).first()
    if not part or not part.is_active:
        flash(
            f"You're not enrolled in {active.name}. Please contact the admin to join.",
            "warning",
        )
        return redirect(url_for("main.index"))

    if part.is_paid:
        flash("You're already paid up!", "info")
        return redirect(url_for("main.index"))

    if request.method == "POST":
        # Simulate successful payment
        part.is_paid = True
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

            active = active_tournament()
            part = (
                Participant.query.filter_by(
                    user_id=user_id, tournament_id=active.id
                ).first()
                if active
                else None
            )
            if part and not part.is_paid:
                part.is_paid = True
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
    active = active_tournament()
    games = (
        Game.query.filter_by(tournament_id=active.id)
        .order_by(Game.game_number)
        .all()
        if active
        else []
    )
    return render_template("schedule.html", games=games, tournament=active)


# --- Email previews (DEV ONLY) ---
# Renders the outgoing emails in the browser without sending anything.
# Disabled in production (APP_ENV=prod) so it never becomes a public surface.
@main.route("/dev/email-preview")
@main.route("/dev/email-preview/<kind>")
def email_preview(kind=None):
    if os.getenv("APP_ENV", "dev") == "prod":
        abort(404)

    from .utils import (
        build_invite_email,
        build_password_reset_email,
        build_tournament_invite_email,
    )

    sample_url = url_for(
        "main.reset_password_token", token="SAMPLE-TOKEN-1234", mode="invite", _external=True
    )
    builders = {
        "invite": lambda: build_invite_email(sample_url),
        "reset": lambda: build_password_reset_email(sample_url),
        "tournament": lambda: build_tournament_invite_email(sample_url, 2026),
    }

    if kind in builders:
        subject, html = builders[kind]()
        return html

    # index of available previews
    items = "".join(
        f'<li style="margin:6px 0"><a href="/dev/email-preview/{k}">{k}</a> '
        f'<span style="color:#888">— {builders[k]()[0]}</span></li>'
        for k in builders
    )
    return (
        "<div style='font-family:system-ui;padding:30px;max-width:640px'>"
        "<h2>Email previews <span style='color:#888;font-size:14px'>(dev only)</span></h2>"
        f"<ul>{items}</ul></div>"
    )


from tasks.scoring import run_prediction_scoring


# --- Admin Scoring ---
@main.route("/admin/run-scoring")
@login_required
def admin_run_scoring():
    if not is_admin():
        abort(403)
    selected = get_selected_tournament()
    if is_archived(selected):
        flash("This tournament is archived and can't be modified.", "warning")
        return redirect(url_for("main.dashboard", tournament_id=selected.id))

    run_prediction_scoring(selected.id)
    flash(f"Scoring run for {selected.name} ({selected.year}).", "success")
    return redirect(url_for("main.dashboard", tournament_id=selected.id))


# --- Live-score sync (cron-triggered) ---
# Pulls live World Cup scores from football-data.org into the active tournament's
# games, then re-runs scoring. Guarded by INTERNAL_SYNC_TOKEN (not a logged-in user),
# so an external scheduler (DO Function / GitHub Actions) can call it.
@main.route("/internal/sync-scores", methods=["GET", "POST"])
def internal_sync_scores():
    expected = current_app.config.get("INTERNAL_SYNC_TOKEN")
    token = request.headers.get("X-Sync-Token") or request.args.get("token")
    if not expected or token != expected:
        abort(403)

    active = active_tournament()
    if not active or not active.is_active:
        return jsonify({"ok": False, "error": "no active tournament"}), 400

    api_key = current_app.config.get("FOOTBALL_DATA_API_KEY")
    if not api_key:
        return jsonify({"ok": False, "error": "FOOTBALL_DATA_API_KEY not set"}), 500

    from .football_data import sync_fixtures

    try:
        summary = sync_fixtures(
            api_key, active.id, create_missing=True, write_scores=True
        )
        run_prediction_scoring(active.id)
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(e)}), 502

    return jsonify({"ok": True, "tournament": active.year, "sync": summary})


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
