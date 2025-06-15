import os
from datetime import datetime

from app import db
from app.models import User, Game, UserPrediction

# Set up log file path
LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../logs"))
LOG_FILE = os.path.join(LOG_DIR, "scoring.log")


def log_scoring_run(message: str):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")


def run_prediction_scoring():
    try:
        users = {u.id: u for u in User.query.all()}
        for user in users.values():
            user.perfect_picks = 0
            user.picks_scoring_one = 0
            user.picks_scoring_two = 0
            user.picks_scoring_zero = 0
            user.invalid_picks = 0

        completed_games = Game.query.filter_by(is_completed=True).all()
        predictions = UserPrediction.query.all()

        pred_map = {}
        for p in predictions:
            pred_map.setdefault(p.game_id, {})[p.user_id] = p

        for game in completed_games:
            final_home = game.home_team_score
            final_away = game.away_team_score
            if final_home is None or final_away is None:
                continue

            game_preds = pred_map.get(game.id, {})

            for user in users.values():
                pred = game_preds.get(user.id)

                if (
                    not pred
                    or pred.home_score_prediction is None
                    or pred.away_score_prediction is None
                ):
                    user.invalid_picks += 1
                    if pred:
                        pred.points_earned = 0
                    continue

                p_home = pred.home_score_prediction
                p_away = pred.away_score_prediction

                # 1. 1-0 or 0-1 predicted but not exact → invalid
                if (p_home, p_away) in [(1, 0), (0, 1)] and (
                    p_home != final_home or p_away != final_away
                ):
                    user.invalid_picks += 1
                    pred.points_earned = 0

                # 2. Perfect prediction
                elif p_home == final_home and p_away == final_away:
                    user.perfect_picks += 1
                    pred.points_earned = 4

                # 3. Correct winner with one score matching → 2 points
                elif (
                    (final_home > final_away and p_home > p_away)
                    or (final_away > final_home and p_away > p_home)
                ) and (p_home == final_home or p_away == final_away):
                    user.picks_scoring_two += 1
                    pred.points_earned = 2

                # 4. Correct winner, no score match → 1 point
                elif (final_home > final_away and p_home > p_away) or (
                    final_away > final_home and p_away > p_home
                ):
                    user.picks_scoring_one += 1
                    pred.points_earned = 1

                # 5. Wrong winner, but one score matches → 1 point
                elif p_home == final_home or p_away == final_away:
                    user.picks_scoring_one += 1
                    pred.points_earned = 1

                # 6. Both predicted and actual were draws (not exact)
                elif final_home == final_away and p_home == p_away:
                    user.picks_scoring_one += 1
                    pred.points_earned = 1

                # 7. Everything else is just wrong → 0 points
                else:
                    user.picks_scoring_zero += 1
                    pred.points_earned = 0

        db.session.commit()
        log_scoring_run("Scoring completed successfully.")

    except Exception as e:
        db.session.rollback()
        log_scoring_run(f"Scoring failed: {str(e)}")
