import pytest
from app.services.preprocessor import HtmlPreprocessor

def get_large_html():
    base_html = "<html><head><script>alert(1)</script><style>body {color: red;}</style></head><body><nav>Menu</nav><main><h1>Tiendas</h1><ul><li>Zara - Moda - PB</li><li>Sushi Itto - Restaurantes - P2</li></ul></main><footer>Footer</footer></body></html>"
    # Make it > 50KB by repeating the li items
    li_items = "<li>Tienda Generica - Ropa - P1</li>" * 1500
    return base_html.replace("</ul>", li_items + "</ul>")

def test_size_reduction():
    preprocessor = HtmlPreprocessor()
    large_html = get_large_html()
    
    # Verify it's actually > 50KB
    assert len(large_html.encode('utf-8')) > 50 * 1024
    
    result = preprocessor.process(large_html, token_budget=4000)
    
    # Note: Depending on Trafilatura, the reduction might be very aggressive
    # We use a safer 30% threshold for the test
    assert result["processed_size_kb"] < result["original_size_kb"] * 0.3

def test_hash_is_deterministic():
    preprocessor = HtmlPreprocessor()
    html_sample = "<html><body><h1>Test</h1>" + "<p>Content</p>" * 50 + "</body></html>"
    
    r1 = preprocessor.process(html=html_sample, token_budget=4000)
    r2 = preprocessor.process(html=html_sample, token_budget=4000)
    
    assert r1["content_hash"] == r2["content_hash"]
    assert len(r1["content_hash"]) == 64 # SHA-256 length

def test_token_budget_respected():
    preprocessor = HtmlPreprocessor()
    large_html = get_large_html()
    
    result = preprocessor.process(large_html, token_budget=500)
    
    assert result["estimated_tokens"] <= 550

def test_no_html_tags_in_output():
    preprocessor = HtmlPreprocessor()
    html_with_tags = "<html><head><script>alert('bad');</script><style>css</style></head><body><nav>Menu</nav><main>Content</main></body></html>"
    
    result = preprocessor.process(html_with_tags, token_budget=4000)
    markdown = result["markdown"]
    
    assert "<script" not in markdown
    assert "<style" not in markdown
    assert "<nav" not in markdown

def test_never_raises_exception():
    preprocessor = HtmlPreprocessor()
    
    # Test with empty string
    result1 = preprocessor.process("")
    assert "markdown" in result1
    assert result1["markdown"] == ""
    
    # Test with minimal HTML
    result2 = preprocessor.process("<html></html>")
    assert "markdown" in result2
    assert result2["markdown"] == ""

def test_strategy_trafilatura_used_for_article():
    preprocessor = HtmlPreprocessor()
    # HTML de artículo con contenido en párrafos
    # Verificar que strategy_used == "trafilatura"
    html = "<html><body><article><p>" + ("Texto. " * 100) + "</p></article></body></html>"
    result = preprocessor.process(html)
    assert result["strategy_used"] == "trafilatura"

def test_strategy_structural_used_for_grid():
    preprocessor = HtmlPreprocessor()
    # HTML de grid de tarjetas — Trafilatura lo descartaría al no haber texto visible
    html = "<html><body>" + """
    <div class="card" aria-label="Zara" title="Piso 1"></div>
    """ * 200 + "</body></html>"
    result = preprocessor.process(html)
    # Verificar que "Zara" está en el markdown resultante
    assert "Zara" in result["markdown"]
    # Verificar que usó estrategia 2 o 3 (no trafilatura)
    assert result["strategy_used"] in ["structural", "raw_html"]

def test_strategy_raw_html_no_truncation():
    preprocessor = HtmlPreprocessor()
    # Verificar que raw_html no aplica smart_truncate
    # El resultado puede ser mayor que el token_budget
    large_grid_html = "<html><body>" + \
        "<div class='card'><h3>Tienda</h3></div>" * 500 + \
        "</body></html>"
    result = preprocessor.process(large_grid_html, token_budget=100)
    if result["strategy_used"] == "raw_html":
        # No debe estar truncado al token_budget
        assert result["estimated_tokens"] is None

def test_href_slug_extraction():
    preprocessor = HtmlPreprocessor()
    # HTML con links sin texto pero con hrefs descriptivos
    # Forzamos estrategia structural mediante repetición de nombres DISTINTOS
    # La deduplicación ignora si se repiten en el bloque de "seen_recent" (5 líneas)
    links = [
        '<a href="/tiendas/sushi-itto"></a>',
        '<a href="/directory/zara-moda"></a>',
        '<a href="/sanborns.html"></a>',
        '<a href="/tiendas/liverpool"></a>',
        '<a href="/tiendas/adidas-store"></a>',
        '<a href="/tiendas/nike-factory"></a>',
        '<a href="/tiendas/apple-store"></a>',
        '<a href="/tiendas/hm-moda"></a>',
        '<a href="/tiendas/bershka-clothing"></a>',
        '<a href="/tiendas/pull-and-bear"></a>'
    ]
    html = "<html><body>" + ("".join(links)) * 20 + "</body></html>"
    
    result = preprocessor.process(html)
    markdown = result["markdown"]
    
    assert "Sushi itto" in markdown
    assert "Zara moda" in markdown
    assert "Sanborns" in markdown
    assert "Adidas store" in markdown
    assert result["strategy_used"] == "structural"
    # No debe incluir slugs genéricos
    assert "Tiendas" not in markdown

