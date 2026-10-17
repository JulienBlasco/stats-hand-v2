"""App Streamlit : visualisation de feuilles de match handball (FDME).

Deux vues : un match unique (score, périodes clés, stats individuelles) ou
l'ensemble des matchs chargés du point de vue d'une équipe suivie (périodes clés,
stats individuelles).

Lancement : `uv run streamlit run stats_hand/app.py` (depuis la racine du projet).
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# `streamlit run` ajoute le dossier du script au sys.path, pas la racine du projet :
# on l'ajoute pour que `import stats_hand...` fonctionne quel que soit le lanceur.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from stats_hand.analysis.box_score import (
    PlayerLine,
    SeasonLine,
    box_score,
    has_shot_tracking,
    player_events,
    season_totals,
    team_saves,
)
from stats_hand.analysis.periods import (
    best_worst_window,
    exclusions,
    momentum_series,
    scoring_runs,
)
from stats_hand.analysis.multi import (
    cumulative_windows,
    mean_rate_series,
    opponent,
    side_of,
    slice_totals,
    team_matches,
    team_record,
    team_save_rate,
    team_shooting,
    teams_by_count,
    top_runs,
)
from stats_hand.analysis.score import score_series, score_stats
from stats_hand.models import GOAL_KINDS, REC, VIS, EventKind, Match
from stats_hand.parsing.match import build_match

C_REC = "#2a78d6"  # bleu — équipe recevante
C_VIS = "#eb6834"  # orange — équipe visiteuse
C_REC_FILL = "rgba(42,120,214,.30)"
C_VIS_FILL = "rgba(235,104,52,.30)"
C_GRID = "#e6e6e3"
C_INK = "#52514e"

st.set_page_config(page_title="Stats Hand", page_icon="🤾", layout="wide")


@st.cache_data(show_spinner=False)
def _parse(name: str, data: bytes) -> Match:
    return build_match(data)


def mmss(s: int) -> str:
    return f"{s // 60:02d}:{s % 60:02d}"


def minute(s: int) -> str:
    return f"{s // 60}'"


def _dt(seconds):
    """Convertit des secondes en Timestamp epoch, pour un axe Plotly de type date
    (seul moyen d'obtenir un hoverformat en minutes/secondes plutôt qu'un nombre décimal).
    Suppose qu'un match ne dépasse jamais 60 minutes (pas de prolongation en championnat)."""
    return pd.to_datetime(seconds, unit="s")


def _layout(fig: go.Figure, height: int, **layout) -> None:
    """Mise en page commune à tous les graphes ; `layout` complète ou remplace les défauts."""
    fig.update_layout(**{
        "template": "plotly_white", "height": height, "dragmode": False,
        "margin": dict(t=28, r=12, l=12, b=10),
    } | layout)


def _halftime_line(fig: go.Figure, **kwargs) -> None:
    fig.add_vline(x=_dt(30 * 60), line=dict(color=C_INK, width=1, dash="dot"), **kwargs)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n > 1 else ''}"


def _style(fig: go.Figure, duration_s: int, *, height: int, y_title: str, **layout) -> go.Figure:
    _layout(fig, height, hovermode="x unified", **layout)
    ticks_min = list(range(0, duration_s // 60 + 1, 10))
    if ticks_min[-1] != duration_s // 60:
        ticks_min.append(duration_s // 60)
    fig.update_xaxes(
        title="minute", type="date", hoverformat="%Mm%Ss", fixedrange=True,
        range=[_dt(0), _dt(duration_s)], gridcolor=C_GRID,
        tickvals=_dt([m * 60 for m in ticks_min]), ticktext=[str(m) for m in ticks_min],
    )
    fig.update_yaxes(title=y_title, gridcolor=C_GRID, fixedrange=True)
    return fig


def rate_figure(duration_s: int, minutes: list[int], rate_a: list[float], rate_b: list[float],
                name_a: str, name_b: str, height: int = 300) -> go.Figure:
    """Deux rythmes de marque lissés (bleu / orange) ; la zone colorée marque celui qui domine."""
    x = _dt([m * 60 for m in minutes])
    lower = [min(a, b) for a, b in zip(rate_a, rate_b)]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=lower, line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(
        x=x, y=rate_a, name=name_a, line=dict(color=C_REC, width=2),
        fill="tonexty", fillcolor=C_REC_FILL,
        hovertemplate="%{y:.2f} but/min<extra>" + name_a + "</extra>"))
    fig.add_trace(go.Scatter(x=x, y=lower, line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(
        x=x, y=rate_b, name=name_b, line=dict(color=C_VIS, width=2),
        fill="tonexty", fillcolor=C_VIS_FILL,
        hovertemplate="%{y:.2f} but/min<extra>" + name_b + "</extra>"))
    _halftime_line(fig)
    _style(fig, duration_s, height=height, y_title="buts / min (lissé 5 min)",
           legend=dict(orientation="h", y=1.15))
    fig.update_yaxes(rangemode="tozero")
    return fig


def momentum_figure(match: Match, height: int = 300) -> go.Figure:
    """Rythme de marque lissé d'un match (moyenne mobile centrée 5 min, façon stats-hand v1)."""
    mom, meta = momentum_series(match), match.meta
    return rate_figure(match.duration_s, [p.minute for p in mom], [p.rate_rec for p in mom],
                       [p.rate_vis for p in mom], meta.rec_name, meta.vis_name, height)


def _pct(x: float | None) -> str:
    return f"{x:.0%}" if x is not None else "—"


def _sanctions(avertissements: int, suspensions_2min: int, disqualifications: int) -> str:
    """🟨 par avertissement, 2️⃣ par exclusion de 2 min, 🟥 pour une disqualification."""
    return "🟨" * avertissements + "2️⃣" * suspensions_2min + "🟥" * disqualifications


def box_table(lines: list[PlayerLine], tracked: bool) -> pd.DataFrame:
    """Tableau individuel d'une équipe ; tirs seulement si le déroulé les détaille."""
    rows = []
    for pl in lines:
        row = {"N°": pl.numero, "Nom": pl.nom, "Buts": pl.buts, "dont 7m": pl.buts_7m}
        if tracked:
            row |= {"Tirs": pl.tirs, "Réussite": _pct(pl.reussite)}
        row["Sanctions"] = _sanctions(pl.avertissements, pl.suspensions_2min, pl.disqualifications)
        rows.append(row)
    return pd.DataFrame(rows)


def keeper_table(lines: list[PlayerLine]) -> pd.DataFrame:
    """Gardiens d'une équipe : joueurs ayant au moins un arrêt."""
    keepers = sorted((pl for pl in lines if pl.arrets > 0), key=lambda pl: (-pl.arrets, pl.nom))
    return pd.DataFrame([{"N°": pl.numero, "Nom": pl.nom, "Arrêts": pl.arrets} for pl in keepers])


def _save_rate_metric(target, arrets: int, subis: int, suivis: int | None = None) -> None:
    """Taux d'arrêt d'une équipe ; `target` est `st` ou une colonne."""
    detail = f"{arrets} arrêts / {subis} tirs cadrés"
    if suivis:
        detail += f" sur {_plural(suivis, 'match')}"
    target.metric("Taux d'arrêt de l'équipe", _pct(arrets / subis if subis else None), detail,
                  delta_color="off")


def scorers_figure(lines: list[PlayerLine] | list[SeasonLine], color: str, fill: str, n_rows: int,
                   max_buts: int) -> go.Figure | None:
    """Barres horizontales des buteurs : buts dans le jeu + buts sur 7m empilés.

    `n_rows` fixe la hauteur (nombre de lignes de l'équipe qui a le plus de buteurs)
    pour que les graphes des deux équipes aient la même hauteur et la même épaisseur
    de barres ; les lignes manquantes restent vides en bas du graphe. `max_buts` fixe
    l'échelle de l'axe des buts, commune aux deux équipes.
    """
    scorers = sorted((pl for pl in lines if pl.buts), key=lambda pl: (pl.buts, pl.nom))
    if not scorers:
        return None
    # les lignes de cumul (SeasonLine) n'ont pas de numéro : il peut changer d'un match à l'autre
    y = [f"{pl.nom} ({pl.numero})" if isinstance(pl, PlayerLine) and pl.numero is not None else pl.nom
         for pl in scorers]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=y, x=[pl.buts - pl.buts_7m for pl in scorers], orientation="h", name="jeu",
        marker_color=color, hovertemplate="%{x} dans le jeu<extra></extra>"))
    fig.add_trace(go.Bar(
        y=y, x=[pl.buts_7m for pl in scorers], orientation="h", name="7m",
        marker=dict(color=fill, line=dict(color=color, width=1)),
        hovertemplate="%{x} sur 7m<extra></extra>"))
    _layout(fig, 60 + 26 * n_rows, barmode="stack", margin=dict(t=10, r=12, l=12, b=10),
            legend=dict(orientation="h", y=-0.12 if n_rows > 6 else -0.3))
    fig.update_xaxes(fixedrange=True, gridcolor=C_GRID, range=[0, max_buts + 0.5],
                     dtick=1 if max_buts <= 10 else None)
    fig.update_yaxes(fixedrange=True, range=[len(scorers) - 0.5 - n_rows, len(scorers) - 0.5])
    return fig


def player_figure(match: Match, team: str, events) -> go.Figure:
    """Score de l'équipe du joueur, avec ses buts (points) et ses sanctions (traits)."""
    pts = score_series(match)
    own = [(p.time_s, p.rec if team == REC else p.vis) for p in pts]
    opp = [(p.time_s, p.vis if team == REC else p.rec) for p in pts]
    color = C_REC if team == REC else C_VIS
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=_dt([t for t, _ in opp]), y=[v for _, v in opp], name=match.team_name(VIS if team == REC else REC),
        line=dict(color=C_GRID, width=2, shape="hv"), hovertemplate="%{y}<extra>adversaire</extra>"))
    fig.add_trace(go.Scatter(
        x=_dt([t for t, _ in own]), y=[v for _, v in own], name=match.team_name(team),
        line=dict(color=color, width=2, shape="hv"), hovertemplate="%{y}<extra>équipe</extra>"))
    goals = [e for e in events if e.kind in GOAL_KINDS]
    if goals:
        fig.add_trace(go.Scatter(
            x=_dt([e.time_s for e in goals]),
            y=[e.score_rec if team == REC else e.score_vis for e in goals],
            mode="markers", name="ses buts",
            marker=dict(color=color, size=10, line=dict(color="white", width=1.5),
                        symbol=["diamond" if e.kind is EventKind.GOAL_7M else "circle" for e in goals]),
            text=[e.raw_action for e in goals], hovertemplate="%{text}<extra></extra>"))
    for e in events:
        if e.kind in (EventKind.SUSPENSION_2MIN, EventKind.DISQUALIFICATION):
            fig.add_vrect(x0=_dt(e.time_s), x1=_dt(min(e.time_s + 120, match.duration_s)),
                          fillcolor=C_INK, opacity=0.08, line_width=0)
        elif e.kind is EventKind.WARNING:
            fig.add_vline(x=_dt(e.time_s), line=dict(color=C_INK, width=1, dash="dot"))
    _halftime_line(fig)
    _style(fig, match.duration_s, height=320, y_title="buts", legend=dict(orientation="h", y=1.15))
    return fig


def render_match(match: Match) -> None:
    """Vue d'un match : en-tête + 3 onglets."""
    meta = match.meta

    # --------------------------------------------------------------------------- en-tête
    c1, c2, c3 = st.columns([2, 1, 2])
    c1.markdown(f"### :blue[{meta.rec_name}]")
    c2.markdown(f"### {meta.score_final[0]} – {meta.score_final[1]}")
    c3.markdown(f"### :orange[{meta.vis_name}]")
    st.caption(
        " · ".join(
            x
            for x in [
                meta.competition,
                meta.phase,
                meta.date.strftime("%d/%m/%Y %H:%M") if meta.date else "",
                f"Journée {meta.journee}" if meta.journee else "",
                meta.salle,
                f"score à la mi-temps {meta.score_mitemps[0]}-{meta.score_mitemps[1]}" if meta.score_mitemps else "",
            ]
            if x
        )
    )

    tab_score, tab_periodes, tab_joueurs = st.tabs(
        ["📈 Évolution du score", "🔑 Périodes clés", "👤 Stats individuelles"]
    )

    # --------------------------------------------------------------------------- onglet 1
    with tab_score:
        pts = score_series(match)
        stats = score_stats(match)
        df = pd.DataFrame([(p.time_s, p.rec, p.vis, p.diff) for p in pts],
                          columns=["time_s", "rec", "vis", "diff"])
        df["t"] = _dt(df["time_s"])

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["t"], y=df["rec"], name=meta.rec_name, line=dict(color=C_REC, width=2, shape="hv"),
            hovertemplate="%{y} — " + meta.rec_name + "<extra></extra>"))
        fig.add_trace(go.Scatter(
            x=df["t"], y=df["vis"], name=meta.vis_name, line=dict(color=C_VIS, width=2, shape="hv"),
            hovertemplate="%{y} — " + meta.vis_name + "<extra></extra>"))
        _halftime_line(fig, annotation_text="mi-temps", annotation_position="top", annotation_yshift=-28)
        # une bande par exclusion : les 2 min concomitantes se superposent (zone plus foncée)
        excl = exclusions(match)
        for x in excl:
            fig.add_vrect(x0=_dt(x.start_s), x1=_dt(x.end_s), fillcolor=C_REC if x.team == REC else C_VIS,
                          opacity=0.12, line_width=0, layer="below")
        for team, name, fill in ((REC, meta.rec_name, C_REC_FILL), (VIS, meta.vis_name, C_VIS_FILL)):
            if any(x.team == team for x in excl):
                fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name=f"2 min {name}",
                                         marker=dict(symbol="square", size=12, color=fill), hoverinfo="skip"))
        _style(fig, match.duration_s, height=420, y_title="buts", legend=dict(orientation="h", y=1.12))
        st.plotly_chart(fig, width="stretch")
        if excl:
            st.caption("Bandes : exclusions 2 min (l'équipe joue en infériorité numérique), "
                       "plus foncées quand elles se chevauchent")

        # différentiel de score (diverging : bleu = REC devant, orange = VIS devant)
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=df["t"], y=df["diff"].clip(lower=0), line=dict(color=C_REC, width=1, shape="hv"),
                                  fill="tozeroy", fillcolor=C_REC_FILL, name=meta.rec_name,
                                  hovertemplate="+%{y}<extra></extra>"))
        fig2.add_trace(go.Scatter(x=df["t"], y=df["diff"].clip(upper=0), line=dict(color=C_VIS, width=1, shape="hv"),
                                  fill="tozeroy", fillcolor=C_VIS_FILL, name=meta.vis_name,
                                  hovertemplate="%{y}<extra></extra>"))
        fig2.add_hline(y=0, line=dict(color=C_INK, width=1))
        _style(fig2, match.duration_s, height=220, y_title="écart (buts)", showlegend=False)
        st.caption("Écart de score au fil du match")
        st.plotly_chart(fig2, width="stretch")

        # périodes clés — momentum
        st.caption("Périodes clés — rythme de marque lissé sur 5 min · la zone colorée marque l'équipe qui domine le rythme")
        st.plotly_chart(momentum_figure(match, height=280), width="stretch")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric(f"Écart max {meta.rec_name}", f"+{stats.max_lead_rec}", minute(stats.max_lead_rec_time))
        m2.metric(f"Écart max {meta.vis_name}", f"+{stats.max_lead_vis}", minute(stats.max_lead_vis_time))
        m3.metric("Retours à égalité", stats.n_draws,
                  f"dernier à {minute(stats.last_draw_time)}" if stats.last_draw_time else "—")
        m4.metric("Changements de leader", stats.n_lead_changes,
                  f"dernier à {minute(stats.last_lead_change_time)}" if stats.last_lead_change_time else "—")

    # --------------------------------------------------------------------------- onglet 2
    with tab_periodes:
        bw_rec, bw_vis = best_worst_window(match)

        fig = momentum_figure(match, height=360)
        for bw, color in ((bw_rec, C_REC), (bw_vis, C_VIS)):
            b = bw.best
            fig.add_vrect(x0=_dt(b.start_s), x1=_dt(b.end_s), fillcolor=color, opacity=0.10,
                          line_width=0, annotation_text=f"top {match.team_name(bw.team).split()[0]}",
                          annotation_position="top left", annotation_yshift=-28)
        st.plotly_chart(fig, width="stretch")

        st.subheader("Meilleure / pire période de 10 minutes")

        def _win_txt(bw, name):
            b, w = bw.best, bw.worst
            return (
                f"**{name}** — meilleure : **{b.goals_rec}-{b.goals_vis}** ({b.diff:+d}) "
                f"de {minute(b.start_s)} à {minute(b.end_s)}  ·  "
                f"pire : **{w.goals_rec}-{w.goals_vis}** ({w.diff:+d}) "
                f"de {minute(w.start_s)} à {minute(w.end_s)}"
            )

        st.markdown(_win_txt(bw_rec, meta.rec_name))
        st.markdown(_win_txt(bw_vis, meta.vis_name))

        st.subheader("Séries de buts consécutifs")
        runs = scoring_runs(match)
        cols = st.columns(2)
        for col, (team, name) in zip(cols, ((REC, meta.rec_name), (VIS, meta.vis_name))):
            rows = [
                {
                    "série": f"{r.length} buts",
                    "créneau": f"{mmss(r.start_s)} → {mmss(r.end_s)}",
                    "score": f"{r.score_from[0]}-{r.score_from[1]} → {r.score_to[0]}-{r.score_to[1]}",
                }
                for r in runs[team]
            ]
            col.markdown(f"**{name}**")
            col.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    # --------------------------------------------------------------------------- onglet 3
    with tab_joueurs:
        tracked = has_shot_tracking(match)
        box_rec, box_vis = box_score(match)
        teams = ((REC, meta.rec_name, box_rec, C_REC, C_REC_FILL),
                 (VIS, meta.vis_name, box_vis, C_VIS, C_VIS_FILL))

        # contrôle FDME : affiché uniquement en cas d'écart
        ecarts = [
            f"{name} — {pl.nom} : {pl.buts} but(s) dans le déroulé, {pl.fdme_buts} sur la feuille"
            for _, name, lines, _, _ in teams for pl in lines if pl.divergence
        ]
        if ecarts:
            st.warning("Écarts entre le déroulé et la colonne « Buts » de la feuille :\n\n"
                       + "\n".join(f"- {x}" for x in ecarts))

        st.subheader("Ce match")
        if not tracked:
            st.caption("Le déroulé de cette feuille ne détaille pas les tirs ni les arrêts : "
                       "seuls les buts et sanctions sont disponibles.")
        n_rows = max(sum(1 for pl in lines if pl.buts) for _, _, lines, _, _ in teams)
        max_buts = max(pl.buts for _, _, lines, _, _ in teams for pl in lines)
        for col, (_, name, lines, color, fill) in zip(st.columns(2), teams):
            col.markdown(f"**{name}**")
            if fig := scorers_figure(lines, color, fill, n_rows, max_buts):
                col.plotly_chart(fig, width="stretch")
            col.dataframe(box_table(lines, tracked), hide_index=True, width="stretch")

        if tracked:
            st.subheader("Gardiens")
            for col, (side, name, lines, _, _) in zip(st.columns(2), teams):
                col.markdown(f"**{name}**")
                _save_rate_metric(col, *team_saves(match, side))
                if (keepers := keeper_table(lines)).empty:
                    col.caption("Aucun arrêt.")
                else:
                    col.dataframe(keepers, hide_index=True, width="stretch")

        st.subheader("Fiche individuelle")
        choices = {
            f"{p.label} — {roster.name}": (roster.team, p.full_name)
            for roster in (match.rec, match.vis) for p in roster.players
        }
        team, nom = choices[st.selectbox("Joueur / joueuse", list(choices))]
        pl = next(x for x in (box_rec if team == REC else box_vis) if x.nom == nom)
        evs = player_events(match, team, nom)
        team_goals = match.score_for_against(team)[0]
        goal_times = [e.time_s for e in evs if e.kind in GOAL_KINDS]

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Buts", pl.buts, f"dont {pl.buts_7m} sur 7m" if pl.buts_7m else None, delta_color="off")
        m2.metric("Part des buts de l'équipe", _pct(pl.buts / team_goals if team_goals else None))
        if tracked:
            m3.metric("Tirs · réussite", f"{pl.tirs} · {_pct(pl.reussite)}")
        else:
            m3.metric("1er / dernier but",
                      f"{minute(goal_times[0])} / {minute(goal_times[-1])}" if goal_times else "—")
        m4.metric("Sanctions", f"{pl.suspensions_2min} × 2 min",
                  f"{pl.avertissements} avert." + (f", {pl.disqualifications} disq." if pl.disqualifications else ""),
                  delta_color="off")

        st.plotly_chart(player_figure(match, team, evs), width="stretch")
        st.caption("● but · ◆ but sur 7m · zone grisée : exclusion 2 min · pointillé : avertissement")
        if evs:
            st.dataframe(pd.DataFrame([
                {"temps": e.mmss, "action": e.raw_action, "score": f"{e.score_rec}-{e.score_vis}"}
                for e in evs
            ]), hide_index=True, width="stretch")
        else:
            st.caption("Aucune action enregistrée à son nom dans le déroulé.")


def _short(name: str, width: int = 16) -> str:
    """Nom d'équipe raccourci pour les boutons du sélecteur."""
    if len(name) <= width:
        return name
    cut = name[:width].rsplit(" ", 1)[0]
    return (cut if len(cut) >= 6 else name[:width]).rstrip(" -") + "…"


def match_label(m: Match, short: bool = False) -> str:
    rec, vis = (_short(m.meta.rec_name), _short(m.meta.vis_name)) if short else (m.meta.rec_name, m.meta.vis_name)
    date = m.meta.date.strftime("%d/%m") if m.meta.date else "?"
    return f"{date} {rec} {m.meta.score_final[0]}-{m.meta.score_final[1]} {vis}"


def _unique_labels(matches: list[Match], short: bool = False) -> list[str]:
    """Libellés des matchs ; un doublon (même affiche) est suffixé du code de la feuille."""
    labels = [match_label(m, short) for m in matches]
    return [f"{lab} ({m.meta.code})" if labels.count(lab) > 1 else lab for lab, m in zip(labels, matches)]


def season_table(season: list[SeasonLine], any_tracked: bool) -> pd.DataFrame:
    rows = []
    for s in season:
        row = {"Nom": s.nom, "Matchs": s.matchs, "Buts": s.buts, "dont 7m": s.buts_7m,
               "Buts/match": s.buts_par_match}
        if any_tracked:
            row |= {"Tirs": s.tirs if s.matchs_suivis else None, "Réussite": _pct(s.reussite)}
        row["Sanctions"] = _sanctions(s.avertissements, s.suspensions_2min, s.disqualifications)
        rows.append(row)
    return pd.DataFrame(rows)


def keeper_season_table(season: list[SeasonLine]) -> pd.DataFrame:
    """Gardiens (au moins un arrêt) sur les matchs dont le déroulé détaille les arrêts."""
    keepers = sorted((s for s in season if s.arrets > 0), key=lambda s: (-s.arrets, s.nom))
    return pd.DataFrame([
        {"Nom": s.nom, "Matchs suivis": s.matchs_suivis, "Arrêts": s.arrets,
         "Arrêts/match": s.arrets / s.matchs_suivis}
        for s in keepers
    ])


def render_ensemble(all_matches: list[Match]) -> None:
    """Vue multi-matchs du point de vue d'une équipe suivie : périodes clés + stats individuelles."""
    team = st.selectbox("Équipe suivie", teams_by_count(all_matches),
                        help="Par défaut, l'équipe présente sur le plus de feuilles.")
    played = team_matches(all_matches, team)
    rec = team_record(played, team)
    ignored = len(all_matches) - len(played)
    st.caption(
        f"{_plural(rec.matchs, 'match')} · "
        f"{rec.victoires} V – {rec.nuls} N – {rec.defaites} D · "
        f"{rec.buts_pour} buts pour, {rec.buts_contre} contre"
        + (f" · {_plural(ignored, 'feuille')} sans cette équipe ignorée{'s' if ignored > 1 else ''}"
           if ignored else "")
    )
    duration_s = max(m.duration_s for m in played)
    tab_periodes, tab_joueurs = st.tabs(["🔑 Périodes clés", "👤 Stats individuelles"])

    # ----------------------------------------------------------------------- périodes clés
    with tab_periodes:
        series = mean_rate_series(played, team)
        fig = rate_figure(duration_s, [p.minute for p in series], [p.rate_for for p in series],
                          [p.rate_against for p in series], team, "adversaires", height=360)
        windows = cumulative_windows(played, team)
        if windows:
            best, worst = windows
            for w, color, label in ((best, C_REC, "meilleure"), (worst, C_VIS, "pire")):
                fig.add_vrect(x0=_dt(w.start_s), x1=_dt(w.end_s), fillcolor=color, opacity=0.10,
                              line_width=0, annotation_text=label,
                              annotation_position="top left", annotation_yshift=-28)
        st.caption("Rythme de marque moyen par match, lissé sur 5 min")
        st.plotly_chart(fig, width="stretch")

        if windows:
            st.subheader("Meilleure / pire période de 10 minutes (cumul)")
            for label, w in (("Meilleure", best), ("Pire", worst)):
                st.markdown(
                    f"**{label}** : de {minute(w.start_s)} à {minute(w.end_s)}, "
                    f"**{w.pour}-{w.contre}** ({w.diff:+d}) sur {_plural(w.matchs, 'match')}"
                )

        st.subheader("Bilan par tranche de 10 minutes")
        slices = slice_totals(played, team)
        x = [f"{s.start_s // 60}-{s.end_s // 60}'" for s in slices]
        diffs = [f"{s.diff:+d}" for s in slices]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=x, y=[s.pour for s in slices], name=team, marker_color=C_REC,
                             customdata=diffs, hovertemplate="%{y} pour (écart %{customdata})<extra></extra>"))
        fig.add_trace(go.Bar(x=x, y=[s.contre for s in slices], name="adversaires", marker_color=C_VIS,
                             hovertemplate="%{y} contre<extra></extra>"))
        _layout(fig, 300, barmode="group", hovermode="x unified", legend=dict(orientation="h", y=1.15))
        fig.update_xaxes(title="minutes", fixedrange=True)
        fig.update_yaxes(title=f"buts (cumul sur {len(played)} matchs)", gridcolor=C_GRID, fixedrange=True)
        st.plotly_chart(fig, width="stretch")

        st.subheader("Séries de buts consécutifs")
        runs = top_runs(played, team)
        for col, (key, title) in zip(st.columns(2), (("pour", f"**{team}**"), ("contre", "**Adversaires**"))):
            col.markdown(title)
            col.dataframe(pd.DataFrame([
                {
                    "série": f"{tr.run.length} buts",
                    "match": f"{tr.match.meta.date:%d/%m} vs {opponent(tr.match, team)}" if tr.match.meta.date
                             else f"vs {opponent(tr.match, team)}",
                    "créneau": f"{mmss(tr.run.start_s)} → {mmss(tr.run.end_s)}",
                    # score affiché équipe suivie en premier
                    "score": "{}-{} → {}-{}".format(
                        *(tr.run.score_from if side_of(tr.match, team) == REC else tr.run.score_from[::-1]),
                        *(tr.run.score_to if side_of(tr.match, team) == REC else tr.run.score_to[::-1])),
                }
                for tr in runs[key]
            ]), hide_index=True, width="stretch")

    # ----------------------------------------------------------------------- stats individuelles
    with tab_joueurs:
        season = [s for s in season_totals(played) if s.equipe == team]
        any_tracked = any(s.matchs_suivis for s in season)

        if shooting := team_shooting(played, team):
            buts, tirs, suivis = shooting
            st.metric("Réussite au tir de l'équipe", _pct(buts / tirs),
                      f"{buts} buts / {tirs} tirs sur {_plural(suivis, 'match')}",
                      delta_color="off")

        st.subheader("Buteurs")
        n_scorers = sum(1 for s in season if s.buts)
        if n_scorers and (fig := scorers_figure(season, C_REC, C_REC_FILL, n_scorers,
                                                max(s.buts for s in season))):
            st.plotly_chart(fig, width="stretch")

        st.subheader("Cumul par joueur")
        st.dataframe(season_table(season, any_tracked), hide_index=True, width="stretch",
                     column_config={"Buts/match": st.column_config.NumberColumn(format="%.1f")})
        if any_tracked and not all(has_shot_tracking(m) for m in played):
            st.caption("Tirs et réussite ne portent que sur les matchs dont le déroulé les détaille.")

        st.subheader("Gardiens")
        if saves := team_save_rate(played, team):
            _save_rate_metric(st, *saves)
        if (keepers := keeper_season_table(season)).empty:
            st.caption("Aucun arrêt détaillé dans les feuilles de match.")
        else:
            st.dataframe(keepers, hide_index=True, width="stretch",
                         column_config={"Arrêts/match": st.column_config.NumberColumn(format="%.1f")})


# --------------------------------------------------------------------------- UI

st.title("🤾 Feuilles de match — visualisation")

files = st.file_uploader(
    "Feuilles de match (PDF FDME)", type="pdf", accept_multiple_files=True
)
if not files:
    st.info("Charge une ou plusieurs feuilles de match en PDF pour commencer.")
    st.stop()

parsed: list[Match] = []
for f in files:
    try:
        parsed.append(_parse(f.name, f.getvalue()))
    except Exception as exc:  # noqa: BLE001
        st.error(f"{f.name} : échec du parsing — {exc}")

if not parsed:
    st.stop()

if len(parsed) == 1:
    render_match(parsed[0])
    st.stop()

# sélecteur de vue : « tous les matchs » ou un match, mis en avant dans un encadré
parsed.sort(key=lambda m: m.meta.date or datetime.min)
ALL = f"📊 Tous les matchs ({len(parsed)})"
with st.container(border=True):
    st.markdown("#### Que veux-tu analyser ?")
    if len(parsed) <= 5:
        # boutons : libellés courts
        labels = _unique_labels(parsed, short=True)
        choice = st.segmented_control("Vue", [ALL, *labels], default=labels[0],
                                      selection_mode="single", label_visibility="collapsed")
        choice = choice or labels[0]  # un clic sur le bouton actif le désélectionne
    else:
        labels = _unique_labels(parsed)
        choice = st.selectbox("Vue", [ALL, *labels], index=1, label_visibility="collapsed")

if choice == ALL:
    render_ensemble(parsed)
else:
    render_match(parsed[labels.index(choice)])
