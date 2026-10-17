"""Analyse multi-matchs du point de vue d'une « équipe suivie ».

Recevant/visiteur n'a pas de sens d'un match à l'autre : chaque fonction prend
le nom d'une équipe (`Roster.name`), ne garde que ses matchs et traduit REC/VIS
en buts « pour » (l'équipe) et « contre » (ses adversaires).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from stats_hand.analysis.box_score import box_score, has_shot_tracking, season_totals
from stats_hand.analysis.periods import (
    Run,
    goals_per_minute,
    rolling_windows,
    scoring_runs,
    smooth,
)
from stats_hand.models import GOAL_KINDS, REC, VIS, Match


def side_of(match: Match, team: str) -> str | None:
    """REC ou VIS selon le côté de l'équipe dans ce match, None si elle n'y joue pas."""
    if match.rec.name == team:
        return REC
    if match.vis.name == team:
        return VIS
    return None


def opponent(match: Match, team: str) -> str:
    return match.vis.name if side_of(match, team) == REC else match.rec.name


def teams_by_count(matches: list[Match]) -> list[str]:
    """Équipes par nombre de feuilles décroissant (puis ordre alphabétique)."""
    count = Counter(name for m in matches for name in (m.rec.name, m.vis.name))
    return sorted(count, key=lambda name: (-count[name], name))


def team_matches(matches: list[Match], team: str) -> list[Match]:
    """Matchs de l'équipe, triés par date."""
    played = [m for m in matches if side_of(m, team)]
    return sorted(played, key=lambda m: m.meta.date or datetime.min)


def _for_against(match: Match, team: str, rec: int, vis: int) -> tuple[int, int]:
    return (rec, vis) if side_of(match, team) == REC else (vis, rec)


@dataclass(frozen=True)
class Record:
    matchs: int
    victoires: int
    nuls: int
    defaites: int
    buts_pour: int
    buts_contre: int


def team_record(matches: list[Match], team: str) -> Record:
    v = n = d = bp = bc = 0
    played = team_matches(matches, team)
    for m in played:
        pour, contre = _for_against(m, team, *m.meta.score_final)
        bp, bc = bp + pour, bc + contre
        v, n, d = v + (pour > contre), n + (pour == contre), d + (pour < contre)
    return Record(len(played), v, n, d, bp, bc)


@dataclass(frozen=True)
class RatePoint:
    minute: int
    rate_for: float  # buts/minute lissés, en moyenne par match
    rate_against: float


def mean_rate_series(matches: list[Match], team: str, window_min: int = 5) -> list[RatePoint]:
    """Rythme de marque moyen par minute (moyenne sur les matchs, puis lissage centré)."""
    per_match = []
    for m in team_matches(matches, team):
        rec, vis = goals_per_minute(m)
        per_match.append((rec, vis) if side_of(m, team) == REC else (vis, rec))
    if not per_match:
        return []
    n = max(len(f) for f, _ in per_match)
    mean_for: list[float] = []
    mean_against: list[float] = []
    for t in range(n):
        present = [(f[t], a[t]) for f, a in per_match if t < len(f)]
        mean_for.append(sum(f for f, _ in present) / len(present))
        mean_against.append(sum(a for _, a in present) / len(present))
    return [
        RatePoint(t, f, a)
        for t, (f, a) in enumerate(zip(smooth(mean_for, window_min), smooth(mean_against, window_min)))
    ]


@dataclass(frozen=True)
class TeamWindow:
    start_s: int
    end_s: int
    pour: int
    contre: int
    matchs: int  # nombre de matchs contribuant à la fenêtre

    @property
    def diff(self) -> int:
        return self.pour - self.contre


def slice_totals(matches: list[Match], team: str, size_s: int = 600) -> list[TeamWindow]:
    """Buts pour/contre cumulés par tranche fixe (0-10, 10-20…) sur les matchs de l'équipe.

    Comme pour `rolling_windows`, un but au buzzer compte dans la dernière tranche.
    """
    played = team_matches(matches, team)
    if not played:
        return []
    end = max(m.duration_s for m in played)
    starts = range(0, end, size_s)
    pour = dict.fromkeys(starts, 0)
    contre = dict.fromkeys(starts, 0)
    n_matchs = dict.fromkeys(starts, 0)
    for m in played:
        side = side_of(m, team)
        for s in starts:
            if s < m.duration_s:
                n_matchs[s] += 1
        for e in m.events:
            if e.kind in GOAL_KINDS and e.team in (REC, VIS):
                s = min(e.time_s, m.duration_s - 1) // size_s * size_s
                (pour if e.team == side else contre)[s] += 1
    return [TeamWindow(s, min(s + size_s, end), pour[s], contre[s], n_matchs[s]) for s in starts]


def cumulative_windows(matches: list[Match], team: str) -> tuple[TeamWindow, TeamWindow] | None:
    """Meilleure et pire fenêtre glissante de 10 min, buts additionnés sur tous les matchs."""
    acc: dict[tuple[int, int], list[int]] = {}
    for m in team_matches(matches, team):
        for w in rolling_windows(m):
            pour, contre = _for_against(m, team, w.goals_rec, w.goals_vis)
            cell = acc.setdefault((w.start_s, w.end_s), [0, 0, 0])
            cell[0] += pour
            cell[1] += contre
            cell[2] += 1
    if not acc:
        return None
    wins = [TeamWindow(s, e, p, c, n) for (s, e), (p, c, n) in sorted(acc.items())]
    return max(wins, key=lambda w: w.diff), min(wins, key=lambda w: w.diff)


@dataclass(frozen=True)
class TeamRun:
    match: Match
    run: Run  # score_from / score_to restent au format (recevant, visiteur) de la feuille


def top_runs(matches: list[Match], team: str, top: int = 5) -> dict[str, list[TeamRun]]:
    """Plus longues séries de buts consécutifs « pour » et « contre », tous matchs confondus."""
    out: dict[str, list[TeamRun]] = {"pour": [], "contre": []}
    for m in team_matches(matches, team):
        side = side_of(m, team)
        for t, runs in scoring_runs(m, top=10**6).items():
            out["pour" if t == side else "contre"].extend(TeamRun(m, r) for r in runs)
    for key, runs in out.items():
        out[key] = sorted(runs, key=lambda tr: -tr.run.length)[:top]
    return out


def team_shooting(matches: list[Match], team: str) -> tuple[int, int, int] | None:
    """(buts, tirs, matchs suivis) de l'équipe sur les matchs dont le déroulé détaille les tirs."""
    lines = [s for s in season_totals(team_matches(matches, team)) if s.equipe == team]
    tirs = sum(s.tirs for s in lines)
    if not tirs:
        return None
    suivis = max(s.matchs_suivis for s in lines)
    return sum(s.buts_suivis for s in lines), tirs, suivis


def team_save_rate(matches: list[Match], team: str) -> tuple[int, int, int] | None:
    """(arrêts, tirs cadrés subis, matchs suivis) des gardiens de l'équipe.

    Tirs cadrés subis = arrêts + buts encaissés, sur les matchs dont le déroulé détaille les tirs.
    """
    arrets = subis = suivis = 0
    for m in team_matches(matches, team):
        if not has_shot_tracking(m):
            continue
        side = side_of(m, team)
        saves = sum(pl.arrets for pl in box_score(m)[0 if side == REC else 1])
        contre = _for_against(m, team, *m.meta.score_final)[1]
        arrets += saves
        subis += saves + contre
        suivis += 1
    return (arrets, subis, suivis) if arrets else None
