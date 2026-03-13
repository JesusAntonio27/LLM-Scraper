# PROGRESS.md — LLM Scraper API MVP

---

## 1. ESTADO GENERAL

**Día 1 — Bloque 1 completado ✅ (tareas 1–7 aprobadas)**  
**Día 1 — Bloque 2 completado ✅ (tareas 8–10 aprobadas y verificadas)**
**Día 1 — Bloque 3 completado ✅ (tareas 11–17 aprobadas)**
**Día 2 — Bloque 4 completado ✅ (tareas 18–23 aprobadas)**

**Día 3 — Bloques 5 y 6 completados ✅ (tareas 24–33 aprobadas)**

**Día 4 — Bloque 7 pendiente**

---

## 2. DECISIONES DE DISEÑO ACTIVAS

_Sin entradas aún — se llena conforme avanza el proyecto._

---

## 3. ARCHIVOS COMPLETADOS

| Archivo | Estado | Iter. | Notas |
|---|---|---|---|
| `.gitignore` | ✅ Completo | 1 | Incluye `.env`, `__pycache__`, `.pytest_cache`, `*.pyc`, `.DS_Store` |
| `.env.example` | ✅ Completo | 1 | 6 variables con valores de ejemplo falsos |
| `.env` | ✅ Completo | 1 | Credenciales reales cargadas — nunca commitear |
| `requirements.txt` | ✅ Completo | 1 | fastapi, uvicorn, httpx, pydantic-settings, anthropic, trafilatura, beautifulsoup4, markdownify, pytest, pytest-asyncio |
| `app/__init__.py` | ⏳ Pendiente | | No creado aún |
| `app/config.py` | ✅ Completo | 1 | Pydantic v2 `model_config`, falla en startup si faltan vars requeridas |
| `app/main.py` | ✅ Completo | 1 | CORS localhost, logging middleware, error handler global sin traceback, `/health` placeholder |
| `app/routers/__init__.py` | ✅ Completo | 1 | Archivo vacío |
| `app/routers/extract.py` | ✅ Completo | 1 | POST /extract + POST /extract/discover |
| `app/routers/utils.py` | ✅ Completo | 1 | POST /preprocess + GET /health |
| `app/services/__init__.py` | ✅ Completo | 1 | Archivo vacío |
| `app/services/pipeline.py` | ✅ Completo | 1 | Orquestador de 5 pasos |
| `app/services/dedup.py` | ✅ Completo | 1 | DeduplicationFilter |
| `app/services/oxylabs.py` | ✅ Completo | 1 | OxylabsFetcher: fetch ok/failed, timeout+5, sin hardcoding, sin modificar HTML |
| `app/services/preprocessor.py` | ✅ Completo | 1 | HtmlPreprocessor (trafilatura + markdown + hash) |
| `app/services/llm_extractor.py` | ✅ Completo | 1 | LLMExtractor (Claude + validación) |
| `app/services/response_builder.py` | ✅ Completo | 1 | ResponseBuilder (ensambla respuesta + CSV) |
| `app/models/__init__.py` | ✅ Completo | 1 | Archivo vacío |
| `app/models/requests.py` | ✅ Completo | 1 | Pydantic: ExtractRequest, DiscoverRequest, etc. |
| `app/models/responses.py` | ✅ Completo | 1 | Pydantic: ExtractResponse, URLResult, etc. |
| `tests/__init__.py` | ✅ Completo | 1 | Archivo vacío |
| `tests/test_oxylabs.py` | ✅ Completo | 1 | Test real + 3 tests unitarios (timeout, 403, ConnectError) con respx mock |
| `tests/test_preprocessor.py` | ✅ Completo | 1 | Test con HTML real |
| `tests/test_llm_extractor.py` | ✅ Completo | 1 | Test con Markdown real |
| `tests/test_integration.py` | ⏳ Pendiente | | Tests end-to-end de los 4 endpoints |
| `Dockerfile` | ✅ Completo | 1 | python:3.12-slim, COPY reqs primero, uvicorn CMD |
| `docker-compose.yml` | ✅ Completo | 1 | Servicio `api`, puerto 8000, env_file .env, volumen local |
| `README.md` | ⏳ Pendiente | | Guía de setup + uso + costos |

---

## 4. TAREAS COMPLETADAS

### Bloque 1 — DevOps / Infra (tareas 1–7)

| # | Tarea | Estado |
|---|---|---|
| 1 | Crear estructura de carpetas del proyecto | ✅ |
| 2 | Crear archivos `__init__.py` vacíos | ✅ |
| 3 | Crear `.gitignore` | ✅ |
| 4 | Crear `.env.example` + `requirements.txt` | ✅ |
| 5 | Crear `app/config.py` (Pydantic BaseSettings) | ✅ |
| 6 | Crear `app/main.py` (FastAPI app + CORS + middleware + error handler) | ✅ |
| 7 | Crear `Dockerfile` + `docker-compose.yml` | ✅ |

### Bloque 2 — Integration Engineer (tareas 8–10)

| # | Tarea | Estado |
|---|---|---|
| 8 | Implementar `OxylabsFetcher` en `services/oxylabs.py` | ✅ |
| 9 | Implementar manejo de errores (timeout, HTTP 4xx/5xx, red) | ✅ |
| 10 | Crear `tests/test_oxylabs.py` (test real contra sitio de plaza) | ✅ |

### Bloque 3 — Data Engineer (tareas 11–17)

| # | Tarea | Estado |
|---|---|---|
| 11 | Implementar extracción con Trafilatura (paso 1) | ✅ |
| 12 | Implementar fallback con BeautifulSoup (paso 2) | ✅ |
| 13 | Implementar conversión a Markdown con markdownify (paso 3) | ✅ |
| 14 | Implementar `smart_truncate` con respeto al token_budget (paso 4) | ✅ |
| 15 | Implementar hash SHA-256 sobre Markdown final (paso 5) | ✅ |
| 16 | Integrar `HtmlPreprocessor.process()` completo | ✅ |
| 17 | Crear `tests/test_preprocessor.py` (test con HTML real) | ✅ |

### Bloque 4 — LLM Engineer (tareas 18–23)

| # | Tarea | Estado |
|---|---|---|
| 18 | Implementar `MODEL_MAP` y selección de modelo | ✅ |
| 19 | Implementar diseño de prompt (system + user + retry) | ✅ |
| 20 | Implementar `_try_parse_json` y `_validates_schema` | ✅ |
| 21 | Implementar `extract()` con lógica de reintento (máximo 1) | ✅ |
| 22 | Implementar `_calculate_cost` con tarifas reales | ✅ |
| 23 | Crear `tests/test_llm_extractor.py` (test con Markdown real) | ✅ |

### Bloque 5 — Backend Engineer (tareas 24–27)

| # | Tarea | Estado |
|---|---|---|
| 24 | Implementar `DeduplicationFilter` en `services/dedup.py` | ✅ |
| 25 | Implementar `pipeline.run()` orquestador de 5 pasos | ✅ |
| 26 | Implementar `ResponseBuilder` en `services/response_builder.py` | ✅ |
| 27 | Implementar concurrencia con `Semaphore` en pipeline | ✅ |

### Bloque 6 — API Developer (tareas 28–33)

| # | Tarea | Estado |
|---|---|---|
| 28 | Crear modelos de request en `models/requests.py` | ✅ |
| 29 | Crear modelos de response en `models/responses.py` | ✅ |
| 30 | Implementar `POST /extract` en `routers/extract.py` | ✅ |
| 31 | Implementar `POST /extract/discover` en `routers/extract.py` | ✅ |
| 32 | Implementar `POST /preprocess` en `routers/utils.py` | ✅ |
| 33 | Implementar `GET /health` en `routers/utils.py` | ✅ |

### Bloque 7 — QA / Validador (tareas 34–39)

| # | Tarea | Estado |
|---|---|---|
| 34 | Crear `test_integration.py` — tests de `/health` | ⏳ |
| 35 | Crear `test_integration.py` — tests de `/preprocess` | ⏳ |
| 36 | Crear `test_integration.py` — tests de `/extract` | ⏳ |
| 37 | Crear `test_integration.py` — tests de deduplicación | ⏳ |
| 38 | Crear `README.md` (setup + uso + costos) | ⏳ |
| 39 | Validación manual con 3+ tipos de sitio | ⏳ |

---

## 5. PROBLEMAS ABIERTOS

_Sin entradas aún — se llena conforme el Code Reviewer detecta problemas._

---

## 6. CONTEXTO PARA EL PRÓXIMO CHAT

- **Último prompt completado:** Día 3 Completo — Tareas 24–33 aprobadas
- **Próximo prompt a ejecutar:** test_integration.py (Día 4 — QA / Validador)
- **Nota:** Bloques 5 y 6 completos. Se verificaron pipelines y routers con éxito.

---

## 7. CONTRATOS VIGENTES

| Servicio | Input | Output (éxito) | Output (fallo) |
|---|---|---|---|
| `OxylabsFetcher.fetch()` | `url, render_js, geo_location, timeout, user_agent_type` | `{status: "ok", html: str, fetch_ms: int}` | `{status: "failed", error: str, fetch_ms: int}` |
| `HtmlPreprocessor.process()` | `html: str, token_budget: int` | `{markdown: str, content_hash: str, original_size_kb: float, processed_size_kb: float, estimated_tokens: int, preprocess_ms: int}` | `{markdown: "", content_hash: str, original_size_kb: float, processed_size_kb: 0, estimated_tokens: 0, preprocess_ms: int}` |
| `LLMExtractor.extract()` | `markdown, schema, output_hint, model, token_budget` | `{status: "extracted", data: dict, meta: dict}` | `{status: "failed", raw_response: str, meta: dict}` |
| `pipeline.run()` | `request: dict` | `{results: list[dict], output: dict, summary: dict}` | N/A (Maneja fallos internamente en results array) |
| `pipeline.run_discover()` | `request: dict` | `{domain: str, suggested_schema: dict, suggested_instructions: str, confidence: float, notes: str, meta: dict}` | `{domain: str, suggested_schema: {}, suggested_instructions: None, confidence: None, notes: None, meta: dict}` |
| `POST /extract` | `ExtractRequest` | `ExtractResponse` | `ExtractResponse` (con resultados erróneos dentro de results[]) |
| `POST /extract/discover` | `DiscoverRequest` | `DiscoverResponse` | N/A |
| `POST /preprocess` | `PreprocessRequest` | `PreprocessResponse` | `PreprocessResponse` (vacío, sin lanzar error 500) |
| `GET /health` | N/A | `HealthResponse` (`status="ok"`) | `HealthResponse` (`status="degraded"`) |
