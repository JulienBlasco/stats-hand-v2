"""Reconstruction d'un box score par joueur à partir du déroulé."""

from __future__ import annotations

from dataclasses import dataclass

from stats_hand.models import REC, VIS, EventKind, Match, Player, Roster


@dataclass
class PlayerLine:
    numero: int | None
    nom: str
    buts: int = 0
    buts_7m: int = 0
    suspensions_2min: int = 0
    avertissements: int = 0
    disqualifications: int = 0
    # valeur brute lue dans la colonne « Buts » de la FDME (cross-check)
    fdme_buts: int | None = None

    @property
    def divergence(self) -> bool:
        return self.fdme_buts is not None and self.fdme_buts != self.buts


def _team_box(match: Match, roster: Roster, team: str) -> list[PlayerLine]:
    lines: dict[str, PlayerLine] = {}
    order: list[str] = []
    for p in roster.players:
        key = p.full_name
        lines[key] = PlayerLine(p.numero, key, fdme_buts=p.fdme_buts)
        order.append(key)

    def line_for(player: Player | None) -> PlayerLine | None:
        if player is None:
            return None
        key = player.full_name
        if key not in lines:
            lines[key] = PlayerLine(player.numero, key)
            order.append(key)
        return lines[key]

    for e in match.events:
        if e.team != team:
            continue
        pl = line_for(e.player)
        if pl is None:
            continue
        if e.kind is EventKind.GOAL:
            pl.buts += 1
        elif e.kind is EventKind.GOAL_7M:
            pl.buts += 1
            pl.buts_7m += 1
        elif e.kind is EventKind.SUSPENSION_2MIN:
            pl.suspensions_2min += 1
        elif e.kind is EventKind.WARNING:
            pl.avertissements += 1
        elif e.kind is EventKind.DISQUALIFICATION:
            pl.disqualifications += 1

    return [lines[k] for k in order]


def box_score(match: Match) -> tuple[list[PlayerLine], list[PlayerLine]]:
    return _team_box(match, match.rec, REC), _team_box(match, match.vis, VIS)
