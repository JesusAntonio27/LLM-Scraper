from fastapi import APIRouter
from app.models.requests import ExtractRequest, DiscoverRequest
from app.models.responses import ExtractResponse, DiscoverResponse
from app.services import pipeline

router = APIRouter()

@router.post("/extract", response_model=ExtractResponse,
             summary="Extraer datos estructurados de URLs",
             description="Recibe URLs + schema y retorna JSON estructurado. Soporta deduplicación por content_hash.")
async def extract(request: ExtractRequest):
    return await pipeline.run(request.model_dump())

@router.post("/extract/discover", response_model=DiscoverResponse,
             summary="Generar schema óptimo para un dominio nuevo",
             description="Analiza una URL de muestra y genera el schema de extracción. Llamar UNA sola vez por dominio. Siempre usa claude-sonnet-4-6.")
async def discover(request: DiscoverRequest):
    return await pipeline.run_discover(request.model_dump())

# NOTA: Este router debe registrarse en main.py con:
# from app.routers import extract
# app.include_router(extract.router)
