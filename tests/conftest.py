from pathlib import Path

import pytest

from stats_hand.parsing.match import build_match

DATA = Path(__file__).parent.parent / "data"
PDFS = sorted(DATA.glob("*.pdf"))


@pytest.fixture(scope="session", params=PDFS, ids=lambda p: p.stem)
def match(request):
    return build_match(request.param)
