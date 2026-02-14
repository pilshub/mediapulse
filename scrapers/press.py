import aiohttp
import feedparser
import asyncio
import logging
import unicodedata
import re
from datetime import datetime
from bs4 import BeautifulSoup

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import SPANISH_PRESS_FEEDS, GOOGLE_NEWS_RSS, GOOGLE_NEWS_RSS_INTL, MAX_RSS_ITEMS, PRESS_SITE_SEARCH
from db import normalize_date

log = logging.getLogger("agentradar")


def _normalize(text):
    """Remove accents and normalize for comparison: Campaña -> campana"""
    text = unicodedata.normalize('NFD', text.lower())
    return ''.join(c for c in text if unicodedata.category(c) != 'Mn')


async def _fetch_google_rss(session, query, source_label, limit=MAX_RSS_ITEMS):
    """Fetch a Google News RSS query and return parsed items."""
    url = GOOGLE_NEWS_RSS.format(query=query.replace(" ", "+"))
    items = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                text = await resp.text()
                feed = feedparser.parse(text)
                for entry in feed.entries[:limit]:
                    items.append({
                        "source": source_label,
                        "title": entry.get("title", ""),
                        "url": entry.get("link", ""),
                        "summary": entry.get("summary", "")[:500],
                        "published_at": _parse_date(entry),
                    })
    except Exception as e:
        log.error(f"[press] {source_label} RSS error: {e}")
    return items


async def scrape_google_news(player_name, session, club=None):
    """Google News search in Spanish + international languages."""
    quoted = f'"{player_name}"'

    # Spanish (main)
    tasks = [
        _fetch_google_rss(session, f'{quoted}+futbol', "Google News"),
    ]
    if club:
        tasks.append(_fetch_google_rss(session, f'{quoted}+"{club}"', "Google News"))

    # International searches (EN, IT, AR, FR, DE)
    intl_queries = {
        "en": [f'{quoted}+football', f'{quoted}+soccer'],
        "it": [f'{quoted}+calcio'],
        "ar": [f'{quoted}+كرة+القدم'],
        "fr": [f'{quoted}+football'],
        "de": [f'{quoted}+fussball'],
    }
    if club:
        for lang in intl_queries:
            intl_queries[lang].append(f'{quoted}+"{club}"')

    for lang, queries in intl_queries.items():
        rss_template = GOOGLE_NEWS_RSS_INTL.get(lang)
        if not rss_template:
            continue
        for q in queries:
            tasks.append(_fetch_google_rss_intl(session, q, f"Google News ({lang.upper()})", rss_template))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    items = []
    for r in results:
        if isinstance(r, list):
            items.extend(r)
    return items


async def _fetch_google_rss_intl(session, query, source_label, rss_template, limit=MAX_RSS_ITEMS):
    """Fetch international Google News RSS."""
    url = rss_template.format(query=query.replace(" ", "+"))
    items = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                text = await resp.text()
                feed = feedparser.parse(text)
                for entry in feed.entries[:limit]:
                    items.append({
                        "source": source_label,
                        "title": entry.get("title", ""),
                        "url": entry.get("link", ""),
                        "summary": entry.get("summary", "")[:500],
                        "published_at": _parse_date(entry),
                    })
    except Exception as e:
        log.error(f"[press] {source_label} RSS error: {e}")
    return items


async def scrape_site_search(player_name, session, club=None):
    """Search for the player inside specific newspaper websites using Google News site: operator."""
    items = []
    quoted = f'"{player_name}"'

    async def search_site(source_name, domain):
        query = f'{quoted}+site:{domain}'
        return await _fetch_google_rss(session, query, source_name, limit=20)

    tasks = [search_site(name, domain) for name, domain in PRESS_SITE_SEARCH.items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, list):
            items.extend(result)
        elif isinstance(result, Exception):
            log.error(f"[press] Site search error: {result}")

    log.info(f"[press] Site search: {len(items)} noticias de {len(PRESS_SITE_SEARCH)} periodicos")
    return items


async def scrape_spanish_press(player_name, session):
    """Scan RSS feeds for mentions of the player."""
    items = []
    name_norm = _normalize(player_name)
    name_parts = [_normalize(p) for p in player_name.split() if len(p) > 2]

    async def fetch_feed(source, url):
        feed_items = []
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    feed = feedparser.parse(text)
                    for entry in feed.entries[:100]:
                        content = _normalize(entry.get("title", "") + " " + entry.get("summary", ""))
                        if name_norm in content or all(part in content for part in name_parts):
                            feed_items.append({
                                "source": source,
                                "title": entry.get("title", ""),
                                "url": entry.get("link", ""),
                                "summary": entry.get("summary", "")[:500],
                                "published_at": _parse_date(entry),
                            })
        except Exception as e:
            log.error(f"[press] {source} RSS feed error: {e}")
        return feed_items

    tasks = [fetch_feed(source, url) for source, url in SPANISH_PRESS_FEEDS.items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, list):
            items.extend(result)

    return items


async def _fetch_article_text(session, url, timeout=8):
    """Fetch and extract the main text content of a news article."""
    try:
        # Follow Google News redirects to get real article URL
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout),
                               allow_redirects=True) as resp:
            if resp.status != 200:
                return ""
            html = await resp.text()

        soup = BeautifulSoup(html, "lxml")

        # Remove scripts, styles, nav, header, footer, ads
        for tag in soup.find_all(["script", "style", "nav", "header", "footer",
                                   "aside", "iframe", "form", "noscript"]):
            tag.decompose()

        # Try common article content selectors
        article = (
            soup.find("article")
            or soup.find("div", class_=re.compile(r"article|post|content|entry|body", re.I))
            or soup.find("main")
        )

        if article:
            paragraphs = article.find_all("p")
        else:
            paragraphs = soup.find_all("p")

        text = " ".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 30)
        # Limit to ~2000 chars to save tokens
        return text[:2000] if text else ""
    except Exception:
        return ""


async def _enrich_articles_with_text(session, items, max_concurrent=5):
    """Fetch full article text for press items in parallel."""
    sem = asyncio.Semaphore(max_concurrent)

    async def fetch_one(item):
        async with sem:
            url = item.get("url", "")
            if not url or "news.google.com" in url:
                # Google News URLs redirect, try anyway
                pass
            text = await _fetch_article_text(session, url)
            if text:
                item["full_text"] = text
                # Also enrich summary if it was just HTML
                if item.get("summary", "").startswith("<"):
                    item["summary"] = text[:500]

    await asyncio.gather(*[fetch_one(item) for item in items], return_exceptions=True)
    enriched = sum(1 for i in items if i.get("full_text"))
    log.info(f"[press] Article text enrichment: {enriched}/{len(items)} articles fetched")


async def scrape_all_press(player_name, club=None, limit_multiplier=1):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AgentRadar/1.0"}
    if limit_multiplier > 1:
        log.info(f"[press] Deep scrape mode: {limit_multiplier}x limits")
    async with aiohttp.ClientSession(headers=headers) as session:
        google, site_search, rss_feeds = await asyncio.gather(
            scrape_google_news(player_name, session, club),
            scrape_site_search(player_name, session, club),
            scrape_spanish_press(player_name, session),
        )
        all_items = google + site_search + rss_feeds

    # Filter out non-article pages (Transfermarkt profiles, stats pages, etc.)
    _profile_patterns = [
        "/profil/spieler/", "/transfers/spieler/", "/leistungsdaten/spieler/",
        "/marktwertverlauf/spieler/", "/statistik/spieler/", "/national/spieler/",
        "/erfolge/spieler/", "/rueckennummern/spieler/",
        "/perfil/jugador/", "/rendimiento/jugador/", "/historial/jugador/",
    ]
    filtered_items = []
    profile_removed = 0
    for item in all_items:
        url = (item.get("url") or "").lower()
        if any(pat in url for pat in _profile_patterns):
            profile_removed += 1
            continue
        filtered_items.append(item)
    if profile_removed:
        log.info(f"[press] Filtered out {profile_removed} profile/stats pages (non-articles)")
    all_items = filtered_items

    # Dedup by URL
    seen = set()
    unique = []
    for item in all_items:
        if item["url"] and item["url"] not in seen:
            seen.add(item["url"])
            unique.append(item)

    # Relevance filter: require BOTH first name AND last name to avoid false positives
    # e.g. "Joaquín Sánchez" must NOT match when searching "Rodri Sánchez"
    name_parts = player_name.strip().split() if player_name else []
    last_name = _normalize(name_parts[-1]) if name_parts else ""
    first_name = _normalize(name_parts[0]) if len(name_parts) > 1 else ""
    if last_name and len(last_name) > 2:
        filtered = []
        for item in unique:
            text = _normalize(item.get("title", "") + " " + item.get("summary", ""))
            if last_name in text and (first_name in text or len(name_parts) == 1):
                filtered.append(item)
        log.info(f"[press] Relevance filter: {len(unique)} -> {len(filtered)} (name='{first_name} {last_name}')")
        unique = filtered

    log.info(f"[press] Total: {len(unique)} noticias (Google={len(google)}, SiteSearch={len(site_search)}, RSS={len(rss_feeds)})")

    # Enrich articles with full text for better GPT-4o analysis
    if unique:
        async with aiohttp.ClientSession(headers=headers) as session:
            await _enrich_articles_with_text(session, unique)

    return unique


def _parse_date(entry):
    for field in ["published_parsed", "updated_parsed"]:
        tp = entry.get(field)
        if tp:
            try:
                return datetime(*tp[:6]).isoformat()
            except Exception:
                pass
    # Try parsing raw date strings before giving up
    for field in ["published", "updated"]:
        raw = entry.get(field, "")
        if raw:
            parsed = normalize_date(raw)
            if parsed:
                return parsed
    # Return empty — DB will use scraped_at as fallback, NOT datetime.now()
    return ""
