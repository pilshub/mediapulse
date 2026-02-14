import aiohttp
import asyncio
import logging

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import normalize_date
from config import (
    APIFY_TOKEN, APIFY_BASE, TWITTER_ACTOR, INSTAGRAM_ACTOR,
    MAX_TWEETS_PLAYER, MAX_INSTAGRAM_POSTS,
)

log = logging.getLogger("agentradar")


async def _run_apify_actor(session, actor_id, input_data, max_items=100, retries=2):
    if not APIFY_TOKEN:
        return []

    for attempt in range(retries + 1):
        try:
            run_url = f"{APIFY_BASE}/acts/{actor_id}/runs?token={APIFY_TOKEN}"
            async with session.post(
                run_url, json=input_data, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status not in (200, 201):
                    body = await resp.text()
                    log.error(f"[player] Apify start error for {actor_id}: {resp.status} {body[:200]}")
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
                log.warning(f"[player] Apify {actor_id} ended: {status}")
                return []

            dataset_id = status_data["data"]["defaultDatasetId"]
            data_url = f"{APIFY_BASE}/datasets/{dataset_id}/items?token={APIFY_TOKEN}&limit={max_items}"
            async with session.get(data_url) as resp:
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log.error(f"[player] Apify {actor_id} error (attempt {attempt+1}/{retries+1}): {e}")
            if attempt < retries:
                await asyncio.sleep(2 ** (attempt + 1))
            else:
                return []
        except Exception as e:
            log.error(f"[player] Apify {actor_id} unexpected error: {e}")
            return []
    return []


async def scrape_player_twitter(twitter_handle, session, max_items=None):
    if not twitter_handle:
        return []

    limit = max_items or MAX_TWEETS_PLAYER
    input_data = {
        "startUrls": [{"url": f"https://twitter.com/{twitter_handle}"}],
        "maxItems": limit,
        "sort": "Latest",
    }

    tweets = await _run_apify_actor(session, TWITTER_ACTOR, input_data, limit)
    items = []

    for tweet in tweets:
        text = tweet.get("full_text", tweet.get("text", ""))
        likes = tweet.get("likeCount", tweet.get("favorite_count", 0)) or 0
        retweets = tweet.get("retweetCount", tweet.get("retweet_count", 0)) or 0
        replies = tweet.get("replyCount", tweet.get("reply_count", 0)) or 0
        views = tweet.get("viewCount", tweet.get("views", 0)) or 0

        total_eng = likes + retweets + replies
        eng_rate = (total_eng / views) if views > 0 else 0

        media_type = "text"
        if tweet.get("media") or tweet.get("entities", {}).get("media"):
            media_type = "media"
        if tweet.get("isRetweet") or tweet.get("retweeted_status"):
            media_type = "retweet"

        # Extract image URL from media
        image_url = ""
        media_list = tweet.get("media") or tweet.get("entities", {}).get("media", [])
        if isinstance(media_list, list) and media_list:
            image_url = media_list[0].get("media_url_https", "") or media_list[0].get("url", "")

        items.append({
            "platform": "twitter",
            "text": text,
            "url": tweet.get("url", ""),
            "likes": likes,
            "comments": replies,
            "shares": retweets,
            "views": views,
            "engagement_rate": round(eng_rate, 6),
            "media_type": media_type,
            "image_url": image_url,
            "posted_at": normalize_date(tweet.get("createdAt", tweet.get("created_at", ""))),
        })

    log.info(f"[player] Twitter @{twitter_handle}: {len(items)} posts")
    return items


async def scrape_player_instagram(instagram_handle, session, max_items=None):
    if not instagram_handle:
        return []

    limit = max_items or MAX_INSTAGRAM_POSTS
    input_data = {
        "directUrls": [f"https://www.instagram.com/{instagram_handle}/"],
        "resultsType": "posts",
        "resultsLimit": limit,
    }

    posts = await _run_apify_actor(session, INSTAGRAM_ACTOR, input_data, limit)
    items = []

    for post in posts:
        likes = post.get("likesCount", post.get("likes", 0)) or 0
        comments = post.get("commentsCount", post.get("comments", 0)) or 0
        views = post.get("videoViewCount", post.get("views", 0)) or 0
        followers = post.get("ownerFollowerCount", 0) or 0

        eng_rate = ((likes + comments) / followers) if followers > 0 else 0

        ptype = post.get("type", "Image")
        if ptype == "Video":
            media_type = "video"
        elif ptype == "Sidecar":
            media_type = "carousel"
        else:
            media_type = "image"

        # Extract image/thumbnail URL
        image_url = post.get("displayUrl", "") or post.get("thumbnailSrc", "") or post.get("previewUrl", "")

        items.append({
            "platform": "instagram",
            "text": post.get("caption", "") or "",
            "url": post.get("url", ""),
            "likes": likes,
            "comments": comments,
            "shares": 0,
            "views": views,
            "engagement_rate": round(eng_rate, 6),
            "media_type": media_type,
            "image_url": image_url,
            "posted_at": normalize_date(post.get("timestamp", post.get("taken_at", ""))),
        })

    log.info(f"[player] Instagram @{instagram_handle}: {len(items)} posts")
    return items


async def scrape_all_player_posts(twitter_handle=None, instagram_handle=None, limit_multiplier=1):
    # Override limits for deep scrape
    tw_limit = MAX_TWEETS_PLAYER * limit_multiplier
    ig_limit = MAX_INSTAGRAM_POSTS * limit_multiplier
    if limit_multiplier > 1:
        log.info(f"[player] Deep scrape mode: {limit_multiplier}x limits (tw={tw_limit}, ig={ig_limit})")

    async with aiohttp.ClientSession() as session:
        twitter, instagram = await asyncio.gather(
            scrape_player_twitter(twitter_handle, session, max_items=tw_limit),
            scrape_player_instagram(instagram_handle, session, max_items=ig_limit),
        )
    total = twitter + instagram
    log.info(f"[player] Total posts del jugador: {len(total)}")
    return total
