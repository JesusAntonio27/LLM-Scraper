import pytest
from app.services.llm_extractor import LLMExtractor

@pytest.mark.asyncio
async def test_extract_returns_valid_json():
    extractor = LLMExtractor()
    markdown = """
    ## Directorio de Tiendas
    ### Zara
    Categoría: Moda | Piso: PB | Local: L-12
    ### Sushi Itto
    Categoría: Restaurantes | Piso: 2 | Local: L-45
    ### Liverpool
    Categoría: Departamental | Piso: PB | Local: L-01
    """
    schema = {"stores": [{"name": "string", "category": "string", "floor": "string"}]}
    output_hint = "directorio de tiendas de plaza comercial en México"
    
    result = await extractor.extract(markdown, schema, output_hint, model="haiku", token_budget=4000)
    
    # Print the resulting JSON to console to satisfy the end user request requirement
    print("\n[RESULT JSON]:", result.get("data"))
    print("[COST USD]:", result.get("meta", {}).get("cost_usd"))
    
    assert result["status"] == "extracted"
    assert "stores" in result["data"]
    assert len(result["data"]["stores"]) > 0
    
    first_store = result["data"]["stores"][0]
    assert "name" in first_store
    assert "category" in first_store
    assert "floor" in first_store

@pytest.mark.asyncio
async def test_discover_uses_sonnet():
    extractor = LLMExtractor()
    markdown = "Contenido irrelevante"
    schema = {"info": "string"}
    
    result = await extractor.extract(markdown, schema, "test", model="sonnet", token_budget=100)
    
    # Verify model_used is exact sonnet alias regardless of outcome
    assert result["meta"]["model_used"] == "claude-sonnet-4-6"

@pytest.mark.asyncio
async def test_cost_is_calculated():
    extractor = LLMExtractor()
    markdown = "Prueba de costo."
    schema = {"test": "boolean"}
    
    result = await extractor.extract(markdown, schema, "test", model="haiku", token_budget=4000)
    
    assert "meta" in result
    meta = result["meta"]
    assert meta["cost_usd"] > 0
    assert meta["tokens_input"] > 0
    assert meta["tokens_output"] > 0

@pytest.mark.asyncio
async def test_never_raises_exception():
    extractor = LLMExtractor()
    markdown = ""
    schema = {}
    
    try:
        result = await extractor.extract(markdown, schema, "test", model="haiku")
        assert "status" in result
        assert isinstance(result, dict)
    except Exception as e:
        pytest.fail(f"extract() raised an exception unexpectedly: {e}")
