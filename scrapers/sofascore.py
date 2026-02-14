import aiohttp
import asyncio
import logging
import re

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import APIFY_TOKEN, APIFY_BASE, SOFASCORE_ACTOR

log = logging.getLogger("agentradar")


async def scrape_sofascore_ratings(sofascore_url, max_retries=2):
    """Scrape player match ratings from SofaScore via Apify actor."""
    if not APIFY_TOKEN or not sofascore_url:
        return []

    input_data = {
        "startUrls": [{"url": sofascore_url}],
    }

    items = []
    async with aiohttp.ClientSession() as session:
        for attempt in range(max_retries + 1):
            try:
                run_url = f"{APIFY_BASE}/acts/{SOFASCORE_ACTOR}/runs?token={APIFY_TOKEN}"
                async with session.post(run_url, json=input_data,
                                        timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status not in (200, 201):
                        body = await resp.text()
                        log.error(f"[sofascore] Apify start error {resp.status}: {body[:200]}")
                        if attempt < max_retries:
                            await asyncio.sleep(2 ** (attempt + 1))
                            continue
                        return []
                    run_data = await resp.json()

                run_id = run_data["data"]["id"]
                status = "RUNNING"
                for _ in range(60):
                    await asyncio.sleep(5)
                    status_url = f"{APIFY_BASE}/actor-runs/{run_id}?token={APIFY_TOKEN}"
                    async with session.get(status_url) as resp:
                        status_data = await resp.json()
                        status = status_data["data"]["status"]
                        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                            break

                if status != "SUCCEEDED":
                    log.warning(f"[sofascore] Apify run ended: {status}")
                    return []

                dataset_id = status_data["data"]["defaultDatasetId"]
                data_url = f"{APIFY_BASE}/datasets/{dataset_id}/items?token={APIFY_TOKEN}&limit=100"
                async with session.get(data_url) as resp:
                    raw_items = await resp.json()

                items = _parse_sofascore_data(raw_items)
                log.info(f"[sofascore] Scraped {len(items)} match ratings")
                return items

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                log.error(f"[sofascore] Error (attempt {attempt+1}/{max_retries+1}): {e}")
                if attempt < max_retries:
                    await asyncio.sleep(2 ** (attempt + 1))
                else:
                    return []
            except Exception as e:
                log.error(f"[sofascore] Unexpected error: {e}")
                return []

    return items


def _parse_sofascore_data(raw_items):
    """Parse raw SofaScore Apify output into structured match ratings."""
    ratings = []
    for item in raw_items:
        # The Apify actor may return different structures depending on the page
        # Try to extract match-level data
        rating = _extract_rating(item)
        if rating:
            ratings.append(rating)
        # Also check if item contains a list of matches
        matches = item.get("matches") or item.get("events") or item.get("statistics") or []
        if isinstance(matches, list):
            for match in matches:
                r = _extract_rating(match)
                if r:
                    ratings.append(r)
    return ratings


def _extract_rating(data):
    """Extract a single match rating from a data dict."""
    if not isinstance(data, dict):
        return None

    rating = (data.get("rating") or data.get("averageRating")
              or data.get("playerRating") or data.get("score"))
    if not rating:
        return None

    try:
        rating = float(rating)
    except (ValueError, TypeError):
        return None

    if rating < 1 or rating > 10:
        return None

    match_date = (data.get("date") or data.get("matchDate") or data.get("startTimestamp")
                  or data.get("event", {}).get("startTimestamp", "") if isinstance(data.get("event"), dict) else "")
    if isinstance(match_date, (int, float)):
        from datetime import datetime
        try:
            match_date = datetime.fromtimestamp(match_date).strftime("%Y-%m-%d")
        except Exception:
            match_date = ""

    opponent = (data.get("opponent") or data.get("opponentTeam", {}).get("name", "")
                if isinstance(data.get("opponentTeam"), dict) else
                data.get("awayTeam", {}).get("name", "") if isinstance(data.get("awayTeam"), dict) else "")
    if not opponent and isinstance(data.get("event"), dict):
        opponent = data["event"].get("awayTeam", {}).get("name", "")

    competition = (data.get("competition") or data.get("tournament", {}).get("name", "")
                   if isinstance(data.get("tournament"), dict) else
                   data.get("league", ""))

    return {
        "match_date": str(match_date) if match_date else "",
        "competition": str(competition) if competition else "",
        "opponent": str(opponent) if opponent else "",
        "rating": rating,
        "minutes_played": int(data.get("minutesPlayed", 0) or data.get("minutes", 0) or 0),
        "goals": int(data.get("goals", 0) or 0),
        "assists": int(data.get("assists", 0) or 0),
        "yellow_cards": int(data.get("yellowCards", 0) or data.get("yellowCard", 0) or 0),
        "red_cards": int(data.get("redCards", 0) or data.get("redCard", 0) or 0),
    }
