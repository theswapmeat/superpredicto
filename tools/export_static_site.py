"""Generate the static, read-only archive of SuperPredicto into ./static_site/.

WHY: after a tournament the dynamic Flask app can be torn down to $0 and this
frozen snapshot hosted for free (GitHub Pages). It renders the REAL page
templates (leaderboard / tournaments / guidelines) but swaps base.html for a
stripped, JS-free static shell (tools/static_archive/base_static.html) and
rewrites every url_for(...) to a relative .html / assets/ path — so there's no
content duplication and nothing depends on Flask at serve time.

READ-ONLY: only queries the DB and writes files under ./static_site/. It never
writes to the database. Respects APP_ENV (dev = local DB, prod = Supabase) — run
with APP_ENV=prod to snapshot the real final standings.

Usage (from repo root):
    APP_ENV=prod python tools/export_static_site.py
    APP_ENV=prod python tools/export_static_site.py --domain superpredicto.com
"""
import os
import random
import shutil
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(REPO_ROOT, "server")
TEMPLATES_DIR = os.path.join(REPO_ROOT, "client", "templates")
STATIC_DIR = os.path.join(REPO_ROOT, "client", "static")
BASE_STATIC = os.path.join(REPO_ROOT, "tools", "static_archive", "base_static.html")
OUT_DIR = os.path.join(REPO_ROOT, "static_site")

sys.path.insert(0, SERVER_DIR)

from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader, select_autoescape

from app import create_app  # noqa: E402  (path set above)
from app.models import Game, Participant, Tournament, User  # noqa: E402
from app.routes import _user_initials, assign_leaderboard_ranks  # noqa: E402

ADMIN_EMAIL = "admin@superpredicto.com"


def standings_for(t):
    """Final standings for one tournament — the PAID + active competing field,
    ranked exactly like the live leaderboard (build_leaderboard). Forces the paid
    gate even for archived seasons so the archive matches what players saw all
    season (the app's leaderboard drops that gate once a season is inactive)."""
    parts = (
        Participant.query.filter_by(tournament_id=t.id, is_active=True)
        .join(Participant.user)
        .filter(
            User.email != ADMIN_EMAIL,
            User.first_name.isnot(None), User.first_name != "",
            User.last_name.isnot(None), User.last_name != "",
            User.display_name.isnot(None), User.display_name != "",
            Participant.is_paid.is_(True),
        )
        .all()
    )
    entries = []
    for p in parts:
        u = p.user
        entries.append({
            "user_id": p.user_id,
            "name": u.display_name
            or f"{u.first_name or ''} {u.last_name or ''}".strip()
            or "-",
            "initials": _user_initials(u),
            "is_you": False,
            "points": (p.perfect_picks or 0) * 4
            + (p.picks_scoring_two or 0) * 2
            + (p.picks_scoring_one or 0) * 1,
            "perfect_picks": p.perfect_picks or 0,
            "picks_scoring_two": p.picks_scoring_two or 0,
            "picks_scoring_one": p.picks_scoring_one or 0,
            "picks_scoring_zero": p.picks_scoring_zero or 0,
            "invalid_picks": p.invalid_picks or 0,
        })
    assign_leaderboard_ranks(entries)
    return entries


def main():
    domain = None
    if "--domain" in sys.argv:
        domain = sys.argv[sys.argv.index("--domain") + 1]

    app = create_app()
    with app.app_context():
        from app import db

        print("Source DB:", db.engine.url.render_as_string(hide_password=True))

        tournaments = Tournament.query.order_by(Tournament.year.desc()).all()
        if not tournaments:
            print("ERROR: no tournaments found in the DB."); return
        latest = tournaments[0]

        # Each tournament's standings page: newest is the root index.html.
        id_to_file = {
            t.id: ("index.html" if t.id == latest.id else f"standings-{t.year}.html")
            for t in tournaments
        }

        def static_url_for(endpoint, **values):
            if endpoint == "static":
                return "assets/" + values["filename"].replace("\\", "/")
            if endpoint == "main.index":
                return id_to_file.get(values.get("tournament_id"), "index.html")
            if endpoint == "main.leaderboard":
                return "index.html"
            if endpoint == "main.tournaments":
                return "tournaments.html"
            if endpoint == "main.guidelines":
                return "guidelines.html"
            # predictions/submit-picks/etc. don't exist in the archive.
            return "#"

        env = Environment(
            loader=ChoiceLoader([
                DictLoader({"base.html": open(BASE_STATIC, encoding="utf-8").read()}),
                FileSystemLoader(TEMPLATES_DIR),
            ]),
            autoescape=select_autoescape(["html", "xml"]),
        )
        env.globals["url_for"] = static_url_for
        env.globals["config"] = app.config

        # Fresh output dir.
        if os.path.isdir(OUT_DIR):
            shutil.rmtree(OUT_DIR)
        os.makedirs(OUT_DIR)

        def write(name, html):
            with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8") as f:
                f.write(html)

        # Example matchup for the archived homepage's right-hand card — no upcoming
        # fixtures exist, so show a random REAL past fixture as an illustration.
        real_games = Game.query.filter(
            Game.tournament_id == latest.id,
            Game.home_team != "TBD", Game.away_team != "TBD",
        ).all()
        example_game = None
        if real_games:
            g = random.choice(real_games)
            example_game = {
                "home_team": g.home_team, "away_team": g.away_team,
                "home_team_code": g.home_team_code, "away_team_code": g.away_team_code,
                "home_team_crest": g.home_team_crest, "away_team_crest": g.away_team_crest,
                "stage_label": g.stage_label,
                "example_home": random.randint(0, 3),
                "example_away": random.randint(0, 3),
                "kick_label": g.date_of_game.strftime("%b %d")
                + " · " + g.time_of_game.strftime("%I:%M %p"),
            }
        match_count = Game.query.filter_by(tournament_id=latest.id).count()

        # --- pages ---
        # Newest tournament = the root homepage (hero overview + example card +
        # its final leaderboard). Older tournaments = a plain standings page.
        idx = env.get_template("index.html")
        lb = env.get_template("leaderboard.html")
        for t in tournaments:
            entries = standings_for(t)
            if t.id == latest.id:
                html = idx.render(
                    tournament=t, leaderboard=entries,
                    show_hero=True, archive=True, logged_in=True,
                    example_game=example_game,
                    live_game=None, open_game=None, user_pick=None,
                    is_eligible=False, any_live=False,
                    match_count=match_count, team_count=48, perfect_pts=4,
                    games_counted=0, active_page="leaderboard",
                )
            else:
                html = lb.render(
                    tournament=t, leaderboard=entries, any_live=False,
                    games_counted=0, active_page="leaderboard",
                )
            write(id_to_file[t.id], html)
            print(f"  {id_to_file[t.id]:22} {t.name} ({t.year}) — {len(entries)} players")

        write("tournaments.html", env.get_template("tournaments.html").render(
            tournaments=tournaments, active_page="tournaments"))
        write("guidelines.html", env.get_template("guidelines.html").render(
            active_page="guidelines"))
        print("  tournaments.html, guidelines.html")

        # --- assets ---
        assets = os.path.join(OUT_DIR, "assets")
        for sub in ("css", "favicon", "brand", "images"):
            shutil.copytree(os.path.join(STATIC_DIR, sub),
                            os.path.join(assets, sub), dirs_exist_ok=True)
        print("  assets/ (css, favicon, brand, images)")

        # GitHub Pages: skip Jekyll processing; optional custom domain.
        write(".nojekyll", "")
        if domain:
            write("CNAME", domain + "\n")
            print(f"  CNAME -> {domain}")

        print(f"\nDone. Static site written to: {OUT_DIR}")
        print("Next: push the CONTENTS of static_site/ to the 'static_branch' root.")


if __name__ == "__main__":
    main()
