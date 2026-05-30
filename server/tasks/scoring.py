from datetime import datetime

from app import db
from app.models import Participant, Game, UserPrediction


def run_prediction_scoring(tournament_id):
    """Score every participant of one tournament from that tournament's completed games.

    Writes the five counters onto each Participant row (per tournament) and sets
    points_earned on each prediction. Only participants of this tournament are
    scored; predictions by non-participants are ignored.
    """
    print(
        f"[Scoring] tournament={tournament_id} started at "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    try:
        participants = Participant.query.filter_by(tournament_id=tournament_id).all()
        part_by_user = {p.user_id: p for p in participants}
        for p in participants:
            p.perfect_picks = 0
            p.picks_scoring_one = 0
            p.picks_scoring_two = 0
            p.picks_scoring_zero = 0
            p.invalid_picks = 0

        completed_games = Game.query.filter_by(
            tournament_id=tournament_id, is_completed=True
        ).all()
        game_ids = [g.id for g in completed_games]
        predictions = (
            UserPrediction.query.filter(UserPrediction.game_id.in_(game_ids)).all()
            if game_ids
            else []
        )

        pred_map = {}
        for pr in predictions:
            pred_map.setdefault(pr.game_id, {})[pr.user_id] = pr

        for game in completed_games:
            final_home = game.home_team_score
            final_away = game.away_team_score
            if final_home is None or final_away is None:
                continue

            game_preds = pred_map.get(game.id, {})

            for user_id, part in part_by_user.items():
                pred = game_preds.get(user_id)

                if (
                    not pred
                    or pred.home_score_prediction is None
                    or pred.away_score_prediction is None
                ):
                    part.invalid_picks += 1
                    if pred:
                        pred.points_earned = 0
                    continue

                p_home = pred.home_score_prediction
                p_away = pred.away_score_prediction

                # 1. 1-0 or 0-1 predicted but not exact -> invalid
                if (p_home, p_away) in [(1, 0), (0, 1)] and (
                    p_home != final_home or p_away != final_away
                ):
                    part.invalid_picks += 1
                    pred.points_earned = 0

                # 2. Perfect prediction
                elif p_home == final_home and p_away == final_away:
                    part.perfect_picks += 1
                    pred.points_earned = 4

                # 3. Correct winner with one score matching -> 2 points
                elif (
                    (final_home > final_away and p_home > p_away)
                    or (final_away > final_home and p_away > p_home)
                ) and (p_home == final_home or p_away == final_away):
                    part.picks_scoring_two += 1
                    pred.points_earned = 2

                # 4. Correct winner, no score match -> 1 point
                elif (final_home > final_away and p_home > p_away) or (
                    final_away > final_home and p_away > p_home
                ):
                    part.picks_scoring_one += 1
                    pred.points_earned = 1

                # 5. Wrong winner, but one score matches -> 1 point
                elif p_home == final_home or p_away == final_away:
                    part.picks_scoring_one += 1
                    pred.points_earned = 1

                # 6. Both predicted and actual were draws (not exact)
                elif final_home == final_away and p_home == p_away:
                    part.picks_scoring_one += 1
                    pred.points_earned = 1

                # 7. Everything else is just wrong -> 0 points
                else:
                    part.picks_scoring_zero += 1
                    pred.points_earned = 0

        db.session.commit()
        print("[Scoring] Run completed successfully.")

    except Exception as e:
        db.session.rollback()
        print(f"[Scoring] Error occurred: {str(e)}")
