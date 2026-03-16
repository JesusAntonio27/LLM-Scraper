import asyncio
import urllib.parse
from app.config import settings
from app.services.dedup import filter_urls, check_hash_changed
from app.services.oxylabs import OxylabsFetcher
from app.services.preprocessor import HtmlPreprocessor
from app.services.llm_extractor import LLMExtractor
from app.services.response_builder import ResponseBuilder

async def run(request: dict) -> dict:
    """
    Orchestrates the 5 steps in order for POST /extract.
    """
    # Extract fields with defaults
    urls = request.get("urls", [])
    # FIX F: Pydantic serializa Optional[dict] como None cuando no se envía —
    # request.get("schema", {}) devuelve None igual, causando AttributeError en _validates_schema
    schema = request.get("schema") or {}
    output_hint = request.get("output_hint", "")
    already_scraped = request.get("already_scraped", [])
    
    llm_options = request.get("llm_options", {})
    model = llm_options.get("model", settings.default_llm_model)
    token_budget = llm_options.get("token_budget", settings.default_token_budget)
    force_agentic = llm_options.get("agentic", False)
    
    fetch_options = request.get("fetch_options", {})
    include_csv = request.get("include_csv", False)
    
    # ── PASO 1: Deduplicación Nivel 1 ──────────────────────────────────────
    dedup_res = filter_urls(urls, already_scraped)
    to_process = dedup_res["to_process"]
    skipped_level1 = dedup_res["skipped_level1"]
    hash_map = dedup_res["hash_map"]
    
    # Pre-allocate results array to preserve order
    results_map = {}
    
    # Populate skipped urls
    for url in skipped_level1:
        results_map[url] = {
            "url": url,
            "status": "skipped",
            "content_hash": None,
            "data": None,
            "meta": {"cost_usd": 0, "tokens_input": 0, "tokens_output": 0}
        }

    # ── PASOS 2-4: Procesar URLs con concurrencia controlada ───────────────
    semaphore = asyncio.Semaphore(settings.max_concurrent_fetches)
    
    async def process_with_semaphore(url):
        async with semaphore:
            return await _process_single_url(
                url=url,
                schema=schema,
                output_hint=output_hint,
                model=model,
                token_budget=token_budget,
                fetch_options=fetch_options,
                hash_map=hash_map,
                force_agentic=force_agentic
            )
            
    # Process all needed URLs
    tasks = [process_with_semaphore(url) for url in to_process]
    processed_results = await asyncio.gather(*tasks)
    
    # Store processed results
    for res in processed_results:
        results_map[res["url"]] = res
        
    # Build final array preserving original order
    final_results = [results_map[url] for url in urls if url in results_map]
    
    # ── PASO 5: ResponseBuilder ────────────────────────────────────────────
    return ResponseBuilder.build(final_results, schema, include_csv)


async def _process_single_url(url: str, schema: dict, output_hint: str, model: str, 
                             token_budget: int, fetch_options: dict, hash_map: dict,
                             force_agentic: bool = False) -> dict:
    """
    Processes a single URL through steps 2, 3, and 4.
    """
    # ── Paso 2: Fetch ──
    fetcher = OxylabsFetcher()
    fetch_result = await fetcher.fetch(url, **fetch_options)

    if fetch_result.get("status") == "failed":
        return {
            "url": url,
            "status": "failed",
            "error": fetch_result.get("error"),
            "data": None,
            "content_hash": None,
            "meta": {"cost_usd": 0, "fetch_ms": fetch_result.get("fetch_ms", 0)}
        }

    # ── Paso 3: Preprocess ──
    preprocessor = HtmlPreprocessor()
    pre_result = preprocessor.process(fetch_result["html"], token_budget)
    
    # Deduplicación Nivel 2
    content_hash = pre_result["content_hash"]
    if not check_hash_changed(url, content_hash, hash_map):
        return {
            "url": url,
            "status": "skipped",
            "content_hash": content_hash,
            "data": None,
            "meta": {
                "cost_usd": 0, "tokens_input": 0, "tokens_output": 0,
                "fetch_ms": fetch_result.get("fetch_ms", 0),
                "preprocess_ms": pre_result.get("preprocess_ms", 0)
            }
        }
        
    # ── Paso 4: Extracción LLM ──
    extractor = LLMExtractor()
    
    # FIX A: auto_agentic anterior era casi-nunca-verdadero porque raw_html solo llega
    # cuando trafilatura Y structural fallan — Oxylabs siempre renderiza algo (menú,
    # footer) que pasa el umbral de 10 líneas. El trigger real es:
    # 1. La estrategia terminó en raw_html (sin contenido extraíble), O
    # 2. El schema pide listas PERO el markdown extraído es demasiado delgado (<300 tokens)
    #    — esto cubre el caso: "tengo texto de navegación pero no tengo los datos reales".
    def _schema_expects_list(s: dict) -> bool:
        if not s:
            return False
        # JSON Schema estándar: properties con type=array
        props = s.get("properties", {})
        if any(isinstance(v, dict) and v.get("type") == "array" for v in props.values()):
            return True
        # Schema simple (dict plano): algún valor es una lista
        return any(isinstance(v, list) for v in s.values())

    content_tokens = pre_result.get("estimated_tokens") or 0
    auto_agentic = (
        pre_result.get("strategy_used") == "raw_html" or
        (_schema_expects_list(schema) and content_tokens < 300)
    )
    
    # BUG 7 FIX: path único por request para evitar race condition cuando hay concurrencia
    import uuid
    context_file = f"navigation_context_{uuid.uuid4().hex[:8]}.md"

    if force_agentic or auto_agentic:
        # Modo agentic — Claude navega con tools
        llm_result = await extractor.extract_agentic(
            url=url,
            markdown=pre_result["markdown"],
            schema=schema,
            output_hint=output_hint,
            fetch_options=fetch_options,
            context_file=context_file
        )
    else:
        # Modo normal — extracción directa
        llm_result = await extractor.extract(
            markdown=pre_result["markdown"],
            schema=schema,
            output_hint=output_hint,
            model=model,
            token_budget=token_budget
        )
    
    # Combinar metadata
    final_meta = {**llm_result.get("meta", {})}
    final_meta["fetch_ms"] = fetch_result.get("fetch_ms", 0)
    final_meta["preprocess_ms"] = pre_result.get("preprocess_ms", 0)
    
    return {
        "url": url,
        "status": llm_result.get("status", "failed"),
        "content_hash": content_hash,
        "data": llm_result.get("data"),
        "meta": final_meta
    }


async def run_discover(request: dict) -> dict:
    """
    Simplified flow for POST /extract/discover.
    """
    url = request.get("url", "")
    # BUG 4 FIX: DiscoverRequest serializa el campo como "hint", no "output_hint"
    output_hint = request.get("hint", "") or request.get("output_hint", "")
    fetch_options = request.get("fetch_options", {})
    
    # 1. Fetch
    fetcher = OxylabsFetcher()
    fetch_result = await fetcher.fetch(url, **fetch_options)
    
    if fetch_result.get("status") == "failed":
        return {
            "domain": urllib.parse.urlparse(url).netloc,
            "suggested_schema": {},
            "suggested_instructions": None,
            "confidence": None,
            "notes": None,
            "meta": {"cost_usd": 0, "fetch_ms": fetch_result.get("fetch_ms", 0)}
        }
        
    # 2. Preprocess
    preprocessor = HtmlPreprocessor()
    pre_result = preprocessor.process(fetch_result["html"], token_budget=4000) # Ensure budget
    
    # 3. LLM (Force sonnet)
    extractor = LLMExtractor()
    
    discover_hint = (
        "TASK: Analyze this markdown and generate a comprehensive JSON schema to extract all structured data. "
        "Also provide extraction instructions and note any edge cases. "
        f"USER HINT: {output_hint}"
    )
    
    llm_result = await extractor.extract(
        markdown=pre_result["markdown"],
        schema={}, # No initial schema
        output_hint=discover_hint,
        model="sonnet",  # BUG 3 FIX: usar la key del MODEL_MAP, no el ID completo
        token_budget=4000
    )
    
    # 4. Format Output
    return {
        "domain": urllib.parse.urlparse(url).netloc,
        "suggested_schema": llm_result.get("data", {}),
        "suggested_instructions": "Ver la salida en suggested_schema. " + output_hint,
        "confidence": 0.9 if llm_result.get("status") == "extracted" else 0.0,
        "notes": llm_result.get("raw_response", None) if llm_result.get("status") == "failed" else None,
        "meta": {
            **llm_result.get("meta", {}),
            "fetch_ms": fetch_result.get("fetch_ms", 0),
            "preprocess_ms": pre_result.get("preprocess_ms", 0)
        }
    }
