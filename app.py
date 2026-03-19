import os
import time
import requests
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import folium
from io import BytesIO
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

# --------------------------
# Config Streamlit
# --------------------------
@st.cache_data(show_spinner=False)
def load_dataframe(uploaded_file):
    """
    Charge un DataFrame depuis CSV ou Excel
    """
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    elif uploaded_file.name.endswith(".xlsx"):
        df = pd.read_excel(uploaded_file)
    else:
        raise ValueError("Format de fichier non supporté")

    return normalize_cols(df)

st.set_page_config(
    page_title="Marché immobilier — Web scraping",
    layout="wide",
)

st.title("🏠 Analyse du marché immobilier (Web Scraping + Python)")
st.caption(
    "Objectifs : nettoyer/structurer, analyser les tendances (prix, surface, localisation, type), "
    "visualiser via dashboard interactif + cartographie. "
)

# --------------------------
# Helpers
# --------------------------
def coerce_numeric(s):
    """Convertit en numérique en gérant virgules/strings."""
    if s is None:
        return s
    s = pd.to_numeric(
        pd.Series(s).astype(str).str.replace(",", ".", regex=False).str.replace(" ", "", regex=False),
        errors="coerce",
    )
    return s.iloc[0]

def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Uniformise un peu les colonnes (trim) et prépare des champs utiles."""
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]

    # Essayer de détecter colonnes probables (robuste)
    # On ne renomme pas de force, mais on crée des alias si besoin.
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if cl in ["adresse", "address"]:
            col_map[c] = "Adresse"
        if cl in ["ville", "city"]:
            col_map[c] = "ville"
        if cl in ["code", "cp", "code_postal", "postal_code", "zipcode"]:
            col_map[c] = "code"
        if cl in ["loyer", "rent", "prix", "price"]:
            col_map[c] = "Loyer"
        if cl in ["superficie_m2", "surface", "area", "superficie"]:
            col_map[c] = "Superficie_m2"
        if cl in ["prix_m2", "price_m2", "prixau_m2", "prix_mètre_carré"]:
            col_map[c] = "Prix_m2"
        if cl in ["type", "type_bien", "property_type"]:
            col_map[c] = "Type"
        if cl in ["departements", "departement", "dept"]:
            col_map[c] = "departements"
        if cl in ["code_region", "region_code"]:
            col_map[c] = "code_region"
        if cl in ["nom_region", "region", "region_name"]:
            col_map[c] = "nom_region"
        if cl in ["equipements", "équipements"]:
            col_map[c] = "Equipements"
        if cl in ["description", "desc"]:
            col_map[c] = "Description"

    df = df.rename(columns=col_map)

    # Casts numériques
    for num_col in ["Loyer", "Superficie_m2", "Prix_m2"]:
        if num_col in df.columns:
            df[num_col] = (
                df[num_col]
                .astype(str)
                .str.replace(",", ".", regex=False)
                .str.replace(" ", "", regex=False)
            )
            df[num_col] = pd.to_numeric(df[num_col], errors="coerce")

    # Si Prix_m2 absent mais Loyer & Superficie dispo
    if "Prix_m2" not in df.columns and {"Loyer", "Superficie_m2"}.issubset(df.columns):
        df["Prix_m2"] = df["Loyer"] / df["Superficie_m2"]

    # Adresse complète pour géocodage
    if {"Adresse", "ville", "code"}.issubset(df.columns):
        df["adresse_complete"] = (
            df["Adresse"].astype(str).str.strip() + ", " +
            df["code"].astype(str).str.strip() + " " +
            df["ville"].astype(str).str.strip()
        )
    else:
        df["adresse_complete"] = np.nan

    return df

@st.cache_data(show_spinner=False)
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    return normalize_cols(df)

def geocode_ban(address: str, sleep=0.05, retries=5):
    """Géocode via BAN France (api-adresse.data.gouv.fr) avec retries/backoff."""
    if not isinstance(address, str) or address.strip() == "" or address.lower() == "nan":
        return None, None, None

    url = "https://api-adresse.data.gouv.fr/search/"
    params = {"q": address, "limit": 1}

    for k in range(retries):
        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            feats = data.get("features", [])
            if not feats:
                return None, None, None
            coords = feats[0]["geometry"]["coordinates"]  # [lon, lat]
            score = feats[0]["properties"].get("score", None)
            lon, lat = coords[0], coords[1]
            time.sleep(sleep)
            return lat, lon, score
        except requests.exceptions.RequestException:
            time.sleep(0.5 * (2 ** k))
    return None, None, None

def geocode_with_cache(df: pd.DataFrame, cache_path="geocache_ban.csv", max_rows=None):
    """Ajoute lat/lon via BAN + cache disque (CSV) pour éviter de re-géocoder."""
    if "adresse_complete" not in df.columns:
        return df

    work = df.copy()

    # Option : limiter le nombre d'adresses à géocoder (si dataset énorme)
    if max_rows is not None:
        work = work.head(max_rows).copy()

    # Charger cache
    if os.path.exists(cache_path):
        cache = pd.read_csv(cache_path)
    else:
        cache = pd.DataFrame(columns=["adresse_complete", "lat", "lon", "score"])

    cache = cache.drop_duplicates("adresse_complete").set_index("adresse_complete")

    lats, lons, scores = [], [], []
    new_rows = []

    for addr in work["adresse_complete"].astype(str).tolist():
        if addr in cache.index:
            lat, lon, sc = cache.loc[addr, ["lat", "lon", "score"]].tolist()
        else:
            lat, lon, sc = geocode_ban(addr)
            new_rows.append({"adresse_complete": addr, "lat": lat, "lon": lon, "score": sc})
        lats.append(lat); lons.append(lon); scores.append(sc)

    work["lat"] = lats
    work["lon"] = lons
    work["ban_score"] = scores

    # Save cache
    if new_rows:
        cache_out = pd.concat([cache.reset_index(), pd.DataFrame(new_rows)], ignore_index=True)
        cache_out = cache_out.drop_duplicates("adresse_complete")
        cache_out.to_csv(cache_path, index=False)

    return work

# --------------------------
# Sidebar: data source
# --------------------------
st.sidebar.header("📦 Données")

uploaded = st.sidebar.file_uploader("C:/Users/kyoan/Documents/Python_Sorbonne/Python_webscrapping/logements_étudiants_complet.xls", type=["csv"])

default_path = "C:/Users/kyoan/Documents/Python_Sorbonne/Python_webscrapping/logements_étudiants_complet.xls"
if uploaded is not None:
    df = load_dataframe(uploaded)
else:
    if not os.path.exists(default_path):
        st.warning("Ajoute un fichier CSV dans data/logements.csv ou charge-le via la sidebar.")
        st.stop()
    df = load_data(default_path)

st.sidebar.divider()
st.sidebar.header("🎛️ Filtres")

# --------------------------
# Filters
# --------------------------
df_f = df.copy()

# Type
if "Type" in df_f.columns:
    types = sorted([t for t in df_f["Type"].dropna().unique().tolist() if str(t).strip() != ""])
    selected_types = st.sidebar.multiselect("Type de bien", types, default=types[:10] if len(types) > 10 else types)
    if selected_types:
        df_f = df_f[df_f["Type"].isin(selected_types)]

# Région
if "nom_region" in df_f.columns:
    regs = sorted([r for r in df_f["nom_region"].dropna().unique().tolist() if str(r).strip() != ""])
    selected_regs = st.sidebar.multiselect("Région", regs, default=regs)
    if selected_regs:
        df_f = df_f[df_f["nom_region"].isin(selected_regs)]

# Surface
if "Superficie_m2" in df_f.columns:
    smin = float(np.nanmin(df_f["Superficie_m2"].values)) if df_f["Superficie_m2"].notna().any() else 0.0
    smax = float(np.nanmax(df_f["Superficie_m2"].values)) if df_f["Superficie_m2"].notna().any() else 0.0
    surface_range = st.sidebar.slider("Surface (m²)", min_value=float(smin), max_value=float(smax), value=(float(smin), float(smax)))
    df_f = df_f[df_f["Superficie_m2"].between(surface_range[0], surface_range[1])]

# Prix/m²
if "Prix_m2" in df_f.columns:
    pmin = float(np.nanmin(df_f["Prix_m2"].values)) if df_f["Prix_m2"].notna().any() else 0.0
    pmax = float(np.nanmax(df_f["Prix_m2"].values)) if df_f["Prix_m2"].notna().any() else 0.0
    prixm2_range = st.sidebar.slider("Prix / m²", min_value=float(pmin), max_value=float(pmax), value=(float(pmin), float(pmax)))
    df_f = df_f[df_f["Prix_m2"].between(prixm2_range[0], prixm2_range[1])]

st.sidebar.divider()
do_geocode = st.sidebar.checkbox("🗺️ Activer la carte (géocodage BAN + cache)", value=False)
max_geocode = st.sidebar.number_input("Limiter le géocodage (nb lignes, 0 = tout)", min_value=0, value=300, step=50)

# --------------------------
# KPIs (Objectif: tendances)
# --------------------------
col1, col2, col3, col4 = st.columns(4)

n = len(df_f)
col1.metric("Annonces (filtrées)", f"{n:,}".replace(",", " "))

if "Prix_m2" in df_f.columns and df_f["Prix_m2"].notna().any():
    col2.metric("Prix/m² moyen", f"{df_f['Prix_m2'].mean():.2f}")
    col3.metric("Médiane prix/m²", f"{df_f['Prix_m2'].median():.2f}")
else:
    col2.metric("Prix/m² moyen", "—")
    col3.metric("Médiane prix/m²", "—")

if "Superficie_m2" in df_f.columns and df_f["Superficie_m2"].notna().any():
    col4.metric("Surface moyenne (m²)", f"{df_f['Superficie_m2'].mean():.1f}")
else:
    col4.metric("Surface moyenne (m²)", "—")

st.divider()

# --------------------------
# Tabs
# --------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "📌 Problématique",
    "📊 Analyses",
    "🗺️ Carte (adresses)",
    "🧾 Données",
])

# --------------------------
# TAB 1 — Problématique (réponse structurée)
# --------------------------
with tab1:
    st.subheader("Problématique")
    st.write("**Comment le prix au m² varie-t-il selon la localisation, la surface et le type de bien en France ?**")

    st.markdown("### 1) Localisation")
    if "nom_region" in df_f.columns and "Prix_m2" in df_f.columns:
        grp = (
            df_f.dropna(subset=["nom_region", "Prix_m2"])
            .groupby("nom_region")["Prix_m2"]
            .agg(["mean", "median", "count"])
            .sort_values("mean", ascending=False)
        )
        st.dataframe(grp, use_container_width=True)

    st.markdown("### 2) Type de bien")
    if "Type" in df_f.columns and "Prix_m2" in df_f.columns:
        grp2 = (
            df_f.dropna(subset=["Type", "Prix_m2"])
            .groupby("Type")["Prix_m2"]
            .agg(["mean", "median", "count"])
            .sort_values("mean", ascending=False)
        )
        st.dataframe(grp2, use_container_width=True)

    st.markdown("### 3) Surface")
    if {"Superficie_m2", "Prix_m2"}.issubset(df_f.columns):
        tmp = df_f.dropna(subset=["Superficie_m2", "Prix_m2"]).copy()
        # catégories de surface
        bins = [0, 15, 25, 35, 50, 70, 100, 150, 10_000]
        labels = ["<=15", "15-25", "25-35", "35-50", "50-70", "70-100", "100-150", "150+"]
        tmp["surface_bin"] = pd.cut(tmp["Superficie_m2"], bins=bins, labels=labels, include_lowest=True)
        grp3 = tmp.groupby("surface_bin")["Prix_m2"].agg(["mean", "median", "count"])
        st.dataframe(grp3, use_container_width=True)

# --------------------------
# TAB 2 — Analyses (Objectifs: tendance + viz)
# --------------------------
with tab2:
    left, right = st.columns([1.2, 1])

    with left:
        st.subheader("Distribution des prix/m²")
        if "Prix_m2" in df_f.columns:
            fig = px.histogram(df_f, x="Prix_m2", nbins=40)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Colonne Prix_m2 introuvable.")

        st.subheader("Relation surface vs prix/m²")
        if {"Superficie_m2", "Prix_m2"}.issubset(df_f.columns):
            fig2 = px.scatter(
                df_f.dropna(subset=["Superficie_m2", "Prix_m2"]),
                x="Superficie_m2",
                y="Prix_m2",
                color="nom_region" if "nom_region" in df_f.columns else None,
                hover_data=["ville", "Adresse"] if {"ville", "Adresse"}.issubset(df_f.columns) else None,
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Il manque Superficie_m2 et/ou Prix_m2.")

    with right:
        st.subheader("Top villes (prix/m² moyen)")
        if {"ville", "Prix_m2"}.issubset(df_f.columns):
            top_v = (
                df_f.dropna(subset=["ville", "Prix_m2"])
                .groupby("ville")["Prix_m2"]
                .agg(["mean", "count"])
                .query("count >= 2")
                .sort_values("mean", ascending=False)
                .head(15)
                .reset_index()
            )
            fig3 = px.bar(top_v, x="mean", y="ville", orientation="h")
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("Il manque ville et/ou Prix_m2.")

        st.subheader("Comparaison par type")
        if {"Type", "Prix_m2"}.issubset(df_f.columns):
            tmp = df_f.dropna(subset=["Type", "Prix_m2"])
            fig4 = px.box(tmp, x="Type", y="Prix_m2")
            st.plotly_chart(fig4, use_container_width=True)
        else:
            st.info("Il manque Type et/ou Prix_m2.")

# --------------------------
# TAB 3 — Carte (Objectifs: visualiser adresses)
# --------------------------
with tab3:
    st.subheader("Carte des annonces (géocodage BAN + cache local)")

    if not do_geocode:
        st.info("Active l’option dans la sidebar : **🗺️ Activer la carte**.")
    else:
        if max_geocode == 0:
            max_rows = None
        else:
            max_rows = int(max_geocode)

        with st.spinner("Géocodage en cours (BAN) + cache…"):
            df_geo = geocode_with_cache(df_f, cache_path="geocache_ban.csv", max_rows=max_rows)
            
        df_geo_ok = df_geo.dropna(subset=["lat", "lon"]).copy()

        st.write(f"✅ Points affichés : **{len(df_geo_ok)}** / {len(df_geo)} (filtrés)")

        # Carte
        m = folium.Map(location=[46.6, 2.5], zoom_start=6)
        cluster = MarkerCluster().add_to(m)

        for _, r in df_geo_ok.iterrows():
            popup = []
            if "Adresse" in df_geo_ok.columns:
                popup.append(f"<b>{r.get('Adresse','')}</b>")
            if {"code", "ville"}.issubset(df_geo_ok.columns):
                popup.append(f"{r.get('code','')} {r.get('ville','')}")
            if "Superficie_m2" in df_geo_ok.columns:
                popup.append(f"Surface: {r.get('Superficie_m2','')} m²")
            if "Prix_m2" in df_geo_ok.columns:
                popup.append(f"Prix/m²: {r.get('Prix_m2','')}")
            if "Loyer" in df_geo_ok.columns:
                popup.append(f"Loyer/Prix: {r.get('Loyer','')}")
            if "Type" in df_geo_ok.columns:
                popup.append(f"Type: {r.get('Type','')}")

            # Texte affiché AU SURVOL
            tooltip_text = f"""
            Prix : {r.get('Loyer', 'NA')} €<br>
            Prix / m² : {round(r.get('Prix_m2', 0), 2)} €<br>
            Surface : {r.get('Superficie_m2', 'NA')} m²
            """

            # Texte affiché AU CLIC (optionnel, plus détaillé)
            popup_text = f"""
            <b>{r.get('Adresse','')}</b><br>
            {r.get('code','')} {r.get('ville','')}<br>
            Type : {r.get('Type','')}<br>
            Équipements : {r.get('Equipements','')}
            """ 
            folium.CircleMarker(
            location=[r["lat"], r["lon"]],
            radius=5,
            color="blue",
            fill=True,
            fill_opacity=0.7,
            tooltip=folium.Tooltip(tooltip_text, sticky=True),
            popup=folium.Popup(popup_text, max_width=300),
        ).add_to(cluster)

        st_folium(m, width=None, height=600)

# --------------------------
# TAB 4 — Données
# --------------------------
with tab4:
    st.subheader("Aperçu des données (après nettoyage + filtres)")
    st.dataframe(df_f, use_container_width=True)

    st.download_button(
        "Télécharger le dataset filtré (CSV)",
        data=df_f.to_csv(index=False).encode("utf-8"),
        file_name="logements_filtre.csv",
        mime="text/csv",
    )

st.caption("🧠 Astuce : le géocodage est mis en cache dans geocache_ban.csv pour ne pas refaire les requêtes.")
