import json

import pandas as pd
import streamlit as st

import db
import textutils as tu

st.set_page_config(page_title="Réseau de recherche – Micro-finances et coopératives", page_icon="📚", layout="wide")

SOUS_THEMES = list(tu.SOUS_THEMES.keys())


def acces_admin() -> bool:
    """Les pages d'analyse sont protégées par un mot de passe (réservées aux responsables)."""
    if st.session_state.get("admin"):
        return True
    mdp = st.sidebar.text_input("Mot de passe responsable", type="password")
    if mdp and mdp == st.secrets.get("ADMIN_PASSWORD"):
        st.session_state["admin"] = True
        st.rerun()
    st.info("🔒 Cette page est réservée aux responsables de la synthèse. Entrez le mot de passe dans le menu de gauche.")
    return False


st.sidebar.title("📚 Réseau de recherche")
page = st.sidebar.radio("Menu", ["Déposer un texte", "Bibliothèque", "Analyse scientifique", "Antiplagiat", "Tableau de bord"])

# ------------------------------------------------------------------ Dépôt
if page == "Déposer un texte":
    st.title("Déposer un texte")
    st.write("Ouvrage : *Dynamiques macro-économiques, monétaires et financières en RDC*. "
             "Chapitre : **Micro-finances et coopératives d'épargne et de crédit**.")
    with st.form("depot", clear_on_submit=True):
        c1, c2 = st.columns(2)
        titre = c1.text_input("Titre du texte *")
        auteur = c2.text_input("Auteur(s) *")
        sous_theme = c1.selectbox("Sous-thème", ["(à déterminer automatiquement)"] + SOUS_THEMES)
        statut = c2.radio("Statut", ["non publié", "publié"], horizontal=True)
        annee = c1.number_input("Année", min_value=1980, max_value=2030, value=2026)
        fichier = st.file_uploader("Fichier (PDF, Word .docx ou .txt) *", type=["pdf", "docx", "txt"])
        envoyer = st.form_submit_button("Envoyer")
    if envoyer:
        if not (titre and auteur and fichier):
            st.error("Le titre, l'auteur et le fichier sont obligatoires.")
        else:
            texte = tu.extract_text(fichier.getvalue(), fichier.name)
            if len(texte.split()) < 50:
                st.error("Le texte extrait est presque vide. S'il s'agit d'un PDF scanné, envoyez une version Word ou texte.")
            else:
                a = tu.analyser(texte)
                if sous_theme.startswith("("):
                    sous_theme = tu.meilleur_sous_theme(a["sous_themes_detectes"])
                db.ajouter_document({"titre": titre, "auteur": auteur, "sous_theme": sous_theme, "statut": statut,
                                     "annee": int(annee), "nom_fichier": fichier.name, "contenu": texte, **a})
                st.success(f"Texte déposé ({a['nb_mots']} mots). Sous-thème : {sous_theme}. Merci !")

# ------------------------------------------------------------------ Bibliothèque
elif page == "Bibliothèque":
    st.title("Bibliothèque des textes")
    if acces_admin():
        df = db.liste_documents()
        if df.empty:
            st.info("Aucun texte déposé pour le moment.")
        else:
            f1, f2, f3 = st.columns(3)
            th = f1.multiselect("Sous-thème", sorted(df["sous_theme"].dropna().unique()))
            st_ = f2.multiselect("Statut", sorted(df["statut"].dropna().unique()))
            au = f3.text_input("Auteur contient")
            if th: df = df[df["sous_theme"].isin(th)]
            if st_: df = df[df["statut"].isin(st_)]
            if au: df = df[df["auteur"].str.contains(au, case=False, na=False)]
            st.dataframe(df[["id", "titre", "auteur", "sous_theme", "statut", "annee", "nb_mots", "date_depot"]],
                         use_container_width=True, hide_index=True)
            st.download_button("⬇️ Exporter en CSV", df.to_csv(index=False).encode("utf-8-sig"), "textes.csv", "text/csv")
            with st.expander("Supprimer un texte"):
                sid = st.number_input("ID du texte", min_value=0, step=1)
                if st.button("Supprimer définitivement") and sid:
                    db.supprimer_document(int(sid))
                    st.success("Texte supprimé.")
                    st.rerun()

# ------------------------------------------------------------------ Analyse
elif page == "Analyse scientifique":
    st.title("Analyse scientifique d'un texte")
    if acces_admin():
        df = db.liste_documents()
        if df.empty:
            st.info("Aucun texte à analyser.")
        else:
            choix = st.selectbox("Choisir un texte", df["id"], format_func=lambda i: f"#{i} – {df.set_index('id').loc[i, 'titre']}")
            d = df.set_index("id").loc[choix]
            c = st.columns(5)
            c[0].metric("Mots", d["nb_mots"])
            c[1].metric("Richesse lexicale", d["richesse_lexicale"], help="Mots distincts / mots totaux")
            c[2].metric("Lisibilité", d["lisibilite"], help="Kandel-Moles : plus c'est bas, plus c'est difficile (30-50 = texte universitaire)")
            c[3].metric("Citations", d["nb_citations"], help="Citations de type (Auteur, 2020) détectées")
            c[4].metric("Références", d["nb_references"], help="Lignes de bibliographie détectées")
            st.write(f"**Sections détectées :** {d['sections_detectees'] or 'aucune'}")
            manquantes = [s for s in ["introduction", "méthodologie", "résultats", "conclusion"] if s not in (d["sections_detectees"] or "")]
            if manquantes:
                st.warning("Sections attendues non détectées : " + ", ".join(manquantes))
            if d["nb_citations"] == 0:
                st.warning("Aucune citation de type (Auteur, année) détectée : vérifiez l'appareil scientifique.")
            st.write(f"**Mots-clés :** {d['mots_cles']}")
            scores = pd.Series(json.loads(d["sous_themes_detectes"]), name="Occurrences pour 1000 mots")
            st.subheader("Correspondance avec les sous-thèmes du chapitre")
            st.bar_chart(scores)

# ------------------------------------------------------------------ Antiplagiat
elif page == "Antiplagiat":
    st.title("Antiplagiat : comparaison entre les textes de l'équipe")
    if acces_admin():
        st.caption("Compare chaque texte aux autres (passages de 6 mots identiques + similarité du vocabulaire). "
                   "Un recouvrement élevé entre deux textes du même auteur est normal (réutilisation de ses propres travaux).")
        if st.button("▶️ Lancer / actualiser l'analyse"):
            docs = db.liste_documents(avec_contenu=True)
            if len(docs) < 2:
                st.warning("Il faut au moins deux textes.")
            else:
                paires = tu.comparer(dict(zip(docs["id"], docs["contenu"])))
                db.enregistrer_similarites([{**p, "doc_a": int(p["doc_a"]), "doc_b": int(p["doc_b"])} for p in paires])
                st.success(f"{len(paires)} comparaisons enregistrées.")
        sim = db.liste_similarites()
        docs = db.liste_documents()
        if sim.empty or docs.empty:
            st.info("Aucun résultat. Lancez l'analyse.")
        else:
            info = docs.set_index("id")
            sim = sim[sim["doc_a"].isin(info.index) & sim["doc_b"].isin(info.index)].copy()
            sim["Texte A"] = sim["doc_a"].map(info["titre"])
            sim["Auteur A"] = sim["doc_a"].map(info["auteur"])
            sim["Texte B"] = sim["doc_b"].map(info["titre"])
            sim["Auteur B"] = sim["doc_b"].map(info["auteur"])
            sim["Même auteur"] = sim["Auteur A"].str.lower().str.strip() == sim["Auteur B"].str.lower().str.strip()
            sim["Niveau"] = sim["recouvrement"].apply(tu.niveau)
            sim["Recouvrement"] = (sim["recouvrement"] * 100).round(1).astype(str) + " %"
            sim["Similarité vocabulaire"] = (sim["cosinus"] * 100).round(1).astype(str) + " %"
            st.dataframe(sim[["Niveau", "Texte A", "Auteur A", "Texte B", "Auteur B", "Même auteur", "Recouvrement", "Similarité vocabulaire"]],
                         use_container_width=True, hide_index=True)
            st.subheader("Passages communs")
            for _, r in sim.head(20).iterrows():
                passages = json.loads(r["passages"] or "[]")
                if passages and r["recouvrement"] >= 0.10:
                    with st.expander(f"{r['Niveau']} · {r['Texte A']} ↔ {r['Texte B']} ({r['Recouvrement']})"):
                        for p in passages:
                            st.write("• …" + p + "…")

# ------------------------------------------------------------------ Tableau de bord
else:
    st.title("Tableau de bord")
    if acces_admin():
        df = db.liste_documents()
        sim = db.liste_similarites()
        if df.empty:
            st.info("Aucun texte déposé pour le moment.")
        else:
            c = st.columns(5)
            c[0].metric("Textes déposés", len(df))
            c[1].metric("Auteurs", df["auteur"].nunique())
            c[2].metric("Mots au total", f"{int(df['nb_mots'].sum()):,}".replace(",", " "))
            c[3].metric("Publiés / non publiés", f"{(df['statut']=='publié').sum()} / {(df['statut']=='non publié').sum()}")
            risque = int((sim["recouvrement"] >= 0.30).sum()) if not sim.empty else 0
            c[4].metric("Paires à risque (≥30 %)", risque)

            g1, g2 = st.columns(2)
            g1.subheader("Textes par sous-thème")
            par_theme = df["sous_theme"].value_counts().reindex(SOUS_THEMES + ["Non déterminé"], fill_value=0)
            g1.bar_chart(par_theme)
            g2.subheader("Textes par auteur")
            g2.bar_chart(df["auteur"].value_counts())

            st.subheader("Couverture : sous-thèmes sans texte")
            vides = [t for t in SOUS_THEMES if par_theme.get(t, 0) == 0]
            st.success("Tous les sous-thèmes sont couverts.") if not vides else st.warning(", ".join(vides))

            st.subheader("Qualité scientifique par texte")
            q = df[["titre", "auteur", "nb_mots", "lisibilite", "nb_citations", "nb_references"]].copy()
            q["Alerte"] = q.apply(lambda r: "⚠️ peu de citations" if r["nb_citations"] < 3 else "✅", axis=1)
            st.dataframe(q, use_container_width=True, hide_index=True)

# ------------------------------------------------------------------ Pied de page (toutes les pages)
st.markdown("---")
st.markdown(
    "<div style='text-align:center; color:gray; font-size:0.9rem; padding:0.5rem 0 1rem 0;'>"
    "© Crispin Koko Learn for Build</div>",
    unsafe_allow_html=True,
)
