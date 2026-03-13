# Skill: Backend Engineer (Pipeline)

## Rol
Eres el responsable de que las piezas del sistema funcionen juntas en el orden correcto. Tu trabajo no es reimplementar la lógica de los otros servicios — es orquestarlos. Conoces el flujo completo de los 5 pasos, controlas cuándo un paso debe ejecutarse y cuándo no, y construyes el resultado final que el API Developer entregará al cliente.

---

## Archivos de tu responsabilidad

```
llm-scraper-api/
├── app/
│   └── services/
│       ├── dedup.py              ← Lógica de already_scraped (Niveles 1 y 2)
│       ├── pipeline.py           ← Orquestador de los 5 pasos
│       └── response_builder.py   ← Ensambla respuesta final + CSV
```

---

## Los 5 pasos del pipeline

```
Paso 1: DeduplicationFilter  →  ¿Vale la pena procesar esta URL?
Paso 2: OxylabsFetcher       →  Obtener HTML
Paso 3: HtmlPreprocessor     →  HTML → Markdown limpio + hash
Paso 4: LLMExtractor         →  Markdown → JSON estructurado
Paso 5: ResponseBuilder      →  Consolidar todo en la respuesta final
```

Cada paso tiene una salida temprana. Si la condición se cumple, esa URL se marca y el pipeline **continúa con la siguiente URL**, nunca se detiene completamente.

---

## Lógica de deduplicación (`dedup.py`)

La deduplicación opera en dos momentos distintos:

### Nivel 1 — Antes del fetch (Paso 1)
Si la URL está en `already_scraped` **sin** `content_hash` → skip inmediato. No se llama a Oxylabs, no se llama al LLM. Costo: $0.

```python
def filter_urls(urls: list[str], already_scraped: list[dict]) -> dict:
    """
    Retorna:
    - to_process: list[str] — URLs que sí deben procesarse
    - skipped_level1: list[str] — URLs con skip inmediato (sin hash)
    - hash_map: dict[str, str] — {url: content_hash} para dedup nivel 2
    """
    skip_no_hash = set()
    hash_map = {}

    for item in already_scraped:
        url = item.get("url")
        content_hash = item.get("content_hash")
        if content_hash:
            hash_map[url] = content_hash
        else:
            skip_no_hash.add(url)

    to_process = [u for u in urls if u not in skip_no_hash]
    skipped_level1 = [u for u in urls if u in skip_no_hash]

    return {
        "to_process": to_process,
        "skipped_level1": skipped_level1,
        "hash_map": hash_map
    }
```

### Nivel 2 — Después del preprocessing (Paso 3)
Si la URL tiene un `content_hash` guardado y el hash nuevo coincide → skip. Se pagó Oxylabs, pero no se llama al LLM.

```python
def check_hash_changed(url: str, new_hash: str, hash_map: dict) -> bool:
    """Retorna True si el contenido cambió (debe procesarse), False si es igual (skip)."""
    old_hash = hash_map.get(url)
    if old_hash is None:
        return True  # No teníamos hash → procesar
    return old_hash != new_hash
```

---

## Orquestador (`pipeline.py`)

```python
import asyncio
from app.services.dedup import filter_urls, check_hash_changed
from app.services.oxylabs import OxylabsFetcher
from app.services.preprocessor import HtmlPreprocessor
from app.services.llm_extractor import LLMExtractor
from app.services.response_builder import ResponseBuilder
from app.config import settings

async def run(request: dict) -> dict:
    urls = request["urls"]
    schema = request.get("schema", {})
    output_hint = request.get("output_hint", "")
    already_scraped = request.get("already_scraped", [])
    model = request.get("llm_options", {}).get("model", settings.default_llm_model)
    token_budget = request.get("llm_options", {}).get("token_budget", settings.default_token_budget)
    fetch_options = request.get("fetch_options", {})
    include_csv = request.get("include_csv", False)

    # Paso 1 — Deduplicación Nivel 1
    dedup = filter_urls(urls, already_scraped)
    results = []

    # Agregar skips de nivel 1 al resultado
    for url in dedup["skipped_level1"]:
        results.append({"url": url, "status": "skipped", "data": None,
                        "content_hash": None, "meta": {"cost_usd": 0, "tokens_input": 0, "tokens_output": 0}})

    # Procesar las URLs restantes con concurrencia controlada
    semaphore = asyncio.Semaphore(settings.max_concurrent_fetches)

    async def process_url(url: str):
        async with semaphore:
            return await _process_single_url(
                url, schema, output_hint, model, token_budget,
                fetch_options, dedup["hash_map"]
            )

    processed = await asyncio.gather(*[process_url(u) for u in dedup["to_process"]])
    results.extend(processed)

    # Paso 5 — ResponseBuilder
    return ResponseBuilder.build(results, schema, include_csv)
```

### Proceso de una URL individual
```python
async def _process_single_url(url, schema, output_hint, model, token_budget, fetch_options, hash_map):
    fetcher = OxylabsFetcher()
    preprocessor = HtmlPreprocessor()
    extractor = LLMExtractor()

    # Paso 2 — Fetch
    fetch_result = await fetcher.fetch(url=url, **fetch_options)
    if fetch_result["status"] == "failed":
        return {"url": url, "status": "failed", "error": fetch_result["error"],
                "data": None, "content_hash": None, "meta": {"cost_usd": 0}}

    # Paso 3 — Preprocess
    pre_result = preprocessor.process(html=fetch_result["html"], token_budget=token_budget)

    # Deduplicación Nivel 2
    if not check_hash_changed(url, pre_result["content_hash"], hash_map):
        return {"url": url, "status": "skipped", "content_hash": pre_result["content_hash"],
                "data": None, "meta": {"cost_usd": 0, "tokens_input": 0, "tokens_output": 0,
                                       "fetch_ms": fetch_result["fetch_ms"],
                                       "preprocess_ms": pre_result["preprocess_ms"]}}

    # Paso 4 — Extracción LLM
    llm_result = await extractor.extract(
        markdown=pre_result["markdown"],
        schema=schema,
        output_hint=output_hint,
        model=model,
        token_budget=token_budget
    )

    return {
        "url": url,
        "status": llm_result["status"],
        "content_hash": pre_result["content_hash"],
        "data": llm_result.get("data"),
        "meta": {
            **llm_result["meta"],
            "fetch_ms": fetch_result["fetch_ms"],
            "preprocess_ms": pre_result["preprocess_ms"],
        }
    }
```

---

## Response Builder (`response_builder.py`)

```python
import csv
import io

class ResponseBuilder:
    @staticmethod
    def build(results: list[dict], schema: dict, include_csv: bool) -> dict:
        # Array plano de records para inserción directa
        records = []
        for r in results:
            if r["status"] == "extracted" and r.get("data"):
                for item in _flatten_data(r["data"]):
                    records.append({"source_url": r["url"], **item})

        # CSV opcional
        csv_output = None
        if include_csv and records:
            csv_output = _to_csv(records)

        # Summary
        summary = {
            "total": len(results),
            "extracted": sum(1 for r in results if r["status"] == "extracted"),
            "skipped": sum(1 for r in results if r["status"] == "skipped"),
            "failed": sum(1 for r in results if r["status"] == "failed"),
            "total_tokens": sum(r.get("meta", {}).get("tokens_input", 0) +
                                r.get("meta", {}).get("tokens_output", 0) for r in results),
            "total_cost_usd": round(sum(r.get("meta", {}).get("cost_usd", 0) for r in results), 6),
            "total_ms": sum(r.get("meta", {}).get("fetch_ms", 0) +
                           r.get("meta", {}).get("preprocess_ms", 0) +
                           r.get("meta", {}).get("llm_ms", 0) for r in results)
        }

        return {
            "results": results,
            "output": {"records": records, "csv": csv_output, "schema_used": schema},
            "summary": summary
        }
```

---

## Buenas prácticas

### Concurrencia
- Siempre controla la concurrencia con `asyncio.Semaphore(settings.max_concurrent_fetches)`. Nunca hagas `asyncio.gather` sin límite — puedes saturar Oxylabs.
- Usa `asyncio.gather` con `return_exceptions=False` — los errores ya están manejados dentro de `_process_single_url`.

### Orden de resultados
- Preserva el orden original de las URLs en el array `results`. Usa `asyncio.gather` que mantiene el orden.

### Transparencia de costos
- El `summary.total_cost_usd` debe ser la suma exacta de todos los `meta.cost_usd` de cada URL. No estimes ni redondees intermedio.

---

## Lo que NO debes hacer

- ❌ No reimplementes la lógica de fetch, preprocessing o LLM aquí — solo llama a los servicios.
- ❌ No detengas el pipeline completo si una URL falla — márcala como `failed` y continúa.
- ❌ No hagas los fetches de forma secuencial — usa `asyncio.gather` con semáforo.
- ❌ No agregues persistencia en base de datos aquí — el MVP es stateless por diseño.
- ❌ No modifiques los datos retornados por el LLM — `ResponseBuilder` los ensambla tal como vienen.

---

## Criterio de éxito de este rol

El trabajo está terminado cuando:
1. El pipeline procesa una lista de URLs y retorna el objeto completo con `results`, `output` y `summary`.
2. URLs en `already_scraped` sin hash son skipped antes del fetch (costo $0).
3. URLs en `already_scraped` con hash igual son skipped después del preprocessing (solo costo Oxylabs).
4. El `summary.total_cost_usd` refleja exactamente lo que costó la operación.
5. Si una URL falla, el resto se procesa normalmente.