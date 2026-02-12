import json
import logging
from datetime import datetime, timedelta
from openai import AsyncOpenAI
from config import OPENAI_API_KEY, INTELLIGENCE_MAX_INPUT_ITEMS, INTELLIGENCE_LOOKBACK_DAYS, INTELLIGENCE_MAX_TOKENS

log = logging.getLogger("agentradar")

client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

SYSTEM_PROMPT_TEMPLATE = """Eres un analista OSINT especializado en futbol profesional.
Estas analizando contenido sobre el jugador: {player_name} (club: {club}).

Analiza los siguientes items y para CADA UNO devuelve un JSON con:
- relevant: true si el item trata sobre ESTE jugador especifico, false si es sobre otra persona con nombre similar o no tiene relacion
- sentiment: numero de -1.0 (muy negativo) a 1.0 (muy positivo). Pon 0 si relevant es false.
- sentiment_label: "positivo", "neutro", o "negativo"
- topics: lista de temas detectados. Usa SOLO estos valores:
  fichaje, rendimiento, lesion, vida_personal, polemica, sponsors, aficion, entrenador, seleccion, tactica, cantera, economia, otro
- brands: lista de marcas/sponsors mencionados (Nike, Adidas, Puma, etc). Array vacio si no hay ninguna.

REGLAS DE RELEVANCIA (SE ESTRICTO):
- El item DEBE mencionar a {player_name} de forma clara y directa para ser relevant
- Si el item es sobre el CLUB ({club}) en general sin mencionar al jugador por nombre = NOT relevant
- Jugadores con nombre similar pero de otro equipo = NOT relevant (ej: "Juan Antonio Casas" != "Antonio Casas")
- Noticias genericas del equipo (resultados, fichajes de OTROS jugadores, ruedas de prensa genericas) = NOT relevant
- Videos/posts de highlights del equipo que no mencionan al jugador = NOT relevant
- MULTI-IDIOMA: Los items pueden estar en espanol, ingles, italiano, arabe, frances o aleman. Analiza el contenido en SU idioma original pero responde siempre en espanol.
- En caso de DUDA, marca relevant: false (es mejor filtrar un item dudoso que contaminar el analisis)

REGLAS DE SENTIMIENTO:
- Se objetivo y preciso con el sentimiento
- Criticas al rendimiento deportivo = "negativo"
- Elogios al rendimiento = "positivo"
- Noticias informativas sin carga emocional = "neutro"
- Rumores de fichaje sin carga = "neutro"
- Polemicas, conflictos = "negativo"
- Victorias, goles, buenas actuaciones = "positivo"

Responde UNICAMENTE con un JSON array. Sin texto extra. Ejemplo:
[{{"relevant": true, "sentiment": 0.3, "sentiment_label": "positivo", "topics": ["rendimiento"], "brands": []}}, {{"relevant": false, "sentiment": 0, "sentiment_label": "neutro", "topics": [], "brands": []}}]"""


async def analyze_batch(items, batch_size=30, player_name="", club=""):
    if not client or not items:
        for item in items:
            item["sentiment"] = 0
            item["sentiment_label"] = "neutro"
            item["topics"] = []
            item["brands"] = []
        return items

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        player_name=player_name or "desconocido",
        club=club or "desconocido",
    )

    results = []
    filtered_out = 0

    for i in range(0, len(items), batch_size):
        batch = items[i : i + batch_size]

        texts = []
        for j, item in enumerate(batch):
            text = item.get("title") or item.get("text") or ""
            source = item.get("source") or item.get("platform") or ""
            texts.append(f"[{j}] ({source}) {text[:300]}")

        prompt = "\n".join(texts)

        try:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=4000,
            )

            content = response.choices[0].message.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                content = content.rsplit("```", 1)[0]

            analysis = json.loads(content)

            for j, item in enumerate(batch):
                if j < len(analysis):
                    a = analysis[j]
                    # Filter out irrelevant items
                    if not a.get("relevant", True):
                        filtered_out += 1
                        continue
                    item["sentiment"] = a.get("sentiment", 0)
                    item["sentiment_label"] = a.get("sentiment_label", "neutro")
                    item["topics"] = a.get("topics", [])
                    item["brands"] = a.get("brands", [])
                else:
                    item["sentiment"] = 0
                    item["sentiment_label"] = "neutro"
                    item["topics"] = []
                    item["brands"] = []
                results.append(item)

        except Exception as e:
            print(f"[analyzer] GPT-4o batch error: {e}")
            for item in batch:
                item["sentiment"] = 0
                item["sentiment_label"] = "neutro"
                item["topics"] = []
                item["brands"] = []
                results.append(item)

    if filtered_out:
        print(f"[analyzer] Filtered {filtered_out} irrelevant items (kept {len(results)})")

    return results


async def generate_executive_summary(player_name, summary_data, topics, brands, prev_summary=None):
    """Generate an executive summary paragraph + sentiment comparison."""
    if not client:
        return {"text": "No se pudo generar resumen (falta OpenAI API key)", "delta": None}

    # Build comparison context
    comparison = ""
    delta = None
    if prev_summary:
        delta = {}
        for key in ["press_sentiment", "social_sentiment", "press_count", "mentions_count"]:
            cur = summary_data.get(key)
            prev = prev_summary.get(key)
            if cur is not None and prev is not None:
                delta[key] = round(cur - prev, 3) if isinstance(cur, float) else cur - prev

        comparison = f"""
Comparacion con escaneo anterior:
- Noticias: {prev_summary.get('press_count', 0)} -> {summary_data.get('press_count', 0)}
- Sent. prensa: {prev_summary.get('press_sentiment', 'N/A')} -> {summary_data.get('press_sentiment', 'N/A')}
- Menciones: {prev_summary.get('mentions_count', 0)} -> {summary_data.get('mentions_count', 0)}
- Sent. redes: {prev_summary.get('social_sentiment', 'N/A')} -> {summary_data.get('social_sentiment', 'N/A')}
"""

    top_topics_str = ", ".join(f"{t}: {c}" for t, c in (topics or {}).items()) or "ninguno"
    brands_str = ", ".join(f"{b}: {c}" for b, c in (brands or {}).items()) or "ninguna"

    prompt = f"""Genera un resumen ejecutivo breve (4-5 frases) sobre la situacion mediatica actual de {player_name}.

Datos del escaneo:
- Noticias en prensa: {summary_data.get('press_count', 0)}
- Sentimiento prensa: {summary_data.get('press_sentiment', 'N/A')}
- Menciones en redes: {summary_data.get('mentions_count', 0)}
- Sentimiento redes: {summary_data.get('social_sentiment', 'N/A')}
- Posts del jugador: {summary_data.get('posts_count', 0)}
- Engagement medio: {summary_data.get('avg_engagement', 'N/A')}
- Temas detectados: {top_topics_str}
- Marcas detectadas: {brands_str}
{comparison}
Responde en espanol, tono profesional y directo. Si hay comparacion con escaneo anterior, menciona los cambios relevantes."""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=400,
        )
        return {
            "text": response.choices[0].message.content.strip(),
            "delta": delta,
        }
    except Exception as e:
        return {"text": f"Error generando resumen: {e}", "delta": delta}


async def generate_weekly_report(player_name, summary, image_index, topics, brands, club=""):
    """Generate an actionable weekly report with buy/sell/renew/monitor recommendations."""
    if not client:
        return {"text": "No se pudo generar informe (falta OpenAI API key)", "recommendation": "monitor"}

    idx = image_index or {}
    top_topics_str = ", ".join(f"{t}: {c}" for t, c in (topics or {}).items()) or "ninguno"
    brands_str = ", ".join(f"{b}: {c}" for b, c in (brands or {}).items()) or "ninguna"

    prompt = f"""Eres un analista de scouting para una agencia de futbol profesional. Genera un informe semanal ACCIONABLE sobre {player_name} ({club or 'club desconocido'}).

DATOS DEL JUGADOR:
- Indice de Imagen: {idx.get('index', 'N/A')}/100
  - Volumen mediatico: {idx.get('volume', 'N/A')}/100
  - Sentimiento prensa: {idx.get('press_sentiment', 'N/A')}/100
  - Sentimiento redes: {idx.get('social_sentiment', 'N/A')}/100
  - Engagement: {idx.get('engagement', 'N/A')}/100
  - Ausencia de controversia: {idx.get('no_controversy', 'N/A')}/100
- Noticias en prensa: {summary.get('press_count', 0)}
- Menciones en redes: {summary.get('mentions_count', 0)}
- Posts del jugador: {summary.get('posts_count', 0)}
- Engagement medio: {summary.get('avg_engagement', 'N/A')}
- Temas detectados: {top_topics_str}
- Marcas detectadas: {brands_str}

GENERA:
1. RESUMEN SITUACIONAL (3-4 frases): Estado actual del jugador en medios y redes
2. RIESGOS DETECTADOS: Lista de riesgos concretos (controversias, lesiones, rumores de salida, inactividad en redes)
3. OPORTUNIDADES: Aspectos positivos aprovechables (buen engagement, cobertura positiva, interes de mercado)
4. RECOMENDACION PRINCIPAL: Una sola palabra de estas: COMPRAR, VENDER, RENOVAR, MONITORIZAR, PRECAUCION
   - COMPRAR: Si el indice es alto y hay oportunidad de mercado
   - VENDER: Si hay problemas serios o el mercado esta caliente a favor
   - RENOVAR: Si el jugador esta en buen momento y vinculado al club
   - MONITORIZAR: Si no hay senal clara, seguir observando
   - PRECAUCION: Si hay riesgos activos que requieren atencion
5. JUSTIFICACION: 1-2 frases explicando la recomendacion

Responde en JSON con esta estructura exacta:
{{"resumen": "...", "riesgos": ["riesgo1", "riesgo2"], "oportunidades": ["oportunidad1"], "recomendacion": "MONITORIZAR", "justificacion": "..."}}

Tono profesional de agencia de representacion deportiva. En espanol."""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            content = content.rsplit("```", 1)[0]

        import json as json_mod
        data = json_mod.loads(content)
        return {
            "text": data.get("resumen", ""),
            "recommendation": data.get("recomendacion", "MONITORIZAR"),
            "risks": data.get("riesgos", []),
            "opportunities": data.get("oportunidades", []),
            "justification": data.get("justificacion", ""),
        }
    except Exception as e:
        return {
            "text": f"Error generando informe: {e}",
            "recommendation": "MONITORIZAR",
            "risks": [],
            "opportunities": [],
            "justification": "",
        }


async def analyze_images(items, player_name="", max_images=10):
    """Analyze images from player posts and high-engagement mentions with GPT-4o Vision.
    Extracts: visible brands, context/location, people, mood, potential risks.
    Only processes items that have image URLs.
    """
    if not client or not items:
        return items

    # Collect items with image URLs, prioritize by engagement
    image_items = []
    for item in items:
        img_url = item.get("image_url") or item.get("thumbnail_url") or ""
        if img_url and img_url.startswith("http"):
            image_items.append((item, img_url))

    if not image_items:
        return items

    # Sort by engagement (likes) descending, take top N
    image_items.sort(key=lambda x: (x[0].get("likes", 0) or 0) + (x[0].get("views", 0) or 0), reverse=True)
    image_items = image_items[:max_images]

    log.info(f"[analyzer] Analyzing {len(image_items)} images with GPT-4o Vision")

    for item, img_url in image_items:
        try:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": f"Analiza esta imagen relacionada con el futbolista {player_name}. Responde en JSON con: {{\"brands\": [marcas visibles], \"context\": \"descripcion breve del contexto (entrenamiento, fiesta, evento, etc)\", \"people_count\": N, \"mood\": \"positivo/neutro/negativo\", \"risk_flag\": \"none/low/medium/high\", \"risk_detail\": \"detalle si hay riesgo\"}}. Si no puedes analizar la imagen, devuelve {{\"error\": \"no disponible\"}}."},
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": img_url, "detail": "low"}},
                        {"type": "text", "text": f"Contexto: Post de {player_name}. Texto: {(item.get('text', '') or '')[:200]}"},
                    ]},
                ],
                temperature=0.1,
                max_tokens=300,
            )
            content = response.choices[0].message.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                content = content.rsplit("```", 1)[0]
            analysis = json.loads(content)
            if "error" not in analysis:
                item["image_analysis"] = analysis
                # Merge detected brands into item brands
                if analysis.get("brands"):
                    existing_brands = item.get("brands", [])
                    item["brands"] = list(set(existing_brands + analysis["brands"]))
                log.info(f"[analyzer] Image analysis: {analysis.get('context', '?')}, brands={analysis.get('brands', [])}")
        except Exception as e:
            log.warning(f"[analyzer] Image analysis error: {e}")

    return items


def extract_topics_and_brands(all_items):
    """Aggregate topics and brands from analyzed items."""
    topics = {}
    brands = {}
    for item in all_items:
        for t in item.get("topics") or []:
            topics[t] = topics.get(t, 0) + 1
        for b in item.get("brands") or []:
            brands[b] = brands.get(b, 0) + 1
    # Sort by count descending
    topics = dict(sorted(topics.items(), key=lambda x: -x[1]))
    brands = dict(sorted(brands.items(), key=lambda x: -x[1]))
    return topics, brands


# ── Intelligence / Early Detection ──

INTELLIGENCE_SYSTEM_PROMPT = """Eres un analista de inteligencia deportiva SENIOR para la agencia de representacion Niagara Sur.
Tu trabajo: analizar el digest mediatico de {player_name} ({club}) y producir un informe de inteligencia PRECISO y DIFERENCIADO.

CATEGORIAS DE RIESGO (usa exactamente estos valores):
- reputacion_personal: Vida privada, escandalos, relaciones, reality TV, redes sociales polemicas
- legal: Problemas legales, investigaciones, sanciones federativas
- rendimiento: Bajada rendimiento, criticas deportivas, malas estadisticas
- fichaje: Rumores traspaso, interes clubes, negociaciones contrato
- lesion: Lesiones, recuperacion, parte medico, estado fisico
- disciplina: Tarjetas, expulsiones, conflictos vestuario/entrenador
- comercial: Patrocinios, valor de marca, acuerdos comerciales
- imagen_publica: Relacion aficion, percepcion general, trending en redes

SEVERIDAD:
- critico: Escandalo viral activo, problema legal confirmado, lesion grave, polemica nacional (>10 items negativos sobre el tema)
- alto: Tendencia negativa clara con multiples fuentes (5-10 items), rumor fichaje con fuentes fiables, lesion moderada
- medio: Tema emergente (3-5 items), rumor sin confirmar, critica puntual en prensa importante
- bajo: Informativo sin riesgo, noticias positivas o neutras, actividad rutinaria

TENDENCIA: escalando (mas items recientes que antiguos), estable, declinando (menos items recientes)

CALIBRACION DE RIESGO GLOBAL (0-100):
- 0-20: Sin actividad relevante o todo positivo/neutro
- 21-40: Actividad normal, algun tema menor a vigilar
- 41-60: Temas activos que requieren atencion, mix positivo/negativo
- 61-80: Problemas claros, multiples narrativas negativas, riesgo reputacional real
- 81-100: Crisis activa, escandalo viral, accion inmediata necesaria

PONDERACION DE FUENTES (credibilidad 1-10):
- Tier 1 (9-10): Marca, AS, Relevo, El Pais, Gazzetta, BBC Sport, The Guardian, L'Equipe
- Tier 2 (7-8): Mundo Deportivo, El Mundo, Estadio Deportivo, BeSoccer, Transfermarkt, Sky Sports, Kicker
- Tier 3 (4-6): Twitter, YouTube, Telegram, Fichajes.net, blogs especializados
- Tier 4 (2-3): TikTok, Reddit, Instagram, foros generales
Una noticia en Marca (10) vale 5x mas que un comentario en Reddit (2). Pondera las narrativas segun la calidad de sus fuentes.

IMPORTANTE: NO pongas 35 por defecto. Calcula el riesgo REAL basado en:
- Proporcion de items negativos vs positivos, PONDERADOS por credibilidad de fuente
- Gravedad de los temas (polemica personal > rumor fichaje neutro)
- Volumen de cobertura (mas items = mas relevancia)
- Diversidad de fuentes (si lo cubren prensa + redes = mas serio)
- PESO de las fuentes: una noticia en Marca/AS vale mas que 10 tweets
{performance_context}
REGLAS:
1. Agrupa items del MISMO tema/historia en una narrativa (minimo 2 items para formar narrativa)
2. TODA narrativa debe incluir items especificos (P12, S45, etc.)
3. Detecta SENALES TEMPRANAS: patrones sutiles que podrian crecer
4. Las recomendaciones deben ser ACCIONABLES: "Preparar comunicado", "Contactar club", "Monitorizar 48h"
5. Si hay items sobre fichaje + rendimiento, evalua si son oportunidad o riesgo
6. Incluye narrativas POSITIVAS tambien (severidad "bajo"), no solo negativas
7. MULTI-IDIOMA: Los items pueden estar en ES, EN, IT, AR, FR, DE. Analiza en su idioma original, responde siempre en ESPANOL. Indica el idioma de las fuentes cuando sea relevante (ej: "Prensa italiana reporta...")
{previous_context}
Responde UNICAMENTE con JSON valido, sin texto extra:
{{"narrativas":[{{"titulo":"string corto","descripcion":"2-3 frases resumen","categoria":"reputacion_personal","severidad":"medio","tendencia":"estable","items":["P12","S45"],"fuentes":["prensa","twitter"],"recomendacion":"Accion concreta"}}],"senales_tempranas":[{{"descripcion":"string","categoria":"rendimiento","evidencia":["S78"],"probabilidad":"media","accion_sugerida":"string"}}],"riesgo_global":45,"resumen_inteligencia":"2-3 frases situacion general","recomendacion_principal":"Una frase accionable"}}"""


async def generate_intelligence_report(player_id, player_name, club, scan_log_id, stats=None, trends=None):
    """Second-pass GPT-4o analysis: group items into narrativas, assess risk, detect signals."""
    if not client:
        return None

    import db

    # First check if there's already an intelligence report - if so, use standard lookback
    # If no prior report exists, use all available items (wider window) for first analysis
    prev_intel = await db.get_last_intelligence_report(player_id)
    if prev_intel:
        lookback = (datetime.now() - timedelta(days=INTELLIGENCE_LOOKBACK_DAYS)).strftime("%Y-%m-%dT00:00:00")
    else:
        lookback = None  # No date filter - use all items for first intelligence report

    half = INTELLIGENCE_MAX_INPUT_ITEMS // 2

    press = await db.get_press(player_id, limit=half, date_from=lookback)
    social = await db.get_social(player_id, limit=half, date_from=lookback)
    posts = await db.get_player_posts_db(player_id, limit=50, date_from=lookback)

    total_items = len(press) + len(social) + len(posts)
    if total_items < 5:
        log.info(f"[intelligence] Skipping {player_name}: only {total_items} items")
        return None

    # Count sentiment distribution for better calibration
    neg_count = sum(1 for i in press + social if i.get('sentiment_label') == 'negativo')
    pos_count = sum(1 for i in press + social if i.get('sentiment_label') == 'positivo')
    total_analyzed = len(press) + len(social)

    # Build token-efficient digest: 1 line per item
    digest_lines = []
    for item in press:
        title = (item.get('title', '') or '')[:80]
        summary = (item.get('summary', '') or '').replace('\n', ' ')[:120]
        digest_lines.append(
            f"P{item['id']}|prensa|{item.get('source', '')}|{item.get('sentiment_label', 'neutro')}|{title}|{summary}"
        )
    for item in social:
        text = (item.get("text", "") or "").replace("\n", " ")[:80]
        digest_lines.append(
            f"S{item['id']}|{item.get('platform', '')}|{(item.get('author', '') or '')[:20]}|{item.get('sentiment_label', 'neutro')}|{text}"
        )
    for item in posts:
        text = (item.get("text", "") or "").replace("\n", " ")[:80]
        digest_lines.append(
            f"A{item['id']}|{item.get('platform', '')}|{item.get('sentiment_label', 'neutro')}|{text}"
        )

    # Add sentiment summary at the top of digest
    digest_header = f"RESUMEN: {total_items} items totales. Sentimiento: {pos_count} positivos, {neg_count} negativos, {total_analyzed - pos_count - neg_count} neutros."
    digest = digest_header + "\n" + "\n".join(digest_lines[:INTELLIGENCE_MAX_INPUT_ITEMS])

    # Build performance context
    performance_context = ""
    if stats or trends:
        perf_lines = []
        if stats:
            perf_lines.append(f"RENDIMIENTO DEPORTIVO (temporada actual): {stats.get('appearances', 0)} partidos, {stats.get('goals', 0)} goles, {stats.get('assists', 0)} asistencias, {stats.get('minutes', 0)} min, {stats.get('yellows', 0)} amarillas, {stats.get('reds', 0)} rojas")
        if trends:
            perf_lines.append(f"GOOGLE TRENDS (30 dias): interes medio={trends.get('average_interest', 0)}/100, pico={trends.get('peak_interest', 0)}/100, tendencia={'subiendo' if trends.get('trend_direction') == 'up' else 'bajando' if trends.get('trend_direction') == 'down' else 'estable'}")
        performance_context = "\n" + "\n".join(perf_lines) + "\n"

    # Build trend context from previous intelligence report (already fetched above)
    previous_context = ""
    if prev_intel and prev_intel.get("narrativas"):
        prev_narr = prev_intel["narrativas"][:5]
        summaries = [f"- {n['titulo']} ({n.get('categoria', '?')}, {n.get('severidad', '?')}, {n.get('tendencia', '?')})" for n in prev_narr]
        previous_context = f"\nCONTEXTO PREVIO (escaneo anterior, usa para detectar tendencias):\n" + "\n".join(summaries) + f"\nRiesgo global anterior: {prev_intel.get('risk_score', 'N/A')}/100\n"

    system = INTELLIGENCE_SYSTEM_PROMPT.format(
        player_name=player_name, club=club or "desconocido",
        previous_context=previous_context,
        performance_context=performance_context,
    )

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": digest},
            ],
            temperature=0.1,
            max_tokens=INTELLIGENCE_MAX_TOKENS,
        )

        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            content = content.rsplit("```", 1)[0]

        data = json.loads(content)
        data["tokens_used"] = response.usage.total_tokens if response.usage else 0
        log.info(f"[intelligence] {player_name}: risk={data.get('riesgo_global', '?')}/100, "
                 f"{len(data.get('narrativas', []))} narrativas, {data['tokens_used']} tokens")
        return data

    except json.JSONDecodeError as e:
        log.error(f"[intelligence] JSON parse error for {player_name}: {e}")
        log.error(f"[intelligence] Raw response: {content[:500]}")
        return None
    except Exception as e:
        log.error(f"[intelligence] Error for {player_name}: {e}", exc_info=True)
        return None
