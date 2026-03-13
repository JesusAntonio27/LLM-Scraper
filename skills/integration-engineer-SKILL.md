# Skill: Integration Engineer (Oxylabs)

## Rol
Eres el responsable de que el proyecto pueda obtener HTML de cualquier sitio web de forma confiable. Tu único cliente es el pipeline interno — no expones nada directamente al usuario. Tu trabajo es abstraer completamente la complejidad de Oxylabs detrás de una interfaz simple: recibe URL + opciones, regresa HTML o un error tipado.

---

## Archivos de tu responsabilidad

```
llm-scraper-api/
├── app/
│   └── services/
│       └── oxylabs.py       ← Tu único archivo de implementación
└── tests/
    └── test_oxylabs.py      ← Test real contra sitio de plaza
```

---

## Contrato que debes cumplir

El pipeline (`services/pipeline.py`) llamará a tu servicio así:

```python
result = await oxylabs_fetcher.fetch(
    url="https://galeriasbajio.com.mx/tiendas",
    render_js=True,
    geo_location="Mexico",
    timeout=30,
    user_agent_type="desktop"
)
```

Tu función debe retornar uno de estos dos resultados — nunca lanzar excepción al pipeline:

```python
# Éxito
{
    "status": "ok",
    "html": "<html>...</html>",
    "fetch_ms": 2100
}

# Fallo (4xx, 5xx, timeout, cualquier error de red)
{
    "status": "failed",
    "error": "timeout after 30s",   # Mensaje descriptivo
    "fetch_ms": 30000
}
```

---

## Cómo funciona Oxylabs en este proyecto

Oxylabs actúa como proxy inteligente: recibe la URL, la renderiza con JS en un browser headless, y devuelve el HTML completamente renderizado. Esto es lo que permite scraping de SPAs y sitios con contenido dinámico.

La API de Oxylabs se llama vía HTTP con autenticación básica:

```python
import httpx
import time

async def fetch(url: str, render_js: bool = True, geo_location: str = None,
                timeout: int = 30, user_agent_type: str = "desktop") -> dict:
    
    payload = {
        "source": "universal",
        "url": url,
        "render": "html" if render_js else None,
        "geo_location": geo_location,
        "user_agent_type": user_agent_type,
    }
    # Limpiar campos None antes de enviar
    payload = {k: v for k, v in payload.items() if v is not None}

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout + 5) as client:
            response = await client.post(
                "https://realtime.oxylabs.io/v1/queries",
                auth=(settings.oxylabs_user, settings.oxylabs_pass),
                json=payload
            )
            fetch_ms = int((time.monotonic() - start) * 1000)
            
            if response.status_code != 200:
                return {"status": "failed", "error": f"HTTP {response.status_code}", "fetch_ms": fetch_ms}
            
            html = response.json()["results"][0]["content"]
            return {"status": "ok", "html": html, "fetch_ms": fetch_ms}

    except httpx.TimeoutException:
        fetch_ms = int((time.monotonic() - start) * 1000)
        return {"status": "failed", "error": f"timeout after {timeout}s", "fetch_ms": fetch_ms}
    
    except Exception as e:
        fetch_ms = int((time.monotonic() - start) * 1000)
        return {"status": "failed", "error": str(e), "fetch_ms": fetch_ms}
```

---

## Buenas prácticas

### Manejo de errores
- **Nunca** dejes que una excepción de red se propague al pipeline. Todo error debe convertirse en `{"status": "failed", ...}`.
- Diferencia los tipos de error en el mensaje: `"HTTP 403"`, `"timeout after 30s"`, `"connection refused"`. El pipeline y los logs lo agradecen.
- El timeout del `httpx.AsyncClient` debe ser ligeramente mayor que el `timeout` del parámetro para darle tiempo a Oxylabs de responder con su propio mensaje de error.

### Rendimiento
- Usa `httpx.AsyncClient` como context manager (`async with`) — no reutilices instancias entre requests.
- El pipeline controlará la concurrencia con `asyncio.Semaphore(settings.max_concurrent_fetches)`. Tu función no necesita saber nada de eso — solo sé async.

### Testing
- El `test_oxylabs.py` debe hacer una llamada **real** a Oxylabs contra un sitio de plaza (ej. `galeriasbajio.com.mx/tiendas`) y verificar:
  1. El status es `"ok"`.
  2. El HTML contiene texto visible (no está vacío ni es solo boilerplate).
  3. El `fetch_ms` es un número positivo.
- Usa `pytest` con `pytest-asyncio` para tests async.

```python
# test_oxylabs.py — estructura mínima
import pytest
from app.services.oxylabs import OxylabsFetcher

@pytest.mark.asyncio
async def test_fetch_real_site():
    fetcher = OxylabsFetcher()
    result = await fetcher.fetch(
        url="https://galeriasbajio.com.mx/tiendas",
        render_js=True,
        geo_location="Mexico"
    )
    assert result["status"] == "ok"
    assert len(result["html"]) > 1000
    assert result["fetch_ms"] > 0
```

---

## Lo que NO debes hacer

- ❌ No hagas retry automático dentro del fetcher — el pipeline decide si reintenta o no.
- ❌ No loggees el HTML completo — puede ser de cientos de KB y llena los logs. Loggea solo la URL, el status y el `fetch_ms`.
- ❌ No uses `requests` (síncrono) — todo el stack es async con `httpx`.
- ❌ No hardcodees las credenciales de Oxylabs — siempre desde `settings.oxylabs_user` y `settings.oxylabs_pass`.
- ❌ No parseees ni modifiques el HTML aquí — eso es responsabilidad del Data Engineer en `preprocessor.py`.

---

## Criterio de éxito de este rol

El trabajo está terminado cuando:
1. `test_oxylabs.py` pasa contra un sitio real de plaza.
2. El HTML retornado en terminal tiene contenido visible (tiendas, nombres, etc.).
3. El fetcher retorna `{"status": "failed", ...}` sin lanzar excepción ante cualquier tipo de error de red.