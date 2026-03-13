from pydantic import BaseModel, Field
from typing import Optional

class FetchOptions(BaseModel):
    render_js: bool = True
    geo_location: Optional[str] = None
    timeout: int = 30
    user_agent_type: str = "desktop"
    browser_instructions: Optional[list[dict]] = None

class LLMOptions(BaseModel):
    model: str = "haiku"
    token_budget: int = 4000
    agentic: bool = False

class AlreadyScraped(BaseModel):
    url: str
    content_hash: Optional[str] = None
    # Sin hash = skip nivel 1. Con hash = skip nivel 2 si no cambió.

class ExtractRequest(BaseModel):
    urls: list[str] = Field(..., min_length=1,
        description="Lista de URLs a procesar. Mínimo 1.")
    schema: Optional[dict] = Field(None,
        description="JSON Schema esperado. Si se omite, el LLM infiere la estructura.")
    output_hint: Optional[str] = Field(None,
        description="Contexto en lenguaje natural. Ej: 'catálogo de productos de farmacia'")
    already_scraped: list[AlreadyScraped] = []
    fetch_options: FetchOptions = FetchOptions()
    llm_options: LLMOptions = LLMOptions()
    include_csv: bool = False

class DiscoverRequest(BaseModel):
    url: str = Field(..., description="URL de muestra del dominio a analizar.")
    hint: Optional[str] = Field(None,
        description="Descripción del contenido. Ej: 'directorio de tiendas de plaza comercial'")
    fetch_options: FetchOptions = FetchOptions()

class PreprocessRequest(BaseModel):
    url: str
    fetch_options: FetchOptions = FetchOptions()
