"""Analyse des périodes clés : momentum lissé, fenêtres de 10 min, séries de buts.

La courbe de momentum reprend la formule de stats-hand v1 (R) : nombre de buts
par minute pour chaque équipe, lissé par une **moyenne mobile centrée sur 5
minutes** (minutes t-2 à t+2, moyenne sur les minutes réellement présentes).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from stats_hand.models import GOAL_KINDS, REC, VIS, Match


def goals_per_minute(match: Match) -> tuple[list[int], list[int]]:
    """Buts marqués par minute entière du match, pour (REC, VIS)."""
    n = max(1, math.ceil(match.duration_s / 60))
    rec = [0] * n
    vis = [0] * n
    for e in match.events:
        if e.kind in GOAL_KINDS and e.team in (REC, VIS):
            idx = min(e.time_s // 60, n - 1)
            (rec if e.team == REC else vis)[idx] += 1
    return rec, vis


@dataclass(frozen=True)
class MomentumPoint:
    minute: int
    rate_rec: float  # buts/minute lissés
    rate_vis: float

    @property
    def diff(self) -> float:
        return self.rate_rec - self.rate_vis


def momentum_series(match: Match, window_min: int = 5) -> list[MomentumPoint]:
    """Rythme de marque lissé (moyenne mobile centrée), une valeur par minute."""
    rec, vis = goals_per_minute(match)
    n = len(rec)
    hw = window_min // 2
    out: list[MomentumPoint] = []
    for t in range(n):
        lo, hi = max(0, t - hw), min(n, t + hw + 1)
        span = hi - lo
        out.append(MomentumPoint(t, sum(rec[lo:hi]) / span, sum(vis[lo:hi]) / span))
    return out


@dataclass(frozen=True)
class Window:
    start_s: int
    end_s: int
    goals_rec: int
    goals_vis: int

    @property
    def diff(self) -> int:
        return self.goals_rec - self.goals_vis


def rolling_windows(match: Match, window_s: int = 600, step_s: int = 60) -> list[Window]:
    """Fenêtres de 10 min glissant minute par minute (fenêtres pleines uniquement)."""
    goals = [e for e in match.events if e.kind in GOAL_KINDS]
    end = match.duration_s
    out: list[Window] = []
    for start in range(0, max(1, end - window_s + step_s), step_s):
        stop = start + window_s
        gr = sum(1 for e in goals if start <= e.time_s < stop and e.team == REC)
        gv = sum(1 for e in goals if start <= e.time_s < stop and e.team == VIS)
        out.append(Window(start, stop, gr, gv))
    return out


@dataclass(frozen=True)
class BestWorst:
    team: str
    best: Window
    worst: Window


def best_worst_window(match: Match, **kw) -> tuple[BestWorst, BestWorst]:
    wins = rolling_windows(match, **kw)
    rec = BestWorst(REC, max(wins, key=lambda w: w.diff), min(wins, key=lambda w: w.diff))
    vis = BestWorst(VIS, min(wins, key=lambda w: w.diff), max(wins, key=lambda w: w.diff))
    return rec, vis


@dataclass(frozen=True)
class Run:
    team: str
    start_s: int
    end_s: int
    length: int
    score_from: tuple[int, int]
    score_to: tuple[int, int]


def scoring_runs(match: Match, top: int = 3) -> dict[str, list[Run]]:
    """Séries de buts consécutifs sans en encaisser, par équipe (top N)."""
    goals = [e for e in match.events if e.kind in GOAL_KINDS and e.team in (REC, VIS)]
    runs: list[Run] = []
    i = 0
    while i < len(goals):
        team = goals[i].team
        j = i
        while j + 1 < len(goals) and goals[j + 1].team == team:
            j += 1
        start_ev, end_ev = goals[i], goals[j]
        before = goals[i - 1] if i > 0 else None
        runs.append(
            Run(
                team=team,
                start_s=start_ev.time_s,
                end_s=end_ev.time_s,
                length=j - i + 1,
                score_from=(before.score_rec, before.score_vis) if before else (0, 0),
                score_to=(end_ev.score_rec, end_ev.score_vis),
            )
        )
        i = j + 1

    out: dict[str, list[Run]] = {}
    for team in (REC, VIS):
        team_runs = sorted(
            (r for r in runs if r.team == team),
            key=lambda r: (r.length, -r.start_s),
            reverse=True,
        )
        out[team] = team_runs[:top]
    return out
