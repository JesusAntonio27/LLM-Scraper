import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter
from app.models.requests import PreprocessRequest
from app.models.responses import PreprocessResponse, HealthResponse
from app.services.oxylabs import OxylabsFetcher
from app.services.preprocessor import HtmlPreprocessor
from app.config import settings
from anthropic import AsyncAnthropic

router = APIRouter()

@router.post("/preprocess", response_model=PreprocessResponse,
             summary="Debug de limpieza HTML",
             description="Fetch + limpieza HTML sin invocar al LLM. Útil para diagnosticar extracción y ver consumo de tokens.")
async def preprocess(request: PreprocessRequest):
    fetcher = OxylabsFetcher()
    preprocessor = HtmlPreprocessor()
    
    fetch_result = await fetcher.fetch(url=request.url, **request.fetch_options.model_dump())
    
    if fetch_result["status"] == "failed":
        return PreprocessResponse(
            markdown="",
            content_hash="",
            original_size_kb=0.0,
            processed_size_kb=0.0,
            estimated_tokens=0,
            fetch_ms=fetch_result.get("fetch_ms", 0)
        )
        
    pre_result = preprocessor.process(html=fetch_result["html"], token_budget=4000)
    return PreprocessResponse(fetch_ms=fetch_result["fetch_ms"], **pre_result)

@router.get("/health", response_model=HealthResponse,
            summary="Verificación del sistema",
            description="Verifica conectividad con Oxylabs y Anthropic antes de scraping.")
async def health():
    async def check_oxylabs():
        try:
            fetcher = OxylabsFetcher()
            res = await fetcher.fetch(url="https://example.com", render_js=False, timeout=5)
            if res["status"] == "ok":
                return "ok"
            else:
                return f"error: {res.get('error', 'unknown error')}"
        except Exception as e:
            return f"error: {str(e)}"
            
    async def check_anthropic():
        try:
            client = AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=5.0)
            await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}]
            )
            return "ok"
        except Exception as e:
            return f"error: {str(e)}"

    oxy_status, ant_status = await asyncio.gather(check_oxylabs(), check_anthropic())
    
    # Evaluar estado general
    status = "ok" if oxy_status == "ok" and ant_status == "ok" else "degraded"
    
    return HealthResponse(
        status=status,
        oxylabs=oxy_status,
        anthropic=ant_status,
        timestamp=datetime.now(timezone.utc).isoformat()
    )
