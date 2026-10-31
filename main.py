import os
import threading
import time
import logging
import feedparser
import requests
from flask import Flask
from telegram import Bot

# Configuration des logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Initialisation de Flask (obligatoire pour maintenir le service Web sur Render)
app = Flask(__name__)

@app.route('/')
def home():
    return "Le bot La Meute Telegram est en ligne, actif et publie toutes les minutes !"

@app.route('/health')
def health():
    return "OK", 200

# -------------------------------------------------------------------
# 1. DICTIONNAIRES DE TOUTES LES SOURCES & FLUX RSS
# -------------------------------------------------------------------

FLUX_RSS = [
    "https://lafranceinsoumise.fr/actualites/feed/",
    "https://melenchon.fr/feed/",
    "https://institutlaboetie.fr/feed/",
    "https://linsoumission.fr/feed/",
    "https://infos-ouvrieres.fr/feed/",
    "https://www.lemediatv.fr/feed/"
]

SOURCES_WEB = {
    "LFI Actualités": "https://lafranceinsoumise.fr/actualites/",
    "L'Insoumission": "https://linsoumission.fr",
    "Mélenchon 2027": "https://melenchon2027.fr",
    "Site officiel JLM": "https://melenchon.fr",
    "Désintox LFI": "https://desintox.lafranceinsoumise.fr",
    "Antoine Léaument": "https://antoineleaument.fr",
    "Infos Ouvrières": "https://infos-ouvrieres.fr",
    "Institut La Boétie": "https://institutlaboetie.fr",
    "Le Média TV": "https://www.lemediatv.fr"
}

SOURCES_YOUTUBE = {
    "Jean-Luc Mélenchon": "https://www.youtube.com/@JLMelenchon",
    "Clémence Guetté": "https://www.youtube.com/@ClémenceGuetté-y7s",
    "Manuel Bompard": "https://www.youtube.com/@manuelbompard",
    "France insoumise": "https://www.youtube.com/@Franceinsoumise",
    "Mathilde Panot": "https://www.youtube.com/@MathildePanotOff",
    "Le Média": "https://www.youtube.com/@LeMediaTV",
    "Institut La Boétie": "https://www.youtube.com/@InstitutLaBoetie",
    "Canal Fi": "https://www.youtube.com/@CanalFi",
    "Bally Bagayoko": "https://www.youtube.com/@ballybagayoko5286",
    "David Guiraud": "https://www.youtube.com/@davidguiraud3214",
    "Rima Hassan": "https://www.youtube.com/@RimaHass",
    "Glupatate": "https://www.youtube.com/@Glupatate",
    "Alma Dufour": "https://www.youtube.com/@alma_dufour",
    "LFI-Monde": "https://www.youtube.com/@LFI-Monde",
    "Paul Vannier": "https://www.youtube.com/@paulvannier_",
    "François Piquemal": "https://www.youtube.com/@FrancoisPiquemal_Depute31",
    "Aurélie Trouvé": "https://www.youtube.com/@trouveaurelie",
    "Bruno Allan": "https://www.youtube.com/@BrunonAllan",
    "Aboubacar Bomangoli": "https://www.youtube.com/@abomangoli",
    "Thomas Portes": "https://www.youtube.com/@ThomasPortes",
    "Sébastien Delogu": "https://www.youtube.com/@sebastien_delogu",
    "Danièle Obono": "https://www.youtube.com/@Daniele_Obono",
    "France insoumise AN": "https://www.youtube.com/@FranceinsoumiseAN",
    "Sophia Chikirou": "https://www.youtube.com/@sophiachikirou7195",
    "Antoine Léaument": "https://www.youtube.com/@ALeaument",
    "Younous Omarjee": "https://www.youtube.com/@younous_omarjee",
    "Leïla Chaibi": "https://www.youtube.com/@leilachaibi9050"
}

# Mémoire glissante pour éviter les doublons récents
POSTS_DEJA_PUBLIES = set()

# -------------------------------------------------------------------
# 2. DÉTECTION INTELLIGENTE DES ÉMOJIS & THÈMES DU SUJET
# -------------------------------------------------------------------

def obtenir_emojis_par_sujet(titre, resume, lien_rss):
    texte = (titre + " " + resume).lower()
    
    if any(m in texte for m in ["2027", "présidentielle", "élection", "campagne", "vote", "urne"]):
        return "🗳️🎯🇫🇷", "CAP VERS 2027"
    elif any(m in texte for m in ["assemblée", "député", "loi", "motion", "gouvernement", "parlement", "amendement", "AN"]):
        return "🏛️📜✊", "COMBAT À L'ASSEMBLÉE"
    elif any(m in texte for m in ["grève", "salarié", "travail", "retraite", "inflation", "salaire", "pauvreté", "social", "ouvrier"]):
        return "✊🏭💶", "LUTTES SOCIALES & POUVOIR D'ACHAT"
    elif any(m in texte for m in ["climat", "écologie", "eau", "pollution", "nucléaire", "carbone", "biodiversité", "planète"]):
        return "🌍🌱💧", "URGENCE ÉCOLOGIQUE"
    elif any(m in texte for m in ["gaza", "palestine", "israël", "guerre", "paix", "international", "ue", "europe", "monde"]):
        return "🌐🕊️🇵🇸", "GÉOPOLITIQUE & INTERNATIONAL"
    elif "boetie" in lien_rss or any(m in texte for m in ["boétie", "formation", "livre", "conférence", "économie", "théorie"]):
        return "📚💡🧠", "INSTITUT LA BOÉTIE & BATAILLE CULTURELLE"
    elif "media" in lien_rss or any(m in texte for m in ["direct", "vidéo", "émission", "revue", "chronique"]):
        return "📺🔴🎙️", "LE MÉDIA & DIRECTS"
    elif "insoumission" in lien_rss or "franceinsoumise" in lien_rss:
        return "🔥✊⚡", "L'INSOUMISSION"
    else:
        return "📢🇫🇷⚡", "ACTUALITÉ POLITIQUE"

# -------------------------------------------------------------------
# 3. BOUCLE DE PUBLICATION CONTINUE (TOUTES LES 1 MINUTE STRICTEMENT)
# -------------------------------------------------------------------

def boucle_verification_flux():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHANNEL_ID")
    invite_link = os.getenv("TELEGRAM_INVITE_LINK", "https://t.me/lameute_insoumise")
    
    if not token or not chat_id:
        logging.error("TELEGRAM_BOT_TOKEN ou TELEGRAM_CHANNEL_ID manquant.")
        return

    url_api = f"https://api.telegram.org/bot{token}/sendMessage"

    # Boucle infinie assurant une publication toutes les 60 secondes (1 minute) non-stop
    while True:
        try:
            article_a_publier = None
            source_rss_active = ""
            
            # 1. Chercher en priorité un article totalement inédit
            for url_rss in FLUX_RSS:
                feed = feedparser.parse(url_rss)
                for entry in feed.entries:
                    art_id = entry.get("id", entry.get("link"))
                    if art_id not in POSTS_DEJA_PUBLIES:
                        article_a_publier = entry
                        source_rss_active = url_rss
                        break
                if article_a_publier:
                    break

            # 2. S'il n'y a rien de neuf, on pioche dans les récents pour ne jamais s'arrêter
            if not article_a_publier:
                for url_rss in FLUX_RSS:
                    feed = feedparser.parse(url_rss)
                    for entry in feed.entries[:5]:
                        art_id = entry.get("id", entry.get("link"))
                        if len(POSTS_DEJA_PUBLIES) > 50:
                            POSTS_DEJA_PUBLIES.clear()
                        
                        if art_id not in POSTS_DEJA_PUBLIES:
                            article_a_publier = entry
                            source_rss_active = url_rss
                            break
                    if article_a_publier:
                        break

            # 3. Publication de l'article avec émojis, résumé et CTA d'abonnement
            if article_a_publier:
                art_id = article_a_publier.get("id", article_a_publier.get("link"))
                POSTS_DEJA_PUBLIES.add(art_id)
                
                titre = article_a_publier.get("title", "Actualité")
                lien = article_a_publier.get("link", "#")
                resume = article_a_publier.get("summary", "Découvrez les dernières actualités.")
                
                import re
                resume_propre = re.sub('<.*?>', '', resume)[:250] + "..."

                emojis, nom_theme = obtenir_emojis_par_sujet(titre, resume, source_rss_active)

                texte_pub = (
                    f"{emojis} **{nom_theme}**\n\n"
                    f"📌 **{titre}**\n\n"
                    f"📝 {resume_propre}\n\n"
                    f"🔗 [Lire l'article complet]({lien})\n\n"
                    f"───────────────────\n"
                    f"🐺 **Fais grandir la meute, partage ce message !**\n"
                    f"👉 [S'abonner au canal]({invite_link})"
                )
                
                payload = {
                    "chat_id": chat_id,
                    "text": texte_pub,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": False
                }
                requests.post(url_api, json=payload)

            else:
                # 4. Message de repli Action Populaire avec le même CTA
                message_engagement = (
                    "✊🔥 **Engagez-vous, rejoignez l'action populaire !**\n\n"
                    "Chaque action compte pour faire progresser nos idées, diffuser nos luttes et préparer l'avenir.\n\n"
                    "👉 Rejoignez le mouvement dès maintenant sur [actionpopulaire.fr](https://actionpopulaire.fr) !\n\n"
                    f"───────────────────\n"
                    f"🐺 **Fais grandir la meute, partage ce message !**\n"
                    f"👉 [S'abonner au canal]({invite_link})"
                )
                payload = {
                    "chat_id": chat_id,
                    "text": message_engagement,
                    "parse_mode": "Markdown"
                }
                requests.post(url_api, json=payload)

        except Exception as e:
            logging.error(f"Erreur dans la boucle de publication 1 min: {e}")

        # Pause exacte de 1 minute (60 secondes) avant le prochain post
        time.sleep(60)

# -------------------------------------------------------------------
# 4. DÉMARRAGE DU THREAD DE FOND & DU SERVEUR FLASK
# -------------------------------------------------------------------

if __name__ == '__main__':
    t = threading.Thread(target=boucle_verification_flux, daemon=True)
    t.start()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
