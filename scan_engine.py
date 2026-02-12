"""Shared scan engine used by both API and scheduler."""
import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta

import db
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, FIRST_SCAN_MULTIPLIER, INTELLIGENCE_ENABLED
from scrapers.press import scrape_all_press
from scrapers.social import scrape_all_social
from scrapers.player import scrape_all_player_posts
from scrapers.trends import scrape_google_trends
from analyzer import analyze_batch, generate_executive_summary, extract_topics_and_brands, generate_intelligence_report

log = logging.getLogger("agentradar")

# Global scan status for UI polling
scan_status = {"running": False, "progress": "", "player_id": None}
scan_lock = asyncio.Lock()


async def run_scan(player_data: dict, update_status=True):
    """Run a full scan for a player.

    player_data: dict with keys name, twitter, instagram, transfermarkt_id, club, tiktok
    update_status: if True, updates the global scan_status for UI polling
    Returns dict with scan results.
    """
    if update_status:
        scan_status.update({"running": True, "progress": "Iniciando...", "player_id": None})

    name = player_data.get("name", "")
    twitter = player_data.get("twitter")
    instagram = player_data.get("instagram")
    tm_id = player_data.get("transfermarkt_id")
    club = player_data.get("club")
    tiktok = player_data.get("tiktok")

    try:
        if update_status:
            scan_status["progress"] = "Registrando jugador..."
        p = await db.get_or_create_player(name, twitter, instagram, tm_id, club)
        player_id = p["id"]
        if update_status:
            scan_status["player_id"] = player_id

        # Create scan log
        scan_log_id = await db.save_scan_log(player_id)

        # Detect first scan (deeper scrape)
        scan_count = await db.get_scan_count(player_id)
        is_first_scan = scan_count == 0
        scan_multiplier = FIRST_SCAN_MULTIPLIER if is_first_scan else 1
        if is_first_scan:
            log.info(f"First scan for {name} - using {FIRST_SCAN_MULTIPLIER}x deeper scrape")

        # Get previous summary for comparison
        prev_summary = await db.get_previous_summary(player_id)

        # Get existing URLs for dedup
        existing_urls = await db.get_existing_urls(player_id)

        # Scrape all sources with detailed progress
        log.info(f"Starting scrapers for {name} (twitter={twitter}, club={club})")
        progress_prefix = "Escaneo profundo: " if is_first_scan else ""

        if update_status:
            scan_status["progress"] = f"{progress_prefix}Escaneando prensa (Google News + RSS)..."
        try:
            press_items = await scrape_all_press(name, club, limit_multiplier=scan_multiplier)
        except Exception as e:
            log.error(f"Press scraper EXCEPTION: {e}", exc_info=True)
            press_items = []

        if update_status:
            scan_status["progress"] = f"{progress_prefix}Prensa: {len(press_items)} noticias. Escaneando redes sociales..."
        try:
            social_items = await scrape_all_social(name, twitter, club, limit_multiplier=scan_multiplier)
        except Exception as e:
            log.error(f"Social scraper EXCEPTION: {e}", exc_info=True)
            social_items = []

        if update_status:
            scan_status["progress"] = f"{progress_prefix}Redes: {len(social_items)} menciones. Escaneando posts del jugador..."
        try:
            player_items = await scrape_all_player_posts(twitter, instagram, tiktok, limit_multiplier=scan_multiplier)
        except Exception as e:
            log.error(f"Player scraper EXCEPTION: {e}", exc_info=True)
            player_items = []

        # Transfermarkt (if ID provided)
        tm_stats = None
        if tm_id:
            try:
                from scrapers.transfermarkt import scrape_transfermarkt_profile, scrape_transfermarkt_stats
                tm_data = await scrape_transfermarkt_profile(tm_id)
                if tm_data:
                    await db.update_player_profile(
                        player_id,
                        photo_url=tm_data.get("photo_url"),
                        market_value=tm_data.get("market_value"),
                        contract_until=tm_data.get("contract_until"),
                        nationality=tm_data.get("nationality"),
                        position=tm_data.get("position"),
                    )
                # Scrape performance stats
                tm_stats = await scrape_transfermarkt_stats(tm_id)
                if tm_stats:
                    await db.save_player_stats(player_id, tm_stats)
                    log.info(f"Stats saved: {tm_stats.get('appearances', 0)} apps, {tm_stats.get('goals', 0)} goals")
            except Exception as e:
                log.error(f"Transfermarkt scraper EXCEPTION: {e}", exc_info=True)

        # Google Trends
        trends_data = None
        try:
            if update_status:
                scan_status["progress"] = f"{progress_prefix}Obteniendo Google Trends..."
            trends_data = await scrape_google_trends(name)
            if trends_data:
                await db.save_player_trends(player_id, trends_data)
                log.info(f"Trends saved: avg={trends_data.get('average_interest', 0)}, peak={trends_data.get('peak_interest', 0)}")
        except Exception as e:
            log.error(f"Google Trends EXCEPTION: {e}", exc_info=True)

        # Dedup - filter out items already in DB
        def _dedup(items):
            new_items = []
            for item in items:
                url = item.get("url", "")
                if url and url in existing_urls:
                    continue
                new_items.append(item)
            return new_items

        press_new = _dedup(press_items)
        social_new = _dedup(social_items)
        player_new = _dedup(player_items)

        pc = len(press_items)
        sc = len(social_items)
        pp = len(player_items)
        new_count = len(press_new) + len(social_new) + len(player_new)

        log.info(f"Scrapers done: press={pc}, social={sc}, player={pp} (new={new_count})")
        if update_status:
            scan_status["progress"] = (
                f"Encontrado: {pc} noticias, {sc} menciones, {pp} posts. Analizando contenido..."
            )

        # Analyze only NEW items with GPT-4o (saves API costs)
        if press_new or social_new or player_new:
            press_new, social_new, player_new = await asyncio.gather(
                analyze_batch(press_new, player_name=name, club=club or ""),
                analyze_batch(social_new, player_name=name, club=club or ""),
                analyze_batch(player_new, player_name=name, club=club or ""),
            )

        # Extract aggregated topics and brands
        all_items = press_new + social_new + player_new
        topics, brands = extract_topics_and_brands(all_items)

        # Store in DB
        if update_status:
            scan_status["progress"] = "Guardando resultados..."
        await asyncio.gather(
            db.insert_press_items(player_id, press_new),
            db.insert_social_mentions(player_id, social_new),
            db.insert_player_posts(player_id, player_new),
        )

        # Check for alerts
        if update_status:
            scan_status["progress"] = "Comprobando alertas..."
        alert_count = await _check_alerts(player_id, press_new, social_new)

        # Generate executive summary
        if update_status:
            scan_status["progress"] = "Generando resumen ejecutivo..."
        current_summary = await db.get_summary(player_id)
        exec_report = await generate_executive_summary(
            name, current_summary, topics, brands, prev_summary,
        )

        # Save scan report linked to scan_log
        await db.save_scan_report_with_log(
            player_id, scan_log_id,
            exec_report.get("text", ""),
            topics, brands,
            exec_report.get("delta"),
            current_summary,
        )

        # Calculate and store Image Index
        if update_status:
            scan_status["progress"] = "Calculando Indice de Imagen..."
        image_index_data = await db.calculate_image_index(player_id)
        await db.update_scan_report_image_index(scan_log_id, image_index_data["index"])
        log.info(f"Image Index for {name}: {image_index_data['index']}/100")

        # Intelligence Analysis (second-pass)
        if INTELLIGENCE_ENABLED:
            if update_status:
                scan_status["progress"] = "Analizando inteligencia..."
            try:
                intel_result = await generate_intelligence_report(
                    player_id, name, club or "", scan_log_id,
                    stats=tm_stats, trends=trends_data,
                )
                if intel_result:
                    # Only save if it has narrativas, or if no previous report exists
                    prev_report = await db.get_last_intelligence_report(player_id)
                    has_narrativas = len(intel_result.get("narrativas", [])) > 0
                    if has_narrativas or not prev_report:
                        await db.save_intelligence_report(player_id, scan_log_id, intel_result)
                    else:
                        log.info(f"[intelligence] Keeping previous report for {name} (new report has 0 narrativas)")
            except Exception as e:
                log.error(f"Intelligence analysis error: {e}", exc_info=True)

        # Send Telegram alert if configured
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            await _send_telegram_alert(name, current_summary, alert_count, exec_report)

        # Finish scan log
        await db.finish_scan_log(scan_log_id, pc, sc, pp, alert_count)

        if update_status:
            scan_status["progress"] = (
                f"Completado: {pc} noticias, {sc} menciones, {pp} posts"
            )

        return {
            "player_id": player_id,
            "press_count": pc,
            "mentions_count": sc,
            "posts_count": pp,
            "alerts_count": alert_count,
            "new_items": new_count,
            "summary": current_summary,
        }

    except Exception as e:
        if update_status:
            scan_status["progress"] = f"Error: {str(e)}"
        log.error(f"SCAN ERROR: {e}", exc_info=True)
        return None
    finally:
        if update_status:
            scan_status["running"] = False


async def _check_alerts(player_id, press_items, social_items):
    count = 0

    def _excerpt(text, max_len=100):
        """Truncate text for alert display."""
        text = (text or "").replace("\n", " ").strip()
        return text[:max_len] + "..." if len(text) > max_len else text

    def _build_detail_lines(items, field="title", max_items=5):
        """Build bullet-point list of item titles/texts for alert message."""
        lines = []
        for item in items[:max_items]:
            text = _excerpt(item.get(field, "") or item.get("text", "") or item.get("title", ""))
            source = item.get("source", "") or item.get("platform", "")
            if text:
                lines.append(f"- [{source}] {text}" if source else f"- {text}")
        return "\n".join(lines)

    # 1. High volume of negative press
    negative_press = [i for i in press_items if i.get("sentiment_label") == "negativo"]
    if len(negative_press) >= 3:
        detail = _build_detail_lines(negative_press, "title")
        sources = list(set(i.get("source", "?") for i in negative_press))
        await db.insert_alert(
            player_id, "prensa_negativa", "alta",
            f"{len(negative_press)} noticias negativas en {', '.join(sources[:4])}",
            f"Titulares negativos detectados:\n{detail}",
            {"count": len(negative_press), "titles": [i.get("title", "") for i in negative_press[:5]],
             "sources": sources},
        )
        count += 1

    # 2. Negative social sentiment majority
    if social_items:
        negative_social = [i for i in social_items if i.get("sentiment_label") == "negativo"]
        if len(negative_social) > len(social_items) * 0.4 and len(social_items) > 5:
            # Group by platform and find most common negative themes
            platforms = {}
            for item in negative_social:
                p = item.get("platform", "?")
                platforms[p] = platforms.get(p, 0) + 1
            platform_str = ", ".join(f"{p}: {c}" for p, c in sorted(platforms.items(), key=lambda x: -x[1])[:4])
            detail = _build_detail_lines(negative_social, "text")
            await db.insert_alert(
                player_id, "redes_negativas", "alta",
                f"Sentimiento negativo en redes ({len(negative_social)}/{len(social_items)} menciones)",
                f"Plataformas afectadas: {platform_str}\nEjemplos:\n{detail}",
                {"negative_ratio": round(len(negative_social) / len(social_items), 2),
                 "platforms": platforms,
                 "samples": [_excerpt(i.get("text", "")) for i in negative_social[:5]]},
            )
            count += 1

    # 3. Trending - high media presence
    if len(press_items) > 15:
        sources = {}
        for item in press_items:
            s = item.get("source", "?")
            sources[s] = sources.get(s, 0) + 1
        source_str = ", ".join(f"{s}: {c}" for s, c in sorted(sources.items(), key=lambda x: -x[1])[:5])
        await db.insert_alert(
            player_id, "trending", "media",
            f"Alta presencia mediatica: {len(press_items)} noticias",
            f"Cobertura por medio: {source_str}",
            {"count": len(press_items), "sources": sources},
        )
        count += 1

    # 4. Transfer rumor detected
    transfer_items = [i for i in press_items if "fichaje" in (i.get("topics") or [])]
    if transfer_items:
        detail = _build_detail_lines(transfer_items, "title")
        sources = list(set(i.get("source", "?") for i in transfer_items))
        await db.insert_alert(
            player_id, "rumor_fichaje", "alta",
            f"Rumor de fichaje en {', '.join(sources[:3])} ({len(transfer_items)} noticias)",
            f"Noticias de fichaje detectadas:\n{detail}",
            {"titles": [i.get("title", "") for i in transfer_items[:5]], "sources": sources},
        )
        count += 1

    # 5. Injury mention detected
    injury_items = [i for i in press_items if "lesion" in (i.get("topics") or [])]
    if injury_items:
        detail = _build_detail_lines(injury_items, "title")
        await db.insert_alert(
            player_id, "lesion", "alta",
            f"Posible lesion ({len(injury_items)} noticias)",
            f"Menciones de lesion detectadas:\n{detail}",
            {"titles": [i.get("title", "") for i in injury_items[:5]]},
        )
        count += 1

    # 6. Controversy/polemic detected
    polemic_items = [i for i in press_items + social_items if "polemica" in (i.get("topics") or [])]
    if len(polemic_items) >= 2:
        detail = _build_detail_lines(polemic_items, "text")
        await db.insert_alert(
            player_id, "polemica", "alta",
            f"Polemica detectada ({len(polemic_items)} menciones en {len(set(i.get('platform', i.get('source', '?')) for i in polemic_items))} fuentes)",
            f"Menciones polemicas:\n{detail}",
            {"count": len(polemic_items),
             "samples": [_excerpt(i.get("text", "") or i.get("title", "")) for i in polemic_items[:5]]},
        )
        count += 1

    # 7. Player inactivity (no posts in 7+ days)
    try:
        last_post_date = await db.get_last_player_post_date(player_id)
        if last_post_date:
            last_post = datetime.fromisoformat(last_post_date.replace("Z", "+00:00").split("+")[0])
            days_inactive = (datetime.now() - last_post).days
            if days_inactive >= 7:
                await db.insert_alert(
                    player_id, "inactividad", "media",
                    f"Inactividad en redes: {days_inactive} dias sin publicar",
                    f"Ultimo post: {last_post_date[:10]}. Lleva {days_inactive} dias sin actividad en redes sociales.",
                    {"days_inactive": days_inactive, "last_post": last_post_date},
                )
                count += 1
    except Exception as e:
        log.warning(f"Inactivity check error: {e}")

    return count


async def _send_telegram_alert(player_name, summary, alert_count, report):
    s = summary
    ps = s.get('press_sentiment')
    ss = s.get('social_sentiment')
    ps_emoji = "🟢" if ps and ps > 0.2 else "🔴" if ps and ps < -0.2 else "🟡"
    ss_emoji = "🟢" if ss and ss > 0.2 else "🔴" if ss and ss < -0.2 else "🟡"
    alert_emoji = "🚨" if alert_count > 0 else "✅"

    msg = f"""📊 *MediaPulse - {player_name}*

📰 Prensa: *{s.get('press_count', 0)}* noticias {ps_emoji} {f"{ps:+.2f}" if ps else "-"}
💬 Redes: *{s.get('mentions_count', 0)}* menciones {ss_emoji} {f"{ss:+.2f}" if ss else "-"}
📱 Posts: *{s.get('posts_count', 0)}* | Eng: {f"{s.get('avg_engagement', 0)*100:.1f}%" if s.get('avg_engagement') else "-"}
{alert_emoji} Alertas: *{alert_count}*

{report.get('text', '')[:400]}"""

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        async with aiohttp.ClientSession() as session:
            await session.post(url, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": msg,
                "parse_mode": "Markdown",
            })
        log.info("[telegram] Alert sent")
    except Exception as e:
        log.error(f"[telegram] Error: {e}")
