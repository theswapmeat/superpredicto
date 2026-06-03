"""Single source of truth for how one prediction scores against one final result.

Both the scorer (tasks/scoring.py) and the predictions view use `classify_pick`,
so the points awarded and the human-readable reason shown to users can never drift
apart. Pure function — no DB, no Flask — trivially testable.

Rule order mirrors the league rules exactly (first match wins):
  1. a 1-0 / 0-1 prediction that isn't exact          -> invalid (0)
  2. exact scoreline                                   -> perfect (4)
  3. correct result AND one score exact                -> 2
  4. correct result, neither score exact               -> 1
  5. wrong result, but one score exact                 -> 1
  6. both predicted and actual are draws (not exact)   -> 1
  7. everything else                                   -> 0
"""

# kind -> Participant counter attribute (the five denormalised counters)
COUNTER_ATTR = {
    "perfect": "perfect_picks",
    "two": "picks_scoring_two",
    "one": "picks_scoring_one",
    "zero": "picks_scoring_zero",
    "invalid": "invalid_picks",
}


def classify_pick(p_home, p_away, final_home, final_away):
    """Return (kind, points, reason) for a prediction vs a final score.

    kind is one of: perfect | two | one | zero | invalid.
    Assumes both predicted scores are set; the "no prediction" case is handled
    by the caller (it counts as invalid with its own message).
    """
    # 1. 1-0 or 0-1 predicted but not exact -> invalid
    if (p_home, p_away) in [(1, 0), (0, 1)] and (
        p_home != final_home or p_away != final_away
    ):
        return ("invalid", 0, "Invalid — a 1-0/0-1 pick must be exact")

    # 2. Perfect prediction
    if p_home == final_home and p_away == final_away:
        return ("perfect", 4, "Perfect — exact scoreline")

    correct_result = (final_home > final_away and p_home > p_away) or (
        final_away > final_home and p_away > p_home
    )
    one_score_exact = p_home == final_home or p_away == final_away

    # 3. Correct result with one score matching -> 2
    if correct_result and one_score_exact:
        return ("two", 2, "Correct result + one score exact")

    # 4. Correct result, no score match -> 1
    if correct_result:
        return ("one", 1, "Correct result")

    # 5. Wrong result, but one score matches -> 1
    if one_score_exact:
        return ("one", 1, "One score exact")

    # 6. Both predicted and actual were draws (not exact) -> 1
    if final_home == final_away and p_home == p_away:
        return ("one", 1, "Correct result (a draw)")

    # 7. Everything else is just wrong -> 0
    return ("zero", 0, "Wrong result, neither score exact")
