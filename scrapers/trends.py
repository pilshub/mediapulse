"""Google Trends search interest scraper (direct API, no dependencies)."""
import aiohttp
import json
import logging

log = logging.getLogger("agentradar")

TRENDS_BASE = "https://trends.google.com/trends"
TRENDS_HEADERS = {
    "accept-language": "es-ES,es;q=0.9,en;q=0.8",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


async def scrape_google_trends(player_name, geo="ES", time_range="today 1-m"):
    """Get Google Trends interest over time for a player name.

    Uses Google's internal API (2-step: get token, then get data).
    Returns dict with: average_interest, peak_interest, trend_direction, timeline
    """
    if not player_name:
        return None

    explore_payload = {
        "comparisonItem": [
            {"keyword": player_name, "geo": geo, "time": time_range}
        ],
        "category": 0,
        "property": "",
    }

    try:
        async with aiohttp.ClientSession(headers=TRENDS_HEADERS) as session:
            # Step 0: Get cookies by visiting main page
            async with session.get(
                TRENDS_BASE, timeout=aiohttp.ClientTimeout(total=10),
                allow_redirects=True,
            ) as resp:
                pass  # Just collect cookies

            # Step 1: Get widget tokens from /api/explore
            params = {
                "hl": "es",
                "tz": "-60",
                "req": json.dumps(explore_payload),
            }
            async with session.get(
                f"{TRENDS_BASE}/api/explore",
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    log.warning(f"[trends] Explore returned {resp.status} for '{player_name}'")
                    return None
                text = await resp.text()

            # Response starts with ")]}'" prefix (4-6 chars) - find first '{'
            json_start = text.index("{")
            data = json.loads(text[json_start:])

            # Find the TIMESERIES widget
            ts_widget = None
            for widget in data.get("widgets", []):
                if widget.get("id") == "TIMESERIES":
                    ts_widget = widget
                    break

            if not ts_widget:
                log.warning(f"[trends] No TIMESERIES widget for '{player_name}'")
                return None

            token = ts_widget["token"]
            request_obj = ts_widget["request"]

            # Step 2: Get actual time series data
            params = {
                "hl": "es",
                "tz": "-60",
                "req": json.dumps(request_obj),
                "token": token,
            }
            async with session.get(
                f"{TRENDS_BASE}/api/widgetdata/multiline",
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    log.warning(f"[trends] Multiline returned {resp.status}")
                    return None
                text = await resp.text()

            json_start = text.index("{")
            data = json.loads(text[json_start:])

            # Parse timeline data
            points = data.get("default", {}).get("timelineData", [])
            if not points:
                log.info(f"[trends] No data points for '{player_name}'")
                return {"average_interest": 0, "peak_interest": 0, "trend_direction": "stable", "timeline": []}

            values = [p["value"][0] for p in points]
            avg = round(sum(values) / len(values))
            peak = max(values)

            # Calculate trend direction: compare first half vs second half
            mid = len(values) // 2
            first_half_avg = sum(values[:mid]) / max(mid, 1)
            second_half_avg = sum(values[mid:]) / max(len(values) - mid, 1)
            if second_half_avg > first_half_avg * 1.2:
                direction = "up"
            elif second_half_avg < first_half_avg * 0.8:
                direction = "down"
            else:
                direction = "stable"

            timeline = [
                {"timestamp": int(p["time"]), "value": p["value"][0]}
                for p in points
            ]

            log.info(f"[trends] '{player_name}': avg={avg}, peak={peak}, trend={direction} ({len(points)} points)")
            return {
                "average_interest": avg,
                "peak_interest": peak,
                "trend_direction": direction,
                "data_points": len(points),
                "timeline": timeline,
            }

    except (ValueError, KeyError, json.JSONDecodeError) as e:
        log.warning(f"[trends] Parse error for '{player_name}': {e}")
        return None
    except Exception as e:
        log.error(f"[trends] Error for '{player_name}': {e}")
        return None
