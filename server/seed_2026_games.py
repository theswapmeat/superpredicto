"""Seed the 2026 tournament's games from worldcup.json.

Sanitizes each match's date/time: the source gives venue-local times across four
North-American UTC offsets (UTC-4/-5/-6/-7). We convert each kickoff to a single
consistent timezone -- Asia/Dubai -- matching the 2025 convention so the app's
kickoff/closing logic (which localizes stored times as Asia/Dubai) works unchanged.

game_number is assigned 1..N by true chronological kickoff. stage is "group" for
Matchday rounds and "knockout" otherwise.

Usage (from the server/ directory):
    python seed_2026_games.py --dry-run     # print, do not write
    python seed_2026_games.py               # insert (idempotent: skips if 2026 already has games)

Respects APP_ENV (dev = local, prod = Supabase).
"""
import os
import sys
import json
from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
    DUBAI = ZoneInfo("Asia/Dubai")
except Exception:  # pragma: no cover - Dubai has no DST, fixed +4
    DUBAI = timezone(timedelta(hours=4))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import create_app, db
from app.models import Tournament, Game

JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "worldcup.json"
)


def normalize(match):
    """Return a dict with Dubai-local date/time, stage, teams for one match."""
    time_str, off_str = match["time"].split()  # e.g. "13:00", "UTC-6"
    hh, mm = (int(p) for p in time_str.split(":"))
    off_hours = int(off_str.replace("UTC", ""))  # -6, -4, ...
    local = datetime.strptime(match["date"], "%Y-%m-%d").replace(
        hour=hh, minute=mm, tzinfo=timezone(timedelta(hours=off_hours))
    )
    utc = local.astimezone(timezone.utc)
    dubai = utc.astimezone(DUBAI)
    return {
        "utc": utc,
        "date_of_game": dubai.date(),
        "time_of_game": dubai.time(),
        "home_team": match["team1"].strip(),
        "away_team": match["team2"].strip(),
        "stage": "group" if match["round"].lower().startswith("matchday") else "knockout",
        "round": match["round"],
    }


def build_games():
    data = json.load(open(JSON_PATH, encoding="utf-8"))
    games = [normalize(m) for m in data["matches"]]
    games.sort(key=lambda g: g["utc"])  # chronological by true kickoff instant
    for i, g in enumerate(games, start=1):
        g["game_number"] = i
    return games


def main():
    dry = "--dry-run" in sys.argv
    games = build_games()

    print(f"Parsed {len(games)} matches from worldcup.json")
    n_group = sum(1 for g in games if g["stage"] == "group")
    print(f"  group={n_group}  knockout={len(games) - n_group}")
    print(f"  Dubai date range: {games[0]['date_of_game']} -> {games[-1]['date_of_game']}")
    print("  First 3 (Dubai local):")
    for g in games[:3]:
        print(f"    #{g['game_number']:>3} {g['date_of_game']} {g['time_of_game']} "
              f"{g['home_team']} vs {g['away_team']} [{g['stage']}]")
    print("  First knockout:")
    for g in games:
        if g["stage"] == "knockout":
            print(f"    #{g['game_number']:>3} {g['date_of_game']} {g['time_of_game']} "
                  f"{g['home_team']} vs {g['away_team']} ({g['round']})")
            break
    print("  Last 2:")
    for g in games[-2:]:
        print(f"    #{g['game_number']:>3} {g['date_of_game']} {g['time_of_game']} "
              f"{g['home_team']} vs {g['away_team']} ({g['round']})")

    app = create_app()
    with app.app_context():
        print("  Target DB:", db.engine.url.render_as_string(hide_password=True))
        t = Tournament.query.filter_by(year=2026).first()
        if not t:
            print("  ERROR: 2026 tournament not found. Run migrations first.")
            return
        existing = Game.query.filter_by(tournament_id=t.id).count()
        if existing:
            print(f"  2026 already has {existing} games — nothing to do (idempotent).")
            return
        if dry:
            print("  DRY RUN — no rows written.")
            return
        for g in games:
            db.session.add(Game(
                date_of_game=g["date_of_game"],
                time_of_game=g["time_of_game"],
                home_team=g["home_team"],
                away_team=g["away_team"],
                game_number=g["game_number"],
                stage=g["stage"],
                tournament_id=t.id,
                is_completed=False,
            ))
        db.session.commit()
        print(f"  Inserted {len(games)} games into the 2026 tournament.")


if __name__ == "__main__":
    main()
