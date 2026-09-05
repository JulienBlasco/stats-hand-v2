"""App Streamlit : visualisation d'une feuille de match handball (FDME).

Lancement : `uv run streamlit run stats_hand/app.py` (depuis la racine du projet).
"""

from __future__ import annotations

import sys
from pathlib import Path

# `streamlit run` ajoute le dossier du script au sys.path, pas la racine du projet :
# on l'ajoute pour que `import stats_hand...` fonctionne quel que soit le lanceur.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from stats_hand.analysis.periods import (
    best_worst_window,
    momentum_series,
    scoring_runs,
)
from stats_hand.analysis.score import score_series, score_stats
from stats_hand.models import REC, VIS, EventKind, Match
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


def _style(fig: go.Figure, match: Match, *, height: int, y_title: str,
           x_title: str = "minute", **layout) -> go.Figure:
    fig.update_layout(
        template="plotly_white", height=height, hovermode="x unified",
        margin=dict(t=28, r=12, l=12, b=10), dragmode=False, **layout,
    )
    ticks_min = list(range(0, match.duration_s // 60 + 1, 10))
    if ticks_min[-1] != match.duration_s // 60:
        ticks_min.append(match.duration_s // 60)
    fig.update_xaxes(
        title=x_title, type="date", hoverformat="%Mm%Ss", fixedrange=True,
        range=[_dt(0), _dt(match.duration_s)], gridcolor=C_GRID,
        tickvals=_dt([m * 60 for m in ticks_min]), ticktext=[str(m) for m in ticks_min],
    )
    fig.update_yaxes(title=y_title, gridcolor=C_GRID, fixedrange=True)
    return fig


def momentum_figure(match: Match, meta, height: int = 300) -> go.Figure:
    """Rythme de marque lissé (moyenne mobile centrée 5 min, façon stats-hand v1)
    + zone colorée = équipe qui domine le rythme."""
    mom = momentum_series(match)
    x = _dt([p.minute * 60 for p in mom])
    rec = [p.rate_rec for p in mom]
    vis = [p.rate_vis for p in mom]
    lower = [min(a, b) for a, b in zip(rec, vis)]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=lower, line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(
        x=x, y=rec, name=meta.rec_name, line=dict(color=C_REC, width=2),
        fill="tonexty", fillcolor=C_REC_FILL,
        hovertemplate="%{y:.2f} but/min<extra>" + meta.rec_name + "</extra>"))
    fig.add_trace(go.Scatter(x=x, y=lower, line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(
        x=x, y=vis, name=meta.vis_name, line=dict(color=C_VIS, width=2),
        fill="tonexty", fillcolor=C_VIS_FILL,
        hovertemplate="%{y:.2f} but/min<extra>" + meta.vis_name + "</extra>"))
    fig.add_vline(x=_dt(30 * 60), line=dict(color=C_INK, width=1, dash="dot"))
    _style(fig, match, height=height, y_title="buts / min (lissé 5 min)",
           legend=dict(orientation="h", y=1.15))
    fig.update_yaxes(rangemode="tozero")
    return fig


# --------------------------------------------------------------------------- UI

st.title("🤾 Feuilles de match — visualisation")

files = st.file_uploader(
    "Feuilles de match (PDF FDME)", type="pdf", accept_multiple_files=True
)
if not files:
    st.info("Charge une ou plusieurs feuilles de match en PDF pour commencer.")
    st.stop()

matches: dict[str, Match] = {}
for f in files:
    try:
        m = _parse(f.name, f.getvalue())
        label = f"{m.meta.rec_name} {m.meta.score_final[0]}-{m.meta.score_final[1]} {m.meta.vis_name}"
        matches[f"{label}  ·  {f.name}"] = m
    except Exception as exc:  # noqa: BLE001
        st.error(f"{f.name} : échec du parsing — {exc}")

if not matches:
    st.stop()

key = st.selectbox("Match", list(matches)) if len(matches) > 1 else next(iter(matches))
match = matches[key]
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

tab_score, tab_periodes = st.tabs(["📈 Évolution du score", "🔑 Périodes clés"])

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
    fig.add_vline(x=_dt(30 * 60), line=dict(color=C_INK, width=1, dash="dot"),
                  annotation_text="mi-temps", annotation_position="top", annotation_yshift=-28)
    for e in match.events:
        if e.kind is EventKind.TIMEOUT:
            fig.add_vline(x=_dt(e.time_s), line=dict(color=C_GRID, width=1))
    _style(fig, match, height=420, y_title="buts", legend=dict(orientation="h", y=1.12))
    st.plotly_chart(fig, width='stretch')

    # différentiel de score (diverging : bleu = REC devant, orange = VIS devant)
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=df["t"], y=df["diff"].clip(lower=0), line=dict(color=C_REC, width=1, shape="hv"),
                              fill="tozeroy", fillcolor=C_REC_FILL, name=meta.rec_name,
                              hovertemplate="+%{y}<extra></extra>"))
    fig2.add_trace(go.Scatter(x=df["t"], y=df["diff"].clip(upper=0), line=dict(color=C_VIS, width=1, shape="hv"),
                              fill="tozeroy", fillcolor=C_VIS_FILL, name=meta.vis_name,
                              hovertemplate="%{y}<extra></extra>"))
    fig2.add_hline(y=0, line=dict(color=C_INK, width=1))
    _style(fig2, match, height=220, y_title="écart (buts)", showlegend=False)
    st.caption("Écart de score au fil du match")
    st.plotly_chart(fig2, width='stretch')

    # périodes clés — momentum
    st.caption("Périodes clés — rythme de marque lissé sur 5 min · la zone colorée marque l'équipe qui domine le rythme")
    st.plotly_chart(momentum_figure(match, meta, height=280), width='stretch')

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

    fig = momentum_figure(match, meta, height=360)
    for bw, color in ((bw_rec, C_REC), (bw_vis, C_VIS)):
        b = bw.best
        fig.add_vrect(x0=_dt(b.start_s), x1=_dt(b.end_s), fillcolor=color, opacity=0.10,
                      line_width=0, annotation_text=f"top {match.team_name(bw.team).split()[0]}",
                      annotation_position="top left", annotation_yshift=-28)
    st.plotly_chart(fig, width='stretch')

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
        col.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
