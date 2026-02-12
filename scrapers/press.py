import aiohttp
import feedparser
import asyncio
import logging
import unicodedata
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import SPANISH_PRESS_FEEDS, GOOGLE_NEWS_RSS, MAX_RSS_ITEMS, PRESS_SITE_SEARCH

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
    """Generic Google News search for the player."""
    quoted = f'"{player_name}"'
    items = await _fetch_google_rss(session, f'{quoted}+futbol', "Google News")

    if club:
        club_items = await _fetch_google_rss(session, f'{quoted}+"{club}"', "Google News")
        items.extend(club_items)

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

    # Dedup by URL
    seen = set()
    unique = []
    for item in all_items:
        if item["url"] and item["url"] not in seen:
            seen.add(item["url"])
            unique.append(item)

    # Relevance filter: discard items that don't mention the player's last name
    last_name = _normalize(player_name.split()[-1]) if player_name else ""
    if last_name and len(last_name) > 2:
        filtered = []
        for item in unique:
            text = _normalize(item.get("title", "") + " " + item.get("summary", ""))
            if last_name in text:
                filtered.append(item)
        log.info(f"[press] Relevance filter: {len(unique)} -> {len(filtered)} (last name '{last_name}')")
        unique = filtered

    log.info(f"[press] Total: {len(unique)} noticias (Google={len(google)}, SiteSearch={len(site_search)}, RSS={len(rss_feeds)})")
    return unique


def _parse_date(entry):
    for field in ["published_parsed", "updated_parsed"]:
        tp = entry.get(field)
        if tp:
            try:
                return datetime(*tp[:6]).isoformat()
            except Exception:
                pass
    return entry.get("published", entry.get("updated", datetime.now().isoformat()))
