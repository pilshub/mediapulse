"""Transfermarkt profile + performance stats scraper."""
import re
import aiohttp
import logging
from bs4 import BeautifulSoup

log = logging.getLogger("agentradar")

TM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}


async def scrape_transfermarkt_profile(tm_id):
    """Scrape basic profile info from Transfermarkt.

    Returns dict with: photo_url, market_value, contract_until, nationality, position
    """
    if not tm_id:
        return None

    url = f"https://www.transfermarkt.com/x/profil/spieler/{tm_id}"

    try:
        async with aiohttp.ClientSession(headers=TM_HEADERS) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15),
                                   allow_redirects=True) as resp:
                if resp.status != 200:
                    log.warning(f"[transfermarkt] HTTP {resp.status} for ID {tm_id}")
                    return None

                html = await resp.text()

                data = {}

                # Photo URL
                photo_match = re.search(r'<img[^>]*class="data-header__profile-image"[^>]*src="([^"]+)"', html)
                if not photo_match:
                    photo_match = re.search(r'<img[^>]*src="(https://img\.a\.transfermarkt\.technology/portrait/[^"]+)"', html)
                if photo_match:
                    data["photo_url"] = photo_match.group(1)

                # Market value
                mv_match = re.search(r'<a[^>]*class="data-header__market-value-wrapper"[^>]*>.*?([€$£]\s*[\d.,]+\s*(?:mill?\.|[MmKk]|bn))', html, re.DOTALL)
                if mv_match:
                    data["market_value"] = mv_match.group(1).strip()
                else:
                    mv_match2 = re.search(r'Valor de mercado.*?([€$£]\s*[\d.,]+\s*(?:mill?\.|[MmKk]))', html, re.DOTALL)
                    if mv_match2:
                        data["market_value"] = mv_match2.group(1).strip()

                # Contract until
                contract_match = re.search(r'(?:Contrato hasta|Contract expires).*?(\d{1,2}/\d{1,2}/\d{4}|\d{1,2}\.\d{1,2}\.\d{4}|[A-Za-z]+ \d{1,2}, \d{4})', html)
                if contract_match:
                    data["contract_until"] = contract_match.group(1)

                # Nationality
                nat_match = re.search(r'<span class="info-table__content info-table__content--bold">\s*<img[^>]*title="([^"]+)"[^>]*class="flaggenrahmen"', html)
                if nat_match:
                    data["nationality"] = nat_match.group(1)

                # Position
                pos_match = re.search(r'<li class="data-header__label">.*?(?:Posici|Position).*?</li>\s*<li class="data-header__content">\s*([^<]+)', html, re.DOTALL)
                if not pos_match:
                    pos_match = re.search(r'(?:Posici.n|Position).*?<span[^>]*>([^<]+)</span>', html, re.DOTALL)
                if pos_match:
                    data["position"] = pos_match.group(1).strip()

                log.info(f"[transfermarkt] Got profile for {tm_id}: {list(data.keys())}")
                return data if data else None

    except Exception as e:
        log.error(f"[transfermarkt] Error scraping {tm_id}: {e}")
        return None


async def scrape_transfermarkt_stats(tm_id):
    """Scrape current season performance stats from Transfermarkt.

    Returns dict with: appearances, goals, assists, minutes, yellows, reds, season
    """
    if not tm_id:
        return None

    # plus/1 gives extended view with all columns
    url = f"https://www.transfermarkt.com/x/leistungsdatendetails/spieler/{tm_id}/plus/1"

    try:
        async with aiohttp.ClientSession(headers=TM_HEADERS) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15),
                                   allow_redirects=True) as resp:
                if resp.status != 200:
                    log.warning(f"[transfermarkt] Stats HTTP {resp.status} for {tm_id}")
                    return None

                html = await resp.text()
                soup = BeautifulSoup(html, "lxml")

                # Find the main stats table
                tables = soup.find_all("div", class_="responsive-table")
                if not tables:
                    log.warning(f"[transfermarkt] No stats tables found for {tm_id}")
                    return None

                # Parse the footer/totals row which has aggregated stats
                stats = {
                    "appearances": 0, "goals": 0, "assists": 0,
                    "minutes": 0, "yellows": 0, "reds": 0,
                    "season": "", "competitions": [],
                }

                # Try to find the totals row (tfoot) in the first table
                table = tables[0].find("table", class_="items")
                if not table:
                    log.warning(f"[transfermarkt] No items table for {tm_id}")
                    return None

                tfoot = table.find("tfoot")
                if tfoot:
                    cells = tfoot.find_all("td")
                    # Footer: blank, "Total:", blank, blank, in_squad, appearances, goals_per_game, goals, assists, -, sub_in, sub_out, yellows, 2nd_yellow, reds, penalty_goals, minutes', total_minutes'
                    cell_texts = [c.get_text(strip=True) for c in cells]

                    def parse_int(text):
                        """Parse integer from cell text, handling ., ', -, etc."""
                        text = text.replace(".", "").replace("'", "").replace(",", "").replace("-", "0").strip()
                        return int(text) if text.isdigit() else 0

                    # Find "Total" label position and work from there
                    total_idx = -1
                    for i, t in enumerate(cell_texts):
                        if "total" in t.lower():
                            total_idx = i
                            break

                    if total_idx >= 0 and len(cell_texts) > total_idx + 14:
                        offset = total_idx + 1  # skip blanks after "Total"
                        # Skip blank cells after Total
                        while offset < len(cell_texts) and cell_texts[offset] == "":
                            offset += 1
                        # Now: in_squad, appearances, goals_per_game, goals, assists, ?, sub_in, sub_out, yellows, 2nd_yellow, reds, penalty, minutes_detail, minutes_total
                        remaining = cell_texts[offset:]
                        if len(remaining) >= 10:
                            stats["appearances"] = parse_int(remaining[1])  # appearances
                            stats["goals"] = parse_int(remaining[3])        # goals
                            stats["assists"] = parse_int(remaining[4])      # assists
                            stats["yellows"] = parse_int(remaining[8])      # yellows
                            stats["reds"] = parse_int(remaining[10]) if len(remaining) > 10 else 0  # reds
                            # Minutes is the last numeric cell
                            for txt in reversed(remaining):
                                mins = parse_int(txt)
                                if mins > 10:
                                    stats["minutes"] = mins
                                    break

                # Also parse individual rows for competition breakdown
                tbody = table.find("tbody")
                if tbody:
                    rows = tbody.find_all("tr", class_=["odd", "even"])
                    for row in rows:
                        cells = row.find_all("td")
                        cell_texts = [c.get_text(strip=True) for c in cells]
                        if len(cell_texts) >= 8:
                            # Row: season, blank, competition, blank, in_squad, appearances, goals_per_game, goals
                            comp_name = cell_texts[2]
                            season = cell_texts[0]
                            if comp_name and comp_name not in ["", "-"]:
                                app = int(cell_texts[5]) if cell_texts[5].isdigit() else 0
                                goals = int(cell_texts[7]) if cell_texts[7].isdigit() else 0
                                stats["competitions"].append({
                                    "name": f"{comp_name} ({season})" if season else comp_name,
                                    "appearances": app,
                                    "goals": goals,
                                })

                # Calculate current season stats (25/26 or latest)
                from datetime import datetime
                current_year = datetime.now().year
                season_str = f"{str(current_year - 1)[2:]}/{str(current_year)[2:]}"  # e.g. "25/26"

                current_season = {"appearances": 0, "goals": 0, "assists": 0,
                                  "minutes": 0, "yellows": 0, "reds": 0}
                # Sum competitions matching current season from row data
                for row in (tbody.find_all("tr", class_=["odd", "even"]) if tbody else []):
                    cells_t = [c.get_text(strip=True) for c in row.find_all("td")]
                    if len(cells_t) >= 8 and cells_t[0] == season_str:
                        current_season["appearances"] += int(cells_t[5]) if cells_t[5].isdigit() else 0
                        current_season["goals"] += int(cells_t[7]) if cells_t[7].isdigit() else 0

                stats["season"] = season_str
                stats["current_season"] = current_season

                # If totals row failed, sum from individual rows
                if stats["appearances"] == 0 and stats["competitions"]:
                    stats["appearances"] = sum(c["appearances"] for c in stats["competitions"])
                    stats["goals"] = sum(c["goals"] for c in stats["competitions"])

                log.info(f"[transfermarkt] Stats for {tm_id}: {stats['appearances']} apps, {stats['goals']} goals, {stats['assists']} assists, {stats['minutes']} min")
                return stats if stats["appearances"] > 0 else None

    except Exception as e:
        log.error(f"[transfermarkt] Stats error for {tm_id}: {e}")
        return None
