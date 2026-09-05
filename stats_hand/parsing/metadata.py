"""Parsing de l'en-tête : équipes, date, compétition, scores."""

from __future__ import annotations

import re
from datetime import datetime

from stats_hand.models import MatchMeta
from stats_hand.parsing.pdf import Page

_CODE = re.compile(r"Code Renc\s+(\S+)")
_COMPET = re.compile(r"Compétition\s+(.+?)\s+Groupe\s+\S+")
_DATE = re.compile(
    r"Date\s+\w+\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})\s+Journée\s+(\S+)\s+Salle\s+(.+)"
)
# "EQUIPE RECEVANTE / EQUIPE VISITEUSE  <but_rec> <but_vis>"
_MATCHUP = re.compile(r"^(?!Compétition|Organisateur)(.+?)\s+/\s+(.+?)\s+(\d{1,3})\s+(\d{1,3})\s*$")


def _dedupe(s: str) -> str:
    """« A B C saison A B C » → « A B C saison » (le champ FDME répète le libellé)."""
    toks = s.split()
    n = len(toks)
    for k in range(n // 2, 0, -1):
        if toks[:k] == toks[n - k :]:
            return " ".join(toks[: n - k])
    return s


def _first(pattern: re.Pattern[str], lines: list[str]) -> re.Match[str] | None:
    for line in lines:
        m = pattern.search(line)
        if m:
            return m
    return None


def _parse_score_detail(
    pages: list[Page], score_final: tuple[int, int] | None
) -> tuple[int, int] | None:
    """Bloc « Détail score » : une ligne de 4+ entiers dont le dernier couple est
    le score final ; le premier couple est le score à la mi-temps (REC, VIS).

    Les libellés (« Période 1 », « REC VIS ») sont parfois en texte vertical non
    extractible : on se repère donc uniquement sur la ligne de nombres.
    """
    for page in pages:
        if page.index != 0 and "erocs" not in page.text and "Détail" not in page.text:
            continue
        for row in page.rows():
            nums = [int(w.text) for w in row if w.text.isdigit() and len(w.text) <= 3]
            if len(nums) < 4:
                continue
            if score_final and tuple(nums[-2:]) != score_final:
                continue
            return nums[0], nums[1]
    return None


def parse_metadata(pages: list[Page]) -> MatchMeta:
    lines = pages[0].lines

    code = m.group(1) if (m := _first(_CODE, lines)) else ""
    competition = _dedupe(m.group(1).strip()) if (m := _first(_COMPET, lines)) else ""

    phase = ""
    for line in lines:
        if line.strip() in {"PHASE REGULIERE", "PHASE REGULIÈRE"} or line.strip().startswith("PHASE "):
            phase = line.strip()
            break

    date = None
    journee = salle = ""
    if m := _first(_DATE, lines):
        date = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%d/%m/%Y %H:%M")
        journee = m.group(3)
        salle = m.group(4).strip()

    rec_name = vis_name = ""
    score_line: tuple[int, int] | None = None
    if m := _first(_MATCHUP, lines):
        rec_name, vis_name = m.group(1).strip(), m.group(2).strip()
        score_line = (int(m.group(3)), int(m.group(4)))

    score_final = score_line or (0, 0)
    mitemps = _parse_score_detail(pages, score_line)

    return MatchMeta(
        code=code,
        competition=competition,
        phase=phase,
        date=date,
        journee=journee,
        salle=salle,
        rec_name=rec_name,
        vis_name=vis_name,
        score_final=score_final,
        score_mitemps=mitemps,
    )
