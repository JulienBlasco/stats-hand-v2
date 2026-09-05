"""Parsing des deux effectifs + officiels, à partir des coordonnées des mots."""

from __future__ import annotations

import re

from stats_hand.models import REC, VIS, Official, Player, Roster
from stats_hand.parsing.pdf import Page, Word

_NUM_COLS = {
    "Buts": "fdme_buts",
    "7m": "fdme_7m",
    "Tirs": "fdme_tirs",
    "Arrets": "fdme_arrets",
    "Av.": "fdme_avert",
    "2'": "fdme_2min",
    "Dis": "fdme_dis",
}
_OFFICIAL_PREFIXES = ("Officiel", "Médecin", "Kiné", "Entraineur", "Entraîneur", "Dirigeant")
_LICENCE = re.compile(r"^\d{7,}$")
_UPPER = re.compile(r"^[A-ZÀ-Ÿ][A-ZÀ-Ÿ'\-]*$")
_MIN_X = 60.0  # en-dessous : texte vertical parasite


def _is_header(row: list[Word]) -> bool:
    texts = {w.text for w in row}
    return "N°" in texts and "NOM" in texts and "Buts" in texts


def _split_name(tokens: list[str]) -> tuple[str, str]:
    """Sépare 'NOM (majuscules) Prénom'. Retire un éventuel '(Né.e ...)'."""
    joined = " ".join(tokens)
    joined = re.sub(r"\(.*?\)", "", joined).strip()
    tokens = joined.split()
    nom_parts: list[str] = []
    i = 0
    while i < len(tokens) and _UPPER.match(tokens[i]):
        nom_parts.append(tokens[i])
        i += 1
    if not nom_parts and tokens:  # garde-fou
        nom_parts = [tokens[0]]
        i = 1
    return " ".join(nom_parts), " ".join(tokens[i:])


def _parse_player_row(row: list[Word], num_cols: list[tuple[str, float]]) -> Player | None:
    words = [w for w in row if w.x0 >= _MIN_X]
    if not words:
        return None

    # marqueur capitaine « X » en tête de ligne
    if words[0].text == "X" and words[0].x0 < 90:
        words = words[1:]

    numero: int | None = None
    if words[0].text.isdigit() and words[0].x0 < 112:
        numero = int(words[0].text)
        words = words[1:]

    lic_idx = next((i for i, w in enumerate(words) if _LICENCE.match(w.text)), None)
    if lic_idx is None or lic_idx == 0:
        return None

    nom, prenom = _split_name([w.text for w in words[:lic_idx]])
    if not nom:
        return None

    licence = words[lic_idx].text
    rest = words[lic_idx + 1 :]
    type_lic = rest[0].text if rest and rest[0].text.isalpha() else ""

    values: dict[str, int] = {}
    for w in rest:
        if not w.text.isdigit():
            continue
        col = min(num_cols, key=lambda c: abs(c[1] - w.x0))
        if abs(col[1] - w.x0) <= 12:
            values[_NUM_COLS[col[0]]] = int(w.text)

    return Player(
        numero=numero,
        nom=nom,
        prenom=prenom,
        licence=licence,
        type_lic=type_lic,
        **values,
    )


def _parse_official_row(row: list[Word]) -> Official | None:
    words = [w for w in row if w.x0 >= _MIN_X]
    tokens = [w.text for w in words]
    if not tokens:
        return None
    # rôle = mots initiaux tant qu'on n'a pas atteint un NOM en majuscules (≥2 lettres)
    i = 0
    while i < len(tokens) and not (_UPPER.match(tokens[i]) and len(tokens[i]) >= 2):
        i += 1
    role = " ".join(tokens[:i]).strip()
    name_tokens = tokens[i:]
    # retire licence + type en fin
    while name_tokens and (_LICENCE.match(name_tokens[-1]) or (len(name_tokens[-1]) <= 3 and name_tokens[-1].isalpha() and name_tokens[-1].isupper())):
        name_tokens.pop()
    if not name_tokens:
        return None
    nom, prenom = _split_name(name_tokens)
    return Official(role=role or "Officiel", nom=nom, prenom=prenom)


def _parse_block(rows: list[list[Word]], start: int, team: str, name: str) -> tuple[Roster, int]:
    header = rows[start]
    num_cols = [(w.text, w.x0) for w in header if w.text in _NUM_COLS]

    players: list[Player] = []
    officials: list[Official] = []
    i = start + 1
    while i < len(rows):
        row = [w for w in rows[i] if w.x0 >= _MIN_X]
        if not row:
            i += 1
            continue
        if _is_header(rows[i]):
            break
        first = row[0].text
        joined = " ".join(w.text for w in row)
        if first.startswith(_OFFICIAL_PREFIXES):
            if off := _parse_official_row(rows[i]):
                officials.append(off)
        elif re.match(r"^(REC\s+VIS|Période|Détail|Prolongation)", joined) or "erocs" in joined:
            break
        else:
            if player := _parse_player_row(rows[i], num_cols):
                players.append(player)
        i += 1

    return Roster(team=team, name=name, players=players, officials=officials), i


def parse_rosters(pages: list[Page], rec_name: str, vis_name: str) -> tuple[Roster, Roster]:
    rows = pages[0].rows()
    headers = [i for i, r in enumerate(rows) if _is_header(r)]
    if len(headers) < 2:
        raise ValueError("Effectifs introuvables dans la feuille de match")

    rec, _ = _parse_block(rows, headers[0], REC, rec_name)
    vis, _ = _parse_block(rows, headers[1], VIS, vis_name)
    return rec, vis
