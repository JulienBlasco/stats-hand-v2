"""Extraction bas niveau du PDF FDME via pdfplumber."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pdfplumber


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class Page:
    index: int
    text: str
    lines: list[str]
    words: list[Word]
    width: float = 595.28
    height: float = 841.89

    def rows(self, words: list[Word] | None = None, tol: float = 3.0) -> list[list[Word]]:
        """Regroupe les mots par ligne (même `top` à `tol` près), triés en x."""
        src = self.words if words is None else words
        out: list[list[Word]] = []
        for w in sorted(src, key=lambda w: (w.top, w.x0)):
            if out and abs(out[-1][0].top - w.top) <= tol:
                out[-1].append(w)
            else:
                out.append([w])
        for row in out:
            row.sort(key=lambda w: w.x0)
        return out

    def reading_lines(self, mid: float | None = None) -> list[str]:
        """Lignes en ordre de lecture, en gérant une éventuelle mise en 2 colonnes
        (le « Déroulé du match » de la FDME) : colonne gauche entière puis droite."""
        mid = self.width / 2 if mid is None else mid
        left = [w for w in self.words if w.x0 < mid]
        right = [w for w in self.words if w.x0 >= mid]
        lines: list[str] = []
        for side in (left, right):
            for row in self.rows(side):
                lines.append(" ".join(w.text for w in row))
        return lines


def load_pages(source: str | Path | bytes) -> list[Page]:
    opener = BytesIO(source) if isinstance(source, bytes) else source
    pages: list[Page] = []
    with pdfplumber.open(opener) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            words = [
                Word(w["text"], w["x0"], w["x1"], w["top"])
                for w in page.extract_words()
            ]
            pages.append(
                Page(i, text, text.splitlines(), words, page.width, page.height)
            )
    return pages
