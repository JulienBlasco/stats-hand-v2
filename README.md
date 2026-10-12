# stats-hand-v2

Traitement de **feuilles de match électroniques (FDME)** de handball en PDF et
visualisation web.

## Utilisation

```bash
uv sync

# App web
uv run streamlit run stats_hand/app.py

# CLI de debug : parse un PDF et sort le match en JSON
uv run python main.py data/WAGQTMD.pdf

# Tests (sur les PDF de data/)
uv run pytest
```

## Architecture

| Module | Rôle |
|---|---|
| `stats_hand/parsing/pdf.py` | extraction pdfplumber (texte + mots positionnés, gestion 2 colonnes) |
| `stats_hand/parsing/metadata.py` | en-tête : équipes, date, compétition, score final + mi-temps |
| `stats_hand/parsing/roster.py` | effectifs + officiels (parsing par coordonnées des colonnes) |
| `stats_hand/parsing/timeline.py` | « Déroulé du match » → liste d'évènements bruts |
| `stats_hand/parsing/match.py` | assemblage + résolution de l'équipe de chaque évènement |
| `stats_hand/analysis/score.py` | évolution du score, écarts, égalités, changements de leader |
| `stats_hand/analysis/periods.py` | momentum lissé (moyenne mobile centrée 5 min, cf. v1), fenêtres 10 min, séries de buts |
| `stats_hand/analysis/box_score.py` | box score par joueur reconstruit depuis le déroulé (buts, tirs/arrêts si détaillés, sanctions) + cumul multi-feuilles par licence |
| `stats_hand/app.py` | app Streamlit (onglets : évolution du score, périodes clés) |

## Notes sur le format FDME

- La ligne d'action du déroulé ne contient **ni numéro ni équipe**. L'équipe d'un
  but se déduit du delta de score ; pour les autres actions, le nom est résolu
  contre les deux effectifs + les officiels.
- Le déroulé est mis en **2 colonnes** (colonne gauche entière puis colonne droite).
- Le temps passe en `H:MM:SS` à la 60ᵉ minute (`01:00:00`).
- Selon le niveau de compétition, le déroulé détaille aussi les **tirs manqués**
  (`Tir NOM`) et les **arrêts** (`Arrêt NOM`) : la colonne « Tirs » de la feuille vaut
  alors buts + tirs manqués. Sans ces lignes, tirs et arrêts ne sont pas affichés.
- Le bloc « Détail score » a parfois ses libellés en texte vertical non extractible :
  on se repère sur la ligne de nombres (dernier couple = score final).
