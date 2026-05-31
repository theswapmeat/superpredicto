"""football-data.org live-score integration for the FIFA World Cup (competition WC).

One reusable upsert (`sync_fixtures`) is the source of truth for fixtures:
- the re-seed script calls it to (re)create all games with their external_id;
- the cron sync endpoint calls it to update scores + completion as matches play.

Games map to live fixtures by `external_id` (the football-data match id), so team
naming differences (e.g. "Czechia" vs "Czech Republic") never matter at runtime.
"""
from datetime import datetime

import pytz
import requests

from . import db
from .models import Game

API_BASE = "https://api.football-data.org/v4"
WC_MATCHES_URL = f"{API_BASE}/competitions/WC/matches"
_DUBAI = pytz.timezone("Asia/Dubai")


def fetch_wc_matches(api_key, timeout=20):
    """Return the list of World Cup match objects (raises RuntimeError on API error)."""
    resp = requests.get(
        WC_MATCHES_URL, headers={"X-Auth-Token": api_key or ""}, timeout=timeout
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"football-data.org error {resp.status_code}: {resp.text[:300]}"
        )
    return resp.json().get("matches", [])


def _dubai_parts(utc_iso):
    """'2026-06-11T19:00:00Z' -> (date, time) in Asia/Dubai wall-clock.

    Matches the app's convention: stored date/time are Dubai-local, and
    Game.kickoff_utc() reconstructs the true UTC instant from them.
    """
    dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00")).astimezone(_DUBAI)
    return dt.date(), dt.time().replace(microsecond=0)


def _stage(api_stage):
    return "group" if (api_stage or "").upper() == "GROUP_STAGE" else "knockout"


def _team(side):
    return ((side or {}).get("name") or "").strip() or "TBD"


def _code(side):
    """Official 3-letter code (tla), e.g. 'RSA'. None for unresolved TBD slots."""
    return ((side or {}).get("tla") or "").strip() or None


def _crest(side):
    return ((side or {}).get("crest") or "").strip() or None


def sync_fixtures(api_key, tournament_id, *, create_missing=True, write_scores=True):
    """Upsert one tournament's games from football-data.org. Returns a summary dict.

    - Game <-> fixture matched by external_id.
    - game_number (re)assigned 1..N by true chronological kickoff.
    - Teams / kickoff / stage kept in step with the API (so knockout teams fill in
      automatically as the bracket resolves; never blanked back to "TBD").
    - Scores + is_completed written only when write_scores and the game is NOT
      manual_override (an admin's hand-correction always wins).
    """
    matches = [m for m in fetch_wc_matches(api_key) if m.get("id")]
    matches.sort(key=lambda m: m.get("utcDate") or "")

    by_ext = {
        g.external_id: g
        for g in Game.query.filter_by(tournament_id=tournament_id).all()
        if g.external_id is not None
    }

    created = scores_updated = teams_updated = skipped_override = 0
    for i, m in enumerate(matches, start=1):
        ext = m["id"]
        d, t = _dubai_parts(m["utcDate"])
        home_obj, away_obj = m.get("homeTeam"), m.get("awayTeam")
        home, away = _team(home_obj), _team(away_obj)
        home_code, away_code = _code(home_obj), _code(away_obj)
        home_crest, away_crest = _crest(home_obj), _crest(away_obj)
        stage = _stage(m.get("stage"))
        group = (m.get("group") or "").strip() or None  # "GROUP_A".. or None (knockout)
        ft = (m.get("score") or {}).get("fullTime") or {}
        h_score, a_score = ft.get("home"), ft.get("away")
        status = m.get("status")
        finished = status == "FINISHED"

        g = by_ext.get(ext)
        if g is None:
            if not create_missing:
                continue
            g = Game(
                external_id=ext,
                tournament_id=tournament_id,
                date_of_game=d,
                time_of_game=t,
                game_number=i,
                stage=stage,
                status=status,
                group_name=group,
                home_team=home,
                away_team=away,
                home_team_code=home_code,
                away_team_code=away_code,
                home_team_crest=home_crest,
                away_team_crest=away_crest,
                is_completed=False,
                manual_override=False,
            )
            db.session.add(g)
            by_ext[ext] = g
            created += 1
        else:
            g.date_of_game, g.time_of_game = d, t
            g.game_number, g.stage, g.group_name = i, stage, group
            g.status = status
            # fill in real team names (knockout slots resolving) — never blank them
            if home != "TBD" and g.home_team != home:
                g.home_team = home
                teams_updated += 1
            if away != "TBD" and g.away_team != away:
                g.away_team = away
                teams_updated += 1
            # codes/crests: set whenever the API has them; never blank to None
            if home_code:
                g.home_team_code = home_code
            if away_code:
                g.away_team_code = away_code
            if home_crest:
                g.home_team_crest = home_crest
            if away_crest:
                g.away_team_crest = away_crest

        if write_scores and not g.manual_override:
            if (g.home_team_score, g.away_team_score, g.is_completed) != (
                h_score,
                a_score,
                finished,
            ):
                g.home_team_score, g.away_team_score = h_score, a_score
                g.is_completed = finished
                scores_updated += 1
        elif g.manual_override:
            skipped_override += 1

    db.session.commit()
    return {
        "fixtures": len(matches),
        "created": created,
        "scores_updated": scores_updated,
        "teams_updated": teams_updated,
        "skipped_manual_override": skipped_override,
    }
