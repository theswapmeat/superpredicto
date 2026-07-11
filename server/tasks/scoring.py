from flask import current_app

from app import db
from app.models import Participant, Game, UserPrediction, Tournament
from app.pick_scoring import classify_pick, COUNTER_ATTR


def run_prediction_scoring(tournament_id):
    """Score every participant of one tournament from that tournament's scored games.

    Scores any game that has both final/current scores set — including in-play
    matches — so the leaderboard updates live (provisionally) and settles at
    full-time. Counters are reset and fully recomputed each run, so it is
    idempotent and provisional points correct themselves as scores change.

    Writes the five counters onto each Participant row (per tournament) and sets
    points_earned on each prediction. Only participants of this tournament are
    scored; predictions by non-participants are ignored.
    """
    current_app.logger.info("scoring tournament=%s started", tournament_id)
    try:
        participants = Participant.query.filter_by(tournament_id=tournament_id).all()
        part_by_user = {p.user_id: p for p in participants}
        for p in participants:
            p.perfect_picks = 0
            p.picks_scoring_one = 0
            p.picks_scoring_two = 0
            p.picks_scoring_zero = 0
            p.invalid_picks = 0

        # Any game with both scores set — final OR in-play (provisional). In
        # Offline / manual mode the leaderboard is frozen to full-time results,
        # so only COMPLETED games count (no provisional movement mid-match).
        tournament = Tournament.query.get(tournament_id)
        offline = bool(tournament and tournament.offline_mode)
        games_q = Game.query.filter(
            Game.tournament_id == tournament_id,
            Game.home_team_score.isnot(None),
            Game.away_team_score.isnot(None),
        )
        if offline:
            games_q = games_q.filter(Game.is_completed.is_(True))
        scored_games = games_q.all()
        game_ids = [g.id for g in scored_games]
        predictions = (
            UserPrediction.query.filter(UserPrediction.game_id.in_(game_ids)).all()
            if game_ids
            else []
        )

        pred_map = {}
        for pr in predictions:
            pred_map.setdefault(pr.game_id, {})[pr.user_id] = pr

        for game in scored_games:
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

                # Single source of truth — same rule the predictions view shows.
                kind, points, _reason = classify_pick(
                    pred.home_score_prediction,
                    pred.away_score_prediction,
                    final_home,
                    final_away,
                )
                pred.points_earned = points
                attr = COUNTER_ATTR[kind]
                setattr(part, attr, getattr(part, attr) + 1)

        db.session.commit()
        current_app.logger.info(
            "scoring tournament=%s completed (%d games scored)",
            tournament_id,
            len(scored_games),
        )

    except Exception:
        db.session.rollback()
        current_app.logger.exception("scoring failed for tournament=%s", tournament_id)
        raise
