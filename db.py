import aiosqlite
import os
import json
import hashlib
import re
import logging
from datetime import datetime, timedelta

log = logging.getLogger("agentradar")
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "agentradar.db")


def normalize_date(raw_date, reference_date=None):
    """Normalize any date format to ISO 8601 string (YYYY-MM-DDTHH:MM:SS)."""
    if not raw_date or not isinstance(raw_date, str):
        return None
    raw_date = raw_date.strip()
    if not raw_date:
        return None

    ref = reference_date or datetime.now()

    # 1. Already ISO? (starts with YYYY-MM-DD)
    if re.match(r"^\d{4}-\d{2}-\d{2}", raw_date):
        cleaned = raw_date.replace("Z", "").split("+")[0].split(".")[0]
        try:
            datetime.fromisoformat(cleaned)
            return cleaned
        except ValueError:
            pass

    # 2. Twitter format: "Fri Dec 26 12:14:02 +0000 2025"
    try:
        dt = datetime.strptime(raw_date, "%a %b %d %H:%M:%S %z %Y")
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:
        pass

    # 3. Spanish relative dates (YouTube): "hace X anos/meses/semanas/dias/horas"
    m = re.match(
        r"hace\s+(\d+)\s+(a[ñn]os?|meses?|semanas?|d[ií]as?|horas?|minutos?)",
        raw_date, re.IGNORECASE,
    )
    if m:
        amount = int(m.group(1))
        unit = m.group(2).lower().replace("ñ", "n").replace("í", "i")
        if "ano" in unit:
            delta = timedelta(days=amount * 365)
        elif "mes" in unit:
            delta = timedelta(days=amount * 30)
        elif "semana" in unit:
            delta = timedelta(weeks=amount)
        elif "dia" in unit:
            delta = timedelta(days=amount)
        elif "hora" in unit:
            delta = timedelta(hours=amount)
        elif "minuto" in unit:
            delta = timedelta(minutes=amount)
        else:
            return None
        return (ref - delta).strftime("%Y-%m-%dT%H:%M:%S")

    # 4. Unix timestamp (numeric string)
    if raw_date.isdigit() and len(raw_date) >= 10:
        try:
            return datetime.fromtimestamp(int(raw_date)).isoformat()
        except (ValueError, OSError):
            pass

    return None


def _content_hash(platform, author, text):
    raw = f"{platform or ''}:{author or ''}:{(text or '')[:200]}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                twitter TEXT,
                instagram TEXT,
                transfermarkt_id TEXT,
                club TEXT,
                photo_url TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS press_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                source TEXT,
                title TEXT,
                url TEXT UNIQUE,
                summary TEXT,
                sentiment REAL,
                sentiment_label TEXT,
                published_at TEXT,
                scraped_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (player_id) REFERENCES players(id)
            );

            CREATE TABLE IF NOT EXISTS social_mentions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                platform TEXT,
                author TEXT,
                text TEXT,
                url TEXT,
                likes INTEGER DEFAULT 0,
                retweets INTEGER DEFAULT 0,
                sentiment REAL,
                sentiment_label TEXT,
                created_at TEXT,
                scraped_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (player_id) REFERENCES players(id)
            );

            CREATE TABLE IF NOT EXISTS player_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                platform TEXT,
                text TEXT,
                url TEXT UNIQUE,
                likes INTEGER DEFAULT 0,
                comments INTEGER DEFAULT 0,
                shares INTEGER DEFAULT 0,
                views INTEGER DEFAULT 0,
                engagement_rate REAL,
                media_type TEXT,
                sentiment REAL,
                sentiment_label TEXT,
                posted_at TEXT,
                scraped_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (player_id) REFERENCES players(id)
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                type TEXT,
                severity TEXT,
                title TEXT,
                message TEXT,
                data_json TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                read INTEGER DEFAULT 0,
                FOREIGN KEY (player_id) REFERENCES players(id)
            );

            CREATE TABLE IF NOT EXISTS scan_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                started_at TEXT,
                finished_at TEXT,
                status TEXT,
                press_count INTEGER DEFAULT 0,
                mentions_count INTEGER DEFAULT 0,
                posts_count INTEGER DEFAULT 0,
                alerts_count INTEGER DEFAULT 0,
                FOREIGN KEY (player_id) REFERENCES players(id)
            );

            CREATE TABLE IF NOT EXISTS scan_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                executive_summary TEXT,
                topics_json TEXT,
                brands_json TEXT,
                delta_json TEXT,
                summary_snapshot_json TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (player_id) REFERENCES players(id)
            );
        """)
        # Weekly reports table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS weekly_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                report_text TEXT,
                recommendation TEXT,
                image_index REAL,
                data_json TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (player_id) REFERENCES players(id)
            )
        """)

        # Migrations - safe to re-run
        migrations = [
            "ALTER TABLE social_mentions ADD COLUMN content_hash TEXT",
            "ALTER TABLE players ADD COLUMN tiktok TEXT",
            "ALTER TABLE scan_reports ADD COLUMN scan_log_id INTEGER",
            "ALTER TABLE players ADD COLUMN market_value TEXT",
            "ALTER TABLE players ADD COLUMN contract_until TEXT",
            "ALTER TABLE players ADD COLUMN nationality TEXT",
            "ALTER TABLE players ADD COLUMN position TEXT",
            "ALTER TABLE scan_reports ADD COLUMN image_index REAL",
        ]
        for m in migrations:
            try:
                await conn.execute(m)
            except Exception:
                pass  # column already exists
        # Unique index for dedup
        try:
            await conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_social_content_hash ON social_mentions(player_id, content_hash)"
            )
        except Exception:
            pass
        # Performance indexes on player_id foreign keys
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS idx_press_player ON press_items(player_id)",
            "CREATE INDEX IF NOT EXISTS idx_social_player ON social_mentions(player_id)",
            "CREATE INDEX IF NOT EXISTS idx_posts_player ON player_posts(player_id)",
            "CREATE INDEX IF NOT EXISTS idx_alerts_player ON alerts(player_id)",
            "CREATE INDEX IF NOT EXISTS idx_scanlog_player ON scan_log(player_id)",
            "CREATE INDEX IF NOT EXISTS idx_scanreports_player ON scan_reports(player_id)",
            "CREATE INDEX IF NOT EXISTS idx_scanreports_logid ON scan_reports(scan_log_id)",
            "CREATE INDEX IF NOT EXISTS idx_press_published ON press_items(player_id, published_at)",
            "CREATE INDEX IF NOT EXISTS idx_social_created ON social_mentions(player_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_alerts_read ON alerts(player_id, read)",
        ]:
            try:
                await conn.execute(idx_sql)
            except Exception:
                pass
        # Index for player_posts posted_at
        try:
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_posts_posted ON player_posts(player_id, posted_at)"
            )
        except Exception:
            pass
        await _migrate_normalize_dates(conn)
        await conn.commit()


async def _migrate_normalize_dates(conn):
    """One-time migration to normalize all existing date strings to ISO 8601."""
    # Check if migration is needed
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM social_mentions WHERE created_at LIKE '%+0000%' OR created_at LIKE 'hace%'"
    )
    bad_social = (await cursor.fetchone())[0]
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM player_posts WHERE posted_at LIKE '%+0000%' OR posted_at LIKE '%Z'"
    )
    bad_posts = (await cursor.fetchone())[0]
    if bad_social == 0 and bad_posts == 0:
        return

    log.info(f"[migration] Normalizing dates: {bad_social} social_mentions, {bad_posts} player_posts")

    # Fix social_mentions (Twitter +0000 format)
    cursor = await conn.execute(
        "SELECT id, created_at, scraped_at FROM social_mentions WHERE created_at LIKE '%+0000%'"
    )
    for row_id, raw_date, scraped_at in await cursor.fetchall():
        normalized = normalize_date(raw_date)
        if normalized:
            await conn.execute("UPDATE social_mentions SET created_at = ? WHERE id = ?", (normalized, row_id))

    # Fix social_mentions (YouTube "hace X" relative dates)
    cursor = await conn.execute(
        "SELECT id, created_at, scraped_at FROM social_mentions WHERE created_at LIKE 'hace%'"
    )
    for row_id, raw_date, scraped_at in await cursor.fetchall():
        ref = datetime.fromisoformat(scraped_at) if scraped_at else datetime.now()
        normalized = normalize_date(raw_date, reference_date=ref)
        if normalized:
            await conn.execute("UPDATE social_mentions SET created_at = ? WHERE id = ?", (normalized, row_id))

    # Fix player_posts (Twitter +0000 format)
    cursor = await conn.execute(
        "SELECT id, posted_at FROM player_posts WHERE posted_at LIKE '%+0000%'"
    )
    for row_id, raw_date in await cursor.fetchall():
        normalized = normalize_date(raw_date)
        if normalized:
            await conn.execute("UPDATE player_posts SET posted_at = ? WHERE id = ?", (normalized, row_id))

    # Fix player_posts (Instagram Z suffix)
    cursor = await conn.execute(
        "SELECT id, posted_at FROM player_posts WHERE posted_at LIKE '%Z'"
    )
    for row_id, raw_date in await cursor.fetchall():
        normalized = normalize_date(raw_date)
        if normalized:
            await conn.execute("UPDATE player_posts SET posted_at = ? WHERE id = ?", (normalized, row_id))

    await conn.commit()
    log.info("[migration] Date normalization complete")


async def get_or_create_player(name, twitter=None, instagram=None, tm_id=None, club=None, tiktok=None):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM players WHERE name = ?", (name,))
        row = await cursor.fetchone()
        if row:
            updates = []
            params = []
            if twitter:
                updates.append("twitter = ?")
                params.append(twitter)
            if instagram:
                updates.append("instagram = ?")
                params.append(instagram)
            if tm_id:
                updates.append("transfermarkt_id = ?")
                params.append(tm_id)
            if club:
                updates.append("club = ?")
                params.append(club)
            if tiktok:
                updates.append("tiktok = ?")
                params.append(tiktok)
            if updates:
                params.append(row["id"])
                await conn.execute(
                    f"UPDATE players SET {', '.join(updates)} WHERE id = ?", params
                )
                await conn.commit()
            return dict(row)
        else:
            cursor = await conn.execute(
                "INSERT INTO players (name, twitter, instagram, transfermarkt_id, club, tiktok) VALUES (?, ?, ?, ?, ?, ?)",
                (name, twitter, instagram, tm_id, club, tiktok),
            )
            await conn.commit()
            return {
                "id": cursor.lastrowid,
                "name": name,
                "twitter": twitter,
                "instagram": instagram,
                "transfermarkt_id": tm_id,
                "club": club,
                "tiktok": tiktok,
            }


async def insert_press_items(player_id, items):
    async with aiosqlite.connect(DB_PATH) as conn:
        inserted = 0
        for item in items:
            try:
                await conn.execute(
                    """INSERT OR IGNORE INTO press_items
                    (player_id, source, title, url, summary, sentiment, sentiment_label, published_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        player_id,
                        item.get("source"),
                        item.get("title"),
                        item.get("url"),
                        item.get("summary", ""),
                        item.get("sentiment"),
                        item.get("sentiment_label"),
                        item.get("published_at"),
                    ),
                )
                inserted += 1
            except Exception:
                pass
        await conn.commit()
        return inserted


async def insert_social_mentions(player_id, items):
    async with aiosqlite.connect(DB_PATH) as conn:
        inserted = 0
        for item in items:
            try:
                ch = _content_hash(item.get("platform"), item.get("author"), item.get("text"))
                await conn.execute(
                    """INSERT OR IGNORE INTO social_mentions
                    (player_id, platform, author, text, url, likes, retweets, sentiment, sentiment_label, created_at, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        player_id,
                        item.get("platform"),
                        item.get("author"),
                        item.get("text"),
                        item.get("url"),
                        item.get("likes", 0),
                        item.get("retweets", 0),
                        item.get("sentiment"),
                        item.get("sentiment_label"),
                        item.get("created_at"),
                        ch,
                    ),
                )
                inserted += 1
            except Exception:
                pass
        await conn.commit()
        return inserted


async def insert_player_posts(player_id, items):
    async with aiosqlite.connect(DB_PATH) as conn:
        inserted = 0
        for item in items:
            try:
                await conn.execute(
                    """INSERT OR IGNORE INTO player_posts
                    (player_id, platform, text, url, likes, comments, shares, views,
                     engagement_rate, media_type, sentiment, sentiment_label, posted_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        player_id,
                        item.get("platform"),
                        item.get("text"),
                        item.get("url"),
                        item.get("likes", 0),
                        item.get("comments", 0),
                        item.get("shares", 0),
                        item.get("views", 0),
                        item.get("engagement_rate"),
                        item.get("media_type"),
                        item.get("sentiment"),
                        item.get("sentiment_label"),
                        item.get("posted_at"),
                    ),
                )
                inserted += 1
            except Exception:
                pass
        await conn.commit()
        return inserted


async def insert_alert(player_id, type_, severity, title, message, data=None):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO alerts (player_id, type, severity, title, message, data_json)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (player_id, type_, severity, title, message, json.dumps(data) if data else None),
        )
        await conn.commit()


async def get_press(player_id, limit=50, offset=0, date_from=None, date_to=None):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        q = "SELECT * FROM press_items WHERE player_id = ?"
        p = [player_id]
        if date_from:
            q += " AND published_at >= ?"
            p.append(date_from)
        if date_to:
            q += " AND published_at <= ?"
            p.append(date_to)
        q += " ORDER BY published_at DESC LIMIT ? OFFSET ?"
        p.extend([limit, offset])
        cursor = await conn.execute(q, p)
        return [dict(r) for r in await cursor.fetchall()]


async def get_social(player_id, limit=50, offset=0, date_from=None, date_to=None):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        q = "SELECT * FROM social_mentions WHERE player_id = ?"
        p = [player_id]
        if date_from:
            q += " AND created_at >= ?"
            p.append(date_from)
        if date_to:
            q += " AND created_at <= ?"
            p.append(date_to)
        q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        p.extend([limit, offset])
        cursor = await conn.execute(q, p)
        return [dict(r) for r in await cursor.fetchall()]


async def get_player_posts_db(player_id, limit=50, offset=0, date_from=None, date_to=None):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        q = "SELECT * FROM player_posts WHERE player_id = ?"
        p = [player_id]
        if date_from:
            q += " AND posted_at >= ?"
            p.append(date_from)
        if date_to:
            q += " AND posted_at <= ?"
            p.append(date_to)
        q += " ORDER BY posted_at DESC LIMIT ? OFFSET ?"
        p.extend([limit, offset])
        cursor = await conn.execute(q, p)
        return [dict(r) for r in await cursor.fetchall()]


async def get_alerts(player_id, limit=20):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM alerts WHERE player_id = ? ORDER BY created_at DESC LIMIT ?",
            (player_id, limit),
        )
        return [dict(r) for r in await cursor.fetchall()]


async def get_stats(player_id, date_from=None, date_to=None):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # Build date filters per table
        pf, pp = "", [player_id]
        sf, sp = "", [player_id]
        af, ap = "", [player_id]
        if date_from:
            pf += " AND published_at >= ?"; pp.append(date_from)
            sf += " AND created_at >= ?"; sp.append(date_from)
            af += " AND posted_at >= ?"; ap.append(date_from)
        if date_to:
            pf += " AND published_at <= ?"; pp.append(date_to)
            sf += " AND created_at <= ?"; sp.append(date_to)
            af += " AND posted_at <= ?"; ap.append(date_to)

        cursor = await conn.execute(
            f"""SELECT date(published_at) as day, COUNT(*) as count, AVG(sentiment) as avg_sentiment
            FROM press_items WHERE player_id = ?{pf} AND published_at IS NOT NULL GROUP BY date(published_at) ORDER BY day""",
            pp,
        )
        press_daily = [dict(r) for r in await cursor.fetchall()]

        cursor = await conn.execute(
            f"""SELECT date(created_at) as day, COUNT(*) as count, AVG(sentiment) as avg_sentiment
            FROM social_mentions WHERE player_id = ?{sf} AND created_at IS NOT NULL GROUP BY date(created_at) ORDER BY day""",
            sp,
        )
        mentions_daily = [dict(r) for r in await cursor.fetchall()]

        cursor = await conn.execute(
            f"""SELECT date(posted_at) as day, COUNT(*) as count, AVG(engagement_rate) as avg_engagement
            FROM player_posts WHERE player_id = ?{af} AND posted_at IS NOT NULL GROUP BY date(posted_at) ORDER BY day""",
            ap,
        )
        posts_daily = [dict(r) for r in await cursor.fetchall()]

        cursor = await conn.execute(
            f"""SELECT sentiment_label, COUNT(*) as count
            FROM press_items WHERE player_id = ?{pf} AND sentiment_label IS NOT NULL
            GROUP BY sentiment_label""",
            pp[:len(pp)],
        )
        press_sentiment = [dict(r) for r in await cursor.fetchall()]

        cursor = await conn.execute(
            f"""SELECT sentiment_label, COUNT(*) as count
            FROM social_mentions WHERE player_id = ?{sf} AND sentiment_label IS NOT NULL
            GROUP BY sentiment_label""",
            sp[:len(sp)],
        )
        social_sentiment = [dict(r) for r in await cursor.fetchall()]

        cursor = await conn.execute(
            f"""SELECT source, COUNT(*) as count
            FROM press_items WHERE player_id = ?{pf} GROUP BY source ORDER BY count DESC""",
            pp[:len(pp)],
        )
        press_sources = [dict(r) for r in await cursor.fetchall()]

        cursor = await conn.execute(
            f"""SELECT * FROM player_posts WHERE player_id = ?{af} ORDER BY likes DESC LIMIT 5""",
            ap[:len(ap)],
        )
        top_posts = [dict(r) for r in await cursor.fetchall()]

        return {
            "press_daily": press_daily,
            "mentions_daily": mentions_daily,
            "posts_daily": posts_daily,
            "press_sentiment": press_sentiment,
            "social_sentiment": social_sentiment,
            "press_sources": press_sources,
            "top_posts": top_posts,
        }


async def get_summary(player_id, date_from=None, date_to=None):
    async with aiosqlite.connect(DB_PATH) as conn:
        # Build date filters per table
        pf, pp = "", [player_id]
        sf, sp = "", [player_id]
        af, ap = "", [player_id]
        if date_from:
            pf += " AND published_at >= ?"; pp.append(date_from)
            sf += " AND created_at >= ?"; sp.append(date_from)
            af += " AND posted_at >= ?"; ap.append(date_from)
        if date_to:
            pf += " AND published_at <= ?"; pp.append(date_to)
            sf += " AND created_at <= ?"; sp.append(date_to)
            af += " AND posted_at <= ?"; ap.append(date_to)

        press_count = (await (await conn.execute(
            f"SELECT COUNT(*) FROM press_items WHERE player_id = ?{pf}", pp
        )).fetchone())[0]

        mentions_count = (await (await conn.execute(
            f"SELECT COUNT(*) FROM social_mentions WHERE player_id = ?{sf}", sp
        )).fetchone())[0]

        posts_count = (await (await conn.execute(
            f"SELECT COUNT(*) FROM player_posts WHERE player_id = ?{af}", ap
        )).fetchone())[0]

        # Alerts are NOT date-filtered (always show unread count)
        alerts_count = (await (await conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE player_id = ? AND read = 0", (player_id,)
        )).fetchone())[0]

        press_sent = (await (await conn.execute(
            f"SELECT AVG(sentiment) FROM press_items WHERE player_id = ?{pf} AND sentiment IS NOT NULL", pp
        )).fetchone())[0]

        social_sent = (await (await conn.execute(
            f"SELECT AVG(sentiment) FROM social_mentions WHERE player_id = ?{sf} AND sentiment IS NOT NULL", sp
        )).fetchone())[0]

        player_sent = (await (await conn.execute(
            f"SELECT AVG(sentiment) FROM player_posts WHERE player_id = ?{af} AND sentiment IS NOT NULL", ap
        )).fetchone())[0]

        avg_engagement = (await (await conn.execute(
            f"SELECT AVG(engagement_rate) FROM player_posts WHERE player_id = ?{af} AND engagement_rate IS NOT NULL", ap
        )).fetchone())[0]

        return {
            "press_count": press_count,
            "mentions_count": mentions_count,
            "posts_count": posts_count,
            "alerts_count": alerts_count,
            "press_sentiment": round(press_sent, 2) if press_sent else None,
            "social_sentiment": round(social_sent, 2) if social_sent else None,
            "player_sentiment": round(player_sent, 2) if player_sent else None,
            "avg_engagement": round(avg_engagement, 4) if avg_engagement else None,
        }


async def get_last_scan(player_id):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM scan_log WHERE player_id = ? ORDER BY started_at DESC LIMIT 1",
            (player_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def save_scan_report(player_id, executive_summary, topics, brands, delta, summary_snapshot):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO scan_reports
            (player_id, executive_summary, topics_json, brands_json, delta_json, summary_snapshot_json)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                player_id,
                executive_summary,
                json.dumps(topics),
                json.dumps(brands),
                json.dumps(delta),
                json.dumps(summary_snapshot),
            ),
        )
        await conn.commit()


async def get_last_report(player_id):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM scan_reports WHERE player_id = ? ORDER BY created_at DESC LIMIT 1",
            (player_id,),
        )
        row = await cursor.fetchone()
        if row:
            r = dict(row)
            r["topics"] = json.loads(r.get("topics_json") or "{}")
            r["brands"] = json.loads(r.get("brands_json") or "{}")
            r["delta"] = json.loads(r.get("delta_json") or "null")
            r["summary_snapshot"] = json.loads(r.get("summary_snapshot_json") or "{}")
            return r
        return None


async def get_previous_summary(player_id):
    """Get the summary snapshot from the second-to-last scan report (for comparison)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT summary_snapshot_json FROM scan_reports WHERE player_id = ? ORDER BY created_at DESC LIMIT 1 OFFSET 1",
            (player_id,),
        )
        row = await cursor.fetchone()
        if row and row["summary_snapshot_json"]:
            return json.loads(row["summary_snapshot_json"])
        return None


async def get_all_players():
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM players ORDER BY name")
        return [dict(r) for r in await cursor.fetchall()]


async def get_existing_urls(player_id):
    """Return set of all known URLs for dedup before analysis."""
    urls = set()
    async with aiosqlite.connect(DB_PATH) as conn:
        for table in ["press_items", "social_mentions", "player_posts"]:
            cursor = await conn.execute(
                f"SELECT url FROM {table} WHERE player_id = ? AND url IS NOT NULL AND url != ''",
                (player_id,),
            )
            rows = await cursor.fetchall()
            urls.update(row[0] for row in rows)
    return urls


# ── Alert management ──

async def mark_alert_read(alert_id):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE alerts SET read = 1 WHERE id = ?", (alert_id,))
        await conn.commit()


async def dismiss_alert(alert_id):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
        await conn.commit()


async def get_alerts_filtered(player_id, limit=50, severity=None, unread_only=False):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        query = "SELECT * FROM alerts WHERE player_id = ?"
        params = [player_id]
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        if unread_only:
            query += " AND read = 0"
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cursor = await conn.execute(query, params)
        return [dict(r) for r in await cursor.fetchall()]


# ── Scan history ──

async def get_scan_history(player_id, limit=50):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT sl.*, sr.executive_summary, sr.topics_json, sr.brands_json,
                      sr.summary_snapshot_json
               FROM scan_log sl
               LEFT JOIN scan_reports sr ON sr.scan_log_id = sl.id
               WHERE sl.player_id = ?
               ORDER BY sl.started_at DESC LIMIT ?""",
            (player_id, limit),
        )
        rows = [dict(r) for r in await cursor.fetchall()]
        for r in rows:
            if r.get("summary_snapshot_json"):
                r["summary_snapshot"] = json.loads(r["summary_snapshot_json"])
            if r.get("topics_json"):
                r["topics"] = json.loads(r["topics_json"])
        return rows


async def save_scan_log(player_id):
    """Create a new scan_log entry, return its id."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "INSERT INTO scan_log (player_id, started_at, status) VALUES (?, ?, ?)",
            (player_id, datetime.now().isoformat(), "running"),
        )
        await conn.commit()
        return cursor.lastrowid


async def finish_scan_log(scan_log_id, press_count, mentions_count, posts_count, alerts_count):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """UPDATE scan_log SET finished_at = ?, status = ?,
               press_count = ?, mentions_count = ?, posts_count = ?, alerts_count = ?
               WHERE id = ?""",
            (datetime.now().isoformat(), "completed",
             press_count, mentions_count, posts_count, alerts_count, scan_log_id),
        )
        await conn.commit()


async def save_scan_report_with_log(player_id, scan_log_id, executive_summary, topics, brands, delta, summary_snapshot):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO scan_reports
            (player_id, scan_log_id, executive_summary, topics_json, brands_json, delta_json, summary_snapshot_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                player_id, scan_log_id, executive_summary,
                json.dumps(topics), json.dumps(brands),
                json.dumps(delta), json.dumps(summary_snapshot),
            ),
        )
        await conn.commit()


# ── Player profile (Transfermarkt) ──

async def update_player_profile(player_id, photo_url=None, market_value=None,
                                contract_until=None, nationality=None, position=None):
    async with aiosqlite.connect(DB_PATH) as conn:
        updates = []
        params = []
        for field, val in [("photo_url", photo_url), ("market_value", market_value),
                           ("contract_until", contract_until), ("nationality", nationality),
                           ("position", position)]:
            if val is not None:
                updates.append(f"{field} = ?")
                params.append(val)
        if updates:
            params.append(player_id)
            await conn.execute(f"UPDATE players SET {', '.join(updates)} WHERE id = ?", params)
            await conn.commit()


async def get_scan_report_by_log_id(scan_log_id):
    """Get a scan report by its scan_log_id (for comparison)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT sr.*, sl.started_at, sl.finished_at, sl.press_count, sl.mentions_count, sl.posts_count
               FROM scan_reports sr
               JOIN scan_log sl ON sl.id = sr.scan_log_id
               WHERE sr.scan_log_id = ?""",
            (scan_log_id,),
        )
        row = await cursor.fetchone()
        if row:
            r = dict(row)
            r["topics"] = json.loads(r.get("topics_json") or "{}")
            r["brands"] = json.loads(r.get("brands_json") or "{}")
            r["delta"] = json.loads(r.get("delta_json") or "null")
            r["summary_snapshot"] = json.loads(r.get("summary_snapshot_json") or "{}")
            return r
        return None


# ── Image Index ──

async def calculate_image_index(player_id):
    """Calculate composite image index 0-100 for a player.

    Components (weights from config):
    - volume (20%): log-normalized total items count
    - press_sentiment (25%): (-1..+1) → (0..100)
    - social_sentiment (25%): (-1..+1) → (0..100)
    - engagement (15%): normalized engagement rate
    - no_controversy (15%): 100 - negative_ratio * 100
    """
    import math
    from config import IMAGE_INDEX_WEIGHTS as W

    async with aiosqlite.connect(DB_PATH) as conn:
        # Total items
        pc = (await (await conn.execute(
            "SELECT COUNT(*) FROM press_items WHERE player_id = ?", (player_id,)
        )).fetchone())[0]
        sc = (await (await conn.execute(
            "SELECT COUNT(*) FROM social_mentions WHERE player_id = ?", (player_id,)
        )).fetchone())[0]
        total = pc + sc

        # Volume score: log scale, 100 items = ~100, 1 item = ~0
        volume_score = min(100, (math.log10(max(total, 1)) / math.log10(100)) * 100)

        # Press sentiment
        ps = (await (await conn.execute(
            "SELECT AVG(sentiment) FROM press_items WHERE player_id = ? AND sentiment IS NOT NULL",
            (player_id,)
        )).fetchone())[0]
        press_score = ((ps + 1) / 2) * 100 if ps is not None else 50

        # Social sentiment
        ss = (await (await conn.execute(
            "SELECT AVG(sentiment) FROM social_mentions WHERE player_id = ? AND sentiment IS NOT NULL",
            (player_id,)
        )).fetchone())[0]
        social_score = ((ss + 1) / 2) * 100 if ss is not None else 50

        # Engagement
        eng = (await (await conn.execute(
            "SELECT AVG(engagement_rate) FROM player_posts WHERE player_id = ? AND engagement_rate IS NOT NULL",
            (player_id,)
        )).fetchone())[0]
        # Normalize: 5% engagement = 100, 0% = 0
        engagement_score = min(100, (eng / 0.05) * 100) if eng else 50

        # Absence of controversy (negative ratio in all items)
        neg_count = 0
        total_sent = 0
        for table in ["press_items", "social_mentions"]:
            row = await (await conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE player_id = ? AND sentiment_label = 'negativo'",
                (player_id,)
            )).fetchone()
            neg_count += row[0]
            row2 = await (await conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE player_id = ? AND sentiment_label IS NOT NULL",
                (player_id,)
            )).fetchone()
            total_sent += row2[0]

        neg_ratio = neg_count / total_sent if total_sent > 0 else 0
        controversy_score = max(0, 100 - neg_ratio * 200)  # 50% neg = 0, 0% neg = 100

        # Weighted composite
        index = (
            volume_score * W["volume"] +
            press_score * W["press_sentiment"] +
            social_score * W["social_sentiment"] +
            engagement_score * W["engagement"] +
            controversy_score * W["no_controversy"]
        )

        return {
            "index": round(index, 1),
            "volume": round(volume_score, 1),
            "press_sentiment": round(press_score, 1),
            "social_sentiment": round(social_score, 1),
            "engagement": round(engagement_score, 1),
            "no_controversy": round(controversy_score, 1),
            "details": {
                "total_items": total,
                "press_count": pc,
                "social_count": sc,
                "neg_ratio": round(neg_ratio, 3),
            }
        }


async def update_scan_report_image_index(scan_log_id, image_index):
    """Update image_index on the scan report."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE scan_reports SET image_index = ? WHERE scan_log_id = ?",
            (image_index, scan_log_id),
        )
        await conn.commit()


# ── Portfolio ──

async def get_portfolio():
    """Get all players with latest summary + image index for portfolio view."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM players ORDER BY name")
        players = [dict(r) for r in await cursor.fetchall()]

    result = []
    for p in players:
        pid = p["id"]
        summary = await get_summary(pid)
        idx_data = await calculate_image_index(pid)
        last_scan = await get_last_scan(pid)

        # Last post date for inactivity check
        async with aiosqlite.connect(DB_PATH) as conn:
            row = await (await conn.execute(
                "SELECT MAX(posted_at) FROM player_posts WHERE player_id = ?", (pid,)
            )).fetchone()
            last_post_date = row[0] if row else None

        result.append({
            **p,
            "summary": summary,
            "image_index": idx_data["index"],
            "image_index_detail": idx_data,
            "last_scan": last_scan,
            "last_post_date": last_post_date,
        })

    return result


# ── Player comparison (cross-player) ──

async def get_player_comparison(player_ids):
    """Get comparison data for multiple players."""
    result = []
    for pid in player_ids:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute("SELECT * FROM players WHERE id = ?", (pid,))
            player = await cursor.fetchone()
            if not player:
                continue
            player = dict(player)

        summary = await get_summary(pid)
        idx_data = await calculate_image_index(pid)
        report = await get_last_report(pid)

        result.append({
            "player": player,
            "summary": summary,
            "image_index": idx_data,
            "topics": report.get("topics", {}) if report else {},
            "brands": report.get("brands", {}) if report else {},
        })

    return result


# ── Weekly reports ──

async def save_weekly_report(player_id, report_text, recommendation, image_index, data=None):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO weekly_reports
            (player_id, report_text, recommendation, image_index, data_json)
            VALUES (?, ?, ?, ?, ?)""",
            (player_id, report_text, recommendation, image_index,
             json.dumps(data) if data else None),
        )
        await conn.commit()


async def get_weekly_reports(player_id, limit=10):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM weekly_reports WHERE player_id = ? ORDER BY created_at DESC LIMIT ?",
            (player_id, limit),
        )
        rows = [dict(r) for r in await cursor.fetchall()]
        for r in rows:
            if r.get("data_json"):
                r["data"] = json.loads(r["data_json"])
        return rows


async def get_scan_count(player_id):
    """Return number of completed scans for a player (used to detect first scan)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        row = await (await conn.execute(
            "SELECT COUNT(*) FROM scan_log WHERE player_id = ? AND status = 'completed'",
            (player_id,),
        )).fetchone()
        return row[0]


async def get_last_player_post_date(player_id):
    """Get the date of the most recent post by the player."""
    async with aiosqlite.connect(DB_PATH) as conn:
        row = await (await conn.execute(
            "SELECT MAX(posted_at) FROM player_posts WHERE player_id = ?", (player_id,)
        )).fetchone()
        return row[0] if row else None


# ── Image Index History ──

async def get_image_index_history(player_id, limit=30):
    """Get image_index values from scan_reports over time."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT sr.image_index, sr.created_at, sl.started_at
               FROM scan_reports sr
               LEFT JOIN scan_log sl ON sl.id = sr.scan_log_id
               WHERE sr.player_id = ? AND sr.image_index IS NOT NULL
               ORDER BY sr.created_at ASC LIMIT ?""",
            (player_id, limit),
        )
        return [dict(r) for r in await cursor.fetchall()]


# ── Sentiment by Platform ──

async def get_sentiment_by_platform(player_id):
    """Get average sentiment grouped by platform."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT platform,
                      COUNT(*) as count,
                      AVG(sentiment) as avg_sentiment,
                      SUM(CASE WHEN sentiment_label='positivo' THEN 1 ELSE 0 END) as positive,
                      SUM(CASE WHEN sentiment_label='neutro' THEN 1 ELSE 0 END) as neutral,
                      SUM(CASE WHEN sentiment_label='negativo' THEN 1 ELSE 0 END) as negative
               FROM social_mentions
               WHERE player_id = ? AND platform IS NOT NULL
               GROUP BY platform ORDER BY count DESC""",
            (player_id,),
        )
        social = [dict(r) for r in await cursor.fetchall()]

        # Add press as a "platform"
        cursor2 = await conn.execute(
            """SELECT 'prensa' as platform,
                      COUNT(*) as count,
                      AVG(sentiment) as avg_sentiment,
                      SUM(CASE WHEN sentiment_label='positivo' THEN 1 ELSE 0 END) as positive,
                      SUM(CASE WHEN sentiment_label='neutro' THEN 1 ELSE 0 END) as neutral,
                      SUM(CASE WHEN sentiment_label='negativo' THEN 1 ELSE 0 END) as negative
               FROM press_items
               WHERE player_id = ? AND sentiment IS NOT NULL""",
            (player_id,),
        )
        press_row = await cursor2.fetchone()
        if press_row and press_row["count"] > 0:
            social.insert(0, dict(press_row))

        return social


# ── Activity Peak Hours/Days ──

async def get_activity_peaks(player_id):
    """Analyze player post times to find peak hours and days."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT posted_at FROM player_posts WHERE player_id = ? AND posted_at IS NOT NULL",
            (player_id,),
        )
        rows = await cursor.fetchall()

    hours = [0] * 24
    days = [0] * 7  # 0=Mon, 6=Sun
    day_names = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]

    for row in rows:
        try:
            dt_str = row["posted_at"]
            if not dt_str:
                continue
            from datetime import datetime as dt_cls
            d = dt_cls.fromisoformat(dt_str.replace("Z", "+00:00").split("+")[0])
            hours[d.hour] += 1
            days[d.weekday()] += 1
        except Exception:
            pass

    return {
        "hours": [{"hour": h, "count": hours[h]} for h in range(24)],
        "days": [{"day": day_names[d], "day_num": d, "count": days[d]} for d in range(7)],
        "peak_hour": max(range(24), key=lambda h: hours[h]) if any(hours) else None,
        "peak_day": day_names[max(range(7), key=lambda d: days[d])] if any(days) else None,
    }


# ── Top Influencers (authors with most mentions) ──

async def get_top_influencers(player_id, limit=10):
    """Get top authors who mention the player most, with total engagement."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT author, platform,
                      COUNT(*) as mentions,
                      SUM(likes) as total_likes,
                      SUM(retweets) as total_retweets,
                      AVG(sentiment) as avg_sentiment
               FROM social_mentions
               WHERE player_id = ? AND author IS NOT NULL AND author != ''
               GROUP BY author
               ORDER BY mentions DESC, total_likes DESC
               LIMIT ?""",
            (player_id, limit),
        )
        return [dict(r) for r in await cursor.fetchall()]


# ── Portfolio sparkline data ──

async def get_portfolio_sparklines():
    """Get recent scan metrics for sparklines in portfolio cards."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT DISTINCT player_id FROM scan_log ORDER BY player_id")
        player_ids = [r["player_id"] for r in await cursor.fetchall()]

    result = {}
    for pid in player_ids:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                """SELECT sr.image_index, sl.started_at
                   FROM scan_reports sr
                   JOIN scan_log sl ON sl.id = sr.scan_log_id
                   WHERE sr.player_id = ? AND sr.image_index IS NOT NULL
                   ORDER BY sr.created_at DESC LIMIT 10""",
                (pid,),
            )
            rows = [dict(r) for r in await cursor.fetchall()]
            # Reverse so oldest is first (for sparkline left-to-right)
            result[pid] = list(reversed(rows))

    return result
