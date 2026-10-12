from stats_hand.analysis.box_score import (
    box_score,
    has_shot_tracking,
    player_events,
    season_totals,
)
from stats_hand.analysis.periods import (
    goals_per_minute,
    momentum_series,
    rolling_windows,
    scoring_runs,
)
from stats_hand.analysis.score import score_series, score_stats
from stats_hand.models import GOAL_KINDS, REC, VIS
from stats_hand.parsing.match import build_match
from tests.conftest import PDFS


def test_score_series_monotone_and_final(match):
    pts = score_series(match)
    assert pts[0].rec == 0 and pts[0].vis == 0
    for a, b in zip(pts, pts[1:]):
        assert b.rec >= a.rec and b.vis >= a.vis
        assert b.time_s >= a.time_s
    assert (pts[-1].rec, pts[-1].vis) == match.meta.score_final
    assert pts[-1].time_s == match.duration_s


def test_score_stats_sane(match):
    s = score_stats(match)
    assert s.max_lead_rec >= 0 and s.max_lead_vis >= 0
    assert s.n_draws >= 0 and s.n_lead_changes >= 0


def test_rolling_windows_cover_match(match):
    wins = rolling_windows(match)
    assert wins[0].start_s == 0
    assert wins[-1].end_s <= match.duration_s
    total = sum(w.goals_rec for w in rolling_windows(match, window_s=600, step_s=600))
    assert total == match.meta.score_final[0]


def test_scoring_runs(match):
    runs = scoring_runs(match)
    for team in (REC, VIS):
        assert runs[team] == sorted(runs[team], key=lambda r: r.length, reverse=True)
        for r in runs[team]:
            assert r.length >= 1 and r.team == team


def test_goals_per_minute_totals(match):
    rec, vis = goals_per_minute(match)
    assert (sum(rec), sum(vis)) == match.meta.score_final


def test_momentum_series(match):
    mom = momentum_series(match)
    assert len(mom) >= 55
    assert all(p.rate_rec >= 0 and p.rate_vis >= 0 for p in mom)
    # la moyenne du rythme lissé ≈ buts/minute réels sur le match
    avg_rec = sum(p.rate_rec for p in mom) / len(mom)
    assert abs(avg_rec - match.meta.score_final[0] / len(mom)) < 0.15


def test_box_score_totals(match):
    rec_lines, vis_lines = box_score(match)
    assert sum(pl.buts for pl in rec_lines) == match.meta.score_final[0]
    assert sum(pl.buts for pl in vis_lines) == match.meta.score_final[1]


def test_player_events_match_box_score(match):
    for team, lines in zip((REC, VIS), box_score(match)):
        for pl in lines:
            evs = player_events(match, team, pl.nom)
            assert sum(1 for e in evs if e.kind in GOAL_KINDS) == pl.buts


def test_box_score_shots(match):
    for lines in box_score(match):
        for pl in lines:
            assert pl.tirs >= pl.buts
            if pl.reussite is not None:
                assert 0 <= pl.reussite <= 1
    if not has_shot_tracking(match):
        assert all(pl.tirs_manques == 0 and pl.arrets == 0 for lines in box_score(match) for pl in lines)


def test_season_totals():
    matches = [build_match(p) for p in PDFS]
    lines = season_totals(matches)
    assert sum(s.buts for s in lines) == sum(sum(m.meta.score_final) for m in matches)
    assert all(1 <= s.matchs <= len(matches) for s in lines)
    assert all(s.matchs_suivis <= s.matchs for s in lines)
    assert [s.buts for s in lines] == sorted((s.buts for s in lines), reverse=True)
    # un même joueur présent sur plusieurs feuilles est bien agrégé (licence)
    assert any(s.matchs > 1 for s in lines)
