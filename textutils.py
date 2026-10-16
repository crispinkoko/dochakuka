"""Extraction de texte, analyse scientifique et antiplagiat (comparaison entre textes)."""
import io
import json
import re
from collections import Counter

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

SOUS_THEMES = {
    "Viabilité financière": ["viabilité", "rentabilité", "autosuffisance", "pérennité", "équilibre financier", "portefeuille", "rendement"],
    "Performance sociale": ["performance sociale", "impact social", "pauvreté", "bien-être", "femmes", "réduction de la pauvreté", "clients"],
    "Gouvernance": ["gouvernance", "conseil d'administration", "gestion", "transparence", "contrôle", "dirigeants", "assemblée générale"],
    "Gestion des risques": ["risque", "risques", "impayés", "défaut", "garantie", "provision", "taux de remboursement"],
    "Mobilisation de l'épargne": ["épargne", "dépôts", "collecte", "mobilisation", "épargnants", "livret"],
    "Inclusion financière": ["inclusion financière", "accès aux services", "exclusion", "bancarisation", "inclusion"],
    "Financement des PME et digitalisation": ["pme", "digitalisation", "mobile money", "numérique", "mobile banking", "fintech", "crédit aux pme"],
    "AVECS dans le système financier": ["avec", "avecs", "associations villageoises", "tontine", "épargne et de crédit", "informel"],
}

STOPWORDS = set("""
alors au aucuns aussi autre avant avec avoir bon car ce cela ces ceux chaque ci comme comment dans des du dedans dehors depuis
devrait doit donc dos début elle elles en encore essai est et eu fait faites fois font hors ici il ils je juste la le les leur là ma
maintenant mais mes mine moins mon mot même ni nommés notre nous ou où par parce pas peu peut pour pourquoi quand que quel quelle
quelles quels qui sa sans ses seulement si sien son sont sous soyez sujet sur ta tandis tellement tels tes ton tous tout trop très
tu voient vont votre vous vu ça étaient état étions été être cette aux ont été sera seront ainsi entre plus dont selon cadre
ainsi lors afin ses leurs être avait avaient sont fait faire peut peuvent sont déjà ceux celles notamment également
introduction conclusion résultats méthodologie bibliographie références discussion
""".split())

SECTIONS = ["introduction", "revue de la littérature", "méthodologie", "résultats", "discussion", "conclusion", "bibliographie", "références"]


# ---------- Extraction ----------
def extract_text(data: bytes, filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
    elif name.endswith(".docx"):
        from docx import Document
        doc = Document(io.BytesIO(data))
        text = "\n".join(p.text for p in doc.paragraphs)
    else:
        for enc in ("utf-8", "latin-1"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
    return re.sub(r"[ \t]+", " ", text).strip()


# ---------- Analyse scientifique ----------
def _mots(text):
    return re.findall(r"[a-zàâäçéèêëîïôöùûüœ'’-]{2,}", text.lower())


def _syllabes(mot):
    return max(1, len(re.findall(r"[aeiouyàâäéèêëîïôöùûüœ]+", mot)))


def analyser(text: str) -> dict:
    mots = _mots(text)
    phrases = [s for s in re.split(r"[.!?]+\s", text) if len(s.split()) > 2]
    nb_mots, nb_phrases = len(mots), max(1, len(phrases))
    richesse = round(len(set(mots)) / nb_mots, 3) if nb_mots else 0.0

    # Indice de lisibilité de Kandel et Moles (adaptation française de Flesch) : 0 difficile -> 100 facile
    if nb_mots:
        syl = sum(_syllabes(m) for m in mots) / nb_mots
        lisibilite = round(207 - 1.015 * (nb_mots / nb_phrases) - 73.6 * syl, 1)
    else:
        lisibilite = 0.0

    # Citations de type (Auteur, 2020) ou (Auteur et al., 2020)
    citations = re.findall(r"\(([A-ZÉ][^()]{1,60}?),?\s(19|20)\d{2}[a-z]?\)", text)
    # Lignes de références : "Nom, X. (2015)" ou "Nom (2015)"
    refs = re.findall(r"^[A-ZÉ][\w'’\- ]+,?[^\n]{0,60}\(?(19|20)\d{2}\)?[.,]", text, flags=re.M)

    low = text.lower()
    sections = [s for s in SECTIONS if re.search(rf"^\W*(\d+[.\s]*)?{s}", low, flags=re.M)]

    freq = Counter(m for m in mots if m not in STOPWORDS and len(m) > 3)
    mots_cles = [m for m, _ in freq.most_common(10)]

    scores = {}
    for theme, termes in SOUS_THEMES.items():
        c = sum(len(re.findall(rf"\b{re.escape(t)}", low)) for t in termes)
        scores[theme] = round(1000 * c / nb_mots, 2) if nb_mots else 0.0  # occurrences pour 1000 mots

    return {
        "nb_mots": nb_mots, "nb_phrases": nb_phrases, "richesse_lexicale": richesse,
        "lisibilite": lisibilite, "nb_citations": len(citations), "nb_references": len(refs),
        "sections_detectees": ", ".join(sections), "mots_cles": ", ".join(mots_cles),
        "sous_themes_detectes": json.dumps(scores, ensure_ascii=False),
    }


def meilleur_sous_theme(scores_json: str) -> str:
    try:
        scores = json.loads(scores_json)
        theme, val = max(scores.items(), key=lambda x: x[1])
        return theme if val > 0 else "Non déterminé"
    except Exception:
        return "Non déterminé"


# ---------- Antiplagiat (comparaison entre textes de l'équipe) ----------
def _shingles(text, n=6):
    mots = _mots(text)
    return {" ".join(mots[i:i + n]) for i in range(len(mots) - n + 1)}


def comparer(textes: dict, seuil_passages=5):
    """textes : {id: texte}. Retourne une liste de paires triées par similarité décroissante."""
    ids = list(textes)
    if len(ids) < 2:
        return []
    tfidf = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1).fit_transform([textes[i] for i in ids])
    cos = cosine_similarity(tfidf)
    sh = {i: _shingles(textes[i]) for i in ids}
    resultats = []
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            ia, ib = ids[a], ids[b]
            commun = sh[ia] & sh[ib]
            petit = min(len(sh[ia]), len(sh[ib]))
            recouvrement = round(len(commun) / petit, 4) if petit else 0.0
            passages = sorted(commun, key=len, reverse=True)[:seuil_passages]
            resultats.append({
                "doc_a": ia, "doc_b": ib, "cosinus": round(float(cos[a][b]), 4),
                "recouvrement": recouvrement,
                "passages": json.dumps(passages, ensure_ascii=False),
            })
    return sorted(resultats, key=lambda r: r["recouvrement"], reverse=True)


def niveau(recouvrement: float) -> str:
    if recouvrement >= 0.30:
        return "🔴 Élevé"
    if recouvrement >= 0.10:
        return "🟠 À vérifier"
    return "🟢 Faible"
