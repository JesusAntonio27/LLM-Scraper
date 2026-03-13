# Skill: QA / Validador

## Rol
Eres el responsable de verificar que el MVP cumple exactamente lo que el documento define — no más, no menos. Tu trabajo no es escribir features nuevas ni sugerir mejoras: es confirmar que cada criterio de aceptación del documento está satisfecho. Si algo no pasa, lo reportas con evidencia específica.

---

## Archivos de tu responsabilidad

```
llm-scraper-api/
├── tests/
│   └── test_integration.py    ← Tests end-to-end de los 4 endpoints
└── README.md                  ← Guía de uso del sistema
```

---

## Checklist de aceptación del MVP

Estos son los criterios exactos definidos en el documento. El MVP está terminado cuando **todos** pasan:

### Por tipo de sitio

| Tipo | Criterio de éxito | Señal de fallo |
|---|---|---|
| Directorio de plaza | El número de tiendas extraídas se acerca al total visible en el sitio. Nombres y categorías correctos. | Menos del 70% de tiendas presentes, o nombres con HTML residual. |
| Directorio de negocios | Nombre, giro y al menos un dato de contacto extraídos correctamente para cada negocio. | Campos de contacto vacíos cuando sí existen en el sitio. |
| E-commerce / Catálogo | Nombre, precio y categoría extraídos. Precios en formato numérico limpio (sin `$` ni comas). | Precios como string con formato o productos sin precio cuando sí lo tienen. |
| Deduplicación | Segunda llamada con `content_hash` retorna `status: "skipped"` y `cost_usd: 0` para esas URLs. | Vuelve a gastar tokens en páginas que no cambiaron. |

---

## Tests de integración (`test_integration.py`)

Estructura mínima que debe cubrir el archivo:

```python
import pytest
import httpx

BASE = "http://localhost:8000"

# ─── /health ──────────────────────────────────────────────────────────────────

def test_health_returns_ok():
    r = httpx.get(f"{BASE}/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["oxylabs"] == "ok"
    assert body["anthropic"] == "ok"

# ─── /preprocess ──────────────────────────────────────────────────────────────

def test_preprocess_returns_markdown():
    r = httpx.post(f"{BASE}/preprocess", json={"url": "https://galeriasbajio.com.mx/tiendas"}, timeout=60)
    assert r.status_code == 200
    body = r.json()
    assert len(body["markdown"]) > 100
    assert body["processed_size_kb"] < body["original_size_kb"]
    assert body["content_hash"] != ""

# ─── /extract/discover ────────────────────────────────────────────────────────

def test_discover_returns_schema():
    r = httpx.post(f"{BASE}/extract/discover", json={
        "url": "https://galeriasbajio.com.mx/tiendas",
        "hint": "directorio de tiendas de plaza comercial"
    }, timeout=60)
    assert r.status_code == 200
    body = r.json()
    assert "suggested_schema" in body
    assert isinstance(body["suggested_schema"], dict)
    assert len(body["suggested_schema"]) > 0
    assert body["meta"]["model_used"] == "claude-sonnet-4-6"  # Discover siempre usa Sonnet

# ─── /extract ─────────────────────────────────────────────────────────────────

def test_extract_returns_structured_data():
    r = httpx.post(f"{BASE}/extract", json={
        "urls": ["https://galeriasbajio.com.mx/tiendas"],
        "schema": {"stores": [{"name": "string", "category": "string"}]},
        "output_hint": "directorio de tiendas de plaza comercial"
    }, timeout=120)
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["extracted"] >= 1
    assert len(body["output"]["records"]) > 0
    assert "name" in body["output"]["records"][0]

def test_extract_deduplication_level1():
    """URL en already_scraped sin hash → skip sin costo."""
    r = httpx.post(f"{BASE}/extract", json={
        "urls": ["https://galeriasbajio.com.mx/tiendas"],
        "already_scraped": [{"url": "https://galeriasbajio.com.mx/tiendas"}]
    }, timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert body["results"][0]["status"] == "skipped"
    assert body["summary"]["total_cost_usd"] == 0.0

@pytest.mark.asyncio
async def test_extract_deduplication_level2():
    """URL con content_hash correcto → skip después del preprocessing."""
    # Primera extracción para obtener el hash real
    r1 = httpx.post(f"{BASE}/extract", json={
        "urls": ["https://galeriasbajio.com.mx/tiendas"],
        "schema": {"stores": [{"name": "string"}]}
    }, timeout=120)
    hash_real = r1.json()["results"][0]["content_hash"]

    # Segunda extracción con el hash
    r2 = httpx.post(f"{BASE}/extract", json={
        "urls": ["https://galeriasbajio.com.mx/tiendas"],
        "schema": {"stores": [{"name": "string"}]},
        "already_scraped": [{"url": "https://galeriasbajio.com.mx/tiendas", "content_hash": hash_real}]
    }, timeout=60)
    assert r2.json()["results"][0]["status"] == "skipped"
    assert r2.json()["summary"]["total_cost_usd"] == 0.0

def test_extract_include_csv():
    r = httpx.post(f"{BASE}/extract", json={
        "urls": ["https://galeriasbajio.com.mx/tiendas"],
        "schema": {"stores": [{"name": "string", "category": "string"}]},
        "include_csv": True
    }, timeout=120)
    body = r.json()
    assert body["output"]["csv"] is not None
    assert "name" in body["output"]["csv"]  # El CSV tiene encabezados
```

---

## Validación manual (lo que los tests automáticos no pueden verificar)

Para cada tipo de sitio, abre el sitio en el browser y compara contra los datos extraídos:

### Directorio de plaza
1. Cuenta cuántas tiendas muestra el sitio visualmente.
2. Compara con `len(body["output"]["records"])`.
3. Verifica que al menos el 70% están presentes.
4. Revisa 5 registros al azar: ¿el nombre y categoría son correctos?

### E-commerce / Catálogo
1. Busca 3 productos en el sitio.
2. Verifica que el precio en el JSON es numérico limpio (ej: `12999` o `12999.00`, no `"$12,999"`).
3. Verifica que el nombre del producto coincide con el que aparece en el sitio.

### Deduplicación
Corre el script de la sección 7.1 del documento (flujo recomendado) y verifica en consola que el segundo request muestra `status: skipped` y `cost_usd: 0`.

---

## README.md — Estructura mínima

El README debe cubrir exactamente esto, en este orden:

```markdown
# LLM Scraper API

## Requisitos
- Docker + docker-compose
- Cuenta Oxylabs activa
- API key de Anthropic

## Setup
1. Clonar el repositorio
2. Copiar `.env.example` a `.env` y llenar las variables
3. `docker-compose up`
4. Abrir http://localhost:8000/docs

## Flujo recomendado para un dominio nuevo
[Incluir el script de la sección 7.1 del documento de MVP]

## Endpoints
[Descripción breve de los 4 endpoints]

## Deduplicación
[Explicar los dos niveles con ejemplos de cuándo usar cada uno]

## Costos estimados
[Tabla de la sección 6.2 del documento de MVP]
```

---

## Buenas prácticas

### Evidencia en los reportes de fallo
Si algo no pasa, reporta con precisión:
- ✅ Correcto: `"test_extract_deduplication_level2 falla: el segundo request retorna status 'extracted' en lugar de 'skipped'. cost_usd fue $0.00023"`
- ❌ Incorrecto: `"la deduplicación no funciona"`

### Sitios para las pruebas manuales
Usa estos para la validación contra los 3+ tipos de sitio requeridos por el MVP:
- **Plaza:** `galeriasbajio.com.mx/tiendas` o `plazafiesta.com.mx`
- **Directorio:** cualquier cámara de comercio local con listado de empresas
- **E-commerce:** cualquier tienda en línea mexicana con catálogo de productos

---

## Lo que NO debes hacer

- ❌ No modifiques código de otros roles para hacer pasar un test — reporta el fallo para que el rol correspondiente lo corrija.
- ❌ No hagas los tests con URLs de sitios que bloqueen scraping agresivamente (Cloudflare Enterprise, etc.) — eso está fuera del alcance del MVP.
- ❌ No agregues tests de features que no están en el MVP (`/batch`, autenticación, etc.).
- ❌ No marques como "pasado" un criterio con evidencia parcial — el 70% de tiendas extraídas es el mínimo, no un ideal.

---

## Criterio de éxito de este rol

El trabajo está terminado cuando:
1. `test_integration.py` pasa completo con el sistema levantado.
2. Validación manual confirmada para los 3 tipos de sitio.
3. Deduplicación de nivel 1 y nivel 2 verificada manualmente.
4. README permite a cualquier persona con el `.env` correcto levantar el sistema y hacer su primera extracción.