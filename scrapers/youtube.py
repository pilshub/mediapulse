import aiohttp
import asyncio
import json
import logging
import re
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import normalize_date
from config import MAX_YOUTUBE_RESULTS

log = logging.getLogger("agentradar")


async def scrape_youtube(player_name, session=None):
    """Search YouTube by scraping search results page."""
    items = []
    close_session = False
    if not session:
        session = aiohttp.ClientSession()
        close_session = True

    queries = [
        f'"{player_name}" futbol',
        f'"{player_name}" goles',
        f'"{player_name}" football',
        f'"{player_name}" goals highlights',
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    }

    for query in queries:
        try:
            url = "https://www.youtube.com/results"
            params = {"search_query": query}
            async with session.get(
                url, params=params, headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    videos = _parse_youtube_html(html)
                    items.extend(videos[:MAX_YOUTUBE_RESULTS])
                    log.info(f"[youtube] '{query}': {len(videos)} videos found")
                else:
                    log.warning(f"[youtube] YouTube returned {resp.status}")
        except Exception as e:
            log.error(f"[youtube] Search error for '{query}': {e}")
        await asyncio.sleep(1)

    # Deduplicate by URL
    seen = set()
    unique = []
    for item in items:
        if item["url"] not in seen:
            seen.add(item["url"])
            unique.append(item)

    log.info(f"[youtube] {len(unique)} videos totales")
    if close_session:
        await session.close()
    return unique


def _parse_youtube_html(html):
    """Extract video data from YouTube search results page."""
    videos = []
    try:
        # YouTube embeds initial data as JSON in the page
        match = re.search(r'var ytInitialData = ({.*?});', html)
        if not match:
            match = re.search(r'ytInitialData\s*=\s*({.*?});', html)
        if not match:
            log.warning("[youtube] Could not find ytInitialData in page")
            return []

        data = json.loads(match.group(1))

        # Navigate the nested structure to find video renderers
        contents = (
            data.get("contents", {})
            .get("twoColumnSearchResultsRenderer", {})
            .get("primaryContents", {})
            .get("sectionListRenderer", {})
            .get("contents", [])
        )

        for section in contents:
            item_section = section.get("itemSectionRenderer", {}).get("contents", [])
            for item in item_section:
                renderer = item.get("videoRenderer")
                if not renderer:
                    continue

                vid_id = renderer.get("videoId", "")
                title = ""
                title_runs = renderer.get("title", {}).get("runs", [])
                if title_runs:
                    title = title_runs[0].get("text", "")

                author = (
                    renderer.get("ownerText", {}).get("runs", [{}])[0].get("text", "")
                    if renderer.get("ownerText", {}).get("runs")
                    else ""
                )

                view_text = renderer.get("viewCountText", {}).get("simpleText", "0")
                views = _parse_view_count(view_text)

                published = renderer.get("publishedTimeText", {}).get("simpleText", "")

                videos.append({
                    "platform": "youtube",
                    "author": author,
                    "text": title,
                    "url": f"https://youtube.com/watch?v={vid_id}",
                    "likes": views,
                    "retweets": 0,
                    "created_at": normalize_date(published),
                    "views": views,
                })

    except json.JSONDecodeError as e:
        log.error(f"[youtube] JSON parse error: {e}")
    except Exception as e:
        log.error(f"[youtube] Parse error: {e}")

    return videos


def _parse_view_count(text):
    """Parse '1.234 visualizaciones' or '1.2M views' to int."""
    if not text:
        return 0
    text = text.lower().replace(".", "").replace(",", "")
    text = re.sub(r'[^\d kmb]', '', text).strip()
    try:
        if 'm' in text:
            return int(float(text.replace('m', '').strip()) * 1_000_000)
        if 'k' in text:
            return int(float(text.replace('k', '').strip()) * 1_000)
        if 'b' in text:
            return int(float(text.replace('b', '').strip()) * 1_000_000_000)
        nums = re.findall(r'\d+', text)
        return int(nums[0]) if nums else 0
    except Exception:
        return 0
