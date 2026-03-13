import pytest
import httpx
import time

BASE = "http://localhost:8000"

# ─── Tests de GET /health ─────────────────────────────────────────────────────

def test_health_returns_ok():
    r = httpx.get(f"{BASE}/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["oxylabs"] == "ok"
    assert body["anthropic"] == "ok"
    assert "timestamp" in body
    assert body["timestamp"] != ""

def test_health_response_structure():
    r = httpx.get(f"{BASE}/health")
    assert r.status_code == 200
    body = r.json()
    expected_keys = {"status", "oxylabs", "anthropic", "timestamp"}
    assert set(body.keys()) == expected_keys

# ─── Tests de POST /preprocess ────────────────────────────────────────────────

def test_preprocess_returns_markdown():
    r = httpx.post(
        f"{BASE}/preprocess", 
        json={"url": "https://galeriasbajio.com.mx/tiendas"}, 
        timeout=60
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["markdown"]) > 100
    assert body["processed_size_kb"] < body["original_size_kb"]
    assert body["content_hash"] != ""
    assert body["estimated_tokens"] > 0

def test_preprocess_no_html_in_output():
    r = httpx.post(
        f"{BASE}/preprocess", 
        json={"url": "https://galeriasbajio.com.mx/tiendas"}, 
        timeout=60
    )
    assert r.status_code == 200
    markdown = r.json()["markdown"]
    assert "<script" not in markdown.lower()
    assert "<style" not in markdown.lower()
    assert "<nav" not in markdown.lower()

def test_preprocess_does_not_call_llm():
    r = httpx.post(
        f"{BASE}/preprocess", 
        json={"url": "https://galeriasbajio.com.mx/tiendas"}, 
        timeout=60
    )
    assert r.status_code == 200
    body = r.json()
    
    # Verificar indirectamente que /preprocess no consume tokens
    assert "tokens_input" not in body
    assert "tokens_output" not in body
    assert "cost_usd" not in body
    
    assert len(body.keys()) == 6

# ─── Tests de POST /extract ───────────────────────────────────────────────────

def test_extract_returns_structured_data():
    r = httpx.post(
        f"{BASE}/extract", 
        json={
            "urls": ["https://galeriasbajio.com.mx/tiendas"],
            "schema": {"stores": [{"name": "string", "category": "string"}]},
            "output_hint": "directorio de tiendas de plaza comercial en México"
        }, 
        timeout=120
    )
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["extracted"] >= 1
    assert len(body["output"]["records"]) > 0
    assert "name" in body["output"]["records"][0]
    assert "source_url" in body["output"]["records"][0]
    assert body["summary"]["total_cost_usd"] > 0

def test_extract_response_structure():
    r = httpx.post(
        f"{BASE}/extract", 
        json={
            "urls": ["https://galeriasbajio.com.mx/tiendas"],
            "schema": {"stores": [{"name": "string", "category": "string"}]},
            "output_hint": "directorio de tiendas de plaza comercial en México"
        }, 
        timeout=120
    )
    assert r.status_code == 200
    body = r.json()
    
    assert set(body.keys()) == {"results", "output", "summary"}
    assert set(body["output"].keys()) == {"records", "csv", "schema_used"}
    assert set(body["summary"].keys()) == {"total", "extracted", "skipped", "failed", "total_tokens", "total_cost_usd", "total_ms"}
    
    assert body["output"]["csv"] is None

def test_extract_include_csv():
    r = httpx.post(
        f"{BASE}/extract", 
        json={
            "urls": ["https://galeriasbajio.com.mx/tiendas"],
            "schema": {"stores": [{"name": "string", "category": "string"}]},
            "output_hint": "directorio de tiendas de plaza comercial en México",
            "include_csv": True
        }, 
        timeout=120
    )
    assert r.status_code == 200
    body = r.json()
    csv_content = body["output"]["csv"]
    assert csv_content is not None
    assert "name" in csv_content
    assert "source_url" in csv_content

def test_extract_failed_url_does_not_raise():
    r = httpx.post(
        f"{BASE}/extract", 
        json={
            "urls": ["https://esta-url-no-existe-jamas-xyz.com"],
            "schema": {"test": "string"}
        }, 
        timeout=120
    )
    assert r.status_code == 200
    body = r.json()
    assert body["results"][0]["status"] == "failed"
    assert body["summary"]["failed"] == 1
    assert body["summary"]["extracted"] == 0

# ─── Tests de deduplicación ───────────────────────────────────────────────────

def test_dedup_level1_skip_without_hash():
    start_time = time.time()
    r = httpx.post(
        f"{BASE}/extract", 
        json={
            "urls": ["https://galeriasbajio.com.mx/tiendas"],
            "schema": {"test": "string"},
            "already_scraped": [{"url": "https://galeriasbajio.com.mx/tiendas"}]
        }, 
        timeout=10
    )
    end_time = time.time()
    
    assert r.status_code == 200
    body = r.json()
    assert body["results"][0]["status"] == "skipped"
    assert body["summary"]["total_cost_usd"] == 0.0
    assert (end_time - start_time) < 5.0 # Verificar que tomó poco tiempo, sin fetch

def test_dedup_level2_skip_with_matching_hash():
    # 1. Extracción real para obtener el content_hash
    r1 = httpx.post(
        f"{BASE}/extract", 
        json={
            "urls": ["https://galeriasbajio.com.mx/tiendas"],
            "schema": {"stores": [{"name": "string"}]},
        }, 
        timeout=120
    )
    assert r1.status_code == 200
    hash_real = r1.json()["results"][0]["content_hash"]
    
    # 2. Usar ese hash en already_scraped
    r2 = httpx.post(
        f"{BASE}/extract", 
        json={
            "urls": ["https://galeriasbajio.com.mx/tiendas"],
            "schema": {"stores": [{"name": "string"}]},
            "already_scraped": [{"url": "https://galeriasbajio.com.mx/tiendas", "content_hash": hash_real}]
        }, 
        timeout=120
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["results"][0]["status"] == "skipped"
    assert body2["summary"]["total_cost_usd"] == 0.0

def test_dedup_level2_processes_when_hash_differs():
    r = httpx.post(
        f"{BASE}/extract", 
        json={
            "urls": ["https://galeriasbajio.com.mx/tiendas"],
            "schema": {"stores": [{"name": "string"}]},
            "already_scraped": [{"url": "https://galeriasbajio.com.mx/tiendas", "content_hash": "hash_falso_que_no_coincide"}]
        }, 
        timeout=120
    )
    assert r.status_code == 200
    body = r.json()
    assert body["results"][0]["status"] != "skipped"
