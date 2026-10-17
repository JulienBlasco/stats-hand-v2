import pytest

from stats_hand.analysis.multi import (
    cumulative_windows,
    mean_rate_series,
    side_of,
    slice_totals,
    team_matches,
    team_record,
    team_save_rate,
    team_shooting,
    teams_by_count,
    top_runs,
)
from stats_hand.parsing.match import build_match
from tests.conftest import PDFS

TEAM = "ISSY HBM 1C"


@pytest.fixture(scope="module")
def matches():
    return [build_match(p) for p in PDFS]


def test_teams_by_count(matches):
    assert teams_by_count(matches)[0] == TEAM


def test_team_matches_sorted(matches):
    played = team_matches(matches, TEAM)
    assert len(played) == 3
    assert all(side_of(m, TEAM) for m in played)
    dates = [m.meta.date for m in played]
    assert dates == sorted(dates)


def test_team_record(matches):
    rec = team_record(matches, TEAM)
    assert rec.victoires + rec.nuls + rec.defaites == rec.matchs == 3
    total = sum(sum(m.meta.score_final) for m in team_matches(matches, TEAM))
    assert rec.buts_pour + rec.buts_contre == total


def test_slice_totals_sum(matches):
    rec = team_record(matches, TEAM)
    slices = slice_totals(matches, TEAM)
    assert len(slices) == 6
    assert sum(s.pour for s in slices) == rec.buts_pour
    assert sum(s.contre for s in slices) == rec.buts_contre


def test_cumulative_windows(matches):
    best, worst = cumulative_windows(matches, TEAM)
    assert best.diff >= worst.diff
    assert best.end_s - best.start_s == 600
    assert best.matchs == 3


def test_top_runs(matches):
    runs = top_runs(matches, TEAM)
    for key in ("pour", "contre"):
        lengths = [tr.run.length for tr in runs[key]]
        assert lengths == sorted(lengths, reverse=True)
        assert all(side_of(tr.match, TEAM) for tr in runs[key])


def test_mean_rate_series(matches):
    rec = team_record(matches, TEAM)
    series = mean_rate_series(matches, TEAM)
    avg = sum(p.rate_for for p in series) / len(series)
    assert abs(avg - rec.buts_pour / (rec.matchs * len(series))) < 0.05


def test_team_shooting(matches):
    buts, tirs, suivis = team_shooting(matches, TEAM)
    assert 0 < buts <= tirs
    assert suivis == 3
    # pas de suivi des tirs sur les feuilles de LBE
    assert team_shooting(matches, "PARIS 92") is None


def test_team_save_rate(matches):
    arrets, subis, suivis = team_save_rate(matches, TEAM)
    assert 0 < arrets <= subis
    assert suivis == 3
    assert team_save_rate(matches, "PARIS 92") is None
