
import os
import re
import time
import html
import sqlite3
import logging
import threading
import requests
import feedparser

from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from flask import Flask, jsonify

# ==================================================
# LA MEUTE - MOTEUR CENTRAL
# ==================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@lameute_insoumise")

CHECK_INTERVAL = 15 * 60
DATABASE = os.getenv("DATABASE_PATH", "/tmp/la_meute.db")

USER_AGENT = "LaMeuteBot/1.0 (news aggregator)"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

app = Flask(__name__)

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

# ==================================================
# LES 9 SOURCES
# ==================================================

SOURCES = [
    {
        "name": "L'Insoumission",
        "url": "https://linsoumission.fr/"
    },
    {
        "name": "Infos Ouvrières",
        "url": "https://infos-ouvrieres.fr/"
    },
    {
        "name": "La France insoumise - Parlementaires",
        "url": "https://lafranceinsoumise.fr/les-parlementaires-de-la-france-insoumise/"
    },
    {
        "name": "Délégation insoumise européenne",
        "url": "https://d-fi.lafranceinsoumise.fr/"
    },
    {
        "name": "Institut La Boétie",
        "url": "https://institutlaboetie.fr/"
    },
    {
        "name": "Mélenchon 2027",
        "url": "https://melenchon2027.fr/"
    },
    {
        "name": "YouTube - Jean-Luc Mélenchon",
        "url": "https://www.youtube.com/@JLMelenchon",
        "type": "youtube"
    },
    {
        "name": "Désintox LFI",
        "url": "https://desintox.lafranceinsoumise.fr/"
    },
    {
        "name": "Jean-Luc Mélenchon",
        "url": "https://melenchon.fr/"
    }
]

# ==================================================
# BASE DE DONNEES
# ==================================================

def init_database():
    with sqlite3.connect(DATABASE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS publications (
                item_id TEXT PRIMARY KEY,
                source TEXT,
                published_at TEXT,
                detected_at TEXT
            )
        """)

def already_published(item_id):
    with sqlite3.connect(DATABASE) as conn:
        result = conn.execute(
            "SELECT 1 FROM publications WHERE item_id = ?",
            (item_id,)
        ).fetchone()

    return result is not None

def save_publication(item_id, source, published_at):
    with sqlite3.connect(DATABASE) as conn:
        conn.execute("""
            INSERT OR IGNORE INTO publications
            (item_id, source, published_at, detected_at)
            VALUES (?, ?, ?, ?)
        """, (
            item_id,
            source,
            published_at,
            datetime.now(timezone.utc).isoformat()
        ))

# ==================================================
# TELEGRAM
# ==================================================

def telegram_request(method, payload):
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN absent")

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

    response = session.post(
        url,
        json=payload,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if not data.get("ok"):
        raise RuntimeError(str(data))

    return data

def publish_telegram(article):
    title = html.escape(article["title"])
    excerpt = html.escape(article["excerpt"][:450])
    source = html.escape(article["source"])
    link = html.escape(article["link"], quote=True)

    caption = (
        "🐺 <b>LA MEUTE</b>\n\n"
        f"<b>{title}</b>\n\n"
        f"{excerpt}\n\n"
        f"📰 Source : {source}\n"
        f'🔗 <a href="{link}">Lire la publication originale</a>'
    )

    image = article.get("image")

    if image:
        try:
            telegram_request("sendPhoto", {
                "chat_id": CHANNEL_ID,
                "photo": image,
                "caption": caption,
                "parse_mode": "HTML"
            })
            return
        except Exception:
            logging.exception("Échec de publication de l'image")

    telegram_request("sendMessage", {
        "chat_id": CHANNEL_ID,
        "text": caption,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    })

# ==================================================
# EXTRACTION DES IMAGES
# ==================================================

def get_image(entry):
    for key in ("media_thumbnail", "media_content"):
        media = entry.get(key, [])

        if media:
            image = media[0].get("url")
            if image:
                return image

    for enclosure in entry.get("enclosures", []):
        if enclosure.get("type", "").startswith("image/"):
            return enclosure.get("href")

    image = entry.get("image", {})

    if isinstance(image, dict):
        return image.get("href")

    return None

# ==================================================
# DECOUVERTE DES FLUX RSS
# ==================================================

def discover_feeds(url):
    feeds = []

    try:
        response = session.get(url, timeout=25)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for link in soup.find_all("link"):
            rel = link.get("rel", [])
            rel = rel if isinstance(rel, list) else [rel]

            feed_type = link.get("type", "")

            if (
                "alternate" in rel
                and (
                    "rss" in feed_type.lower()
                    or "atom" in feed_type.lower()
                    or "xml" in feed_type.lower()
                )
            ):
                href = link.get("href")

                if href:
                    feeds.append(urljoin(url, href))

    except Exception:
        logging.exception("Découverte RSS impossible : %s", url)

    # Essais classiques pour les sites WordPress
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    feeds.extend([
        urljoin(base, "/feed/"),
        urljoin(base, "/feed"),
        urljoin(base, "/rss/"),
        urljoin(base, "/rss.xml")
    ])

    return list(dict.fromkeys(feeds))

# ==================================================
# API WORDPRESS
# ==================================================

def fetch_wordpress(url, source_name):
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    api_url = urljoin(
        base,
        "/wp-json/wp/v2/posts"
    )

    try:
        response = session.get(
            api_url,
            params={
                "per_page": 10,
                "_embed": "true",
                "orderby": "date",
                "order": "desc"
            },
            timeout=25
        )

        if response.status_code != 200:
            return []

        posts = response.json()

        if not isinstance(posts, list):
            return []

        articles = []

        for post in posts:
            title = BeautifulSoup(
                post.get("title", {}).get("rendered", ""),
                "html.parser"
            ).get_text(" ", strip=True)

            excerpt = BeautifulSoup(
                post.get("excerpt", {}).get("rendered", ""),
                "html.parser"
            ).get_text(" ", strip=True)

            image = None

            embedded = post.get("_embedded", {})
            media = embedded.get("wp:featuredmedia", [])

            if media:
                image = media[0].get("source_url")

            articles.append({
                "id": str(post["id"]),
                "title": title,
                "excerpt": excerpt,
                "link": post["link"],
                "image": image,
                "source": source_name,
                "date": post.get("date", "")
            })

        return articles

    except Exception:
        logging.exception("Erreur API WordPress : %s", source_name)
        return []

# ==================================================
# YOUTUBE
# ==================================================

def fetch_youtube(url, source_name):
    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()

        # Récupération de l'identifiant de chaîne
        match = re.search(
            r'"channelId"\s*:\s*"(UC[^"]+)"',
            response.text
        )

        if not match:
            match = re.search(
                r'"externalId"\s*:\s*"(UC[^"]+)"',
                response.text
            )

        if not match:
            logging.warning(
                "Identifiant YouTube introuvable : %s",
                source_name
            )
            return []

        channel_id = match.group(1)

        feed_url = (
            "https://www.youtube.com/feeds/videos.xml"
            f"?channel_id={channel_id}"
        )

        feed = feedparser.parse(feed_url)

        articles = []

        for entry in feed.entries:
            articles.append({
                "id": entry.get("yt_videoid", entry.get("id")),
                "title": entry.get("title", ""),
                "excerpt": BeautifulSoup(
                    entry.get("summary", ""),
                    "html.parser"
                ).get_text(" ", strip=True)[:450],
                "link": entry.get("link", ""),
                "image": get_image(entry),
                "source": source_name,
                "date": entry.get("published", "")
            })

        return articles

    except Exception:
        logging.exception("Erreur YouTube")
        return []

# ==================================================
# COLLECTE RSS / ATOM
# ==================================================

def fetch_rss(url, source_name):
    feeds = discover_feeds(url)

    for feed_url in feeds:
        try:
            response = session.get(feed_url, timeout=20)
            response.raise_for_status()

            feed = feedparser.parse(response.content)

            if not feed.entries:
                continue

            articles = []

            for entry in feed.entries:
                link = entry.get("link", "")

                if not link:
                    continue

                articles.append({
                    "id": entry.get("id") or link,
                    "title": entry.get("title", ""),
                    "excerpt": BeautifulSoup(
                        entry.get("summary", ""),
                        "html.parser"
                    ).get_text(" ", strip=True)[:450],
                    "link": link,
                    "image": get_image(entry),
                    "source": source_name,
                    "date": entry.get("published", "")
                })

            if articles:
                logging.info(
                    "%s : %s articles récupérés",
                    source_name,
                    len(articles)
                )
                return articles

        except Exception:
            continue

    return []

# ==================================================
# MOTEUR DE COLLECTE
# ==================================================

def fetch_source(source):
    name = source["name"]
    url = source["url"]

    logging.info("Vérification : %s", name)

    if source.get("type") == "youtube":
        return fetch_youtube(url, name)

    # Essai WordPress
    articles = fetch_wordpress(url, name)

    if articles:
        return articles

    # Essai RSS / Atom
    return fetch_rss(url, name)

def process_source(source):
    articles = fetch_source(source)

    # Les plus anciens d'abord
    articles.reverse()

    for article in articles:
        item_id = article.get("id")

        if not item_id or not article.get("title"):
            continue

        if not article.get("link", "").startswith("https://"):
            continue

        if already_published(item_id):
            continue

        try:
            publish_telegram(article)

            save_publication(
                item_id,
                article["source"],
                article.get("date", "")
            )

            logging.info(
                "Publication réussie : %s",
                article["title"]
            )

            time.sleep(2)

        except Exception:
            logging.exception(
                "Erreur de publication : %s",
                article["title"]
            )

# ==================================================
# BOUCLE AUTOMATIQUE
# ==================================================

last_check = None
is_running = False

def monitoring_loop():
    global last_check, is_running

    if is_running:
        return

    is_running = True

    while True:
        logging.info("🐺 Début du cycle La Meute")

        for source in SOURCES:
            try:
                process_source(source)
            except Exception:
                logging.exception(
                    "Erreur source : %s",
                    source["name"]
                )

        last_check = datetime.now(
            timezone.utc
        ).isoformat()

        logging.info(
            "Fin du cycle. Prochaine vérification dans 15 minutes."
        )

        time.sleep(CHECK_INTERVAL)

# ==================================================
# SERVEUR WEB POUR RENDER
# ==================================================

@app.route("/")
def home():
    return jsonify({
        "project": "La Meute",
        "status": "running",
        "sources": len(SOURCES),
        "interval_minutes": 15,
        "last_check": last_check
    })

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200

# ==================================================
# DEMARRAGE
# ==================================================

if __name__ == "__main__":
    init_database()

    worker = threading.Thread(
        target=monitoring_loop,
        daemon=True
    )

    worker.start()

    port = int(os.getenv("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )
