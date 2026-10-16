"""Accès à la base Supabase."""
import pandas as pd
import streamlit as st
from supabase import create_client


@st.cache_resource
def client():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


def ajouter_document(champs: dict):
    return client().table("documents").insert(champs).execute()


def liste_documents(avec_contenu=False) -> pd.DataFrame:
    colonnes = "*" if avec_contenu else (
        "id,titre,auteur,sous_theme,statut,annee,nom_fichier,nb_mots,nb_phrases,richesse_lexicale,"
        "lisibilite,nb_citations,nb_references,sections_detectees,mots_cles,sous_themes_detectes,date_depot"
    )
    rows = client().table("documents").select(colonnes).order("date_depot", desc=True).execute().data
    return pd.DataFrame(rows)


def supprimer_document(doc_id: int):
    client().table("documents").delete().eq("id", doc_id).execute()


def enregistrer_similarites(paires: list):
    client().table("similarites").delete().neq("id", 0).execute()  # on recalcule tout
    if paires:
        client().table("similarites").insert(paires).execute()


def liste_similarites() -> pd.DataFrame:
    rows = client().table("similarites").select("*").order("recouvrement", desc=True).execute().data
    return pd.DataFrame(rows)
