"""Telegram public channel scraper - no auth needed."""
import re
import aiohttp
import logging
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import normalize_date

log = logging.getLogger("agentradar")

TG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


async def scrape_telegram_channel(channel, player_name, session):
    """Scrape public Telegram channel for mentions of player_name.

    Uses the public preview at t.me/s/{channel} which doesn't require auth.
    Returns list of social-mention-style dicts.
    """
    if not channel or not player_name:
        return []

    url = f"https://t.me/s/{channel}"
    items = []

    try:
        async with session.get(url, headers=TG_HEADERS,
                               timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                log.warning(f"[telegram-scraper] HTTP {resp.status} for {channel}")
                return []

            html = await resp.text()

            # Extract messages from the public preview HTML
            messages = re.findall(
                r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
                html, re.DOTALL,
            )

            # Extract all <time datetime="..."> tags (one per message block)
            datetimes = re.findall(
                r'<time[^>]*datetime="([^"]+)"',
                html,
            )

            name_lower = player_name.lower()
            name_parts = name_lower.split()

            for i, msg_html in enumerate(messages):
                # Strip HTML tags to get plain text
                text = re.sub(r'<[^>]+>', ' ', msg_html).strip()
                text = re.sub(r'\s+', ' ', text)

                # Check if player is mentioned
                text_lower = text.lower()
                if name_lower not in text_lower:
                    # Try partial match (last name)
                    if len(name_parts) > 1 and name_parts[-1] not in text_lower:
                        continue
                    elif len(name_parts) == 1:
                        continue

                # Get corresponding date if available
                msg_date = None
                if i < len(datetimes):
                    msg_date = normalize_date(datetimes[i])
                if not msg_date:
                    msg_date = datetime.now().isoformat()

                items.append({
                    "platform": "telegram",
                    "author": channel,
                    "text": text[:500],
                    "url": f"https://t.me/s/{channel}",
                    "likes": 0,
                    "retweets": 0,
                    "created_at": msg_date,
                })

        log.info(f"[telegram-scraper] {channel}: {len(items)} mentions of {player_name}")
    except Exception as e:
        log.error(f"[telegram-scraper] Error scraping {channel}: {e}")

    return items


async def scrape_all_telegram(player_name, channels):
    """Scrape all configured Telegram channels for player mentions."""
    if not channels:
        return []

    items = []
    async with aiohttp.ClientSession() as session:
        for channel in channels:
            channel_items = await scrape_telegram_channel(channel, player_name, session)
            items.extend(channel_items)

    log.info(f"[telegram-scraper] Total: {len(items)} mentions across {len(channels)} channels")
    return items
