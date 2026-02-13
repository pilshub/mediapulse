import aiohttp
import asyncio
import logging
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import normalize_date
from config import (
    APIFY_TOKEN, APIFY_BASE, TWITTER_ACTOR, TIKTOK_ACTOR,
    INSTAGRAM_HASHTAG_ACTOR, MAX_INSTAGRAM_MENTIONS,
    REDDIT_SUBREDDITS, MAX_TWEETS_MENTIONS, MAX_REDDIT_POSTS, MAX_TIKTOK_POSTS,
    TELEGRAM_CHANNELS, GOOGLE_NEWS_RSS, FORUM_SITES,
)
from scrapers.youtube import scrape_youtube
from scrapers.telegram import scrape_all_telegram
import feedparser
import unicodedata

log = logging.getLogger("agentradar")


def _normalize(text):
    """Remove accents and normalize for comparison."""
    text = unicodedata.normalize('NFD', text.lower())
    return ''.join(c for c in text if unicodedata.category(c) != 'Mn')


def _filter_by_relevance(items, player_name):
    """Post-scrape filter: discard items that don't mention the player's surname.
    This catches TikTok/YouTube/Reddit false positives like 'Venezia FC' general
    news or 'Juan Antonio Casas' when searching for 'Antonio Casas'.
    Extra strict for TikTok due to fuzzy search behavior.
    """
    if not player_name or not items:
        return items

    name_parts = player_name.strip().split()
    if len(name_parts) < 2:
        return items  # Can't reliably filter with just one name

    # Use last name as primary filter. For compound names like "Rodri Sanchez",
    # surname = "sanchez". For "Antonio Casas", surname = "casas".
    surname = _normalize(name_parts[-1])
    # Also require first name nearby to avoid matching different people with same surname
    first_name = _normalize(name_parts[0])

    if len(surname) < 3:
        return items  # Too short to filter reliably

    filtered = []
    removed = 0
    for item in items:
        platform = item.get("platform", "")

        # TikTok: stricter filtering - must appear in actual caption
        if platform == "tiktok":
            caption = _normalize(item.get("text", "") or "")
            # Skip very short/empty captions (often generic/unrelated)
            if len(caption.strip()) < 15:
                removed += 1
                continue
            # Surname must appear in the caption itself, not just metadata
            if surname not in caption:
                removed += 1
                continue
            # Require first name too for confidence
            if first_name not in caption:
                removed += 1
                continue
            filtered.append(item)
        else:
            # Standard filter for other platforms
            text = _normalize(
                (item.get("text", "") or "") + " " +
                (item.get("title", "") or "") + " " +
                (item.get("author", "") or "")
            )
            if surname in text and (first_name in text or len(name_parts) == 1):
                filtered.append(item)
            else:
                removed += 1

    if removed:
        log.info(f"[social] Relevance filter: {len(items)} -> {len(filtered)} "
                 f"(removed {removed} items not mentioning '{player_name}')")
    return filtered


async def _apify_run_with_retry(session, actor, input_data, max_items, label, retries=2):
    """Run Apify actor with exponential backoff retry."""
    for attempt in range(retries + 1):
        try:
            run_url = f"{APIFY_BASE}/acts/{actor}/runs?token={APIFY_TOKEN}"
            async with session.post(run_url, json=input_data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status not in (200, 201):
                    body = await resp.text()
                    log.error(f"[social] {label} Apify start error {resp.status}: {body[:200]}")
                    if attempt < retries:
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
                log.warning(f"[social] {label} Apify run ended: {status}")
                return []

            dataset_id = status_data["data"]["defaultDatasetId"]
            data_url = f"{APIFY_BASE}/datasets/{dataset_id}/items?token={APIFY_TOKEN}&limit={max_items}"
            async with session.get(data_url) as resp:
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log.error(f"[social] {label} error (attempt {attempt+1}/{retries+1}): {e}")
            if attempt < retries:
                await asyncio.sleep(2 ** (attempt + 1))
            else:
                return []
        except Exception as e:
            log.error(f"[social] {label} unexpected error: {e}")
            return []
    return []


def _build_search_queries(player_name, twitter_handle=None, club=None):
    """Build search queries using Twitter advanced search syntax (multi-language)."""
    queries = [f'"{player_name}"']  # Exact match with quotes
    if club:
        queries.append(f'"{player_name}" {club}')
    if twitter_handle:
        queries.append(f"@{twitter_handle}")
    # International: English football keywords
    queries.append(f'"{player_name}" football OR soccer OR transfer OR goal')
    return queries


async def scrape_twitter_mentions(player_name, session, twitter_handle=None, club=None,
                                   max_items=None):
    if not APIFY_TOKEN:
        log.info("[social] No APIFY_TOKEN, skipping Twitter mentions")
        return []

    limit = max_items or MAX_TWEETS_MENTIONS
    search_terms = _build_search_queries(player_name, twitter_handle, club)
    log.info(f"[social] Twitter search terms: {search_terms} (limit={limit})")

    input_data = {
        "searchTerms": search_terms,
        "maxItems": limit,
        "sort": "Latest",
    }

    tweets = await _apify_run_with_retry(session, TWITTER_ACTOR, input_data, limit, "Twitter")
    items = []
    for tweet in tweets:
        items.append({
            "platform": "twitter",
            "author": tweet.get("author", {}).get("userName", "")
                or tweet.get("user", {}).get("screen_name", "unknown"),
            "text": tweet.get("full_text", tweet.get("text", "")),
            "url": tweet.get("url", ""),
            "likes": tweet.get("likeCount", tweet.get("favorite_count", 0)) or 0,
            "retweets": tweet.get("retweetCount", tweet.get("retweet_count", 0)) or 0,
            "created_at": normalize_date(tweet.get("createdAt", tweet.get("created_at", ""))),
        })

    log.info(f"[social] Twitter: {len(items)} menciones")
    return items


async def scrape_reddit(player_name, session):
    items = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    for sub in REDDIT_SUBREDDITS:
        try:
            url = f"https://www.reddit.com/r/{sub}/search.json"
            params = {
                "q": f'"{player_name}"',
                "sort": "new",
                "limit": 25,
                "restrict_sr": "true",
                "t": "year",
            }

            async with session.get(
                url, params=params, headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    posts = data.get("data", {}).get("children", [])
                    per_sub = MAX_REDDIT_POSTS // len(REDDIT_SUBREDDITS)
                    for post in posts[:per_sub]:
                        pd = post.get("data", {})
                        items.append({
                            "platform": "reddit",
                            "author": pd.get("author", ""),
                            "text": f"{pd.get('title', '')} {pd.get('selftext', '')[:300]}",
                            "url": f"https://reddit.com{pd.get('permalink', '')}",
                            "likes": pd.get("score", 0),
                            "retweets": pd.get("num_comments", 0),
                            "created_at": datetime.fromtimestamp(
                                pd.get("created_utc", 0)
                            ).isoformat()
                            if pd.get("created_utc")
                            else "",
                        })

            await asyncio.sleep(1.5)
        except Exception as e:
            log.error(f"[social] Reddit r/{sub} error: {e}")

    log.info(f"[social] Reddit: {len(items)} menciones")
    return items


async def scrape_tiktok_mentions(player_name, session, club=None, max_items=None):
    """Scrape TikTok mentions via Apify with retry.
    NOTE: TikTok search ignores exact-match quotes, so we DON'T include
    club name (it causes false positives like generic club news).
    We rely on post-scrape relevance filter instead.
    """
    if not APIFY_TOKEN:
        log.info("[social] No APIFY_TOKEN, skipping TikTok mentions")
        return []

    limit = max_items or MAX_TIKTOK_POSTS
    # Don't use quotes or club name - TikTok ignores them and they cause FPs
    search_query = player_name

    input_data = {
        "searchQueries": [search_query],
        "resultsPerPage": limit,
        "shouldDownloadVideos": False,
    }

    videos = await _apify_run_with_retry(session, TIKTOK_ACTOR, input_data, limit, "TikTok")
    items = []
    for video in videos:
        text = video.get("text", "") or video.get("desc", "")
        items.append({
            "platform": "tiktok",
            "author": video.get("authorMeta", {}).get("name", "")
                or video.get("author", {}).get("uniqueId", "unknown"),
            "text": text,
            "url": video.get("webVideoUrl", "") or video.get("url", ""),
            "likes": video.get("diggCount", video.get("likes", 0)) or 0,
            "retweets": video.get("shareCount", video.get("shares", 0)) or 0,
            "created_at": normalize_date(video.get("createTimeISO", video.get("created_at", ""))),
        })

    log.info(f"[social] TikTok: {len(items)} menciones")
    return items


async def scrape_google_web(player_name, session, club=None):
    """Search forums, blogs, and fan sites via Google News RSS with site: operator."""
    items = []
    quoted = f'"{player_name}"'

    for site_name, domain in FORUM_SITES.items():
        query = f'{quoted}+site:{domain}'
        url = GOOGLE_NEWS_RSS.format(query=query.replace(" ", "+"))
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    feed = feedparser.parse(text)
                    for entry in feed.entries[:10]:
                        items.append({
                            "platform": site_name.lower().replace(" ", "_"),
                            "author": site_name,
                            "text": entry.get("title", "") + " " + entry.get("summary", "")[:200],
                            "url": entry.get("link", ""),
                            "likes": 0,
                            "retweets": 0,
                            "created_at": _parse_date_simple(entry),
                        })
        except Exception as e:
            log.error(f"[social] Google web {site_name} error: {e}")

    log.info(f"[social] Google Web: {len(items)} resultados de {len(FORUM_SITES)} sitios")
    return items


def _parse_date_simple(entry):
    for field in ["published_parsed", "updated_parsed"]:
        tp = entry.get(field)
        if tp:
            try:
                return datetime(*tp[:6]).isoformat()
            except Exception:
                pass
    return entry.get("published", entry.get("updated", datetime.now().isoformat()))


async def scrape_instagram_mentions(player_name, session, instagram_handle=None, max_items=None):
    """Scrape Instagram hashtag/tag mentions via Apify."""
    if not APIFY_TOKEN:
        log.info("[social] No APIFY_TOKEN, skipping Instagram mentions")
        return []

    limit = max_items or MAX_INSTAGRAM_MENTIONS
    # Build hashtag from player name: "Rodri Sanchez" -> "rodrisanchez"
    hashtag = player_name.lower().replace(" ", "").replace("-", "")
    hashtags = [hashtag]
    # Also search with handle if available
    if instagram_handle:
        hashtags.append(instagram_handle.lower().replace("@", ""))

    input_data = {
        "hashtags": hashtags,
        "resultsLimit": limit,
    }

    posts = await _apify_run_with_retry(session, INSTAGRAM_HASHTAG_ACTOR, input_data, limit, "Instagram Mentions")
    items = []
    for post in posts:
        text = post.get("caption", "") or ""
        items.append({
            "platform": "instagram",
            "author": post.get("ownerUsername", "") or post.get("owner", {}).get("username", "unknown"),
            "text": text,
            "url": post.get("url", "") or post.get("shortCode", ""),
            "likes": post.get("likesCount", post.get("likes", 0)) or 0,
            "retweets": post.get("commentsCount", post.get("comments", 0)) or 0,
            "created_at": normalize_date(post.get("timestamp", post.get("taken_at", ""))),
        })

    log.info(f"[social] Instagram Mentions: {len(items)} posts (hashtags: {hashtags})")
    return items


async def scrape_all_social(player_name, twitter_handle=None, club=None, limit_multiplier=1, instagram_handle=None):
    # Override limits for deep scrape
    tw_limit = MAX_TWEETS_MENTIONS * limit_multiplier
    tk_limit = MAX_TIKTOK_POSTS * limit_multiplier
    if limit_multiplier > 1:
        log.info(f"[social] Deep scrape mode: {limit_multiplier}x limits (tw={tw_limit}, tk={tk_limit})")

    ig_limit = MAX_INSTAGRAM_MENTIONS * limit_multiplier

    async with aiohttp.ClientSession() as session:
        twitter, reddit, youtube, tiktok, ig_mentions = await asyncio.gather(
            scrape_twitter_mentions(player_name, session, twitter_handle, club,
                                    max_items=tw_limit),
            scrape_reddit(player_name, session),
            scrape_youtube(player_name, session),
            scrape_tiktok_mentions(player_name, session, club, max_items=tk_limit),
            scrape_instagram_mentions(player_name, session, instagram_handle, max_items=ig_limit),
        )

    # Telegram
    telegram = await scrape_all_telegram(player_name, TELEGRAM_CHANNELS)

    # Google Web Search (forums, blogs, fan sites)
    async with aiohttp.ClientSession() as session:
        web_results = await scrape_google_web(player_name, session, club)

    total = twitter + reddit + youtube + tiktok + ig_mentions + telegram + web_results
    log.info(f"[social] Total menciones (pre-filter): {len(total)} (Twitter={len(twitter)}, Reddit={len(reddit)}, YouTube={len(youtube)}, TikTok={len(tiktok)}, IG={len(ig_mentions)}, Telegram={len(telegram)}, Web={len(web_results)})")

    # Post-scrape relevance filter: remove items that don't mention the player
    total = _filter_by_relevance(total, player_name)
    log.info(f"[social] Total menciones (post-filter): {len(total)}")
    return total
