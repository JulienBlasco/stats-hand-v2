"""Parsing du « Déroulé du match » : liste d'évènements bruts."""

from __future__ import annotations

import re
from dataclasses import dataclass

from stats_hand.models import EventKind
from stats_hand.parsing.pdf import Page

_LINE = re.compile(
    r"^(\d{1,2}):(\d{2})(?::(\d{2}))?\s+(\d{1,3})\s*-\s*(\d{1,3})\s+(.+?)\s*$"
)
_PERIOD = re.compile(r"^(PERIODE|PÉRIODE|PROLONGATION)\s+(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class RawEvent:
    time_s: int
    period: int
    kind: EventKind
    raw_action: str
    label: str
    score_rec: int
    score_vis: int


# ordre important : motifs les plus spécifiques d'abord
_KIND_RULES: list[tuple[re.Pattern[str], EventKind]] = [
    (re.compile(r"^But\s*7\s*m\b", re.I), EventKind.GOAL_7M),
    (re.compile(r"^Tir\s*7\s*m\b", re.I), EventKind.SHOT),
    (re.compile(r"^But\b", re.I), EventKind.GOAL),
    (re.compile(r"^Tir\b", re.I), EventKind.SHOT),
    (re.compile(r"^(Arr[eê]t)\b", re.I), EventKind.SAVE),
    (re.compile(r"^2\s*MN\b", re.I), EventKind.SUSPENSION_2MIN),
    (re.compile(r"^Avertissement\b", re.I), EventKind.WARNING),
    (re.compile(r"^Disqualification\b", re.I), EventKind.DISQUALIFICATION),
    (re.compile(r"^Temps\s*mort\b", re.I), EventKind.TIMEOUT),
    (re.compile(r"^Commotion\b", re.I), EventKind.CONCUSSION),
]


def _classify(action: str) -> tuple[EventKind, str]:
    for pattern, kind in _KIND_RULES:
        if m := pattern.match(action):
            return kind, action[m.end():].strip()
    return EventKind.OTHER, action


def parse_events(pages: list[Page]) -> list[RawEvent]:
    events: list[RawEvent] = []
    period = 1
    seen_deroule = False

    for page in pages:
        for line in page.reading_lines():
            stripped = line.strip()
            if "Déroulé" in stripped:
                seen_deroule = True
            if m := _PERIOD.match(stripped):
                period = int(m.group(2))
                continue
            if not seen_deroule:
                continue
            m = _LINE.match(stripped)
            if not m:
                continue
            a, b, c, rec, vis, action = m.groups()
            if c is None:
                time_s = int(a) * 60 + int(b)
            else:
                time_s = int(a) * 3600 + int(b) * 60 + int(c)
            kind, label = _classify(action)
            events.append(
                RawEvent(
                    time_s=time_s,
                    period=period,
                    kind=kind,
                    raw_action=action,
                    label=label,
                    score_rec=int(rec),
                    score_vis=int(vis),
                )
            )
    return events
