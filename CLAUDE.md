# AgentRadar - Documentacion Completa del Proyecto

## QUE ES
Plataforma OSINT de monitorizacion online de jugadores de futbol profesional. Desarrollada para la agencia de futbol **Niagara Sur**. Escanea 8+ fuentes (prensa, Twitter, Reddit, YouTube, Instagram, TikTok, Telegram, Transfermarkt), analiza todo con GPT-4o (sentimiento, topics, marcas, relevancia) y presenta resultados en un dashboard web con alertas automaticas, export PDF/CSV y escaneos diarios programados.

## COMO ARRANCAR

```bash
cd C:\Users\fermi\agentradar
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

Abre http://localhost:8000 en el navegador. Si hay datos previos en la DB, carga el dashboard automaticamente. Si no, muestra el formulario de setup para escanear el primer jugador.

**Prerequisitos**: Python 3.10+, pip install -r requirements.txt, archivo .env con APIFY_TOKEN y OPENAI_API_KEY.

## ARQUITECTURA GENERAL

```
Usuario -> index.html + app.js (frontend)
               |
               v
           app.py (FastAPI, 20+ endpoints, CORS, auth-free)
               |
       +-------+--------+--------+
       |       |        |        |
  scan_engine  db.py  scheduler  notifications
       |               |              |
  +----+----+    APScheduler     aiosmtplib
  |    |    |    (07:00 diario)
  v    v    v
scrapers/   analyzer.py
(8 modulos)  (GPT-4o)
```

## FLUJO DE UN ESCANEO (paso a paso)

1. **Usuario pulsa "Escanear"** en frontend -> `POST /api/scan` con {name, twitter, instagram, club, transfermarkt_id, tiktok}
2. **app.py** valida input (Pydantic), comprueba que no hay escaneo en curso (asyncio.Lock), lanza `run_scan()` como asyncio.Task
3. **scan_engine.py** `run_scan()`:
   a. Registra/actualiza jugador en DB (`db.get_or_create_player`)
   b. Crea entrada en `scan_log` con status "running"
   c. Obtiene URLs existentes para deduplicacion (`db.get_existing_urls`)
   d. Obtiene resumen del escaneo anterior para comparar deltas
   e. **Lanza scrapers en paralelo**:
      - `scrape_all_press(name, club)` -> Google News RSS + 8 feeds prensa espanola
      - `scrape_all_social(name, twitter, club)` -> Twitter (Apify) + Reddit (JSON) + YouTube (HTML) + TikTok (Apify) + Telegram (HTML publico)
      - `scrape_all_player_posts(twitter, instagram, tiktok)` -> Posts propios via Apify
   f. Si hay `transfermarkt_id`: scrape perfil TM (foto, valor, contrato, nacionalidad, posicion)
   g. **Dedup**: filtra items cuya URL ya existe en DB (ahorra tokens GPT-4o)
   h. **Analisis GPT-4o** (`analyzer.py`): procesa items en batches de 30, extrae:
      - relevancia (descarta items no relacionados con el jugador)
      - sentimiento (-1.0 a +1.0)
      - topics (fichaje, rendimiento, lesion, polemica, sponsors, etc.)
      - marcas detectadas
   i. **Guarda en DB**: press_items, social_mentions, player_posts (INSERT OR IGNORE)
   j. **Chequea alertas**: 3+ noticias negativas = alerta alta, >40% menciones negativas = alerta alta, 15+ noticias = trending media
   k. **Genera resumen ejecutivo** con GPT-4o (4-5 frases profesionales, menciona cambios vs escaneo anterior)
   l. **Guarda scan_report** vinculado al scan_log con topics, marcas, deltas, snapshot
   m. **Notifica** via Telegram si esta configurado
   n. Marca scan_log como "completed" con conteos finales
4. **Frontend** hace polling cada 2s a `GET /api/scan/status`, muestra progreso detallado por fase
5. **Cuando termina**: carga dashboard con todos los datos en paralelo (summary, report, press, social, activity, alerts, stats, scans)

## FLUJO DEL ESCANEO DIARIO AUTOMATICO

1. **APScheduler** dispara `daily_scan_job()` a las 07:00 (configurable)
2. Comprueba que no hay escaneo manual en curso
3. Obtiene todos los jugadores de DB
4. Escanea cada uno secuencialmente con 30s de delay entre ellos (para no saturar APIs)
5. Al terminar todos: envia email digest si SMTP esta configurado
6. Actualiza `last_daily_run` con estadisticas

## ARCHIVOS Y QUE HACE CADA UNO

### Backend

**app.py** (~460 lineas) - Servidor FastAPI
- Lifespan: init_db() + start_scheduler() al arrancar, stop_scheduler() al parar
- Middleware: CORS habilitado
- Logging: RotatingFileHandler (5MB max, 3 backups) en data/scan.log
- 20+ endpoints REST (ver seccion API)
- Export PDF: genera HTML standalone con html.escape() para XSS prevention
- Export CSV: StreamingResponse con csv.DictWriter
- Validacion: PlayerInput con Pydantic (nombre max 200 chars, handles sanitizados)

**scan_engine.py** (~257 lineas) - Orquestador de escaneos
- `run_scan(player_data, update_status)` - Pipeline completo descrito arriba
- `scan_status` dict global para polling del frontend
- `scan_lock` asyncio.Lock para evitar race conditions
- `_check_alerts()` - Logica de generacion de alertas
- `_send_telegram_alert()` - Notificacion via Telegram bot API

**analyzer.py** (~184 lineas) - Analisis GPT-4o
- System prompt detallado con reglas de relevancia y sentimiento
- `analyze_batch()` - Procesa en batches de 30, parsea JSON response, filtra irrelevantes
- `generate_executive_summary()` - Resumen ejecutivo con comparacion vs escaneo anterior
- `extract_topics_and_brands()` - Agrega y ordena por frecuencia
- Temperatura 0.1 para consistencia en analisis, 0.3 para resumen

**db.py** (~710 lineas) - Capa de base de datos SQLite
- 7 tablas: players, press_items, social_mentions, player_posts, alerts, scan_log, scan_reports
- Sistema de migraciones seguro (ALTER TABLE con try/except)
- 10 indexes de rendimiento en player_id, fechas, read status
- Dedup: content_hash SHA-256 en social_mentions + UNIQUE index
- Paginacion con LIMIT/OFFSET en todas las queries de datos
- Funciones para: CRUD jugadores, insert items, alertas (read/dismiss/filter), scan history, comparison

**scheduler.py** (~109 lineas) - Escaneos programados
- AsyncIOScheduler con CronTrigger
- Escanea todos los jugadores secuencialmente con delay configurable
- Skip si hay escaneo manual en curso
- Envia email digest al terminar
- Estado consultable via API

**notifications.py** (~108 lineas) - Email digest
- Tabla HTML con resumen por jugador (prensa, menciones, posts, alertas, nuevos items)
- Solo envia si SMTP_HOST y DIGEST_RECIPIENTS estan configurados
- aiosmtplib para envio async

**config.py** (~73 lineas) - Configuracion
- Todo via .env (dotenv): API keys, scheduler, SMTP, limites scraping
- 8 feeds RSS prensa espanola + Google News
- 6 subreddits de futbol
- 4 instancias Invidious (YouTube sin API key)
- 3 actores Apify (Twitter, Instagram, TikTok)

### Scrapers (carpeta scrapers/)

**press.py** (~145 lineas) - Prensa
- `scrape_google_news()`: RSS de Google News con nombre exacto + filtro club
- `scrape_spanish_press()`: 8 feeds RSS (Marca, AS, Mundo Deportivo, El Pais, Relevo, Gazzetta, Tuttosport, El Mundo). Filtra por nombre normalizado (sin acentos).
- Dedup por URL + filtro relevancia por apellido
- Logging con logger (no print)

**social.py** (~200 lineas) - Menciones redes
- `scrape_twitter_mentions()`: Apify actor con search terms (nombre exacto + club + @handle)
- `scrape_reddit()`: JSON API de 6 subreddits, 1.5s delay entre cada uno
- `scrape_tiktok_mentions()`: Apify actor busqueda por nombre
- `scrape_all_social()`: orquesta Twitter+Reddit+YouTube+TikTok en paralelo, Telegram secuencial
- `_apify_run_with_retry()`: helper compartido con 2 reintentos + backoff exponencial
- Cada Apify run: POST start -> poll status cada 5s (max 60 polls = 5min) -> GET dataset items

**player.py** (~209 lineas) - Posts propios
- `scrape_player_twitter()`: Posts del timeline del jugador via Apify
- `scrape_player_instagram()`: Posts de Instagram via Apify
- `scrape_player_tiktok()`: Videos de TikTok via Apify
- `_run_apify_actor()`: helper con retry (2 reintentos, backoff exponencial)
- Calcula engagement_rate: (likes+comments+shares)/views o /followers
- Detecta media_type: text, media, retweet, video, carousel, image

**youtube.py** (~150 lineas) - YouTube
- Scrape HTML de YouTube search results (NO usa API key)
- Busca "{nombre} futbol" y "{nombre} goles"
- Extrae ytInitialData JSON del HTML de la pagina
- Parsea view count (1.2M, 500K, etc.)

**transfermarkt.py** (~76 lineas) - Perfil Transfermarkt
- Scrape HTML con regex del perfil del jugador
- Extrae: photo_url, market_value, contract_until, nationality, position
- Cache implicito: solo se ejecuta si hay transfermarkt_id

**telegram.py** (~90 lineas) - Telegram
- Scrape de canales publicos via `https://t.me/s/{channel}` (sin auth)
- Regex para extraer mensajes y metadatos
- Filtra por nombre del jugador en el contenido

### Frontend (carpeta static/)

**index.html** (~203 lineas)
- Tailwind CSS via CDN + Chart.js
- Dark theme con colores custom (dark-900 a dark-500, accent blue)
- Secciones: Header, Player Modal, Setup Panel, Scan Progress, Dashboard
- 6 tabs: Prensa, Redes, Actividad, Alertas, Historial, Graficos
- Header con: foto jugador (circular), nombre, club, valor mercado, contrato, scheduler status, ultimo escaneo

**app.js** (~920 lineas) - Frontend v4
- `launchScan()` / `startScan()`: Inicia escaneo nuevo o re-escaneo
- `pollScanStatus()`: Polling cada 2s con progreso detallado
- `loadDashboard(playerId)`: Carga 8 endpoints en paralelo, renderiza todo
- `showPlayerSwitcher()`: Modal para cambiar entre jugadores o agregar nuevo
- `renderPress/Social/Activity()`: Tablas con sentiment badges, platform icons, CSV export
- `renderAlerts()`: Filtros severidad/no-leidas, marcar leida, descartar con confirmacion
- `renderHistorial()`: Tabla de escaneos con checkboxes para comparacion
- `renderHistorico()`: 4 graficos Chart.js (volumen prensa/menciones, sentimiento prensa/redes por dia)
- `loadMorePress()`: Paginacion "Cargar mas" (50 items por pagina)
- `runComparison()`: Modal side-by-side comparando 2 escaneos
- `exportPDF()` / `exportCSV(type)`: Descarga de informes
- `loadSchedulerStatus()` / `loadLastScan()`: Info en header
- `escapeHtml()`: Prevencion XSS en rendering

**style.css** (~166 lineas)
- Scrollbar custom, tab buttons, scan spinner animation
- Sentiment badges (positivo verde, neutro amarillo, negativo rojo)
- Alert severity borders (alta rojo, media amarillo, baja azul)
- Platform colors (twitter blue, reddit orange, instagram pink, youtube red, tiktok cyan, telegram blue)
- Card hover, fade-in animation, gauge component
- Filter buttons, scan history rows, topic badges escalados

## API ENDPOINTS COMPLETA

```
GET  /                           Sirve index.html
GET  /health                     {"status":"ok","timestamp":"..."}

# Jugadores
POST /api/player                 Crear/actualizar jugador
GET  /api/player                 Ultimo jugador registrado
GET  /api/player/{id}            Jugador por ID
GET  /api/players                Lista todos los jugadores

# Datos (todos con ?player_id=X&limit=50&offset=0)
GET  /api/press                  Noticias de prensa
GET  /api/social                 Menciones en redes sociales
GET  /api/activity               Posts propios del jugador
GET  /api/alerts                 Alertas (?severity=alta&unread_only=true)
GET  /api/stats                  Estadisticas agregadas (graficos)
GET  /api/summary                Resumen actual (conteos, sentimientos, engagement)
GET  /api/report                 Ultimo informe (resumen ejecutivo, topics, marcas, deltas)

# Alertas
PATCH /api/alerts/{id}/read      Marcar alerta como leida
DELETE /api/alerts/{id}          Descartar alerta

# Escaneo
POST /api/scan                   Iniciar escaneo manual
GET  /api/scan/status            Estado del escaneo en curso
GET  /api/last-scan              Info del ultimo escaneo completado
GET  /api/scans                  Historial de escaneos (?player_id=X)
GET  /api/compare                Comparar 2 escaneos (?scan_id_a=X&scan_id_b=Y)

# Image Index + Portfolio
GET  /api/player/{id}/image-index  Indice de imagen 0-100 con desglose
GET  /api/portfolio              Todos los jugadores con metricas para vista portfolio
GET  /api/compare-players        Comparativa multi-jugador (?player_ids=1,2,3)

# Informes Semanales
POST /api/player/{id}/weekly-report  Generar informe semanal con recomendacion
GET  /api/player/{id}/weekly-reports Lista de informes semanales (?limit=10)

# Scheduler
GET  /api/scheduler/status       Estado del programador diario

# Exportar
GET  /api/export/pdf             Informe HTML descargable (?player_id=X)
GET  /api/export/csv             Datos CSV (?player_id=X&type=press|social|activity)
```

## BASE DE DATOS

Archivo: `data/agentradar.db` (SQLite)

### Tablas

```sql
players (id, name, twitter, instagram, transfermarkt_id, club, tiktok,
         photo_url, market_value, contract_until, nationality, position, created_at)

press_items (id, player_id, source, title, url UNIQUE, summary,
             sentiment, sentiment_label, published_at, scraped_at)

social_mentions (id, player_id, platform, author, text, url, likes, retweets,
                 sentiment, sentiment_label, created_at, scraped_at, content_hash)
    -- UNIQUE INDEX on (player_id, content_hash) para dedup

player_posts (id, player_id, platform, text, url UNIQUE, likes, comments, shares, views,
              engagement_rate, media_type, sentiment, sentiment_label, posted_at, scraped_at)

alerts (id, player_id, type, severity, title, message, data_json, created_at, read)

scan_log (id, player_id, started_at, finished_at, status,
          press_count, mentions_count, posts_count, alerts_count)

scan_reports (id, player_id, scan_log_id, executive_summary,
              topics_json, brands_json, delta_json, summary_snapshot_json, image_index, created_at)

weekly_reports (id, player_id, report_text, recommendation, image_index,
               data_json, created_at)
```

### Indexes (10)
- idx_press_player, idx_social_player, idx_posts_player, idx_alerts_player, idx_scanlog_player, idx_scanreports_player
- idx_scanreports_logid (JOIN scan_log <-> scan_reports)
- idx_press_published, idx_social_created (ORDER BY fecha)
- idx_alerts_read (filtro no leidas)
- idx_social_content_hash (dedup UNIQUE)

## CONFIGURACION (.env)

```env
# REQUERIDOS
APIFY_TOKEN=apify_api_...           # Scraping Twitter/Instagram/TikTok
OPENAI_API_KEY=sk-proj-...          # Analisis GPT-4o

# OPCIONALES - Telegram alerts
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=-100...

# OPCIONALES - Scheduler
DAILY_SCAN_ENABLED=true             # Default: true
DAILY_SCAN_HOUR=7                   # Default: 7
DAILY_SCAN_MINUTE=0                 # Default: 0
SCAN_DELAY_SECONDS=30               # Default: 30

# OPCIONALES - Email digest
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=email@gmail.com
SMTP_PASS=app_password
DIGEST_RECIPIENTS=dest1@mail.com,dest2@mail.com

# OPCIONALES - Telegram channels to scrape
TELEGRAM_CHANNELS=canal1,canal2
```

## DATOS ACTUALES EN DB

- **Rodri Sanchez** (Al-Arabi SC, TM ID: 630995): 40 noticias, 232 menciones, 50 posts, 2 alertas
- **Jose Campana** (AD Ceuta, TM ID: 120095): datos de escaneo anterior
- Scheduler activo: 07:00 diario

## MEJORAS IMPLEMENTADAS

### Sesion anterior (seguridad + UX)
- XSS fix en PDF export (html.escape)
- asyncio.Lock en scan_status (race condition)
- CORS middleware
- /health endpoint
- Pydantic validation en PlayerInput
- 10 DB indexes
- RotatingFileHandler (5MB, 3 backups)
- Todos los print() -> logging en 4 scrapers
- Retry con backoff exponencial en Apify (2 reintentos)
- _apify_run_with_retry() compartido
- Ultimo escaneo visible en header
- Paginacion "Cargar mas" en prensa
- Confirmacion al descartar alertas
- CSV export en cada tab
- Comparacion side-by-side de escaneos
- Progreso detallado por fase de scraper

### Sesion actual (6 mejoras de alto valor)
1. **Indice de Imagen 0-100**: Score compuesto ponderado (volumen 20%, sent.prensa 25%, sent.redes 25%, engagement 15%, ausencia controversia 15%). Se calcula al final de cada escaneo y se almacena en scan_reports. Visualizado con anillo SVG circular en dashboard.
2. **Portfolio Dashboard**: Vista de todos los jugadores con semaforo (verde/amarillo/rojo segun indice). Cards con foto, metricas resumen, sentimiento, ultimo escaneo. Click para ver dashboard individual.
3. **Informe Semanal con Recomendaciones**: GPT-4o genera informe accionable (COMPRAR/VENDER/RENOVAR/MONITORIZAR/PRECAUCION) con riesgos, oportunidades, justificacion. Manual via boton + scheduler semanal (dom 20:00). Tabla weekly_reports en DB.
4. **Alertas Inteligentes**: 7 tipos: prensa negativa, redes negativas, trending, rumor de fichaje, lesion detectada, polemica, inactividad en redes (7+ dias sin publicar).
5. **Comparativa Multi-Jugador**: Endpoint + UI modal para comparar 2+ jugadores side-by-side con indice de imagen, metricas, temas top.
6. **Escaneo Profundo Inicial**: Primer escaneo de un jugador nuevo usa 3x los limites normales (FIRST_SCAN_MULTIPLIER). Se detecta automaticamente via scan_log count.

## PENDIENTE PARA PRODUCCION

- [ ] Deploy (Railway, VPS, o similar)
- [ ] HTTPS + dominio
- [ ] Autenticacion basica para el dashboard
- [ ] Backup automatico de SQLite
- [ ] Monitoring/uptime
- [ ] Rate limiting en API

## COMO AGREGAR UN NUEVO JUGADOR

1. Desde el frontend: click "+" Jugador en header -> rellenar formulario -> "Escanear nuevo jugador"
2. O via API: `POST /api/scan` con JSON `{"name": "...", "twitter": "handle", "instagram": "handle", "club": "...", "transfermarkt_id": "123456", "tiktok": "handle"}`
3. El escaneo tarda 2-5 minutos dependiendo de las fuentes disponibles

## COSTE ESTIMADO POR ESCANEO

- **Apify**: ~0.01-0.05 USD por actor run (Twitter, Instagram, TikTok)
- **OpenAI GPT-4o**: ~0.02-0.10 USD por escaneo (depende de items encontrados, ~30 items/batch)
- **Total**: ~0.05-0.20 USD por jugador/escaneo
- Con 5 jugadores y escaneo diario: ~$15-30/mes

## PROPUESTA COMERCIAL

En `proposal/propuesta-niagara-sur.html` hay una propuesta comercial completa con imagenes generadas (cover, infographic, closing, foto ejemplo) para presentar a Niagara Sur. Precio propuesto: 3.500 EUR setup + 500 EUR/mes mantenimiento.
