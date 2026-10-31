import os
import asyncio
import logging
import feedparser
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# Configuration des logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# -------------------------------------------------------------------
# 1. DICTIONNAIRES DE TOUTES LES SOURCES
# -------------------------------------------------------------------

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

FLUX_RSS = [
    "https://lafranceinsoumise.fr/actualites/feed/",
    "https://melenchon.fr/feed/",
    "https://institutlaboetie.fr/feed/",
    "https://linsoumission.fr/feed/",
    "https://infos-ouvrieres.fr/feed/",
    "https://www.lemediatv.fr/feed/"
]

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

# Mémoire globale pour éviter les doublons (peut être relié à database.py)
POSTS_DEJA_PUBLIES = set()

# -------------------------------------------------------------------
# 2. FONCTIONS DE PUBLICATION ET GESTION DES FLUX
# -------------------------------------------------------------------

async def verifier_et_publier_flux(context: ContextTypes.DEFAULT_TYPE):
    """
    Vérifie les flux RSS toutes les 10 minutes.
    S'il y a du nouveau, publie l'article. 
    Sinon, publie un message d'engagement Action Populaire.
    """
    chat_id = os.getenv("TELEGRAM_CHANNEL_ID") # ID de votre canal Telegram configuré dans Render
    if not chat_id:
        logging.warning("TELEGRAM_CHANNEL_ID non défini dans les variables d'environnement.")
        return

    nouveau_contenu_trouve = False

    for url_rss in FLUX_RSS:
        try:
            feed = feedparser.parse(url_rss)
            if feed.entries:
                dernier_article = feed.entries[0] # Le plus récent
                art_id = dernier_article.get("id", dernier_article.get("link"))
                
                if art_id not in POSTS_DEJA_PUBLIES:
                    POSTS_DEJA_PUBLIES.add(art_id)
                    nouveau_contenu_trouve = True
                    
                    titre = dernier_article.get("title", "Actualité")
                    lien = dernier_article.get("link", "#")
                    resume = dernier_article.get("summary", "Découvrez les dernières actualités.")
                    # Nettoyage basique des balises HTML du résumé si présentes
                    import re
                    resume_propre = re.sub('<.*?>', '', resume)[:300] + "..."

                    texte_pub = (
                        f"📢 **NOUVELLE ACTUALITÉ**\n\n"
                        f"📌 **{titre}**\n\n"
                        f"📝 {resume_propre}\n\n"
                        f"🔗 [Lire l'article complet]({lien})"
                    )
                    
                    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Lire sur le site", url=lien)]])
                    
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=texte_pub,
                        parse_mode="Markdown",
                        reply_markup=keyboard,
                        disable_web_page_preview=False
                    )
                    break # On publie une nouveauté par cycle pour éviter le spam
        except Exception as e:
            logging.error(f"Erreur lors de la lecture du flux {url_rss}: {e}")

    # Si rien de nouveau n'a été publié, on publie le message d'engagement
    if not nouveau_contenu_trouve:
        message_engagement = (
            "✊ **Engagez-vous, rejoignez l'action populaire !**\n\n"
            "Chaque action compte pour faire progresser nos idées, diffuser nos luttes et préparer l'avenir.\n\n"
            "👉 Rejoignez le mouvement dès maintenant sur [actionpopulaire.fr](https://actionpopulaire.fr) !"
        )
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=message_engagement,
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Erreur envoi message engagement: {e}")

async def envoyer_video_direct_format(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    titre: str,
    miniature_url: str,
    description_courte: str,
    lien: str,
    est_direct: bool = False
):
    """
    Format spécifique pour les directs et rediffusions YouTube (Titre, Miniature, Texte, Lien).
    """
    type_badge = "🔴 **EN DIRECT**" if est_direct else "📺 **REDIFFUSION / VIDÉO**"
    
    caption = (
        f"{type_badge}\n\n"
        f"📌 **{titre}**\n\n"
        f"📝 {description_courte}\n\n"
        f"🔗 [Regarder sur YouTube]({lien})"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Voir la vidéo", url=lien)]
    ])
    
    try:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=miniature_url,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    except Exception:
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode="Markdown",
            reply_markup=keyboard
        )

# -------------------------------------------------------------------
# 3. COMMANDES TELEGRAM CLASSIQUES
# -------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Le bot **La Meute Telegram** est opérationnel et surveille les flux RSS et sources.\n\n"
        "Commandes disponibles :\n"
        "• /sources : Liste des sites politiques\n"
        "• /youtube : Liste des chaînes YouTube"
    )

async def cmd_sources(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "📰 **Sources politiques et insoumises :**\n\n"
    for name, url in SOURCES_WEB.items():
        text += f"• [{name}]({url})\n"
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)

async def cmd_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "🎥 **Chaînes YouTube suivies :**\n\n"
    for name, url in SOURCES_YOUTUBE.items():
        text += f"• [{name}]({url})\n"
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)

# -------------------------------------------------------------------
# 4. INITIALISATION DU BOT ET DU TIMER (10 MINUTES)
# -------------------------------------------------------------------

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logging.error("TELEGRAM_BOT_TOKEN manquant dans les variables d'environnement.")
        return

    application = Application.builder().token(token).build()

    # Handlers des commandes
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("sources", cmd_sources))
    application.add_handler(CommandHandler("youtube", cmd_youtube))

    # Configuration du JobQueue pour tourner toutes les 10 minutes (600 secondes)
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(verifier_et_publier_flux, interval=600, first=10)

    # Lancement du bot
    application.run_polling()

if __name__ == '__main__':
    main()
