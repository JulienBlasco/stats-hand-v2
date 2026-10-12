"""Reconstruction d'un box score par joueur à partir du déroulé, et cumul multi-matchs."""

from __future__ import annotations

from dataclasses import dataclass

from stats_hand.models import REC, VIS, Event, EventKind, Match, Player, Roster, normalize


@dataclass
class PlayerLine:
    numero: int | None
    nom: str
    licence: str = ""
    buts: int = 0
    buts_7m: int = 0
    # « Tir » du déroulé = tir non converti (les buts n'y figurent pas)
    tirs_manques: int = 0
    arrets: int = 0
    suspensions_2min: int = 0
    avertissements: int = 0
    disqualifications: int = 0
    # valeur brute lue dans la colonne « Buts » de la FDME (cross-check)
    fdme_buts: int | None = None

    @property
    def tirs(self) -> int:
        return self.buts + self.tirs_manques

    @property
    def reussite(self) -> float | None:
        """Taux de réussite au tir (0-1), None sans tir."""
        return self.buts / self.tirs if self.tirs else None

    @property
    def divergence(self) -> bool:
        return self.fdme_buts is not None and self.fdme_buts != self.buts


def has_shot_tracking(match: Match) -> bool:
    """Le déroulé détaille-t-il les tirs et arrêts ? (pas le cas de toutes les FDME)"""
    return any(e.kind in (EventKind.SHOT, EventKind.SAVE) for e in match.events)


def _team_box(match: Match, roster: Roster, team: str) -> list[PlayerLine]:
    lines: dict[str, PlayerLine] = {}
    order: list[str] = []
    for p in roster.players:
        key = p.full_name
        lines[key] = PlayerLine(p.numero, key, licence=p.licence, fdme_buts=p.fdme_buts)
        order.append(key)

    def line_for(player: Player | None) -> PlayerLine | None:
        if player is None:
            return None
        key = player.full_name
        if key not in lines:
            lines[key] = PlayerLine(player.numero, key, licence=player.licence)
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
        elif e.kind is EventKind.SHOT:
            pl.tirs_manques += 1
        elif e.kind is EventKind.SAVE:
            pl.arrets += 1
        elif e.kind is EventKind.SUSPENSION_2MIN:
            pl.suspensions_2min += 1
        elif e.kind is EventKind.WARNING:
            pl.avertissements += 1
        elif e.kind is EventKind.DISQUALIFICATION:
            pl.disqualifications += 1

    return [lines[k] for k in order]


def box_score(match: Match) -> tuple[list[PlayerLine], list[PlayerLine]]:
    return _team_box(match, match.rec, REC), _team_box(match, match.vis, VIS)


def player_events(match: Match, team: str, full_name: str) -> list[Event]:
    """Évènements d'un joueur, dans l'ordre du déroulé."""
    return [
        e for e in match.events
        if e.team == team and e.player is not None and e.player.full_name == full_name
    ]


@dataclass
class SeasonLine:
    licence: str
    nom: str
    equipe: str
    matchs: int = 0
    buts: int = 0
    buts_7m: int = 0
    # tirs / arrêts ne sont comptés que sur les matchs dont le déroulé les détaille
    matchs_suivis: int = 0
    buts_suivis: int = 0
    tirs: int = 0
    arrets: int = 0
    suspensions_2min: int = 0
    avertissements: int = 0
    disqualifications: int = 0

    @property
    def buts_par_match(self) -> float:
        return self.buts / self.matchs if self.matchs else 0.0

    @property
    def reussite(self) -> float | None:
        return self.buts_suivis / self.tirs if self.tirs else None


def season_totals(matches: list[Match]) -> list[SeasonLine]:
    """Cumul par joueur sur plusieurs feuilles (clé : licence, sinon équipe + nom).

    Le numéro de maillot est ignoré : il peut changer d'un match à l'autre.
    """
    acc: dict[object, SeasonLine] = {}
    for match in matches:
        tracked = has_shot_tracking(match)
        for roster, lines in zip((match.rec, match.vis), box_score(match)):
            for pl in lines:
                key = pl.licence or (roster.name, normalize(pl.nom))
                sl = acc.get(key)
                if sl is None:
                    sl = acc[key] = SeasonLine(pl.licence, pl.nom, roster.name)
                sl.equipe = roster.name
                sl.matchs += 1
                sl.buts += pl.buts
                sl.buts_7m += pl.buts_7m
                if tracked:
                    sl.matchs_suivis += 1
                    sl.buts_suivis += pl.buts
                    sl.tirs += pl.tirs
                    sl.arrets += pl.arrets
                sl.suspensions_2min += pl.suspensions_2min
                sl.avertissements += pl.avertissements
                sl.disqualifications += pl.disqualifications
    return sorted(acc.values(), key=lambda s: (-s.buts, s.nom))
