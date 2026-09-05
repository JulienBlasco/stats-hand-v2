from stats_hand.models import GOAL_KINDS, REC, VIS, EventKind


def test_metadata(match):
    assert match.meta.code
    assert match.meta.rec_name and match.meta.vis_name
    assert match.meta.date is not None
    assert match.meta.score_final != (0, 0)


def test_rosters_non_empty(match):
    assert len(match.rec.players) >= 12
    assert len(match.vis.players) >= 12
    for p in match.rec.players + match.vis.players:
        assert p.nom and p.prenom
        assert p.numero is not None


def test_events_present(match):
    assert len(match.events) >= 30
    assert any(e.period == 2 for e in match.events)


def test_final_score_matches_timeline(match):
    goals = [e for e in match.events if e.kind in GOAL_KINDS]
    last = goals[-1]
    assert (last.score_rec, last.score_vis) == match.meta.score_final


def test_goal_team_consistent_with_score(match):
    prev = (0, 0)
    for e in match.events:
        if e.kind in GOAL_KINDS:
            d_rec = e.score_rec - prev[0]
            d_vis = e.score_vis - prev[1]
            if d_rec == 1 and d_vis == 0:
                assert e.team == REC
            elif d_vis == 1 and d_rec == 0:
                assert e.team == VIS
        prev = (e.score_rec, e.score_vis)


def test_goal_count_equals_final(match):
    rec = sum(1 for e in match.events if e.kind in GOAL_KINDS and e.team == REC)
    vis = sum(1 for e in match.events if e.kind in GOAL_KINDS and e.team == VIS)
    assert (rec, vis) == match.meta.score_final


def test_name_resolution_rate(match):
    named = [
        e for e in match.events
        if e.kind in {EventKind.WARNING, EventKind.SUSPENSION_2MIN,
                      EventKind.DISQUALIFICATION, EventKind.CONCUSSION}
    ]
    resolved = sum(1 for e in named if e.team is not None)
    assert not named or resolved / len(named) >= 0.9


def test_goals_have_player(match):
    goals = [e for e in match.events if e.kind in GOAL_KINDS]
    assert sum(1 for e in goals if e.player is not None) / len(goals) >= 0.95


def test_halftime_when_present(match):
    mt = match.meta.score_mitemps
    if mt is not None:
        assert 0 <= mt[0] <= match.meta.score_final[0]
        assert 0 <= mt[1] <= match.meta.score_final[1]
