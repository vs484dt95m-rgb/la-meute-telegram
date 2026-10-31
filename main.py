import os
import threading
import time
import logging
import feedparser
import requests
from flask import Flask
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

# Configuration des logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Initialisation de Flask (nécessaire pour Render / Web Service)
app = Flask(__name__)

@app.route('/')
def home():
    return "Le bot La Meute Telegram est en ligne et actif !"

@app.route('/health')
def health():
    return "OK", 200

# -------------------------------------------------------------------
# 1. DICTIONNAIRES DE TOUTES LES SOURCES
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

POSTS_DEJA_PUBLIES = set()

# -------------------------------------------------------------------
# 2. LOGIQUE DE PUBLICATION AUTOMATIQUE (TOUTES LES 10 MINUTES)
# -------------------------------------------------------------------

def boucle_verification_flux():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHANNEL_ID")
    
    if not token or not chat_id:
        logging.error("TELEGRAM_BOT_TOKEN ou TELEGRAM_CHANNEL_ID manquant.")
        return

    bot = Bot(token=token)
    
    while True:
        try:
            nouveau_contenu_trouve = False
            
            for url_rss in FLUX_RSS:
                feed = feedparser.parse(url_rss)
                if feed.entries:
                    dernier_article = feed.entries[0]
                    art_id = dernier_article.get("id", dernier_article.get("link"))
                    
                    if art_id not in POSTS_DEJA_PUBLIES:
                        POSTS_DEJA_PUBLIES.add(art_id)
                        nouveau_contenu_trouve = True
                        
                        titre = dernier_article.get("title", "Actualité")
                        lien = dernier_article.get("link", "#")
                        resume = dernier_article.get("summary", "Découvrez les dernières actualités.")
                        
                        import re
                        resume_propre = re.sub('<.*?>', '', resume)[:300] + "..."

                        texte_pub = (
                            f"📢 **NOUVELLE ACTUALITÉ**\n\n"
                            f"📌 **{titre}**\n\n"
                            f"📝 {resume_propre}\n\n"
                            f"🔗 [Lire l'article complet]({lien})"
                        )
                        
                        # Utilisation de requests pour envoyer via l'API Telegram de façon synchrone
                        url_api = f"https://api.telegram.org/bot{token}/sendMessage"
                        payload = {
                            "chat_id": chat_id,
                            "text": texte_pub,
                            "parse_mode": "Markdown",
                            "disable_web_page_preview": False
                        }
                        requests.post(url_api, json=payload)
                        break # Un post par cycle

            # Si rien de nouveau, publication du message d'engagement Action Populaire
            if not nouveau_contenu_trouve:
                message_engagement = (
                    "✊ **Engagez-vous, rejoignez l'action populaire !**\n\n"
                    "Chaque action compte pour faire progresser nos idées, diffuser nos luttes et préparer l'avenir.\n\n"
                    "👉 Rejoignez le mouvement dès maintenant sur [actionpopulaire.fr](https://actionpopulaire.fr) !"
                )
                url_api = f"https://api.telegram.org/bot{token}/sendMessage"
                payload = {
                    "chat_id": chat_id,
                    "text": message_engagement,
                    "parse_mode": "Markdown"
                }
                requests.post(url_api, json=payload)

        except Exception as e:
            logging.error(f"Erreur dans la boucle de flux: {e}")

        # Attente de 10 minutes (600 secondes)
        time.sleep(600)

# -------------------------------------------------------------------
# 3. LANCEMENT DU THREAD DE FOND ET DE FLASK
# -------------------------------------------------------------------

if __name__ == '__main__':
    # Démarrage de la vérification des flux en arrière-plan
    t = threading.Thread(target=boucle_verification_flux, daemon=True)
    t.start()
    
    # Démarrage de Flask (requis pour Render avec Gunicorn)
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
