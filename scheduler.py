"""Daily scan scheduler using APScheduler."""
import asyncio
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import db
from config import (
    DAILY_SCAN_ENABLED, DAILY_SCAN_HOUR, DAILY_SCAN_MINUTE, SCAN_DELAY_SECONDS,
    WEEKLY_REPORT_DAY, WEEKLY_REPORT_HOUR, WEEKLY_REPORT_MINUTE,
)

log = logging.getLogger("agentradar")

scheduler = AsyncIOScheduler()
last_daily_run = {"started_at": None, "finished_at": None, "players_scanned": 0, "status": "idle"}


async def daily_scan_job():
    """Run scan for all registered players sequentially."""
    global last_daily_run
    last_daily_run = {
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
        "players_scanned": 0,
        "status": "running",
    }
    log.info("[scheduler] Daily scan job started")

    try:
        from scan_engine import run_scan, scan_status

        # Skip if a manual scan is already running
        if scan_status.get("running"):
            log.info("[scheduler] Manual scan running, skipping daily job")
            last_daily_run["status"] = "skipped"
            last_daily_run["finished_at"] = datetime.now().isoformat()
            return

        players = await db.get_all_players()
        log.info(f"[scheduler] Scanning {len(players)} players")

        results = []
        for player in players:
            player_data = {
                "name": player["name"],
                "twitter": player.get("twitter"),
                "instagram": player.get("instagram"),
                "transfermarkt_id": player.get("transfermarkt_id"),
                "club": player.get("club"),
                "tiktok": player.get("tiktok"),
            }
            log.info(f"[scheduler] Scanning {player['name']}...")
            result = await run_scan(player_data, update_status=False)
            results.append(result)
            last_daily_run["players_scanned"] += 1

            # Breathing room between players
            if SCAN_DELAY_SECONDS > 0:
                await asyncio.sleep(SCAN_DELAY_SECONDS)

        last_daily_run["status"] = "completed"
        last_daily_run["finished_at"] = datetime.now().isoformat()
        log.info(f"[scheduler] Daily scan completed: {len(results)} players")

        # Send email digest if configured
        try:
            from notifications import send_digest_email
            await send_digest_email(players, results)
        except Exception as e:
            log.error(f"[scheduler] Email digest error: {e}")

    except Exception as e:
        log.error(f"[scheduler] Daily scan error: {e}", exc_info=True)
        last_daily_run["status"] = f"error: {str(e)}"
        last_daily_run["finished_at"] = datetime.now().isoformat()


async def weekly_report_job():
    """Generate weekly actionable reports for all players."""
    log.info("[scheduler] Weekly report job started")
    try:
        from analyzer import generate_weekly_report

        players = await db.get_all_players()
        for player in players:
            pid = player["id"]
            try:
                summary = await db.get_summary(pid)
                image_index = await db.calculate_image_index(pid)
                report = await db.get_last_report(pid)
                topics = report.get("topics", {}) if report else {}
                brands = report.get("brands", {}) if report else {}

                result = await generate_weekly_report(
                    player["name"], summary, image_index, topics, brands, player.get("club", ""),
                )

                await db.save_weekly_report(
                    pid,
                    result.get("text", ""),
                    result.get("recommendation", "MONITORIZAR"),
                    image_index.get("index", 0),
                    {
                        "risks": result.get("risks", []),
                        "opportunities": result.get("opportunities", []),
                        "justification": result.get("justification", ""),
                    },
                )
                log.info(f"[scheduler] Weekly report for {player['name']}: {result.get('recommendation', '?')}")
            except Exception as e:
                log.error(f"[scheduler] Weekly report error for {player['name']}: {e}")

            await asyncio.sleep(5)

        log.info(f"[scheduler] Weekly reports done for {len(players)} players")

    except Exception as e:
        log.error(f"[scheduler] Weekly report job error: {e}", exc_info=True)


def start_scheduler():
    """Start the daily scan scheduler."""
    if not DAILY_SCAN_ENABLED:
        log.info("[scheduler] Disabled by config")
        return

    scheduler.add_job(
        daily_scan_job,
        CronTrigger(hour=DAILY_SCAN_HOUR, minute=DAILY_SCAN_MINUTE),
        id="daily_scan",
        replace_existing=True,
    )

    # Weekly report (e.g. Sunday 20:00)
    scheduler.add_job(
        weekly_report_job,
        CronTrigger(day_of_week=WEEKLY_REPORT_DAY, hour=WEEKLY_REPORT_HOUR, minute=WEEKLY_REPORT_MINUTE),
        id="weekly_report",
        replace_existing=True,
    )

    scheduler.start()
    days = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
    log.info(f"[scheduler] Started - daily scan at {DAILY_SCAN_HOUR:02d}:{DAILY_SCAN_MINUTE:02d}, weekly report {days[WEEKLY_REPORT_DAY]} {WEEKLY_REPORT_HOUR:02d}:{WEEKLY_REPORT_MINUTE:02d}")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("[scheduler] Stopped")


def get_scheduler_status():
    """Get scheduler status for API."""
    job = scheduler.get_job("daily_scan") if scheduler.running else None
    return {
        "enabled": DAILY_SCAN_ENABLED,
        "running": scheduler.running if DAILY_SCAN_ENABLED else False,
        "next_run": str(job.next_run_time) if job else None,
        "schedule": f"{DAILY_SCAN_HOUR:02d}:{DAILY_SCAN_MINUTE:02d}",
        "last_run": last_daily_run,
    }
