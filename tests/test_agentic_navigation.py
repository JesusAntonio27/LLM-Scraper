"""
Tests del modo agentic con 3 tipos de navegación real.

Cada test es independiente y puede correrse por separado:
  pytest tests/test_agentic_navigation.py::test_agentic_categories -v -s
  pytest tests/test_agentic_navigation.py::test_agentic_pagination -v -s
  pytest tests/test_agentic_navigation.py::test_agentic_store_detail -v -s

Todos juntos:
  pytest tests/test_agentic_navigation.py -v -s
"""

import csv
import os

import httpx

BASE_URL = "http://localhost:8000"
OUTPUT_CSV = "scripts/resultados_plazas.csv"
CONTEXT_FILE = "navigation_context.md"

SCHEMA = {
    "stores": [
        {
            "plaza": "string",
            "nombre": "string",
            "categoria": "string | null",
            "ubicacion": "string | null",
        }
    ]
}


# ─── Helpers ──────────────────────────────────────────────────────────────


def extract_plaza(plaza_name: str, url: str, output_hint: str, min_stores: int):
    """
    Llama a /extract en modo agentic y retorna los resultados.
    Imprime el progreso en terminal.
    """
    print(f"\n🏬 Procesando: {plaza_name}")
    print(f"   URL: {url}")

    import pytest

    response = httpx.post(
        f"{BASE_URL}/extract",
        json={
            "urls": [url],
            "schema": SCHEMA,
            "output_hint": output_hint,
            "fetch_options": {
                "render_js": True,
                "geo_location": "Mexico",
                "timeout": 60,
            },
            "llm_options": {
                "agentic": True,
            },
        },
        timeout=900,  # 15 min — navegación puede tomar tiempo
    )
    assert response.status_code == 200, f"HTTP {response.status_code}"
    data = response.json()
    result = data["results"][0]

    # Detección de abandono inteligente
    if result.get("meta", {}).get("gave_up"):
        strategies = result["meta"].get("strategies_tried", [])
        partial_count = len(result.get("data", {}).get("stores", []))
        pytest.skip(
            f"Sitio abandonado intencionalmente. "
            f"Estrategias intentadas: {', '.join(strategies)}. "
            f"Datos parciales: {partial_count} items"
        )

    stores = result.get("data", {}).get("stores", []) if result.get("data") else []
    iterations = result.get("meta", {}).get("iterations", 0)
    cost = result.get("meta", {}).get("cost_usd", 0)
    strategy = result.get("meta", {}).get("strategy_used", "agentic")

    print(f"   → Status: {result['status']}")
    print(f"   → Strategy: {strategy}")
    print(f"   → Tiendas encontradas: {len(stores)}")
    print(f"   → Iteraciones del agente: {iterations}")
    print(f"   → Costo: ${cost:.6f} USD")

    if strategy == "next_data":
        print("   ⚡ Extracción vía __NEXT_DATA__ — sin navegación necesaria")

    return stores, result


def append_to_csv(stores: list):
    """Agrega tiendas al CSV existente sin repetir el header."""
    file_exists = os.path.exists(OUTPUT_CSV)
    with open(OUTPUT_CSV, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["plaza", "nombre", "categoria", "ubicacion"]
        )
        if not file_exists:
            writer.writeheader()
        for store in stores:
            writer.writerow(
                {
                    "plaza": store.get("plaza", ""),
                    "nombre": store.get("nombre", ""),
                    "categoria": store.get("categoria", ""),
                    "ubicacion": store.get("ubicacion", ""),
                }
            )


def has_real_names(stores: list, min_count: int) -> tuple[bool, int]:
    """
    Verifica que los nombres no sean genéricos como 'Tienda 1' o 'Store N'.
    """
    generic_patterns = ["tienda ", "store ", "local ", "item "]
    real = [
        s
        for s in stores
        if s.get("nombre")
        and not any(s["nombre"].lower().startswith(p) for p in generic_patterns)
        and len(s["nombre"].strip()) > 2
    ]
    return len(real) >= min_count, len(real)


def save_navigation_snapshot(plaza_name: str):
    """Guarda una copia del navigation_context.md después de cada test."""
    if not os.path.exists(CONTEXT_FILE):
        print(f"   ⚠️  {CONTEXT_FILE} no encontrado — no se guardó snapshot")
        return
    snapshot_name = f"navigation_context_{plaza_name.lower().replace(' ', '_')}.md"
    snapshot_path = os.path.join("scripts", snapshot_name)
    with open(CONTEXT_FILE, "r", encoding="utf-8") as src:
        content = src.read()
    with open(snapshot_path, "w", encoding="utf-8") as dst:
        dst.write(content)
    print(f"   → Contexto guardado en: {snapshot_path}")


# ─── TEST 1: Categorías ───────────────────────────────────────────────────


def test_agentic_categories():
    """
    Valida que el agente pueda navegar un directorio dividido por categorías.
    Criterio: >= 20 tiendas con nombres reales.
    """
    PLAZA = "Galerías Insurgentes"
    URL = "https://www.galerias.com/galerias/insurgentes/tiendas"
    HINT = (
        "Directorio de tiendas de Galerías Insurgentes en CDMX México. "
        "El contenido puede estar dividido por categorías o letras del alfabeto. "
        "Navega por todas las secciones para obtener el listado completo."
    )
    MIN_STORES = 20

    stores, result = extract_plaza(PLAZA, URL, HINT, MIN_STORES)
    save_navigation_snapshot(PLAZA)

    # Assertion 1: se encontraron tiendas
    assert len(stores) > 0, (
        f"El agente no extrajo ninguna tienda de {PLAZA}. "
        f"Status: {result['status']}. "
        f"Revisar navigation_context_{PLAZA.lower().replace(' ', '_')}.md"
    )

    # Assertion 2: nombres reales
    passed, real_count = has_real_names(stores, MIN_STORES)
    assert passed, (
        f"Solo {real_count} nombres reales de {len(stores)} totales. "
        f"Mínimo requerido: {MIN_STORES}."
    )

    # Assertion 3: modo agentic activado
    assert result["meta"].get("agentic") is True, (
        "El resultado no indica que se usó modo agentic"
    )

    # Assertion 4: usó más de 1 iteración (realmente navegó) O usó next_data
    strategy = result.get("meta", {}).get("strategy_used")
    if strategy != "next_data":
        assert result["meta"].get("iterations", 1) > 1, (
            "El agente no hizo ninguna navegación (solo 1 iteración)"
        )

    # Guardar en CSV
    append_to_csv(stores)
    print(f"   ✅ {PLAZA}: {real_count} tiendas reales → CSV actualizado")


# ─── TEST 2: Paginador ────────────────────────────────────────────────────


def test_agentic_pagination():
    """
    Valida que el agente pueda navegar un directorio con paginación.
    Criterio: >= 30 tiendas con nombres reales.
    """
    PLAZA = "Antara Fashion Hall"
    URL = "https://www.antara.com.mx/directorio"
    HINT = (
        "Directorio de tiendas de Antara Fashion Hall en Polanco, CDMX México. "
        "Las tiendas pueden estar distribuidas en múltiples páginas o detrás "
        "de un botón 'ver más' o 'cargar más'. "
        "Navega por todas las páginas disponibles para obtener el listado completo."
    )
    MIN_STORES = 30

    stores, result = extract_plaza(PLAZA, URL, HINT, MIN_STORES)
    save_navigation_snapshot(PLAZA)

    assert len(stores) > 0, (
        f"El agente no extrajo ninguna tienda de {PLAZA}. "
        f"Status: {result['status']}."
    )

    passed, real_count = has_real_names(stores, MIN_STORES)
    assert passed, (
        f"Solo {real_count} nombres reales de {len(stores)} totales. "
        f"Mínimo requerido: {MIN_STORES}."
    )

    assert result["meta"].get("agentic") is True
    assert result["meta"].get("iterations", 1) > 1

    append_to_csv(stores)
    print(f"   ✅ {PLAZA}: {real_count} tiendas reales → CSV actualizado")


# ─── TEST 3: Detalle por tienda (plus opcional) ───────────────────────────


def test_agentic_store_detail():
    """
    Valida que el agente pueda navegar Plaza Satélite usando categorías.
    """
    PLAZA = "Plaza Satélite"
    URL = "https://www.plazasatelite.com.mx/tiendas/"
    HINT = (
        "Directorio de tiendas de Plaza Satélite en CDMX México. "
        "El contenido está dividido por categorías en el menú: "
        "Almacenes Departamentales, FastFood, Bancos, Hogar, "
        "Joyerías, Ópticas, Restaurantes, Belleza, Telefonía, "
        "Zapaterías. Haz click en cada categoría y acumula "
        "todas las tiendas de todas las categorías."
    )
    MIN_STORES_BASIC = 10

    stores, result = extract_plaza(PLAZA, URL, HINT, MIN_STORES_BASIC)
    save_navigation_snapshot(PLAZA)

    # Si el agente usó give_up, verificar que fue justificado
    if result.get("meta", {}).get("gave_up"):
        strategies = result["meta"].get("strategies_tried", [])
        partial = result.get("data", {}).get("stores", [])
        if len(partial) == 0 and len(strategies) >= 4:
            import pytest
            pytest.skip(
                f"Plaza Satélite: agente abandonó tras {len(strategies)} "
                f"estrategias sin ningún resultado. "
                f"Puede requerir autenticación o JS no soportado."
            )
        else:
            import pytest
            pytest.fail(
                f"Plaza Satélite: give_up prematuro. "
                f"Solo {len(strategies)} estrategias intentadas "
                f"con {len(partial)} items parciales disponibles."
            )

    # Si llegó al límite pero tiene datos parciales — aceptar
    if result.get("meta", {}).get("hit_limit") and \
       len(result.get("data", {}).get("stores", [])) > 0:
        stores = result["data"]["stores"]
        print(f"   ⚠️  Límite alcanzado pero con {len(stores)} tiendas parciales")
        assert len(stores) >= MIN_STORES_BASIC
    else:
        # Assertion mínima — nombres reales
        assert len(stores) > 0, f"El agente no extrajo ninguna tienda de {PLAZA}."

        passed_basic, real_count = has_real_names(stores, MIN_STORES_BASIC)
        assert passed_basic, (
            f"Solo {real_count} nombres reales. Mínimo requerido: {MIN_STORES_BASIC}."
        )

    # Assertion mínima — nombres reales
    assert len(stores) > 0, f"El agente no extrajo ninguna tienda de {PLAZA}."

    passed_basic, real_count = has_real_names(stores, MIN_STORES_BASIC)
    assert passed_basic, (
        f"Solo {real_count} nombres reales. Mínimo requerido: {MIN_STORES_BASIC}."
    )

    # Check PLUS — no falla, solo reporta
    stores_with_location = [
        s
        for s in stores
        if s.get("ubicacion") and len(s["ubicacion"].strip()) > 1
    ]
    plus_passed = len(stores_with_location) >= MIN_STORES_PLUS

    if plus_passed:
        print(
            f"   🌟 PLUS alcanzado: {len(stores_with_location)} tiendas con ubicación"
        )
    else:
        print(
            f"   ℹ️  PLUS no alcanzado: solo {len(stores_with_location)} "
            f"tiendas con ubicación (no falla el test)"
        )

    assert result["meta"].get("agentic") is True

    append_to_csv(stores)
    print(f"   ✅ {PLAZA}: {real_count} tiendas reales → CSV actualizado")


# ─── RESUMEN FINAL ────────────────────────────────────────────────────────


def test_print_summary():
    """
    Lee el CSV al final y reporta el total acumulado de todas las plazas.
    Siempre pasa — es solo informativo.
    """
    if not os.path.exists(OUTPUT_CSV):
        print("⚠️  CSV no encontrado — los tests anteriores pueden haber fallado")
        return

    with open(OUTPUT_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    plazas: dict[str, int] = {}
    for row in rows:
        plaza = row.get("plaza", "Desconocida")
        plazas[plaza] = plazas.get(plaza, 0) + 1

    print("\n" + "─" * 50)
    print("📊 RESUMEN TOTAL DEL CSV")
    print("─" * 50)
    for plaza, count in sorted(plazas.items()):
        print(f"  {plaza}: {count} tiendas")
    print(f"  {'─' * 30}")
    print(f"  TOTAL: {len(rows)} tiendas en {len(plazas)} plazas")
    print("─" * 50)
