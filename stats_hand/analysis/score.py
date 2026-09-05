"""Analyse de l'évolution du score."""

from __future__ import annotations

from dataclasses import dataclass

from stats_hand.models import GOAL_KINDS, REC, VIS, Match


@dataclass(frozen=True)
class ScorePoint:
    time_s: int
    rec: int
    vis: int

    @property
    def diff(self) -> int:
        return self.rec - self.vis


def score_series(match: Match) -> list[ScorePoint]:
    """Série en escalier : (0-0) au coup d'envoi, un point par but, clôture à la fin."""
    pts = [ScorePoint(0, 0, 0)]
    for e in match.events:
        if e.kind in GOAL_KINDS:
            pts.append(ScorePoint(e.time_s, e.score_rec, e.score_vis))
    last = pts[-1]
    end = match.duration_s
    if last.time_s < end:
        pts.append(ScorePoint(end, last.rec, last.vis))
    return pts


@dataclass(frozen=True)
class ScoreStats:
    max_lead_rec: int
    max_lead_rec_time: int
    max_lead_vis: int
    max_lead_vis_time: int
    n_draws: int  # nombre de fois où le score revient à égalité (hors 0-0)
    n_lead_changes: int
    last_draw_time: int | None
    last_lead_change_time: int | None


def score_stats(match: Match) -> ScoreStats:
    pts = score_series(match)
    max_r = max_v = 0
    t_r = t_v = 0
    draws = 0
    lead_changes = 0
    last_draw: int | None = None
    last_change: int | None = None
    prev_sign = 0

    for p in pts[1:]:
        d = p.diff
        if d > max_r:
            max_r, t_r = d, p.time_s
        if -d > max_v:
            max_v, t_v = -d, p.time_s

        sign = (d > 0) - (d < 0)
        if sign == 0:
            draws += 1
            last_draw = p.time_s
        if sign != 0 and prev_sign != 0 and sign != prev_sign:
            lead_changes += 1
            last_change = p.time_s
        if sign != 0:
            prev_sign = sign

    return ScoreStats(
        max_lead_rec=max_r,
        max_lead_rec_time=t_r,
        max_lead_vis=max_v,
        max_lead_vis_time=t_v,
        n_draws=draws,
        n_lead_changes=lead_changes,
        last_draw_time=last_draw,
        last_lead_change_time=last_change,
    )
