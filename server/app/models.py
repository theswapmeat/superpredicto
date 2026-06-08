from datetime import datetime
import pytz

from . import db
from sqlalchemy.sql import func
from sqlalchemy import UniqueConstraint

_DUBAI_TZ = pytz.timezone("Asia/Dubai")


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String, unique=True, nullable=False)
    first_name = db.Column(db.String, nullable=True)
    last_name = db.Column(db.String, nullable=True)
    display_name = db.Column(db.String(20), nullable=True)
    avatar = db.Column(db.String)
    password_hash = db.Column(db.String, nullable=True)
    must_change_password = db.Column(db.Boolean, default=True)
    # One-shot flag: set True once the "24h to kickoff, finish signing up" blast
    # has been emailed to this (still-unactivated) invitee, so it's sent only once.
    signup_reminder_sent = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    updated_at = db.Column(
        db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("display_name", name="uq_users_display_name"),)

    def __repr__(self):
        return f"<User {self.email}>"


class Tournament(db.Model):
    __tablename__ = "tournaments"

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    # Exactly one tournament should be active (the "current" one the app shows by default).
    is_active = db.Column(db.Boolean, default=False, nullable=False)

    __table_args__ = (db.UniqueConstraint("year", name="uq_tournaments_year"),)

    def __repr__(self):
        return f"<Tournament {self.name} ({self.year})>"


class Participant(db.Model):
    """A user's membership in a specific tournament.

    Being a User (an account) is separate from being IN a tournament. Payment and
    active status are tracked per tournament here, NOT on the global User row.
    """

    __tablename__ = "participants"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    tournament_id = db.Column(db.Integer, db.ForeignKey("tournaments.id"), nullable=False)
    is_paid = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    # One-shot: set once the "signed up but unpaid" reminder has been emailed.
    payment_reminder_sent = db.Column(db.Boolean, default=False, nullable=False)
    joined_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

    # Per-tournament scoring (populated by the scoring job). Replaces the old
    # global scoring columns that lived on User.
    perfect_picks = db.Column(db.Integer, default=0)
    picks_scoring_one = db.Column(db.Integer, default=0)
    picks_scoring_two = db.Column(db.Integer, default=0)
    picks_scoring_zero = db.Column(db.Integer, default=0)
    invalid_picks = db.Column(db.Integer, default=0)

    user = db.relationship("User", backref=db.backref("participations", lazy=True))
    tournament = db.relationship(
        "Tournament", backref=db.backref("participants", lazy=True)
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "tournament_id", name="uq_participant_user_tournament"
        ),
    )

    def __repr__(self):
        return f"<Participant user:{self.user_id} tournament:{self.tournament_id}>"


class Game(db.Model):
    __tablename__ = "games"

    id = db.Column(db.Integer, primary_key=True)
    date_of_game = db.Column(db.Date, nullable=False)
    time_of_game = db.Column(db.Time(timezone=False), nullable=False)
    home_team = db.Column(db.String, nullable=False)
    away_team = db.Column(db.String, nullable=False)
    # Official 3-letter codes (football-data.org `tla`, e.g. "RSA") + crest URLs.
    # None until the API resolves the team (knockout TBD slots).
    home_team_code = db.Column(db.String, nullable=True)
    away_team_code = db.Column(db.String, nullable=True)
    home_team_crest = db.Column(db.String, nullable=True)
    away_team_crest = db.Column(db.String, nullable=True)
    home_team_score = db.Column(db.Integer, nullable=True)
    away_team_score = db.Column(db.Integer, nullable=True)
    # Penalty-shootout result (knockout only) — cosmetic, never scored. Set only
    # when a tied knockout game is decided on penalties; surfaced via pens_label.
    home_team_pens = db.Column(db.Integer, nullable=True)
    away_team_pens = db.Column(db.Integer, nullable=True)
    is_completed = db.Column(db.Boolean, default=False)
    game_number = db.Column(db.Integer, nullable=False)
    # "group" or "knockout" — replaces the brittle game_number >= 49 hardcode.
    stage = db.Column(db.String, nullable=True)
    # Raw football-data.org status: SCHEDULED / TIMED / IN_PLAY / PAUSED /
    # FINISHED / SUSPENDED / POSTPONED ... Drives the "LIVE" pulse (see is_live).
    status = db.Column(db.String, nullable=True)
    # Raw group code from football-data.org for group games, e.g. "GROUP_A"
    # (None for knockout games). Surfaced via the group_label property.
    group_name = db.Column(db.String, nullable=True)
    # football-data.org match id — links a Game to its live fixture for auto-sync.
    external_id = db.Column(db.Integer, unique=True, nullable=True)
    # Set True once an admin hand-edits the score, so the auto-sync won't overwrite it.
    manual_override = db.Column(db.Boolean, default=False, nullable=False)

    tournament_id = db.Column(
        db.Integer,
        db.ForeignKey("tournaments.id"),
        nullable=False
        # ✅ Avoid `default=1` here; instead handle in migration or seed logic
    )
    tournament = db.relationship(
        "Tournament",
        backref=db.backref("games", lazy=True),
        lazy=True
    )

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    updated_at = db.Column(
        db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def kickoff_utc(self):
        """Kickoff as a timezone-aware UTC datetime.

        Stored date/time are Asia/Dubai wall-clock; this returns the true instant
        so the client can render it in each viewer's local timezone.
        """
        local = _DUBAI_TZ.localize(
            datetime.combine(self.date_of_game, self.time_of_game)
        )
        return local.astimezone(pytz.utc)

    @property
    def is_live(self):
        """True while the match is being played (incl. half-time)."""
        return self.status in ("IN_PLAY", "PAUSED")

    @property
    def pens_label(self):
        """Cosmetic shootout result, e.g. 'ARG won 4–2 on pens'. None if not a shootout."""
        ph, pa = self.home_team_pens, self.away_team_pens
        if ph is None or pa is None:
            return None
        if ph >= pa:
            code = self.home_team_code or (self.home_team or "")[:3].upper()
        else:
            code = self.away_team_code or (self.away_team or "")[:3].upper()
        return f"{code} won {max(ph, pa)}–{min(ph, pa)} on pens"

    @property
    def stage_label(self):
        """Human label for the pickcard tag, e.g. 'Group A' or 'Knockout'."""
        if self.stage == "group" and self.group_name:
            return self.group_name.replace("GROUP_", "Group ")  # "GROUP_A" -> "Group A"
        return "Group" if self.stage == "group" else "Knockout"

    def __repr__(self):
        return f"<Game {self.game_number}: {self.home_team} vs {self.away_team}>"


class UserPrediction(db.Model):
    __tablename__ = "user_predictions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    home_score_prediction = db.Column(db.Integer, nullable=True)
    away_score_prediction = db.Column(db.Integer, nullable=True)
    points_earned = db.Column(db.Integer, default=0)

    user = db.relationship("User", backref=db.backref("predictions", lazy=True), lazy=True)
    game = db.relationship("Game", backref=db.backref("predictions", lazy=True), lazy=True)

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    updated_at = db.Column(
        db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self):
        return f"<Prediction User:{self.user_id} Game:{self.game_id}>"


class PickReminder(db.Model):
    """Idempotency record: one row per (user, game) we've sent a 'kickoff soon,
    you haven't picked' reminder for, so each user is nudged at most once per game.
    """

    __tablename__ = "pick_reminders"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    sent_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "game_id", name="uq_pick_reminder_user_game"),
    )

    def __repr__(self):
        return f"<PickReminder User:{self.user_id} Game:{self.game_id}>"
