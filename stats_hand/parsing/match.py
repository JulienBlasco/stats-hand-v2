"""Assemblage d'un objet `Match` complet à partir d'un PDF FDME."""

from __future__ import annotations

import logging
from pathlib import Path

from stats_hand.models import (
    GOAL_KINDS,
    REC,
    VIS,
    Event,
    EventKind,
    Match,
    Player,
    Roster,
    normalize,
)
from stats_hand.parsing.metadata import parse_metadata
from stats_hand.parsing.pdf import load_pages
from stats_hand.parsing.roster import parse_rosters
from stats_hand.parsing.timeline import RawEvent, parse_events

logger = logging.getLogger(__name__)


class _NameIndex:
    """Résout un libellé 'NOM Prénom' vers (team, Player|None)."""

    def __init__(self, rec: Roster, vis: Roster) -> None:
        self.full: dict[str, tuple[str, Player | None]] = {}
        self.by_lastname: dict[str, list[tuple[str, Player | None]]] = {}
        for roster in (rec, vis):
            for p in roster.players:
                self._add(roster.team, p.full_name, p)
            for o in roster.officials:
                self._add(roster.team, o.full_name, None)

    def _add(self, team: str, name: str, player: Player | None) -> None:
        key = normalize(name)
        if not key:
            return
        self.full.setdefault(key, (team, player))
        self.by_lastname.setdefault(key.split(" ")[0], []).append((team, player))

    def resolve(self, label: str) -> tuple[str | None, Player | None]:
        key = normalize(label)
        if not key:
            return None, None
        if key in self.full:
            return self.full[key]
        # match par préfixe (nom de famille + début du prénom)
        for full_key, val in self.full.items():
            if key.startswith(full_key) or full_key.startswith(key):
                return val
        candidates = self.by_lastname.get(key.split(" ")[0], [])
        if len(candidates) == 1:
            return candidates[0]
        return None, None


def _resolve_team(
    ev: RawEvent, prev: tuple[int, int], index: _NameIndex
) -> tuple[str | None, Player | None]:
    d_rec = ev.score_rec - prev[0]
    d_vis = ev.score_vis - prev[1]

    if ev.kind in GOAL_KINDS:
        name_team, player = index.resolve(ev.label)
        if d_rec > 0 and d_vis <= 0:
            return REC, player
        if d_vis > 0 and d_rec <= 0:
            return VIS, player
        return name_team, player  # score ambigu : on se rabat sur le nom

    if ev.kind == EventKind.TIMEOUT:
        low = ev.label.lower()
        if "recevant" in low:
            return REC, None
        if "visiteur" in low:
            return VIS, None
        return None, None

    return index.resolve(ev.label)


def build_match(source: str | Path | bytes) -> Match:
    pages = load_pages(source)
    meta = parse_metadata(pages)
    rec, vis = parse_rosters(pages, meta.rec_name, meta.vis_name)
    raw_events = parse_events(pages)

    index = _NameIndex(rec, vis)
    events: list[Event] = []
    prev = (0, 0)
    unresolved = 0
    for ev in raw_events:
        team, player = _resolve_team(ev, prev, index)
        if team is None and ev.kind is not EventKind.OTHER:
            unresolved += 1
            logger.debug("évènement non résolu à %ds: %r", ev.time_s, ev.raw_action)
        events.append(
            Event(
                time_s=ev.time_s,
                period=ev.period,
                kind=ev.kind,
                raw_action=ev.raw_action,
                label=ev.label,
                team=team,
                player=player,
                score_rec=ev.score_rec,
                score_vis=ev.score_vis,
            )
        )
        prev = (ev.score_rec, ev.score_vis)

    if unresolved:
        logger.info("%s: %d/%d évènements sans équipe", meta.code, unresolved, len(events))

    return Match(meta=meta, rec=rec, vis=vis, events=events)
