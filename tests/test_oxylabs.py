"""
Integration Engineer — tests/test_oxylabs.py
Tarea 10: Pruebas reales contra Oxylabs.

Todos los casos hacen llamadas HTTP reales — no hay mocks.
Requiere credenciales válidas en .env (OXYLABS_USER / OXYLABS_PASS).

Corre con: pytest tests/test_oxylabs.py -v
"""

import pytest

from app.services.oxylabs import OxylabsFetcher

# ──────────────────────────────────────────────────────────────────────────────
# Casos de prueba
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_real_site():
    """
    Llamada real a un sitio estable (example.com).

    Verifica:
    - status == "ok"
    - HTML con contenido (no boilerplate vacío)
    - fetch_ms es un número positivo
    """
    fetcher = OxylabsFetcher()
    result = await fetcher.fetch(
        url="https://example.com",
        render_js=True,
    )

    assert result["status"] == "ok", (
        f"Se esperaba status='ok', se obtuvo: {result}"
    )
    assert len(result["html"]) > 200, (
        f"HTML demasiado corto ({len(result['html'])} chars) — posible respuesta vacía"
    )
    assert result["fetch_ms"] > 0, "fetch_ms debe ser un número positivo"


@pytest.mark.asyncio
async def test_fetch_invalid_url():
    """
    Llamada a un dominio que no existe.

    Verifica:
    - status == "failed"
    - El campo "error" está presente y no es una cadena vacía
    - No se lanza ninguna excepción (sin try/except en el test)
    """
    fetcher = OxylabsFetcher()
    result = await fetcher.fetch(
        url="https://domain-does-not-exist-999999.xyz",
        render_js=True,
    )

    assert result["status"] == "failed", (
        f"Se esperaba status='failed', se obtuvo: {result}"
    )
    assert "error" in result, "El resultado debe tener campo 'error'"
    assert len(result["error"]) > 0, "El mensaje de error no debe estar vacío"
    assert "fetch_ms" in result, "El resultado debe tener campo 'fetch_ms'"


@pytest.mark.asyncio
async def test_fetch_returns_no_exception():
    """
    Contrato fundamental: incluso con un dominio completamente inválido
    el fetcher retorna un dict con 'status', nunca lanza excepción.

    Verifica:
    - El retorno es un dict
    - El dict contiene la clave "status"
    - "status" es "ok" o "failed" — ningún otro valor
    - "fetch_ms" está presente y es un entero ≥ 0
    """
    fetcher = OxylabsFetcher()
    result = await fetcher.fetch(
        url="https://esto-no-existe-jamas.xyz",
        render_js=False,
        timeout=15,
    )

    assert isinstance(result, dict), "El fetcher debe retornar un dict"
    assert "status" in result, "El dict debe tener la clave 'status'"
    assert result["status"] in ("ok", "failed"), (
        f"'status' debe ser 'ok' o 'failed', se obtuvo: {result['status']}"
    )
    assert "fetch_ms" in result, "El dict debe tener la clave 'fetch_ms'"
    assert isinstance(result["fetch_ms"], int), "fetch_ms debe ser un entero"
    assert result["fetch_ms"] >= 0, "fetch_ms debe ser ≥ 0"
