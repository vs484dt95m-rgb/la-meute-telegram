import os
import re
import html
import logging
import requests
import psycopg

from datetime import datetime
from html.parser import HTMLParser
from psycopg.rows import dict_row

# -----------------------------
# CONFIGURATION
# -----------------------------

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
DATABASE_URL = os.environ["DATABASE_URL"]

API_URL = "https://api.telegram.org/bot" + BOT_TOKEN
SOURCE_URL = "https://lafranceinsoumise.fr"
WP_API = SOURCE_URL + "/wp-json/wp/v2/posts"

INITIAL_POST_LIMIT = 3
MAX_POSTS_PER_RUN = 10

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# -----------------------------
# NETTOYAGE HTML
# -----------------------------

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def get_text(self):
        return " ".join(self.parts)


def clean_html(value):
    parser = TextExtractor()
    parser.feed(value or "")
    text = " ".join(parser.parts)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def safe_url(url):
    return (
        isinstance(url, str)
        and url.startswith("https://lafranceinsoumise.fr/")
    )


# -----------------------------
# BASE DE DONNEES
# -----------------------------

def get_db():
    return psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row
    )


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS published (
                post_id BIGINT PRIMARY KEY,
                published_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)


def is_published(post_id):
    with get_db() as conn:
        result = conn.execute(
            "SELECT post_id FROM published WHERE post_id = %s",
            (post_id,)
        ).fetchone()

    return result is not None


def save_published(post_id):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO published (post_id)
            VALUES (%s)
            ON CONFLICT (post_id) DO NOTHING
            """,
            (post_id,)
        )


def initialize_history(posts):
    """Au premier lancement, éviter de republier tout l'historique."""
    if not posts:
        return

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO published (post_id)
            VALUES (%s)
            ON CONFLICT (post_id) DO NOTHING
            """,
            (posts[0]["id"],)
        )

    logging.info("Historique initialisé.")


# -----------------------------
# RECUPERATION DES ARTICLES
# -----------------------------

def fetch_articles():
    params = {
        "per_page": 20,
        "page": 1,
        "orderby": "date",
        "order": "desc",
        "_fields": "id,date,link,title,excerpt"
    }

    response = requests.get(
        WP_API,
        params=params,
        timeout=30,
        headers={"User-Agent": "LaMeuteNewsBot/1.0"}
    )

    response.raise_for_status()

    articles = response.json()

    if not isinstance(articles, list):
        raise ValueError("Réponse API inattendue")

    valid = []

    for article in articles:
        link = article.get("link", "")

        if not safe_url(link):
            continue

        valid.append(article)

    return valid


# -----------------------------
# FORMATAGE TELEGRAM
# -----------------------------

def format_article(article):
    title = clean_html(
        article.get("title", {}).get("rendered", "")
    )

    excerpt = clean_html(
        article.get("excerpt", {}).get("rendered", "")
    )

    link = article["link"]

    date = article.get("date", "")
    try:
        date = datetime.fromisoformat(
            date.replace("Z", "+00:00")
        ).strftime("%d/%m/%Y à %H:%M")
    except ValueError:
        date = "Date non précisée"

    if len(excerpt) > 500:
        excerpt = excerpt[:497] + "..."

    message = (
        "🐺 <b>LA MEUTE | ACTUALITÉ</b>\n\n"
        f"<b>{html.escape(title)}</b>\n\n"
        f"{html.escape(excerpt)}\n\n"
        f"📅 {date}\n"
        "📰 Source : La France insoumise\n"
        f'🔗 <a href="{html.escape(link, quote=True)}">'
        "Lire l'article original</a>"
    )

    return message


# -----------------------------
# PUBLICATION TELEGRAM
# -----------------------------

def publish(message):
    response = requests.post(
        API_URL + "/sendMessage",
        json={
            "chat_id": CHANNEL_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        },
        timeout=30
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError("Telegram a refusé la publication")

    return True


# -----------------------------
# EXECUTION PRINCIPALE
# -----------------------------

def main():
    logging.info("Démarrage de La Meute")

    init_db()

    articles = fetch_articles()

    if not articles:
        logging.info("Aucun article trouvé.")
        return

    # Premier démarrage : marquer le plus récent
    # pour ne pas diffuser tout l'historique.
    with get_db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS total FROM published"
        ).fetchone()["total"]

    if count == 0:
        initialize_history(articles)
        logging.info(
            "Premier lancement terminé. "
            "Les prochains articles seront publiés."
        )
        return

    # Publier du plus ancien au plus récent
    new_articles = [
        article for article in reversed(articles)
        if not is_published(article["id"])
    ]

    new_articles = new_articles[:MAX_POSTS_PER_RUN]

    if not new_articles:
        logging.info("Aucune nouvelle actualité.")
        return

    for article in new_articles:
        try:
            message = format_article(article)

            publish(message)

            # Enregistrer seulement après confirmation Telegram
            save_published(article["id"])

            logging.info(
                "Article publié : %s",
                article["id"]
            )

        except Exception:
            logging.exception(
                "Erreur pour l'article %s",
                article.get("id")
            )

    logging.info("Fin de l'exécution.")


if __name__ == "__main__":
    main()
