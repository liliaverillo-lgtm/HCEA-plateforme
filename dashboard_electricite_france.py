#!/usr/bin/env python3
"""
Dashboard — Modulation nucléaire par réacteur (France)
Normalisation par la puissance nominale IAEA PRIS

Usage :
    pip install entsoe-py pandas plotly streamlit
    streamlit run dashboard_electricite_france.py
"""

import warnings
warnings.filterwarnings("ignore")

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from entsoe import EntsoePandasClient
from datetime import datetime, timedelta
import math

# ═══════════════════════════════════════════════════════════════════
# 0. CONFIGURATION
# ═══════════════════════════════════════════════════════════════════
API_KEY           = "c5cb3857-bc40-4f4c-a4db-088946785b4a"
COUNTRY           = "FR"
TZ                = "Europe/Paris"
SEUIL_ON_PCT      = 5      # % de la puissance nominale — en dessous = arrêté
N_COLS_SPARKLINES = 4

# ───────────────────────────────────────────────────────────────────
# PUISSANCES NOMINALES NETTES (MWe) — Source : IAEA PRIS / ASNR
# Noms correspondant à la nomenclature ENTSO-E
# ───────────────────────────────────────────────────────────────────
PUISSANCE_NOMINALE_MW = {
    # ── Palier CP0 — Bugey (2 modèles différents au sein du même palier) ──
    "BUGEY 2": 910,  "BUGEY 3": 910,  "BUGEY 4": 880,  "BUGEY 5": 880,
    # ── Palier CPY — 900 MWe ──────────────────────────────────────
    "BLAYAIS 1": 910,    "BLAYAIS 2": 910,    "BLAYAIS 3": 910,    "BLAYAIS 4": 910,
    "CHINON 1": 905,     "CHINON 2": 905,     "CHINON 3": 905,     "CHINON 4": 905,
    "CRUAS 1": 915,      "CRUAS 2": 915,      "CRUAS 3": 915,      "CRUAS 4": 915,
    "DAMPIERRE 1": 890,  "DAMPIERRE 2": 890,  "DAMPIERRE 3": 890,  "DAMPIERRE 4": 890,
    "GRAVELINES 1": 910, "GRAVELINES 2": 910, "GRAVELINES 3": 910,
    "GRAVELINES 4": 910, "GRAVELINES 5": 910, "GRAVELINES 6": 910,
    "ST LAURENT 1": 915, "ST LAURENT 2": 915,
    "TRICASTIN 1": 915,  "TRICASTIN 2": 915,  "TRICASTIN 3": 915,  "TRICASTIN 4": 915,
    # ── Palier P4 — 1 300 MWe ────────────────────────────────────
    "FLAMANVILLE 1": 1310, "FLAMANVILLE 2": 1310,
    "PALUEL 1": 1330,      "PALUEL 2": 1330,      "PALUEL 3": 1330,  "PALUEL 4": 1330,
    "ST ALBAN 1": 1335,    "ST ALBAN 2": 1335,
    # ── Palier P'4 — 1 300 MWe ───────────────────────────────────
    "BELLEVILLE 1": 1310,  "BELLEVILLE 2": 1310,
    "CATTENOM 1": 1300,    "CATTENOM 2": 1300,  "CATTENOM 3": 1300,  "CATTENOM 4": 1300,
    "GOLFECH 1": 1310,     "GOLFECH 2": 1310,
    "NOGENT 1": 1310,      "NOGENT 2": 1310,
    "PENLY 1": 1320,       "PENLY 2": 1320,
    # ── Palier N4 — 1 450 MWe (net ~1 495-1 500 MWe) ─────────────
    "CHOOZ 1": 1500,   "CHOOZ 2": 1500,
    "CIVAUX 1": 1495,  "CIVAUX 2": 1495,
    # ── EPR ───────────────────────────────────────────────────────
    "FLAMANVILLE 3": 1630,
}

# ═══════════════════════════════════════════════════════════════════
# 1. INTERFACE
# ═══════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="☢️ Modulation nucléaire France",
    layout="wide",
    page_icon="☢️",
)
st.title("☢️ Modulation nucléaire par réacteur — France")
st.caption(
    "Production normalisée par la puissance nominale (IAEA PRIS) · "
    "Vert = puissance nominale · Noir = arrêt / forte modulation"
)

HIER = datetime.now().date() - timedelta(days=1)
start_date = HIER - timedelta(days=6)   # 7 jours glissants
end_date = HIER

with st.sidebar:
    st.header("📅 Période")
    st.info(f"📆 {start_date} → {end_date} (7 derniers jours)")
    lancer = st.button("🔄 Charger", type="primary", use_container_width=True)

if not lancer:
    st.info("👈 Choisissez une période et cliquez sur **Charger**.")
    st.stop()
if start_date > end_date:
    st.error("La date de début doit être antérieure à la date de fin.")
    st.stop()


# ═══════════════════════════════════════════════════════════════════
# 2. CHARGEMENT → DataFrame brut
# ═══════════════════════════════════════════════════════════════════
@st.cache_data(ttl=1800, show_spinner=False)
def charger_dataframes(start_str: str, end_str: str) -> pd.DataFrame:
    """
    Télécharge la production par réacteur (psr_type B14 = Nuclear).
    Retourne le DataFrame brut sans traitement.
    """
    client   = EntsoePandasClient(api_key=API_KEY)
    start_ts = pd.Timestamp(start_str + " 00:00", tz=TZ)
    end_ts   = pd.Timestamp(end_str   + " 23:59", tz=TZ)
    return client.query_generation_per_plant(
        country_code=COUNTRY,
        start=start_ts,
        end=end_ts,
        psr_type="B14",
    )


with st.spinner("⏳ Chargement ENTSO-E…"):
    try:
        df_brut = charger_dataframes(str(start_date), str(end_date))
    except Exception as e:
        st.error(f"Erreur de chargement : {e}")
        st.stop()

st.success(f"✅ Données chargées — {start_date} → {end_date}")


# ═══════════════════════════════════════════════════════════════════
# 3. TRAITEMENT
# ═══════════════════════════════════════════════════════════════════

def extraire_actual_aggregated(df: pd.DataFrame) -> pd.DataFrame:
    """Extrait uniquement les colonnes 'Actual Aggregated' du MultiIndex."""
    if isinstance(df.columns, pd.MultiIndex):
        niv0 = df.columns.get_level_values(0).astype(str)
        niv1 = df.columns.get_level_values(1).astype(str)
        masque1 = niv1.str.contains("Aggregated", case=False, na=False)
        masque0 = niv0.str.contains("Aggregated", case=False, na=False)
        if masque1.any():
            out = df.loc[:, masque1].copy()
            out.columns = out.columns.droplevel(1)
        elif masque0.any():
            out = df.loc[:, masque0].copy()
            out.columns = out.columns.droplevel(0)
        else:
            out = df.copy()
            out.columns = niv0
    else:
        out = df.copy()
    out.columns = [str(c) for c in out.columns]
    return out


# ── 3a. Production réelle (MW) ────────────────────────────────────
df_nuc = extraire_actual_aggregated(df_brut)
df_nuc = df_nuc.dropna(axis=1, how="all")
if df_nuc.columns.duplicated().any():
    df_nuc = df_nuc.T.groupby(level=0).max().T
df_nuc = df_nuc.resample("1h").mean().ffill().fillna(0)
df_nuc = df_nuc[sorted(df_nuc.columns)]

if df_nuc.empty or df_nuc.shape[1] == 0:
    st.error("Aucune donnée disponible. Essayez une période passée.")
    with st.expander("Debug — colonnes brutes"):
        st.write(list(df_brut.columns)[:20])
    st.stop()

reacteurs = df_nuc.columns.tolist()

# ── 3b. Normalisation par la puissance nominale → taux de charge (%) ──
# Pour les réacteurs absents du dictionnaire : fallback sur 900 MW
def get_pnom(nom: str) -> float:
    if nom in PUISSANCE_NOMINALE_MW:
        return PUISSANCE_NOMINALE_MW[nom]
    # Fallback : estimation par la production max observée (robuste)
    return max(df_nuc[nom].max(), 900.0)

serie_pnom = pd.Series(
    {r: get_pnom(r) for r in reacteurs},
    name="Pnom (MWe)"
)

# Taux de charge en % — plafonné à 105 % (quelques dépassements ponctuels possibles)
df_taux = (df_nuc.div(serie_pnom) * 100).clip(upper=105)

# ── 3c. Indicateurs ───────────────────────────────────────────────
taux_derniere    = df_taux.iloc[-1]
prod_derniere    = df_nuc.iloc[-1]
reacteurs_on     = int((taux_derniere >= SEUIL_ON_PCT).sum())
reacteurs_off    = int((taux_derniere <  SEUIL_ON_PCT).sum())
taux_moyen_fleet = taux_derniere[taux_derniere >= SEUIL_ON_PCT].mean()


# ═══════════════════════════════════════════════════════════════════
# 4. MÉTRIQUES
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("☢️ Production totale",       f"{prod_derniere.sum():,.0f} MW")
c2.metric("✅ En marche",               f"{reacteurs_on} réacteurs")
c3.metric("🔴 Arrêtés / < 5 %",        f"{reacteurs_off} réacteurs")
c4.metric("📊 Taux de charge moyen",   f"{taux_moyen_fleet:.1f} %")
c5.metric("⚡ Puissance nominale parc", f"{serie_pnom.sum() / 1e3:.1f} GW")
st.markdown("---")


# ═══════════════════════════════════════════════════════════════════
# 5. HEATMAP — Taux de charge par réacteur
# ═══════════════════════════════════════════════════════════════════
st.subheader("🔲 Heatmap — Taux de charge par réacteur (% de la puissance nominale)")
st.caption("🟢 Vert clair = proche de la puissance nominale (≥ 95 %) · ⚫ Noir = arrêt · 🟡 intermédiaire = modulation")

# Colorscale : noir → rouge foncé → orange → jaune-vert → vert clair
COLORSCALE_MODULATION = [
    [0.00, "rgb(5,5,5)"],          # 0 %   — arrêt total
    [0.04, "rgb(40,5,5)"],         # 4 %   — quasi arrêt
    [0.15, "rgb(120,20,0)"],       # 15 %  — très faible
    [0.30, "rgb(180,60,0)"],       # 30 %  — forte modulation
    [0.45, "rgb(200,120,0)"],      # 45 %  — modulation notable
    [0.60, "rgb(210,190,0)"],      # 60 %  — modulation modérée
    [0.75, "rgb(170,210,30)"],     # 75 %  — bon régime
    [0.88, "rgb(80,200,40)"],      # 88 %  — proche nominal
    [0.95, "rgb(30,220,60)"],      # 95 %  — très proche nominal
    [0.99, "rgb(10,230,70)"],      # 99 %  — quasi nominal
    [1.00, "rgb(0,255,80)"],       # 100 % — pleine puissance (vert vif restrictif)
]
fig_heatmap = go.Figure(go.Heatmap(
    z             = df_taux[reacteurs].T.values,
    x             = df_taux.index,
    y             = reacteurs,
    colorscale    = COLORSCALE_MODULATION,
    zmin          = 0,
    zmax          = 100,
    hoverongaps   = False,
    hovertemplate = (
        "<b>%{y}</b><br>%{x}<br>"
        "<b>%{z:.1f} % de la Pnom</b><extra></extra>"
    ),
    colorbar = dict(
        title      = "% Pnom",
        ticksuffix = " %",
        tickvals   = [0, 25, 50, 75, 100],
        tickfont   = dict(size=10),
    ),
))
fig_heatmap.update_layout(
    xaxis_title = "",
    yaxis       = dict(tickfont=dict(size=10), autorange="reversed"),
    template    = "plotly_dark",
    height      = max(420, len(reacteurs) * 14),
    margin      = dict(l=140, r=90, t=20, b=40),
)
st.plotly_chart(fig_heatmap, use_container_width=True, theme=None)


# ═══════════════════════════════════════════════════════════════════
# 6. SPARKLINES — Taux de charge individuel
# ═══════════════════════════════════════════════════════════════════
st.subheader("📈 Courbes individuelles — Taux de charge par réacteur")
st.caption("🟢 Vert = en marche · 🔴 Rouge = arrêté · Axe Y = % de la puissance nominale (IAEA PRIS)")

n_rows_spark = max(1, math.ceil(len(reacteurs) / N_COLS_SPARKLINES))

titres = [
    f"{r}\n{serie_pnom[r]:.0f} MW"
    for r in reacteurs
]

fig_spark = make_subplots(
    rows=n_rows_spark,
    cols=N_COLS_SPARKLINES,
    subplot_titles=titres,
    shared_xaxes=True,
    vertical_spacing=0.03,        # ← était 0.07 — CRITIQUE : réduire fortement
    horizontal_spacing=0.06,      # ← légère augmentation pour les labels Y
)


for idx, reacteur in enumerate(reacteurs):
    row = idx // N_COLS_SPARKLINES + 1
    col = idx %  N_COLS_SPARKLINES + 1
    serie_pct = df_taux[reacteur]
    en_marche = serie_pct.iloc[-1] >= SEUIL_ON_PCT
    couleur   = "#00C853" if en_marche else "#E53935"
    fill_col  = "rgba(0,200,83,0.15)" if en_marche else "rgba(229,57,53,0.15)"

    fig_spark.add_trace(
        go.Scatter(
            x             = serie_pct.index,
            y             = serie_pct.values,
            mode          = "lines",
            line          = dict(color=couleur, width=1.2),
            fill          = "tozeroy",
            fillcolor     = fill_col,
            name          = reacteur,
            showlegend    = False,
            customdata    = df_nuc[reacteur].values,
            hovertemplate = (
                f"<b>{reacteur}</b> (Pnom {serie_pnom[reacteur]:.0f} MW)<br>"
                "%{x}<br>"
                "<b>%{customdata:.0f} MW produits</b><br>"
                "<b>%{y:.1f} % Pnom</b><extra></extra>"
            ),
        ),
        row=row, col=col,
    )
    # Ligne de référence à 100 %
    fig_spark.add_hline(
        y=100, line_dash="dot",
        line_color="rgba(255,255,255,0.2)",
        line_width=0.8,
        row=row, col=col,
    )

fig_spark.update_layout(
    template="plotly_dark",
    height=max(800, n_rows_spark * 200),  # ← était 140 par ligne → 200
    hovermode="x unified",
    margin=dict(l=30, r=20, t=60, b=20),
)

fig_spark.update_annotations(font_size=9)
fig_spark.update_xaxes( showticklabels=False,
    showspikes=False,
    showgrid=False,
)
fig_spark.update_yaxes(  # ← garde les horizontales
    gridcolor="rgba(180,180,180,0.3)",      # ← grises et fines
    gridwidth=0.5,  
    showticklabels = True,
    ticksuffix     = "%",
    nticks         = 3,
    tickfont       = dict(size=9, color="#CCCCCC"),
    showgrid       = True,
    zeroline       = False,
    rangemode      = "tozero",   # commence toujours à 0, mais le haut s'adapte aux données
)

st.plotly_chart(fig_spark, use_container_width=True, theme=None)


# ═══════════════════════════════════════════════════════════════════
# 7. TABLEAU DE SYNTHÈSE
# ═══════════════════════════════════════════════════════════════════
with st.expander("📋 Tableau — taux de charge par réacteur (dernière valeur)"):
    df_table = pd.DataFrame({
        "Pnom (MWe)"       : serie_pnom,
        "Production (MW)"  : prod_derniere.round(0),
        "Taux de charge (%)": taux_derniere.round(1),
        "État"             : taux_derniere.apply(
            lambda x: "✅ En marche" if x >= SEUIL_ON_PCT else "🔴 Arrêté"
        ),
    }).sort_values("Taux de charge (%)", ascending=False)
    st.dataframe(df_table, use_container_width=True)

with st.expander("📋 Télécharger les données horaires (taux de charge %)"):
    csv = df_taux.to_csv().encode("utf-8")
    st.download_button(
        "⬇️ CSV — taux de charge horaire par réacteur",
        csv,
        file_name=f"modulation_nucleaire_FR_{start_date}_{end_date}.csv",
        mime="text/csv",
    )
