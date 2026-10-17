"""Modèles de données partagés pour une feuille de match (FDME handball)."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

REC = "REC"
VIS = "VIS"


class EventKind(str, Enum):
    GOAL = "GOAL"
    GOAL_7M = "GOAL_7M"
    SHOT = "SHOT"
    SAVE = "SAVE"
    SUSPENSION_2MIN = "SUSPENSION_2MIN"
    WARNING = "WARNING"
    DISQUALIFICATION = "DISQUALIFICATION"
    TIMEOUT = "TIMEOUT"
    CONCUSSION = "CONCUSSION"
    OTHER = "OTHER"


GOAL_KINDS = {EventKind.GOAL, EventKind.GOAL_7M}


def normalize(text: str) -> str:
    """Majuscules, sans accents, espaces normalisés — pour comparer des noms."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.upper().split())


@dataclass(frozen=True)
class Player:
    numero: int | None
    nom: str
    prenom: str
    licence: str = ""
    type_lic: str = ""
    # Colonnes chiffrées de la FDME (None si absentes).
    fdme_buts: int | None = None
    fdme_7m: int | None = None
    fdme_tirs: int | None = None
    fdme_arrets: int | None = None
    fdme_avert: int | None = None
    fdme_2min: int | None = None
    fdme_dis: int | None = None

    @property
    def full_name(self) -> str:
        return f"{self.nom} {self.prenom}".strip()

    @property
    def label(self) -> str:
        n = f"n°{self.numero} " if self.numero is not None else ""
        return f"{n}{self.full_name}".strip()


@dataclass(frozen=True)
class Official:
    role: str
    nom: str
    prenom: str
    licence: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.nom} {self.prenom}".strip()


@dataclass(frozen=True)
class Roster:
    team: str  # REC | VIS
    name: str
    players: list[Player] = field(default_factory=list)
    officials: list[Official] = field(default_factory=list)


@dataclass(frozen=True)
class MatchMeta:
    code: str
    competition: str
    phase: str
    date: datetime | None
    journee: str
    salle: str
    rec_name: str
    vis_name: str
    score_final: tuple[int, int]  # (rec, vis)
    score_mitemps: tuple[int, int] | None


@dataclass(frozen=True)
class Event:
    time_s: int
    period: int
    kind: EventKind
    raw_action: str
    label: str  # texte nominatif brut (nom du joueur / officiel, "Recevant"...)
    team: str | None  # REC | VIS | None
    player: Player | None
    score_rec: int
    score_vis: int

    @property
    def mmss(self) -> str:
        return f"{self.time_s // 60:02d}:{self.time_s % 60:02d}"


@dataclass(frozen=True)
class Match:
    meta: MatchMeta
    rec: Roster
    vis: Roster
    events: list[Event]

    def team_name(self, team: str | None) -> str:
        if team == REC:
            return self.rec.name
        if team == VIS:
            return self.vis.name
        return "?"

    def score_for_against(self, team: str) -> tuple[int, int]:
        """Score final (buts pour, buts contre) du côté `team` (REC | VIS)."""
        rec, vis = self.meta.score_final
        return (rec, vis) if team == REC else (vis, rec)

    @property
    def duration_s(self) -> int:
        base = 60 * 60
        return max([base] + [e.time_s for e in self.events])
