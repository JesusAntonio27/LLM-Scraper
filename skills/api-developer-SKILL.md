# Skill: API Developer

## Rol
Eres el responsable de exponer el sistema al mundo exterior a través de los 4 endpoints definidos en el MVP. Tu trabajo es definir los contratos Pydantic exactos, conectar los endpoints con el pipeline, y asegurarte de que Swagger documente todo correctamente. No escribes lógica de negocio — delegas al pipeline y a los servicios.

---

## Archivos de tu responsabilidad

```
llm-scraper-api/
├── app/
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── extract.py      ← POST /extract + POST /extract/discover
│   │   └── utils.py        ← POST /preprocess + GET /health
│   └── models/
│       ├── __init__.py
│       ├── requests.py     ← Modelos Pydantic de entrada
│       └── responses.py    ← Modelos Pydantic de salida
```

---

## Los 4 endpoints del MVP

Solo estos. No agregues ninguno más.

| Método | Ruta | Propósito |
|---|---|---|
| `POST` | `/extract` | Core del sistema. URLs + schema → datos estructurados |
| `POST` | `/extract/discover` | Analiza un sitio nuevo y genera el schema óptimo |
| `POST` | `/preprocess` | Solo fetch + limpieza HTML, sin LLM. Para debug |
| `GET` | `/health` | Verifica conectividad con Oxylabs y Anthropic |

---

## Contratos de la API

### `POST /extract` — Request
```python
from pydantic import BaseModel, Field
from typing import Optional

class FetchOptions(BaseModel):
    render_js: bool = True
    geo_location: Optional[str] = None
    timeout: int = 30
    user_agent_type: str = "desktop"

class LLMOptions(BaseModel):
    model: str = "haiku"   # "haiku" | "sonnet"
    token_budget: int = 4000

class AlreadyScraped(BaseModel):
    url: str
    content_hash: Optional[str] = None  # Sin hash = skip nivel 1. Con hash = skip nivel 2 si no cambió

class ExtractRequest(BaseModel):
    urls: list[str] = Field(..., min_length=1)
    schema: Optional[dict] = None
    output_hint: Optional[str] = None
    already_scraped: list[AlreadyScraped] = []
    fetch_options: FetchOptions = FetchOptions()
    llm_options: LLMOptions = LLMOptions()
    include_csv: bool = False
```

### `POST /extract` — Response
```python
class URLMeta(BaseModel):
    tokens_input: int = 0
    tokens_output: int = 0
    model_used: Optional[str] = None
    cost_usd: float = 0.0
    fetch_ms: Optional[int] = None
    preprocess_ms: Optional[int] = None
    llm_ms: Optional[int] = None

class URLResult(BaseModel):
    url: str
    status: str   # "extracted" | "skipped" | "failed"
    content_hash: Optional[str] = None
    data: Optional[dict] = None
    meta: URLMeta

class OutputBlock(BaseModel):
    records: list[dict]
    csv: Optional[str] = None
    schema_used: Optional[dict] = None

class Summary(BaseModel):
    total: int
    extracted: int
    skipped: int
    failed: int
    total_tokens: int
    total_cost_usd: float
    total_ms: int

class ExtractResponse(BaseModel):
    results: list[URLResult]
    output: OutputBlock
    summary: Summary
```

### `POST /extract/discover` — Request y Response
```python
class DiscoverRequest(BaseModel):
    url: str
    hint: Optional[str] = None
    fetch_options: FetchOptions = FetchOptions()

class DiscoverResponse(BaseModel):
    domain: str
    suggested_schema: dict
    suggested_instructions: Optional[str] = None
    confidence: Optional[float] = None
    notes: Optional[str] = None
    meta: URLMeta
```

### `POST /preprocess` — Request y Response
```python
class PreprocessRequest(BaseModel):
    url: str
    fetch_options: FetchOptions = FetchOptions()

class PreprocessResponse(BaseModel):
    markdown: str
    content_hash: str
    original_size_kb: float
    processed_size_kb: float
    estimated_tokens: int
    fetch_ms: int
```

### `GET /health` — Response
```python
class HealthResponse(BaseModel):
    status: str           # "ok" | "degraded"
    oxylabs: str          # "ok" | "error: <mensaje>"
    anthropic: str        # "ok" | "error: <mensaje>"
    timestamp: str        # ISO 8601
```

---

## Implementación de los routers

### `routers/extract.py`
```python
from fastapi import APIRouter
from app.models.requests import ExtractRequest, DiscoverRequest
from app.models.responses import ExtractResponse, DiscoverResponse
from app.services import pipeline

router = APIRouter()

@router.post("/extract", response_model=ExtractResponse)
async def extract(request: ExtractRequest):
    return await pipeline.run(request.model_dump())

@router.post("/extract/discover", response_model=DiscoverResponse)
async def discover(request: DiscoverRequest):
    return await pipeline.run_discover(request.model_dump())
```

### `routers/utils.py`
```python
from fastapi import APIRouter
from datetime import datetime, timezone
from app.models.requests import PreprocessRequest
from app.models.responses import PreprocessResponse, HealthResponse
from app.services.oxylabs import OxylabsFetcher
from app.services.preprocessor import HtmlPreprocessor

router = APIRouter()

@router.post("/preprocess", response_model=PreprocessResponse)
async def preprocess(request: PreprocessRequest):
    fetcher = OxylabsFetcher()
    preprocessor = HtmlPreprocessor()
    fetch_result = await fetcher.fetch(url=request.url, **request.fetch_options.model_dump())
    if fetch_result["status"] == "failed":
        # Retornar error descriptivo sin lanzar 500
        return PreprocessResponse(markdown="", content_hash="", ...)
    pre_result = preprocessor.process(html=fetch_result["html"])
    return PreprocessResponse(fetch_ms=fetch_result["fetch_ms"], **pre_result)

@router.get("/health", response_model=HealthResponse)
async def health():
    # Verificar Oxylabs y Anthropic con llamadas reales mínimas
    ...
```

---

## Buenas prácticas

### Pydantic
- Usa `Optional[X] = None` para campos que el cliente puede omitir. Nunca uses `Optional[X]` sin valor por default.
- Usa `Field(..., min_length=1)` en `urls` para evitar requests vacíos.
- Usa `model_dump()` para pasar el request al pipeline — no pases el objeto Pydantic directamente a los servicios.

### Documentación en Swagger
- Agrega `description` a los campos Pydantic que no sean obvios:
```python
output_hint: Optional[str] = Field(
    None,
    description="Describe en lenguaje natural qué tipo de datos estás extrayendo. Ej: 'catálogo de productos de farmacia'"
)
```
- Agrega `summary` y `description` a cada endpoint en el decorador:
```python
@router.post("/extract", response_model=ExtractResponse,
             summary="Extraer datos estructurados de URLs",
             description="Recibe URLs + schema y retorna JSON estructurado con los datos extraídos.")
```

### Health check
- El `/health` debe hacer una llamada real pero mínima a Oxylabs y a Anthropic (no solo un ping de red).
- El timeout del health check debe ser de 5 segundos máximo — no bloquear.
- Si cualquiera de los dos falla, el status es `"degraded"`, no `"ok"`.

### Registro de routers en `main.py`
```python
from app.routers import extract, utils

app.include_router(extract.router)
app.include_router(utils.router)
```

---

## Lo que NO debes hacer

- ❌ No pongas lógica de negocio en los routers — solo validación de entrada (Pydantic) y delegación al pipeline.
- ❌ No agregues endpoints que no estén en el MVP (`/batch`, `/normalize`, `/webhooks`, etc.).
- ❌ No uses `dict` como tipo de retorno en los routers — siempre usa `response_model` para que Swagger funcione.
- ❌ No conviertas errores del pipeline en HTTP 500 genérico — los errores de URLs individuales van dentro del `results` con `status: "failed"`, no como excepciones HTTP.
- ❌ No hagas llamadas a servicios externos directamente en los routers — solo a través de servicios en `app/services/`.

---

## Criterio de éxito de este rol

El trabajo está terminado cuando:
1. Los 4 endpoints responden en Swagger (`/docs`).
2. `POST /extract` con una URL real retorna un `ExtractResponse` válido.
3. `POST /extract/discover` retorna un `suggested_schema` válido para un dominio nuevo.
4. `POST /preprocess` retorna el Markdown limpio sin invocar al LLM.
5. `GET /health` retorna `"ok"` cuando ambas APIs están disponibles, `"degraded"` si alguna falla.
6. Todos los campos opcionales tienen valores por default correctos (no `null` donde el MVP define un default).