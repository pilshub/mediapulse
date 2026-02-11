import json
from openai import AsyncOpenAI
from config import OPENAI_API_KEY

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

REGLAS DE RELEVANCIA:
- Si el item menciona otro club diferente a {club} y no menciona a {player_name} explicitamente, es NOT relevant
- Jugadores con nombre similar pero de otro equipo = NOT relevant
- En caso de duda, marca relevant: true

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
