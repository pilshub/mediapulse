import sys
import os
import asyncio
import json
import html
import csv
import io
import hashlib
import hmac
import secrets
import aiohttp
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Rotating file logger (max 5MB, keep 3 backups)
LOG_PATH = os.path.join(os.path.dirname(__file__), "data", "scan.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
_fh = RotatingFileHandler(LOG_PATH, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
_fh.setFormatter(_fmt)
_sh = logging.StreamHandler()
_sh.setFormatter(_fmt)
logging.basicConfig(level=logging.INFO, handlers=[_fh, _sh])
log = logging.getLogger("agentradar")

from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, field_validator
from typing import Optional

import db
from scan_engine import run_scan, scan_status, scan_lock
from scheduler import start_scheduler, stop_scheduler, get_scheduler_status
from analyzer import generate_weekly_report

# -- Auth config --
DASHBOARD_PASS = os.getenv("DASHBOARD_PASS", "")
AUTH_SECRET = os.getenv("AUTH_SECRET", secrets.token_hex(32))
AUTH_ENABLED = bool(DASHBOARD_PASS)


def _make_token():
    """Create signed auth token."""
    msg = f"mediapulse:{AUTH_SECRET}".encode()
    return hmac.new(AUTH_SECRET.encode(), msg, hashlib.sha256).hexdigest()


def _verify_token(token):
    """Verify auth token."""
    expected = _make_token()
    return hmac.compare_digest(token, expected)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not AUTH_ENABLED:
            return await call_next(request)

        path = request.url.path
        # Allow public paths
        if path == "/health" or path == "/login" or path.startswith("/static"):
            return await call_next(request)

        # Check auth cookie
        token = request.cookies.get("ar_token", "")
        if token and _verify_token(token):
            return await call_next(request)

        # API calls get 401, pages get redirect
        if path.startswith("/api/"):
            return JSONResponse({"detail": "No autenticado"}, status_code=401)
        return RedirectResponse("/login")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    start_scheduler()
    if AUTH_ENABLED:
        log.info("[auth] Authentication enabled (password-only)")
    else:
        log.info("[auth] No DASHBOARD_PASS set - auth disabled")
    yield
    stop_scheduler()


app = FastAPI(title="AgentRadar", lifespan=lifespan)

# Auth middleware (before CORS)
app.add_middleware(AuthMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


class PlayerInput(BaseModel):
    name: str
    twitter: Optional[str] = None
    instagram: Optional[str] = None
    transfermarkt_id: Optional[str] = None
    club: Optional[str] = None
    tiktok: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v):
        v = v.strip()
        if not v or len(v) > 200:
            raise ValueError("Nombre requerido (max 200 chars)")
        return v

    @field_validator("twitter", "instagram", "tiktok", mode="before")
    @classmethod
    def sanitize_handle(cls, v):
        if v is None:
            return v
        v = v.strip().lstrip("@")
        return v if v else None


# -- Routes --


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/login")
async def login_page():
    return HTMLResponse("""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MediaPulse - Login</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0a0a;color:#e7e9ea;font-family:-apple-system,BlinkMacSystemFont,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{background:#161616;border:1px solid #222;border-radius:16px;padding:40px;width:100%;max-width:380px}
h1{font-size:24px;margin-bottom:8px;text-align:center}
.sub{color:#71767b;font-size:13px;text-align:center;margin-bottom:32px}
label{display:block;font-size:13px;color:#71767b;margin-bottom:6px}
input{width:100%;padding:12px 16px;background:#0a0a0a;border:1px solid #333;border-radius:8px;color:#fff;font-size:14px;margin-bottom:16px;outline:none}
input:focus{border-color:#1d9bf0}
button{width:100%;padding:12px;background:#1d9bf0;color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer}
button:hover{background:#1a8cd8}
.err{color:#f4212e;font-size:13px;text-align:center;margin-bottom:16px;display:none}
</style></head><body>
<div class="card">
<h1>MediaPulse</h1>
<p class="sub">Plataforma de monitorizacion OSINT</p>
<div class="err" id="err">Contrasena incorrecta</div>
<form method="POST" action="/login">
<label>Contrasena</label><input name="password" type="password" required autofocus>
<button type="submit">Entrar</button>
</form>
</div>
<script>
if(location.search.includes('error=1'))document.getElementById('err').style.display='block';
</script>
</body></html>""")


@app.post("/login")
async def login_submit(password: str = Form(...)):
    if password == DASHBOARD_PASS:
        token = _make_token()
        resp = RedirectResponse("/", status_code=302)
        resp.set_cookie("ar_token", token, httponly=True, samesite="lax", max_age=86400 * 7)
        return resp
    return RedirectResponse("/login?error=1", status_code=302)


@app.get("/logout")
async def logout():
    resp = RedirectResponse("/login")
    resp.delete_cookie("ar_token")
    return resp


@app.get("/")
async def index():
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/api/player")
async def get_player():
    import aiosqlite
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM players ORDER BY id DESC LIMIT 1")
        row = await cursor.fetchone()
        if row:
            return dict(row)
    return JSONResponse(content=None)


@app.get("/api/player/{player_id}")
async def get_player_by_id(player_id: int):
    import aiosqlite
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM players WHERE id = ?", (player_id,))
        row = await cursor.fetchone()
        if row:
            return dict(row)
    raise HTTPException(404, "Jugador no encontrado")


@app.get("/api/players")
async def list_players():
    return await db.get_all_players()


@app.post("/api/player")
async def set_player(player: PlayerInput):
    p = await db.get_or_create_player(
        player.name, player.twitter, player.instagram,
        player.transfermarkt_id, player.club, player.tiktok,
    )
    return p


@app.get("/api/press")
async def get_press(player_id: int, limit: int = 50, offset: int = 0,
                    date_from: Optional[str] = None, date_to: Optional[str] = None):
    return await db.get_press(player_id, limit, offset, date_from, date_to)


@app.get("/api/social")
async def get_social(player_id: int, limit: int = 50, offset: int = 0,
                     date_from: Optional[str] = None, date_to: Optional[str] = None,
                     platform: Optional[str] = None):
    return await db.get_social(player_id, limit, offset, date_from, date_to, platform)


@app.get("/api/activity")
async def get_activity(player_id: int, limit: int = 50, offset: int = 0,
                       date_from: Optional[str] = None, date_to: Optional[str] = None):
    return await db.get_player_posts_db(player_id, limit, offset, date_from, date_to)


@app.get("/api/search")
async def search_content(player_id: int, q: str, limit: int = 30):
    """Search across press, social and player posts."""
    return await db.search_all(player_id, q, limit)


@app.get("/api/alerts")
async def get_alerts(player_id: int, limit: int = 50, severity: Optional[str] = None, unread_only: bool = False):
    return await db.get_alerts_filtered(player_id, limit, severity, unread_only)


@app.patch("/api/alerts/{alert_id}/read")
async def mark_alert_read(alert_id: int):
    await db.mark_alert_read(alert_id)
    return {"ok": True}


@app.delete("/api/alerts/{alert_id}")
async def dismiss_alert(alert_id: int):
    await db.dismiss_alert(alert_id)
    return {"ok": True}


@app.get("/api/stats")
async def get_stats(player_id: int, date_from: Optional[str] = None, date_to: Optional[str] = None):
    return await db.get_stats(player_id, date_from, date_to)


@app.get("/api/summary")
async def get_summary(player_id: int, date_from: Optional[str] = None, date_to: Optional[str] = None):
    return await db.get_summary(player_id, date_from, date_to)


@app.get("/api/report")
async def get_report(player_id: int):
    report = await db.get_last_report(player_id)
    if report:
        return report
    return JSONResponse(content=None)


@app.get("/api/scan/status")
async def get_scan_status():
    return scan_status


@app.post("/api/scan")
async def start_scan_endpoint(player: PlayerInput):
    async with scan_lock:
        if scan_status["running"]:
            raise HTTPException(400, "Ya hay un escaneo en curso")
        scan_status["running"] = True

    player_data = {
        "name": player.name,
        "twitter": player.twitter,
        "instagram": player.instagram,
        "transfermarkt_id": player.transfermarkt_id,
        "club": player.club,
        "tiktok": player.tiktok,
    }
    asyncio.create_task(run_scan(player_data, update_status=True))
    return {"message": "Escaneo iniciado"}


# -- Scan History --


@app.get("/api/scans")
async def get_scan_history(player_id: int, limit: int = 50):
    return await db.get_scan_history(player_id, limit)


# -- Scheduler --


@app.get("/api/scheduler/status")
async def scheduler_status():
    return get_scheduler_status()


@app.get("/api/costs")
async def get_costs():
    """Get estimated API cost breakdown."""
    return await db.get_cost_estimate()


# -- CSV Export --


@app.get("/api/export/csv")
async def export_csv(player_id: int, type: str = "press"):
    """Export press/social/activity data as CSV."""
    if type == "press":
        items = await db.get_press(player_id, 9999)
        fields = ["source", "title", "url", "sentiment_label", "published_at"]
    elif type == "social":
        items = await db.get_social(player_id, 9999)
        fields = ["platform", "author", "text", "url", "likes", "retweets", "sentiment_label", "created_at"]
    elif type == "activity":
        items = await db.get_player_posts_db(player_id, 9999)
        fields = ["platform", "text", "url", "likes", "comments", "shares", "views", "engagement_rate", "sentiment_label", "posted_at"]
    else:
        raise HTTPException(400, "type must be press, social, or activity")

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for item in items:
        writer.writerow({k: item.get(k, "") for k in fields})

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={type}_{player_id}.csv"},
    )


# -- Comparison --


@app.get("/api/compare")
async def compare_scans(scan_id_a: int, scan_id_b: int):
    """Compare two scan reports side by side."""
    a = await db.get_scan_report_by_log_id(scan_id_a)
    b = await db.get_scan_report_by_log_id(scan_id_b)
    if not a or not b:
        raise HTTPException(404, "Scan report(s) not found")
    return {"a": a, "b": b}


# -- Last scan info --


@app.get("/api/last-scan")
async def get_last_scan_info(player_id: int):
    scan = await db.get_last_scan(player_id)
    return scan or {}


# -- Image Index --


@app.get("/api/player/{player_id}/image-index")
async def get_image_index(player_id: int):
    return await db.calculate_image_index(player_id)


@app.get("/api/player/{player_id}/image-index-history")
async def get_image_index_history(player_id: int, limit: int = 30):
    return await db.get_image_index_history(player_id, limit)


# -- Sentiment by Platform --


@app.get("/api/player/{player_id}/sentiment-by-platform")
async def get_sentiment_by_platform(player_id: int):
    return await db.get_sentiment_by_platform(player_id)


# -- Activity Peaks --


@app.get("/api/player/{player_id}/activity-peaks")
async def get_activity_peaks(player_id: int):
    return await db.get_activity_peaks(player_id)


# -- Top Influencers --


@app.get("/api/player/{player_id}/top-influencers")
async def get_top_influencers(player_id: int, limit: int = 10):
    return await db.get_top_influencers(player_id, limit)


# -- Portfolio (all players at a glance) --


@app.get("/api/portfolio")
async def get_portfolio():
    return await db.get_portfolio()


@app.get("/api/portfolio/sparklines")
async def get_portfolio_sparklines():
    return await db.get_portfolio_sparklines()


# -- Cross-player comparison --


@app.get("/api/compare-players")
async def compare_players(player_ids: str):
    """Compare multiple players. player_ids is comma-separated."""
    ids = [int(x.strip()) for x in player_ids.split(",") if x.strip().isdigit()]
    if len(ids) < 2:
        raise HTTPException(400, "Se necesitan al menos 2 jugadores para comparar")
    return await db.get_player_comparison(ids)


# -- Weekly Report --


@app.post("/api/player/{player_id}/weekly-report")
async def generate_weekly_report_endpoint(player_id: int):
    """Generate a weekly actionable report for a player."""
    player = None
    import aiosqlite
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM players WHERE id = ?", (player_id,))
        row = await cursor.fetchone()
        if row:
            player = dict(row)
    if not player:
        raise HTTPException(404, "Jugador no encontrado")

    summary = await db.get_summary(player_id)
    image_index = await db.calculate_image_index(player_id)
    report = await db.get_last_report(player_id)
    topics = report.get("topics", {}) if report else {}
    brands = report.get("brands", {}) if report else {}

    result = await generate_weekly_report(
        player["name"], summary, image_index, topics, brands, player.get("club", ""),
    )

    # Save to DB
    await db.save_weekly_report(
        player_id,
        result.get("text", ""),
        result.get("recommendation", "MONITORIZAR"),
        image_index.get("index", 0),
        {
            "risks": result.get("risks", []),
            "opportunities": result.get("opportunities", []),
            "justification": result.get("justification", ""),
            "summary": summary,
            "image_index": image_index,
        },
    )

    return result


@app.get("/api/player/{player_id}/weekly-reports")
async def get_weekly_reports(player_id: int, limit: int = 10):
    return await db.get_weekly_reports(player_id, limit)


@app.get("/api/player/{player_id}/weekly-report-pdf")
async def export_weekly_report_pdf(player_id: int, report_id: Optional[int] = None):
    """Export a weekly report as downloadable HTML."""
    h = html.escape
    import aiosqlite
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM players WHERE id = ?", (player_id,))
        player = dict(await cursor.fetchone() or {})
    if not player:
        raise HTTPException(404, "Jugador no encontrado")

    reports = await db.get_weekly_reports(player_id, 1)
    if not reports:
        raise HTTPException(404, "Sin informes semanales")
    wr = reports[0]
    rec = h(wr.get("recommendation", ""))
    rec_colors = {"COMPRAR": "#00ba7c", "RENOVAR": "#1d9bf0", "MONITORIZAR": "#ffd166", "PRECAUCION": "#f97316", "VENDER": "#f4212e"}
    rc = rec_colors.get(rec, "#ffd166")
    data = wr.get("data", {})
    risks = "".join(f"<li>{h(r)}</li>" for r in (data.get("risks") or []))
    opps = "".join(f"<li>{h(o)}</li>" for o in (data.get("opportunities") or []))
    idx_val = wr.get("image_index", 0) or 0
    idx_color = "#00ba7c" if idx_val >= 70 else "#ffd166" if idx_val >= 40 else "#f4212e"

    report_html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Informe Semanal - {h(player.get('name',''))}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0a0a0a;color:#e7e9ea;padding:40px;max-width:800px;margin:0 auto;}}
.header{{background:#161616;border:1px solid #222;border-radius:12px;padding:16px 24px;display:flex;align-items:center;justify-content:space-between;margin-bottom:24px;}}
.logo{{font-size:18px;font-weight:bold;color:#fff;}} .logo span{{color:#1d9bf0;}}
.card{{background:#161616;border:1px solid #222;border-radius:12px;padding:20px;margin:16px 0;}}
h2{{color:#fff;margin-top:0;}} ul{{color:#ccc;}}
@media print{{body{{background:#fff;color:#000;}} .card,.header{{background:#f9f9f9;border-color:#ddd;}}}}
</style></head><body>
<div class="header"><div class="logo">Media<span>Pulse</span></div><div style="color:#71767b;font-size:12px;">Informe Semanal - {datetime.now().strftime('%d/%m/%Y')}</div></div>
<h1 style="color:#1d9bf0;">{h(player.get('name',''))}</h1>
<p style="color:#71767b;">{h(player.get('club',''))} | Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
<div class="card">
<div style="display:flex;align-items:center;gap:16px;margin-bottom:16px;">
<span style="background:{rc}20;color:{rc};padding:8px 20px;border-radius:8px;font-weight:bold;font-size:16px;border:1px solid {rc}40;">{rec}</span>
<div><span style="font-size:28px;font-weight:bold;color:{idx_color};">{round(idx_val)}</span><span style="color:#71767b;font-size:14px;">/100 Indice de Imagen</span></div>
</div>
<p style="font-size:14px;color:#ccc;line-height:1.6;">{h(wr.get('report_text',''))}</p>
{f'<p style="color:#999;font-style:italic;">{h(data.get("justification",""))}</p>' if data.get("justification") else ''}
</div>
{f'<div class="card"><h2 style="color:#f4212e;">Riesgos</h2><ul>{risks}</ul></div>' if risks else ''}
{f'<div class="card"><h2 style="color:#00ba7c;">Oportunidades</h2><ul>{opps}</ul></div>' if opps else ''}
<div style="margin-top:40px;padding-top:20px;border-top:1px solid #222;color:#71767b;font-size:11px;text-align:center;">MediaPulse - Informe Semanal | Confidencial</div>
</body></html>"""
    return HTMLResponse(content=report_html, headers={
        "Content-Disposition": f"attachment; filename=InformeSemanal_{player.get('name','').replace(' ','_')}_{datetime.now().strftime('%Y%m%d')}.html"
    })


# -- PDF Export --


@app.get("/api/export/pdf")
async def export_pdf(player_id: int):
    """Generate a downloadable HTML report."""
    player_data = None
    import aiosqlite
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM players WHERE id = ?", (player_id,))
        row = await cursor.fetchone()
        if row:
            player_data = dict(row)

    if not player_data:
        raise HTTPException(404, "Jugador no encontrado")

    summary = await db.get_summary(player_id)
    report = await db.get_last_report(player_id)
    press = await db.get_press(player_id, 30)
    social = await db.get_social(player_id, 30)
    activity = await db.get_player_posts_db(player_id, 20)
    alerts = await db.get_alerts(player_id, 10)
    image_index = await db.calculate_image_index(player_id)
    weekly = await db.get_weekly_reports(player_id, 1)

    html = _build_pdf_html(player_data, summary, report, press, social, activity, alerts, image_index, weekly)
    return HTMLResponse(content=html, headers={
        "Content-Disposition": f"attachment; filename=Informe_{player_data['name'].replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.html"
    })


# -- PDF Builder --


def _build_pdf_html(player, summary, report, press, social, activity, alerts, image_index=None, weekly=None):
    """Build a standalone HTML report for PDF export."""
    h = html.escape  # shorthand for XSS prevention
    s = summary or {}
    r = report or {}
    topics = r.get("topics", {})
    brands = r.get("brands", {})
    delta = r.get("delta", {}) or {}

    photo_url = player.get("photo_url")
    market_value = player.get("market_value")
    contract_until = player.get("contract_until")
    nationality = player.get("nationality")
    position = player.get("position")

    def sent_badge(label):
        label = h(str(label))
        colors = {"positivo": "#00ba7c", "neutro": "#ffd166", "negativo": "#f4212e"}
        c = colors.get(label, "#666")
        return f'<span style="background:{c}20;color:{c};padding:2px 8px;border-radius:12px;font-size:11px;">{label}</span>'

    def delta_arrow(key):
        v = delta.get(key)
        if v is None:
            return ""
        if isinstance(v, float):
            arrow = "+" if v > 0 else ""
            color = "#00ba7c" if v > 0 else "#f4212e" if v < 0 else "#666"
            return f' <span style="color:{color};font-size:11px;">({arrow}{v:.2f})</span>'
        arrow = "+" if v > 0 else ""
        color = "#00ba7c" if v > 0 else "#f4212e" if v < 0 else "#666"
        return f' <span style="color:{color};font-size:11px;">({arrow}{v})</span>'

    # Player photo HTML
    if photo_url:
        photo_html = f'<img src="{h(photo_url)}" style="width:64px;height:64px;border-radius:50%;object-fit:cover;border:2px solid #1d9bf0;">'
    else:
        initials = "".join(w[0].upper() for w in player.get("name", "").split()[:2])
        photo_html = f'<div style="width:64px;height:64px;background:#1d9bf0;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:bold;color:#fff;font-size:20px;">{h(initials)}</div>'

    # Profile info
    profile_parts = [player.get('club', '')]
    if position:
        profile_parts.append(position)
    if nationality:
        profile_parts.append(nationality)
    profile_info = h(" | ".join(p for p in profile_parts if p))

    # Market value + contract
    tm_html = ""
    if market_value or contract_until:
        parts = []
        if market_value:
            parts.append(f'<span style="color:#00ba7c;font-weight:bold;">{h(market_value)}</span>')
        if contract_until:
            parts.append(f'Contrato: {h(contract_until)}')
        tm_html = f'<p style="margin:5px 0 0;font-size:13px;">{" | ".join(parts)}</p>'

    press_html = "".join(
        f'<tr><td style="padding:6px;border-bottom:1px solid #222;">{sent_badge(p.get("sentiment_label",""))}</td>'
        f'<td style="padding:6px;border-bottom:1px solid #222;">{h(p.get("source",""))}</td>'
        f'<td style="padding:6px;border-bottom:1px solid #222;"><a href="{h(p.get("url",""))}" style="color:#1d9bf0;">{h(p.get("title",""))}</a></td></tr>'
        for p in press[:20]
    )

    topics_html = "".join(
        f'<span style="background:#1d9bf020;color:#1d9bf0;padding:4px 12px;border-radius:16px;margin:3px;display:inline-block;font-size:12px;">{h(str(t))} ({c})</span>'
        for t, c in topics.items()
    )

    brands_html = "".join(
        f'<span style="background:#e1306c20;color:#e1306c;padding:4px 12px;border-radius:16px;margin:3px;display:inline-block;font-size:12px;">{h(str(b))} ({c})</span>'
        for b, c in brands.items()
    ) or '<span style="color:#666;">Ninguna detectada</span>'

    alerts_html = "".join(
        f'<div style="padding:8px;margin:4px 0;border-left:3px solid {"#f4212e" if a.get("severity")=="alta" else "#ffd166"};background:#161616;">'
        f'<strong>{h(a.get("title",""))}</strong> <span style="color:#666;font-size:11px;">({h(a.get("severity",""))})</span><br>'
        f'<span style="color:#999;font-size:12px;">{h(a.get("message",""))}</span></div>'
        for a in alerts
    ) or '<p style="color:#666;">Sin alertas</p>'

    # Image Index section
    idx_html = ""
    if image_index:
        idx_val = image_index.get("index", 0)
        idx_color = "#00ba7c" if idx_val >= 70 else "#ffd166" if idx_val >= 40 else "#f4212e"
        idx_label = "POSITIVO" if idx_val >= 70 else "NEUTRO" if idx_val >= 40 else "RIESGO"
        components = [
            ("Volumen", image_index.get("volume", 0)),
            ("Sent. Prensa", image_index.get("press_sentiment", 0)),
            ("Sent. Redes", image_index.get("social_sentiment", 0)),
            ("Engagement", image_index.get("engagement", 0)),
            ("Sin Controversia", image_index.get("no_controversy", 0)),
        ]
        comp_html = "".join(
            f'<div style="text-align:center;"><div style="font-size:18px;font-weight:bold;">{round(v)}</div><div style="font-size:10px;color:#71767b;">{n}</div></div>'
            for n, v in components
        )
        idx_html = f"""
        <div class="card" style="margin-bottom:20px;">
        <h2 style="margin-top:0;">Indice de Imagen</h2>
        <div style="display:flex;align-items:center;gap:20px;">
            <div style="text-align:center;">
                <div style="font-size:42px;font-weight:bold;color:{idx_color};">{round(idx_val)}</div>
                <div style="font-size:12px;color:{idx_color};font-weight:bold;">{idx_label}</div>
                <div style="font-size:10px;color:#71767b;">/100</div>
            </div>
            <div style="flex:1;display:flex;justify-content:space-around;">{comp_html}</div>
        </div>
        </div>"""

    # Weekly report recommendation
    rec_html = ""
    if weekly:
        wr = weekly[0]
        rec = h(wr.get("recommendation", ""))
        rec_colors = {"COMPRAR": "#00ba7c", "RENOVAR": "#1d9bf0", "MONITORIZAR": "#ffd166", "PRECAUCION": "#f97316", "VENDER": "#f4212e"}
        rc = rec_colors.get(rec, "#ffd166")
        data = wr.get("data", {})
        risks_html = "".join(f"<li>{h(r)}</li>" for r in (data.get("risks") or []))
        opps_html = "".join(f"<li>{h(o)}</li>" for o in (data.get("opportunities") or []))
        rec_html = f"""
        <div class="card" style="margin-bottom:20px;">
        <h2 style="margin-top:0;">Recomendacion</h2>
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">
            <span style="background:{rc}20;color:{rc};padding:6px 16px;border-radius:8px;font-weight:bold;font-size:14px;border:1px solid {rc}40;">{rec}</span>
            <span style="color:#999;font-size:12px;">{h(data.get("justification", ""))}</span>
        </div>
        <p style="font-size:13px;color:#ccc;">{h(wr.get("report_text", ""))}</p>
        {"<div style='margin-top:10px;'><strong style='color:#f4212e;font-size:11px;'>RIESGOS:</strong><ul style='font-size:12px;color:#999;'>" + risks_html + "</ul></div>" if risks_html else ""}
        {"<div style='margin-top:10px;'><strong style='color:#00ba7c;font-size:11px;'>OPORTUNIDADES:</strong><ul style='font-size:12px;color:#999;'>" + opps_html + "</ul></div>" if opps_html else ""}
        </div>"""

    player_name = h(player.get('name', ''))
    eng_pct = f"{s.get('avg_engagement', 0)*100:.2f}%" if s.get('avg_engagement') else "-"
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>MediaPulse - {player_name}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0a0a0a;color:#e7e9ea;padding:40px;max-width:900px;margin:0 auto;}}
h1{{color:#1d9bf0;margin:0;}} h2{{color:#fff;border-bottom:1px solid #222;padding-bottom:8px;margin-top:30px;}}
.card{{background:#161616;border:1px solid #222;border-radius:12px;padding:20px;margin:12px 0;}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;}}
.stat{{text-align:center;}} .stat-value{{font-size:24px;font-weight:bold;color:#fff;}}
.stat-label{{font-size:11px;color:#71767b;text-transform:uppercase;}}
table{{width:100%;border-collapse:collapse;}} a{{color:#1d9bf0;text-decoration:none;}}
.header-bar{{background:#161616;border:1px solid #222;border-radius:12px;padding:16px 24px;display:flex;align-items:center;justify-content:space-between;margin-bottom:24px;}}
.logo{{display:flex;align-items:center;gap:8px;font-size:18px;font-weight:bold;color:#fff;}}
.logo span{{color:#1d9bf0;}}
@media print{{body{{background:#fff;color:#000;}} .card{{border-color:#ddd;background:#f9f9f9;}} .header-bar{{background:#f0f0f0;border-color:#ddd;}}}}
</style></head><body>
<div class="header-bar">
<div class="logo">Media<span>Pulse</span></div>
<div style="color:#71767b;font-size:12px;">Informe generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}</div>
</div>

<div style="display:flex;align-items:center;gap:16px;margin-bottom:24px;">
{photo_html}
<div>
<h1>{player_name}</h1>
<p style="margin:4px 0 0;color:#71767b;">{profile_info}</p>
{tm_html}
</div>
</div>

{idx_html}
{rec_html}

<div class="card grid" style="grid-template-columns:repeat(4,1fr);">
<div class="stat"><div class="stat-value">{s.get('press_count',0)}{delta_arrow('press_count')}</div><div class="stat-label">Noticias</div></div>
<div class="stat"><div class="stat-value">{s.get('press_sentiment','-')}{delta_arrow('press_sentiment')}</div><div class="stat-label">Sent. Prensa</div></div>
<div class="stat"><div class="stat-value">{s.get('mentions_count',0)}{delta_arrow('mentions_count')}</div><div class="stat-label">Menciones</div></div>
<div class="stat"><div class="stat-value">{s.get('social_sentiment','-')}{delta_arrow('social_sentiment')}</div><div class="stat-label">Sent. Redes</div></div>
</div>
<div class="card grid" style="grid-template-columns:repeat(3,1fr);">
<div class="stat"><div class="stat-value">{s.get('posts_count',0)}</div><div class="stat-label">Posts Jugador</div></div>
<div class="stat"><div class="stat-value">{eng_pct}</div><div class="stat-label">Engagement</div></div>
<div class="stat"><div class="stat-value">{s.get('alerts_count',0)}</div><div class="stat-label">Alertas</div></div>
</div>

<div class="card">
<h2 style="margin-top:0;">Resumen Ejecutivo</h2>
<p>{h(r.get('executive_summary','Sin resumen disponible'))}</p>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
<div class="card">
<h2 style="margin-top:0;">Temas Detectados</h2>
{topics_html or '<span style="color:#666;">Sin temas</span>'}
</div>
<div class="card">
<h2 style="margin-top:0;">Marcas Detectadas</h2>
{brands_html}
</div>
</div>

<h2>Prensa ({len(press)} noticias)</h2>
<table>{press_html}</table>

<h2>Alertas</h2>
{alerts_html}

<div style="margin-top:40px;padding-top:20px;border-top:1px solid #222;color:#71767b;font-size:11px;text-align:center;">
MediaPulse - Monitorizacion OSINT de Jugadores | {datetime.now().strftime('%d/%m/%Y %H:%M')} | Confidencial - Uso interno
</div>
</body></html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
