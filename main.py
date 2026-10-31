import os
import threading
import time
import logging
import feedparser
import requests
from flask import Flask

# Configuration des logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

app = Flask(__name__)

@app.route('/')
def home():
    return "Le bot La Meute Telegram est en ligne et actif (toutes les 10 minutes) !"

@app.route('/health')
def health():
    return "OK", 200

# -------------------------------------------------------------------
# 1. SOURCES & FLUX RSS AVEC NOMS DE SOURCES CLAIRS
# -------------------------------------------------------------------

FLUX_RSS = {
    "https://lafranceinsoumise.fr/actualites/feed/": "La France Insoumise",
    "https://melenchon.fr/feed/": "Jean-Luc Mélenchon",
    "https://institutlaboetie.fr/feed/": "Institut La Boétie",
    "https://linsoumission.fr/feed/": "L'Insoumission",
    "https://infos-ouvrieres.fr/feed/": "Infos Ouvrières",
    "https://www.lemediatv.fr/feed/": "Le Média TV"
}

POSTS_DEJA_PUBLIES = set()

# -------------------------------------------------------------------
# 2. DÉTECTION DES ÉMOJIS
# -------------------------------------------------------------------

def obtenir_emojis_par_sujet(titre, resume, nom_source):
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
    elif "boétie" in nom_source.lower() or any(m in texte for m in ["boétie", "formation", "livre", "conférence", "économie", "théorie"]):
        return "📚💡🧠", "INSTITUT LA BOÉTIE & BATAILLE CULTURELLE"
    elif "média" in nom_source.lower() or any(m in texte for m in ["direct", "vidéo", "émission", "revue", "chronique"]):
        return "📺🔴🎙️", "LE MÉDIA & DIRECTS"
    else:
        return "🔥✊⚡", "ACTUALITÉ POLITIQUE"

# -------------------------------------------------------------------
# 3. BOUCLE DE PUBLICATION (TOUTES LES 10 MINUTES)
# -------------------------------------------------------------------

def boucle_verification_flux():
    logging.info("--- DÉMARRAGE DU THREAD DE PUBLICATION TELEGRAM (10 MIN) ---")
    time.sleep(5)

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHANNEL_ID")
    invite_link = os.getenv("TELEGRAM_INVITE_LINK", "https://t.me/lameute_insoumise")
    
    if not token or not chat_id:
        logging.error("ERREUR CRITIQUE : TELEGRAM_BOT_TOKEN ou TELEGRAM_CHANNEL_ID manquant !")
        return

    url_api = f"https://api.telegram.org/bot{token}/sendMessage"

    while True:
        try:
            logging.info("Vérification des flux RSS en cours...")
            article_a_publier = None
            nom_source_active = "La France Insoumise"
            
            # Étape 1 : Article inédit
            for url_rss, nom_src in FLUX_RSS.items():
                feed = feedparser.parse(url_rss)
                for entry in feed.entries:
                    art_id = entry.get("id", entry.get("link"))
                    if art_id not in POSTS_DEJA_PUBLIES:
                        article_a_publier = entry
                        nom_source_active = nom_src
                        break
                if article_a_publier:
                    break

            # Étape 2 : Si rien de neuf, on pioche dans les récents
            if not article_a_publier:
                for url_rss, nom_src in FLUX_RSS.items():
                    feed = feedparser.parse(url_rss)
                    for entry in feed.entries[:5]:
                        art_id = entry.get("id", entry.get("link"))
                        if len(POSTS_DEJA_PUBLIES) > 50:
                            POSTS_DEJA_PUBLIES.clear()
                        
                        if art_id not in POSTS_DEJA_PUBLIES:
                            article_a_publier = entry
                            nom_source_active = nom_src
                            break
                    if article_a_publier:
                        break

            # Étape 3 : Envoi de l'article formaté
            if article_a_publier:
                art_id = article_a_publier.get("id", article_a_publier.get("link"))
                POSTS_DEJA_PUBLIES.add(art_id)
                
                titre = article_a_publier.get("title", "Actualité")
                lien = article_a_publier.get("link", "#")
                resume = article_a_publier.get("summary", "Découvrez les dernières actualités.")
                
                import re
                resume_propre = re.sub('<.*?>', '', resume)[:250] + "..."

                emojis, nom_theme = obtenir_emojis_par_sujet(titre, resume, nom_source_active)

                texte_pub = (
                    f"{emojis} **{nom_theme}**\n\n"
                    f"📌 **{titre}**\n\n"
                    f"📝 {resume_propre}\n\n"
                    f"via {nom_source_active}\n"
                    f"🔗 [Lire l'article complet]({lien})\n\n"
                    f"───────────────────\n"
                    f"🐺 **Fais grandir la meute, partage ce message !**\n"
                    f"👉 [S'abonner au canal]({invite_link})\n\n"
                    f"#LaMeuteInsoumise\n"
                    f"#JLM2027"
                )
                
                payload = {
                    "chat_id": chat_id,
                    "text": texte_pub,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": False
                }
                
                response = requests.post(url_api, json=payload)
                if response.status_code == 200:
                    logging.info(f"Article publié avec succès : {titre}")
                else:
                    logging.error(f"Erreur Telegram API ({response.status_code}) : {response.text}")

            else:
                # Étape 4 : Message de repli Action Populaire
                message_engagement = (
                    "✊🔥 **Engagez-vous, rejoignez l'action populaire !**\n\n"
                    "Chaque action compte pour faire progresser nos idées, diffuser nos luttes et préparer l'avenir.\n\n"
                    "👉 Rejoignez le mouvement dès maintenant sur [actionpopulaire.fr](https://actionpopulaire.fr) !\n\n"
                    f"───────────────────\n"
                    f"🐺 **Fais grandir la meute, partage ce message !**\n"
                    f"👉 [S'abonner au canal]({invite_link})\n\n"
                    f"#LaMeuteInsoumise\n"
                    f"#JLM2027"
                )
                payload = {
                    "chat_id": chat_id,
                    "text": message_engagement,
                    "parse_mode": "Markdown"
                }
                response = requests.post(url_api, json=payload)
                if response.status_code == 200:
                    logging.info("Message Action Populaire publié avec succès.")
                else:
                    logging.error(f"Erreur Telegram API Action Populaire : {response.text}")

        except Exception as e:
            logging.error(f"Erreur critique dans la boucle de publication : {e}")

        # Attente de 10 minutes (600 secondes)
        time.sleep(600)

# -------------------------------------------------------------------
# 4. LANCEMENT AUTOMATIQUE DU THREAD AU CHARGEMENT DU MODULE
# -------------------------------------------------------------------
thread_bot = threading.Thread(target=boucle_verification_flux, daemon=True)
thread_bot.start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
