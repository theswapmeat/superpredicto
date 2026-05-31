"""Re-seed a tournament's games from football-data.org (the live source of truth).

DESTRUCTIVE: deletes the tournament's existing games AND any predictions tied to
them, then recreates every fixture from the API with its external_id set. It does
NOT touch participants / enrollments.

Usage (from server/):
    python reseed_games_from_api.py --year 2026             # DRY RUN (default, safe)
    python reseed_games_from_api.py --year 2026 --confirm   # actually do it

Needs FOOTBALL_DATA_API_KEY in the environment. Respects APP_ENV (dev = local DB,
prod = Supabase) — double-check the "Target DB" line before confirming.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import Tournament, Game, UserPrediction
from app.football_data import fetch_wc_matches, sync_fixtures


def main():
    year = 2026
    if "--year" in sys.argv:
        year = int(sys.argv[sys.argv.index("--year") + 1])
    confirm = "--confirm" in sys.argv

    api_key = os.getenv("FOOTBALL_DATA_API_KEY")
    if not api_key:
        print("ERROR: FOOTBALL_DATA_API_KEY is not set in the environment.")
        return

    app = create_app()
    with app.app_context():
        print("Target DB:", db.engine.url.render_as_string(hide_password=True))
        t = Tournament.query.filter_by(year=year).first()
        if not t:
            print(f"ERROR: tournament for year {year} not found. Run migrations first.")
            return

        game_ids = [g.id for g in Game.query.filter_by(tournament_id=t.id).all()]
        n_preds = (
            UserPrediction.query.filter(UserPrediction.game_id.in_(game_ids)).count()
            if game_ids
            else 0
        )
        try:
            n_api = len(fetch_wc_matches(api_key))
        except Exception as e:
            print("ERROR talking to football-data.org:", e)
            return

        print(f"Tournament: {t.name} ({t.year})  id={t.id}")
        print(f"  existing games:        {len(game_ids)}")
        print(f"  predictions to DELETE: {n_preds}")
        print(f"  fixtures from the API: {n_api}")
        print("  (participants / enrollments are NOT touched)")

        if not confirm:
            print("\nDRY RUN — nothing written. Re-run with --confirm to apply.")
            return

        if game_ids:
            UserPrediction.query.filter(
                UserPrediction.game_id.in_(game_ids)
            ).delete(synchronize_session=False)
            Game.query.filter_by(tournament_id=t.id).delete(
                synchronize_session=False
            )
            db.session.commit()
            print(f"  deleted {n_preds} predictions and {len(game_ids)} games.")

        summary = sync_fixtures(api_key, t.id, create_missing=True, write_scores=True)
        print("  re-seeded from API:", summary)


if __name__ == "__main__":
    main()
