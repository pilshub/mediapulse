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
                    # Totals row typically: label, in_squad, appearances, goals, assists, ...
                    # Extract numbers from cells
                    nums = []
                    for cell in cells:
                        text = cell.get_text(strip=True).replace(".", "").replace("'", "").replace(",", "")
                        text = text.replace("-", "0")
                        if text.isdigit():
                            nums.append(int(text))
                        else:
                            nums.append(0)

                    # Map numbers: typically [in_squad, appearances, goals, assists, ?, sub_in, sub_out, yellows, 2nd_yellow, reds, penalty_goals, minutes]
                    if len(nums) >= 8:
                        stats["appearances"] = nums[1] if len(nums) > 1 else 0
                        stats["goals"] = nums[2] if len(nums) > 2 else 0
                        stats["assists"] = nums[3] if len(nums) > 3 else 0
                        stats["yellows"] = nums[7] if len(nums) > 7 else 0
                        stats["reds"] = nums[9] if len(nums) > 9 else 0
                        stats["minutes"] = nums[-1] if nums[-1] > 10 else 0  # minutes is last and largest

                # Also parse individual rows for competition breakdown
                tbody = table.find("tbody")
                if tbody:
                    rows = tbody.find_all("tr", class_=["odd", "even"])
                    for row in rows:
                        cells = row.find_all("td")
                        if len(cells) >= 4:
                            comp_link = cells[0].find("a")
                            comp_name = comp_link.get_text(strip=True) if comp_link else cells[0].get_text(strip=True)
                            if comp_name and comp_name not in ["", "-"]:
                                # Get appearances from this competition
                                app_text = cells[2].get_text(strip=True) if len(cells) > 2 else "0"
                                goals_text = cells[3].get_text(strip=True) if len(cells) > 3 else "0"
                                stats["competitions"].append({
                                    "name": comp_name,
                                    "appearances": int(app_text) if app_text.isdigit() else 0,
                                    "goals": int(goals_text) if goals_text.isdigit() else 0,
                                })

                # Detect season from page
                season_match = re.search(r'(?:Saison|Season)\s*(\d{2}/\d{2})', html)
                if season_match:
                    stats["season"] = season_match.group(1)

                # If totals row failed, sum from individual rows
                if stats["appearances"] == 0 and stats["competitions"]:
                    stats["appearances"] = sum(c["appearances"] for c in stats["competitions"])
                    stats["goals"] = sum(c["goals"] for c in stats["competitions"])

                log.info(f"[transfermarkt] Stats for {tm_id}: {stats['appearances']} apps, {stats['goals']} goals, {stats['assists']} assists, {stats['minutes']} min")
                return stats if stats["appearances"] > 0 else None

    except Exception as e:
        log.error(f"[transfermarkt] Stats error for {tm_id}: {e}")
        return None
