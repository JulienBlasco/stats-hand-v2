"""CLI de debug : parse une feuille de match et imprime le résultat en JSON.

Usage : uv run python main.py data/WAGQTMD.pdf
"""

from __future__ import annotations

import dataclasses
import json
import sys
from enum import Enum

from stats_hand.parsing.match import build_match


def _default(o: object):
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return dataclasses.asdict(o)
    if isinstance(o, Enum):
        return o.value
    if hasattr(o, "isoformat"):
        return o.isoformat()
    raise TypeError(type(o))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 1
    match = build_match(argv[1])
    print(json.dumps(match, default=_default, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
