"""Email digest notifications after daily scans."""
import logging
from datetime import datetime

log = logging.getLogger("agentradar")


async def send_digest_email(players, results):
    """Send daily digest email with scan results for all players.

    Only sends if SMTP is configured and DIGEST_RECIPIENTS is set.
    """
    from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, DIGEST_RECIPIENTS

    if not SMTP_HOST or not DIGEST_RECIPIENTS:
        log.info("[email] SMTP not configured, skipping digest")
        return

    recipients = [r.strip() for r in DIGEST_RECIPIENTS.split(",") if r.strip()]
    if not recipients:
        return

    # Build HTML email body
    html = _build_digest_html(players, results)
    subject = f"Monitorizacion Diaria - {datetime.now().strftime('%d/%m/%Y')}"

    try:
        import aiosmtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText(html, "html", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASS,
            use_tls=True if SMTP_PORT == 465 else False,
            start_tls=True if SMTP_PORT == 587 else False,
        )
        log.info(f"[email] Digest sent to {len(recipients)} recipients")
    except Exception as e:
        log.error(f"[email] Error sending digest: {e}")


def _build_digest_html(players, results):
    """Build HTML email body with scan results table."""
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    rows = ""
    for player, result in zip(players, results):
        if result is None:
            rows += f"""
            <tr>
                <td style="padding:10px;border-bottom:1px solid #eee;">{player.get('name','')}</td>
                <td style="padding:10px;border-bottom:1px solid #eee;" colspan="5">Error en escaneo</td>
            </tr>"""
            continue

        rows += f"""
        <tr>
            <td style="padding:10px;border-bottom:1px solid #eee;font-weight:bold;">{player.get('name','')}</td>
            <td style="padding:10px;border-bottom:1px solid #eee;text-align:center;">{result.get('press_count', 0)}</td>
            <td style="padding:10px;border-bottom:1px solid #eee;text-align:center;">{result.get('mentions_count', 0)}</td>
            <td style="padding:10px;border-bottom:1px solid #eee;text-align:center;">{result.get('posts_count', 0)}</td>
            <td style="padding:10px;border-bottom:1px solid #eee;text-align:center;">{result.get('alerts_count', 0)}</td>
            <td style="padding:10px;border-bottom:1px solid #eee;text-align:center;">{result.get('new_items', 0)}</td>
        </tr>"""

    total_players = len(players)
    total_scanned = sum(1 for r in results if r is not None)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#f5f5f5;padding:20px;">
<div style="max-width:700px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
    <div style="background:#1d9bf0;padding:20px;text-align:center;">
        <h1 style="color:#fff;margin:0;font-size:20px;">Monitorizacion Diaria</h1>
        <p style="color:rgba(255,255,255,0.8);margin:5px 0 0;font-size:13px;">{now} - {total_scanned}/{total_players} jugadores escaneados</p>
    </div>
    <div style="padding:20px;">
        <table style="width:100%;border-collapse:collapse;">
            <thead>
                <tr style="background:#f8f9fa;">
                    <th style="padding:10px;text-align:left;font-size:12px;text-transform:uppercase;color:#666;">Jugador</th>
                    <th style="padding:10px;text-align:center;font-size:12px;text-transform:uppercase;color:#666;">Prensa</th>
                    <th style="padding:10px;text-align:center;font-size:12px;text-transform:uppercase;color:#666;">Menciones</th>
                    <th style="padding:10px;text-align:center;font-size:12px;text-transform:uppercase;color:#666;">Posts</th>
                    <th style="padding:10px;text-align:center;font-size:12px;text-transform:uppercase;color:#666;">Alertas</th>
                    <th style="padding:10px;text-align:center;font-size:12px;text-transform:uppercase;color:#666;">Nuevos</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    <div style="padding:15px 20px;background:#f8f9fa;text-align:center;color:#999;font-size:11px;">
        Generado automaticamente | Monitorizacion Online de Jugadores
    </div>
</div>
</body></html>"""
