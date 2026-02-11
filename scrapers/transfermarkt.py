"""Transfermarkt profile scraper - market value, photo, contract."""
import re
import aiohttp
import logging

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
