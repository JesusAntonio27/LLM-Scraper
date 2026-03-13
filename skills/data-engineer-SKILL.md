# Skill: Data Engineer (Preprocessor)

## Rol
Eres el responsable de la reducción de tokens. Tu trabajo es convertir HTML crudo (400–800 KB típico) en Markdown limpio de 2–5 KB que el LLM pueda procesar eficientemente. Este paso es el más crítico para el costo del sistema: cada KB que no eliminas aquí se convierte en tokens que se pagan.

---

## Archivos de tu responsabilidad

```
llm-scraper-api/
├── app/
│   └── services/
│       └── preprocessor.py      ← Tu único archivo de implementación
└── tests/
    └── test_preprocessor.py     ← Test con HTML real
```

---

## Contrato que debes cumplir

El pipeline (`services/pipeline.py`) llamará a tu servicio así:

```python
result = preprocessor.process(
    html="<html>...</html>",
    token_budget=4000
)
```

Tu función debe retornar **siempre** este objeto — nunca lanzar excepción:

```python
{
    "markdown": "## Tiendas\n\n### Zara\nPiso: PB...",
    "content_hash": "b9c2f1a4e3d8...",   # SHA-256 del markdown resultante
    "original_size_kb": 487.3,
    "processed_size_kb": 4.1,
    "estimated_tokens": 1024,
    "preprocess_ms": 48
}
```

---

## Pipeline de limpieza

Aplica las herramientas en este orden exacto. Cada paso tiene un propósito específico:

### Paso 1 — Trafilatura (extracción de contenido principal)
Trafilatura identifica y extrae el contenido principal del documento HTML, descartando automáticamente navegación, publicidad, footers y elementos decorativos.

```python
import trafilatura

def _extract_main_content(html: str) -> str:
    result = trafilatura.extract(
        html,
        include_tables=True,
        include_links=False,    # Los links agregan ruido, no datos
        include_images=False,
        output_format="markdown"
    )
    return result or ""  # Trafilatura puede retornar None — siempre manejar
```

### Paso 2 — BeautifulSoup (limpieza de residuos)
Cuando Trafilatura no logra extraer el contenido (retorna None o muy poco texto), usar BeautifulSoup como fallback:

```python
from bs4 import BeautifulSoup

def _clean_with_bs4(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    
    # Eliminar estos tags completamente (con su contenido)
    for tag in soup(["script", "style", "nav", "footer", 
                     "header", "aside", "iframe", "noscript"]):
        tag.decompose()
    
    return soup.get_text(separator="\n", strip=True)
```

### Paso 3 — markdownify (conversión a Markdown)
Convierte el HTML limpio a Markdown estructurado. El LLM procesa Markdown más eficientemente que HTML crudo: misma información, menos tokens.

```python
import markdownify

def _to_markdown(html: str) -> str:
    return markdownify.markdownify(
        html,
        heading_style="ATX",   # Usa ## en lugar de === subrayado
        strip=["a", "img"]     # Elimina links e imágenes del markdown
    )
```

### Paso 4 — smart_truncate (respeto al token_budget)
Nunca cortes el contenido a la mitad de un registro. Si el presupuesto de tokens se alcanza, corta en el último separador de registro completo.

```python
def _smart_truncate(text: str, token_budget: int) -> str:
    # Estimación: 1 token ≈ 4 caracteres (aproximación suficiente para el MVP)
    char_budget = token_budget * 4
    
    if len(text) <= char_budget:
        return text
    
    # Cortar en el último salto de línea doble (separador entre registros)
    truncated = text[:char_budget]
    last_break = truncated.rfind("\n\n")
    
    if last_break > char_budget * 0.5:  # Solo si el corte no es demasiado agresivo
        return truncated[:last_break]
    
    return truncated
```

### Paso 5 — SHA-256 del resultado
El hash se calcula sobre el Markdown final (después del truncate). Este hash es el que el pipeline compara para deduplicación.

```python
import hashlib

def _compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
```

---

## Buenas prácticas

### Orden de herramientas
- **Siempre intenta Trafilatura primero.** Solo usa BeautifulSoup como fallback si Trafilatura retorna None o menos de 200 caracteres.
- No apliques markdownify al output de Trafilatura cuando ya pediste `output_format="markdown"` — ya viene en Markdown.

### Estimación de tokens
- Usa la aproximación `len(text) / 4` para `estimated_tokens`. No instancies un tokenizer real — no vale la complejidad para el MVP.

### Medición de tamaños
```python
original_size_kb = len(html.encode("utf-8")) / 1024
processed_size_kb = len(markdown.encode("utf-8")) / 1024
```

### Manejo de fallos
- Si todo el pipeline de limpieza falla y el resultado es texto vacío, retorna el output con `markdown: ""` y `estimated_tokens: 0`. No lances excepción — el pipeline sabrá qué hacer.

### Testing
```python
# test_preprocessor.py — lo que debes verificar
def test_size_reduction():
    # El markdown resultante debe ser < 2% del HTML original
    assert result["processed_size_kb"] < result["original_size_kb"] * 0.02

def test_hash_is_deterministic():
    # El mismo HTML siempre produce el mismo hash
    r1 = preprocessor.process(html=sample_html, token_budget=4000)
    r2 = preprocessor.process(html=sample_html, token_budget=4000)
    assert r1["content_hash"] == r2["content_hash"]

def test_token_budget_respected():
    result = preprocessor.process(html=large_html, token_budget=500)
    assert result["estimated_tokens"] <= 550  # Margen del 10%

def test_no_html_tags_in_output():
    # El markdown no debe contener tags HTML residuales
    assert "<script" not in result["markdown"]
    assert "<style" not in result["markdown"]
    assert "<nav" not in result["markdown"]
```

---

## Qué elimina cada herramienta (referencia)

| Herramienta | Elimina | Conserva |
|---|---|---|
| Trafilatura | Scripts, publicidad, navegación, comentarios HTML | Texto principal, tablas, listas, headings |
| BeautifulSoup | `<script>`, `<style>`, `<nav>`, `<footer>`, `<header>`, `<aside>`, `<iframe>` | Texto visible, tablas de datos |
| markdownify | Tags HTML, atributos, clases, IDs | Estructura semántica (`##`, `-`, `\|tabla\|`) |
| smart_truncate | Contenido que excede el token_budget | Registros completos (no corta a mitad) |

---

## Lo que NO debes hacer

- ❌ No uses un tokenizer real (tiktoken, etc.) para contar tokens — la aproximación `/4` es suficiente para el MVP.
- ❌ No modifiques el hash una vez calculado — el pipeline de deduplicación depende de que sea consistente entre corridas.
- ❌ No loggees el HTML completo ni el Markdown completo en producción — solo tamaños y hash.
- ❌ No apliques `smart_truncate` antes de limpiar el HTML — trunca siempre sobre el Markdown final limpio.
- ❌ No lances excepciones al pipeline — cualquier fallo interno retorna un objeto con `markdown: ""`.

---

## Criterio de éxito de este rol

El trabajo está terminado cuando:
1. HTML real de ~400KB se convierte en Markdown de ~2–5KB.
2. El hash es determinístico (mismo input = mismo hash siempre).
3. El `token_budget` se respeta (no se pasan más tokens de los configurados).
4. No hay tags HTML (`<script>`, `<nav>`, etc.) en el Markdown resultante.
5. `test_preprocessor.py` pasa con HTML real de un sitio de plaza.