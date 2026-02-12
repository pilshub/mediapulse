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

# Telegram channels to scrape
TELEGRAM_CHANNELS = [c.strip() for c in os.getenv("TELEGRAM_CHANNELS", "").split(",") if c.strip()]

# Apify
APIFY_BASE = "https://api.apify.com/v2"
TWITTER_ACTOR = "apidojo~tweet-scraper"
INSTAGRAM_ACTOR = "apify~instagram-scraper"
TIKTOK_ACTOR = "clockworks~tiktok-scraper"

# RSS Feeds prensa deportiva espanola
SPANISH_PRESS_FEEDS = {
    "Marca": "https://e00-marca.uecdn.es/rss/futbol/primera-division.xml",
    "AS": "https://as.com/rss/tags/futbol.xml",
    "Mundo Deportivo": "https://www.mundodeportivo.com/feed/rss/futbol",
    "El Pais Deportes": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/deportes/portada",
    "El Mundo Deportes": "https://e00-elmundo.uecdn.es/elmundodeporte/rss/futbol.xml",
    "Relevo": "https://www.relevo.com/rss/futbol.xml",
    "Gazzetta": "https://www.gazzetta.it/rss/Calcio.xml",
    "Tuttosport": "https://www.tuttosport.com/rss/calcio.xml",
}

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}+futbol&hl=es&gl=ES&ceid=ES:es"
GOOGLE_ALERTS_RSS = "https://www.google.com/alerts/feeds/{alert_id}"

# YouTube (via Invidious public API - no key needed)
INVIDIOUS_INSTANCES = [
    "https://vid.puffyan.us",
    "https://invidious.fdn.fr",
    "https://inv.nadeko.net",
    "https://invidious.nerdvpn.de",
]
MAX_YOUTUBE_RESULTS = 20

# Reddit
REDDIT_SUBREDDITS = ["soccer", "LaLiga", "futbol", "calcio", "SerieA", "football", "PremierLeague", "Bundesliga", "Ligue1"]

# Limites scraping
MAX_TWEETS_MENTIONS = 200
MAX_TWEETS_PLAYER = 100
MAX_INSTAGRAM_POSTS = 50
MAX_REDDIT_POSTS = 50
MAX_RSS_ITEMS = 50
MAX_TIKTOK_POSTS = 30

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

# Server
HOST = "0.0.0.0"
PORT = 8000
