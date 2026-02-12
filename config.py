import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Telegram alerts
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Scheduler
DAILY_SCAN_ENABLED = os.getenv("DAILY_SCAN_ENABLED", "true").lower() == "true"
DAILY_SCAN_HOUR = int(os.getenv("DAILY_SCAN_HOUR", "7"))
DAILY_SCAN_MINUTE = int(os.getenv("DAILY_SCAN_MINUTE", "0"))
SCAN_DELAY_SECONDS = int(os.getenv("SCAN_DELAY_SECONDS", "30"))

# Email digest
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
DIGEST_RECIPIENTS = os.getenv("DIGEST_RECIPIENTS", "")  # comma-separated

# Telegram channels to scrape (Spanish football news)
_default_telegram = "fichaboreal,noticiasfutbol_es,transfermarktES,LaLigaNews_es,mundodeportivoes"
TELEGRAM_CHANNELS = [c.strip() for c in os.getenv("TELEGRAM_CHANNELS", _default_telegram).split(",") if c.strip()]

# Apify
APIFY_BASE = "https://api.apify.com/v2"
TWITTER_ACTOR = "apidojo~tweet-scraper"
INSTAGRAM_ACTOR = "apify~instagram-scraper"
INSTAGRAM_HASHTAG_ACTOR = "apify~instagram-hashtag-scraper"
TIKTOK_ACTOR = "clockworks~tiktok-scraper"

# Instagram mention search limits
MAX_INSTAGRAM_MENTIONS = 50

# RSS Feeds prensa deportiva (espanola + internacional)
SPANISH_PRESS_FEEDS = {
    # Spanish
    "Marca": "https://e00-marca.uecdn.es/rss/futbol/primera-division.xml",
    "AS": "https://as.com/rss/tags/futbol.xml",
    "Mundo Deportivo": "https://www.mundodeportivo.com/feed/rss/futbol",
    "El Pais Deportes": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/deportes/portada",
    "El Mundo Deportes": "https://e00-elmundo.uecdn.es/elmundodeporte/rss/futbol.xml",
    "Relevo": "https://www.relevo.com/rss/futbol.xml",
    # Italian
    "Gazzetta": "https://www.gazzetta.it/rss/Calcio.xml",
    "Tuttosport": "https://www.tuttosport.com/rss/calcio.xml",
    "Corriere dello Sport": "https://www.corrieredellosport.it/rss/calcio",
    # English
    "BBC Sport": "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "The Guardian Football": "https://www.theguardian.com/football/rss",
    "Sky Sports Football": "https://www.skysports.com/rss/12040",
    # French
    "L'Equipe": "https://www.lequipe.fr/rss/actu_rss_Football.xml",
    # German
    "Kicker": "https://rss.kicker.de/news/aktuell",
}

# Google News RSS (multi-language: ES, EN, IT, AR, FR, DE)
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=es&gl=ES&ceid=ES:es"
GOOGLE_NEWS_RSS_INTL = {
    "en": "https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en",
    "it": "https://news.google.com/rss/search?q={query}&hl=it&gl=IT&ceid=IT:it",
    "ar": "https://news.google.com/rss/search?q={query}&hl=ar&gl=QA&ceid=QA:ar",
    "fr": "https://news.google.com/rss/search?q={query}&hl=fr&gl=FR&ceid=FR:fr",
    "de": "https://news.google.com/rss/search?q={query}&hl=de&gl=DE&ceid=DE:de",
}
GOOGLE_ALERTS_RSS = "https://www.google.com/alerts/feeds/{alert_id}"

# Site-specific search: Google News RSS with site: operator
# Finds articles about the player on each newspaper's website directly
PRESS_SITE_SEARCH = {
    # Spanish
    "Marca": "marca.com",
    "AS": "as.com",
    "Mundo Deportivo": "mundodeportivo.com",
    "Sport": "sport.es",
    "El Pais": "elpais.com",
    "El Mundo": "elmundo.es",
    "Relevo": "relevo.com",
    "Estadio Deportivo": "estadiodeportivo.com",
    "Diario de Sevilla": "diariodesevilla.es",
    "ABC Sevilla": "sevilla.abc.es",
    "La Voz del Sur": "lavozdelsur.es",
    "El Desmarque": "eldesmarque.com",
    "Fichajes.net": "fichajes.net",
    "BeSoccer": "besoccer.com",
    "Transfermarkt": "transfermarkt.es",
    # English
    "BBC Sport": "bbc.com/sport",
    "The Guardian Sport": "theguardian.com/football",
    "Sky Sports": "skysports.com",
    "ESPN": "espn.com",
    "Goal.com": "goal.com",
    "Football Italia": "football-italia.net",
    # Italian
    "Gazzetta": "gazzetta.it",
    "Tuttosport": "tuttosport.com",
    "Corriere dello Sport": "corrieredellosport.it",
    "Calciomercato": "calciomercato.com",
    # French
    "L'Equipe": "lequipe.fr",
    "Foot Mercato": "footmercato.net",
    # German
    "Kicker": "kicker.de",
    "Transfermarkt DE": "transfermarkt.de",
    # Arabic
    "Al Jazeera Sports": "aljazeera.net/sport",
    "Kooora": "kooora.com",
}

# YouTube (via HTML scraping - no API key needed)

# Reddit (international subreddits)
REDDIT_SUBREDDITS = [
    "soccer", "LaLiga", "futbol", "calcio", "SerieA", "football",
    "PremierLeague", "Bundesliga", "Ligue1", "RealBetis", "SevillaFC",
    "soccertransfers", "footballhighlights", "ACMilan", "Juve", "ASRoma",
]

# Forums, blogs, fan sites (Google web search with site:)
FORUM_SITES = {
    "ForoCoches": "forocoches.com",
    "Mediavida": "mediavida.com",
    "El Desmarque": "eldesmarque.com",
    "Todo Fichajes": "todofichajes.com",
    "FutbolFantasy": "futbolfantasy.com",
    "Soy del Betis": "soydelbetis.com",
    "Sevilla Fans": "sevillafc.es",
    "Football Espana": "footballespana.net",
    "La Colina de Nervion": "lacolinadenervion.com",
    "TribaLa": "tribala.com",
}

# Limites scraping (doubled from v1)
MAX_TWEETS_MENTIONS = 400
MAX_TWEETS_PLAYER = 200
MAX_INSTAGRAM_POSTS = 100
MAX_REDDIT_POSTS = 100
MAX_RSS_ITEMS = 100
MAX_TIKTOK_POSTS = 60
MAX_YOUTUBE_RESULTS = 40

# First scan multiplier (deeper scrape for new players)
FIRST_SCAN_MULTIPLIER = 3

# Default dashboard view window (days)
STANDARD_SCAN_DAYS = 7

# Image Index weights (must sum to 1.0)
IMAGE_INDEX_WEIGHTS = {
    "volume": 0.20,
    "press_sentiment": 0.25,
    "social_sentiment": 0.25,
    "engagement": 0.15,
    "no_controversy": 0.15,
}

# Weekly report day (0=Mon, 6=Sun)
WEEKLY_REPORT_DAY = 6  # Sunday
WEEKLY_REPORT_HOUR = 20
WEEKLY_REPORT_MINUTE = 0

# Intelligence / Early Detection
INTELLIGENCE_ENABLED = os.getenv("INTELLIGENCE_ENABLED", "true").lower() == "true"
INTELLIGENCE_MAX_INPUT_ITEMS = int(os.getenv("INTELLIGENCE_MAX_INPUT_ITEMS", "200"))
INTELLIGENCE_LOOKBACK_DAYS = int(os.getenv("INTELLIGENCE_LOOKBACK_DAYS", "7"))
INTELLIGENCE_MAX_TOKENS = int(os.getenv("INTELLIGENCE_MAX_TOKENS", "3000"))
RISK_CATEGORIES = [
    "reputacion_personal", "legal", "rendimiento", "fichaje",
    "lesion", "disciplina", "comercial", "imagen_publica",
]
SEVERITY_LEVELS = ["critico", "alto", "medio", "bajo"]

# Source credibility weights (1-10 scale)
# Higher = more reliable/impactful source for sentiment analysis
SOURCE_WEIGHTS = {
    # Tier 1: Major national sports press (highest credibility)
    "Marca": 10, "AS": 10, "Relevo": 9, "El Pais": 10, "El Mundo": 9,
    "Mundo Deportivo": 9, "Sport": 8, "Google News": 8,
    # Tier 2: Regional/specialized press
    "Estadio Deportivo": 7, "Diario de Sevilla": 7, "ABC Sevilla": 7,
    "La Voz del Sur": 6, "El Desmarque": 6, "BeSoccer": 7,
    "Fichajes.net": 5, "Transfermarkt": 8,
    # Tier 3: International press
    "Gazzetta": 9, "Tuttosport": 7, "BBC Sport": 10, "The Guardian": 9,
    "Sky Sports": 8, "L'Equipe": 9, "Kicker": 8, "Al Jazeera Sports": 7,
    # Tier 4: Social platforms (lower credibility per item)
    "twitter": 4, "reddit": 3, "youtube": 5, "tiktok": 2,
    "instagram": 3, "telegram": 4,
    # Tier 5: Forums/blogs (lowest)
    "forocoches": 2, "mediavida": 2, "Football Espana": 4,
    "La Colina de Nervion": 5, "TribaLa": 3,
    "Todo Fichajes": 4, "FutbolFantasy": 3,
    "Soy del Betis": 3, "Sevilla Fans": 3,
}
DEFAULT_SOURCE_WEIGHT = 4

# Server
HOST = "0.0.0.0"
PORT = 8000
