#!/usr/bin/env python3
"""
Dashboard — Production nucléaire par réacteur (France)
Source : ENTSO-E Transparency Platform

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
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════
API_KEY           = "c5cb3857-bc40-4f4c-a4db-088946785b4a"
COUNTRY           = "FR"
TZ                = "Europe/Paris"
SEUIL_ON_MW       = 50
COULEUR_ON        = "#00C853"
COULEUR_OFF       = "#E53935"
COULEUR_ON_FILL   = "rgba(0,200,83,0.15)"
COULEUR_OFF_FILL  = "rgba(229,57,53,0.15)"
N_COLS_SPARKLINES = 4

# ═══════════════════════════════════════════════════════════════════
# INTERFACE
# ═══════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="☢️ Réacteurs nucléaires France",
    layout="wide",
    page_icon="☢️",
)
st.title("☢️ Production nucléaire par réacteur — France")
st.caption("Source : ENTSO-E Transparency Platform · psr_type B14 (Nuclear)")

# Note : ENTSO-E publie les données avec ~1 jour de délai.
# La date d'aujourd'hui retourne souvent des données vides.
HIER = datetime.now().date() - timedelta(days=1)

with st.sidebar:
    st.header("📅 Période")
    st.caption("ℹ️ Les données du jour en cours sont parfois disponibles avec quelques heures de délai.")
    start_date = st.date_input(
        "Début",
        value=HIER - timedelta(days=2),
        max_value=datetime.now().date(),
    )
    end_date = st.date_input(
        "Fin",
        value=HIER,
        max_value=datetime.now().date(),
    )
    nb_jours = (end_date - start_date).days + 1
    st.info(f"📆 {nb_jours} jour(s)")
    if nb_jours > 14:
        st.warning("⚠️ Au-delà de 14 jours le chargement peut être lent.")
    lancer = st.button("🔄 Charger", type="primary", use_container_width=True)

if not lancer:
    st.info("👈 Choisissez une période puis cliquez sur **Charger**.")
    st.stop()
if start_date > end_date:
    st.error("La date de début doit être antérieure à la date de fin.")
    st.stop()


# ═══════════════════════════════════════════════════════════════════
# CHARGEMENT → DataFrame brut
# ═══════════════════════════════════════════════════════════════════
@st.cache_data(ttl=1800, show_spinner=False)
def charger_dataframes(start_str: str, end_str: str) -> pd.DataFrame:
    """
    Télécharge la production par réacteur nucléaire (psr_type B14).
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


with st.spinner("⏳ Chargement ENTSO-E (production par réacteur)…"):
    try:
        df_brut = charger_dataframes(str(start_date), str(end_date))
    except Exception as e:
        st.error(f"Erreur lors du chargement : {e}")
        st.stop()

st.success(f"✅ Données chargées — {start_date} → {end_date}")


# ═══════════════════════════════════════════════════════════════════
# TRAITEMENT DU DataFrame
# ═══════════════════════════════════════════════════════════════════
# query_generation_per_plant renvoie un MultiIndex (réacteur, type_mesure)
# On garde uniquement les colonnes "Actual Aggregated" (pas "Actual Consumption")
# en cherchant le mot "Aggregated" dans les valeurs du niveau qui le contient.

def extraire_actual_aggregated(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extrait uniquement les colonnes de production réelle ('Actual Aggregated')
    quel que soit l'ordre des niveaux du MultiIndex.
    """
    if isinstance(df.columns, pd.MultiIndex):
        niv0 = df.columns.get_level_values(0).astype(str)
        niv1 = df.columns.get_level_values(1).astype(str)

        # Chercher "Aggregated" dans chaque niveau
        masque_niv1 = niv1.str.contains("Aggregated", case=False, na=False)
        masque_niv0 = niv0.str.contains("Aggregated", case=False, na=False)

        if masque_niv1.any():
            # Cas standard : niveau 1 = type de mesure, niveau 0 = nom réacteur
            out = df.loc[:, masque_niv1].copy()
            out.columns = out.columns.droplevel(1)
        elif masque_niv0.any():
            # Cas inversé : niveau 0 = type de mesure, niveau 1 = nom réacteur
            out = df.loc[:, masque_niv0].copy()
            out.columns = out.columns.droplevel(0)
        else:
            # Aucun filtre possible → prendre toutes les colonnes,
            # utiliser le niveau 0 comme nom de colonne
            out = df.copy()
            out.columns = niv0
    else:
        out = df.copy()

    out.columns = [str(c) for c in out.columns]
    return out


df_nuc = extraire_actual_aggregated(df_brut)

# Vérification : données non vides
if df_nuc.empty or df_nuc.shape[1] == 0:
    st.error(
        "Aucune donnée disponible pour cette période. "
        "ENTSO-E publie les données avec ~1 jour de délai — "
        "essayez une période se terminant avant-hier."
    )
    with st.expander("🔍 Debug — colonnes brutes reçues de l'API"):
        st.write(list(df_brut.columns)[:20])
    st.stop()

# Nettoyage : colonnes entièrement vides
df_nuc = df_nuc.dropna(axis=1, how="all")

# Gérer les doublons de noms (même réacteur avec Aggregated + Consumption)
# On garde la valeur max par colonne (= la production réelle, pas la consommation STEP)
if df_nuc.columns.duplicated().any():
    df_nuc = df_nuc.T.groupby(level=0).max().T

# Rééchantillonner à 1h
df_nuc = df_nuc.resample("1h").mean().ffill().fillna(0)

# Tri alphabétique (sans reindex pour éviter l'erreur sur doublons résiduels)
df_nuc = df_nuc[sorted(df_nuc.columns)]

if df_nuc.empty or df_nuc.shape[1] == 0:
    st.error("Le DataFrame est vide après traitement.")
    st.stop()

reacteurs     = df_nuc.columns.tolist()
prod_derniere = df_nuc.iloc[-1]
reacteurs_on  = int((prod_derniere >= SEUIL_ON_MW).sum())
reacteurs_off = int((prod_derniere <  SEUIL_ON_MW).sum())
nuc_total_mw  = prod_derniere.sum()


# ═══════════════════════════════════════════════════════════════════
# MÉTRIQUES
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
c1, c2, c3, c4 = st.columns(4)
c1.metric("☢️ Production totale", f"{nuc_total_mw:,.0f} MW")
c2.metric("✅ En marche",         f"{reacteurs_on} réacteurs")
c3.metric("🔴 Arrêtés",          f"{reacteurs_off} réacteurs")
c4.metric("📊 Total réacteurs",  f"{len(reacteurs)}")
st.markdown("---")


# ═══════════════════════════════════════════════════════════════════
# GRAPHIQUE 1 — Heatmap
# ═══════════════════════════════════════════════════════════════════
st.subheader("🔲 Heatmap — Production par réacteur au fil du temps")
st.caption("Vert foncé = production nominale · Noir = arrêt complet")

fig_heatmap = go.Figure(go.Heatmap(
    z          = df_nuc[reacteurs].T.values,
    x          = df_nuc.index,
    y          = reacteurs,
    colorscale = [
        [0.00, "rgb(10,10,10)"],
        [0.04, "rgb(80,10,10)"],
        [0.30, "rgb(0,80,30)"],
        [0.65, "rgb(0,160,60)"],
        [1.00, "rgb(0,220,90)"],
    ],
    hoverongaps   = False,
    hovertemplate = "<b>%{y}</b><br>%{x}<br><b>%{z:.0f} MW</b><extra></extra>",
    colorbar      = dict(title="MW", tickfont=dict(size=10)),
))
fig_heatmap.update_layout(
    xaxis_title = "",
    yaxis       = dict(tickfont=dict(size=10), autorange="reversed"),
    template    = "plotly_dark",
    height      = max(420, len(reacteurs) * 14),
    margin      = dict(l=140, r=80, t=20, b=40),
)
st.plotly_chart(fig_heatmap, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
# GRAPHIQUE 2 — Sparklines individuelles
# ═══════════════════════════════════════════════════════════════════
st.subheader("📈 Courbes individuelles par réacteur")
st.caption("🟢 Vert = en marche (dernière valeur ≥ 50 MW) · 🔴 Rouge = arrêté")

n_rows_spark = max(1, math.ceil(len(reacteurs) / N_COLS_SPARKLINES))

fig_spark = make_subplots(
    rows               = n_rows_spark,
    cols               = N_COLS_SPARKLINES,
    subplot_titles     = reacteurs,
    shared_xaxes       = True,
    vertical_spacing   = 0.06,
    horizontal_spacing = 0.04,
)

for idx, reacteur in enumerate(reacteurs):
    row       = idx // N_COLS_SPARKLINES + 1
    col       = idx %  N_COLS_SPARKLINES + 1
    serie     = df_nuc[reacteur]
    en_marche = serie.iloc[-1] >= SEUIL_ON_MW
    couleur   = COULEUR_ON   if en_marche else COULEUR_OFF
    fill_col  = COULEUR_ON_FILL if en_marche else COULEUR_OFF_FILL

    fig_spark.add_trace(
        go.Scatter(
            x             = serie.index,
            y             = serie.values,
            mode          = "lines",
            line          = dict(color=couleur, width=1.2),
            fill          = "tozeroy",
            fillcolor     = fill_col,
            name          = reacteur,
            showlegend    = False,
            hovertemplate = f"<b>{reacteur}</b>: %{{y:.0f}} MW<extra></extra>",
        ),
        row=row, col=col,
    )

fig_spark.update_layout(
    template  = "plotly_dark",
    height    = max(500, n_rows_spark * 130),
    hovermode = "x unified",
    margin    = dict(l=20, r=20, t=40, b=20),
)
fig_spark.update_annotations(font_size=9)
fig_spark.update_xaxes(showticklabels=False)
fig_spark.update_yaxes(showticklabels=False)

st.plotly_chart(fig_spark, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
# DONNÉES BRUTES
# ═══════════════════════════════════════════════════════════════════
with st.expander("📋 Tableau — dernière valeur par réacteur"):
    df_table = prod_derniere.sort_values(ascending=False).rename("MW").to_frame()
    df_table["État"] = df_table["MW"].apply(
        lambda x: "✅ En marche" if x >= SEUIL_ON_MW else "🔴 Arrêté"
    )
    st.dataframe(df_table.round(0), use_container_width=True)

with st.expander("📋 Télécharger les données horaires complètes"):
    csv = df_nuc.to_csv().encode("utf-8")
    st.download_button(
        "⬇️ CSV — production horaire par réacteur",
        csv,
        file_name=f"nucleaire_reacteurs_FR_{start_date}_{end_date}.csv",
        mime="text/csv",
    )
