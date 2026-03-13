# Skill: LLM Engineer

## Rol
Eres el responsable de convertir Markdown limpio en datos estructurados usando Claude. Tu trabajo es diseñar el prompt correcto, seleccionar el modelo adecuado, validar que el JSON retornado cumple el schema, y manejar el reintento cuando no lo cumple. También eres responsable de medir y reportar el costo exacto de cada extracción.

---

## Archivos de tu responsabilidad

```
llm-scraper-api/
├── app/
│   └── services/
│       └── llm_extractor.py     ← Tu único archivo de implementación
└── tests/
    └── test_llm_extractor.py    ← Test con Markdown real
```

---

## Contrato que debes cumplir

El pipeline (`services/pipeline.py`) llamará a tu servicio así:

```python
result = await llm_extractor.extract(
    markdown="## Tiendas\n\n### Zara\nPiso: PB...",
    schema={"stores": [{"name": "string", "category": "string", "floor": "string | null"}]},
    output_hint="Directorio de tiendas de una plaza comercial en México",
    model="haiku",           # "haiku" | "sonnet"
    token_budget=4000
)
```

Tu función debe retornar uno de estos dos resultados:

```python
# Éxito
{
    "status": "extracted",
    "data": {"stores": [{"name": "Zara", "category": "Moda", "floor": "PB"}]},
    "meta": {
        "tokens_input": 820,
        "tokens_output": 423,
        "model_used": "claude-haiku-4-5-20251001",
        "cost_usd": 0.000187,
        "llm_ms": 790
    }
}

# Fallo (después de reintento)
{
    "status": "failed",
    "raw_response": "texto crudo que retornó el LLM",
    "meta": {
        "tokens_input": 820,
        "tokens_output": 150,
        "model_used": "claude-haiku-4-5-20251001",
        "cost_usd": 0.000090,
        "llm_ms": 600
    }
}
```

---

## Selección de modelo

| Contexto | Modelo a usar |
|---|---|
| `/extract` con schema conocido (default) | `claude-haiku-4-5-20251001` |
| `/extract` con `model: "sonnet"` forzado por el cliente | `claude-sonnet-4-6` |
| `/extract/discover` — siempre | `claude-sonnet-4-6` (sin excepción) |

```python
MODEL_MAP = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6"
}
```

---

## Diseño del prompt

El prompt tiene tres componentes. El orden importa:

### 1. System prompt (contexto del rol)
```
Eres un extractor de datos estructurados. Tu tarea es extraer información de contenido web en formato Markdown y retornar ÚNICAMENTE un objeto JSON válido que cumpla exactamente el schema proporcionado. No incluyas explicaciones, no incluyas backticks, no incluyas texto fuera del JSON.
```

### 2. User prompt (instrucción con datos)
```
Contexto: {output_hint}

Schema esperado (JSON Schema):
{json.dumps(schema, indent=2, ensure_ascii=False)}

Contenido a extraer:
{markdown}

Retorna ÚNICAMENTE el JSON. Sin backticks, sin explicaciones.
```

### 3. Prompt de reintento (cuando el JSON no cumple el schema)
```
El JSON que retornaste no cumple el schema. Intenta de nuevo.

Schema esperado:
{json.dumps(schema, indent=2, ensure_ascii=False)}

Retorna ÚNICAMENTE el JSON válido que cumpla exactamente el schema. Sin backticks, sin texto adicional.
```

---

## Lógica de validación y reintento

```python
import json
import time
from anthropic import AsyncAnthropic

client = AsyncAnthropic()

async def extract(markdown, schema, output_hint, model="haiku", token_budget=4000):
    model_id = MODEL_MAP.get(model, MODEL_MAP["haiku"])
    
    # Intento 1
    start = time.monotonic()
    response = await _call_claude(model_id, markdown, schema, output_hint)
    llm_ms = int((time.monotonic() - start) * 1000)
    
    parsed = _try_parse_json(response.content[0].text)
    
    if parsed is not None and _validates_schema(parsed, schema):
        return _build_success(parsed, response, model_id, llm_ms)
    
    # Reintento único
    start = time.monotonic()
    retry_response = await _call_claude_retry(model_id, schema)
    llm_ms += int((time.monotonic() - start) * 1000)
    
    parsed_retry = _try_parse_json(retry_response.content[0].text)
    
    if parsed_retry is not None and _validates_schema(parsed_retry, schema):
        return _build_success(parsed_retry, retry_response, model_id, llm_ms)
    
    # Fallo definitivo
    return _build_failed(retry_response, model_id, llm_ms)
```

---

## Cálculo de costos

Calcula el costo en USD basado en los tokens reportados por la API de Anthropic. Usa estas tarifas (por millón de tokens):

| Modelo | Input | Output |
|---|---|---|
| claude-haiku-4-5-20251001 | $0.80 | $4.00 |
| claude-sonnet-4-6 | $3.00 | $15.00 |

```python
PRICING = {
    "claude-haiku-4-5-20251001":  {"input": 0.80 / 1_000_000, "output": 4.00 / 1_000_000},
    "claude-sonnet-4-6":          {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
}

def _calculate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    prices = PRICING.get(model_id, PRICING["claude-haiku-4-5-20251001"])
    return round(
        input_tokens * prices["input"] + output_tokens * prices["output"],
        6
    )
```

---

## Buenas prácticas

### Parsing defensivo de JSON
El LLM a veces incluye backticks o texto antes/después del JSON aunque se le indique que no. Siempre limpiar antes de parsear:

```python
def _try_parse_json(text: str) -> dict | None:
    # Eliminar backticks y bloques de código
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]
    clean = clean.strip("`").strip()
    
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return None
```

### Validación de schema
Para el MVP, la validación es **estructural superficial**: verificar que las claves del primer nivel del schema existen en el JSON retornado. No necesitas jsonschema completo:

```python
def _validates_schema(data: dict, schema: dict) -> bool:
    for key in schema.keys():
        if key not in data:
            return False
    return True
```

### Logging
Loggea: modelo usado, tokens input/output, costo, éxito/fallo, y si hubo reintento. No loggees el contenido del markdown ni el JSON completo en producción.

---

## Lo que NO debes hacer

- ❌ No hagas más de un reintento — el documento del MVP especifica exactamente uno.
- ❌ No uses `/discover` con Haiku bajo ninguna circunstancia — siempre Sonnet.
- ❌ No inventes el costo — usa únicamente los tokens reportados por `response.usage`.
- ❌ No lances excepción si el JSON no cumple el schema — retorna `status: "failed"` con el texto crudo.
- ❌ No modifiques el Markdown antes de enviarlo al LLM — eso ya lo hizo el Data Engineer.
- ❌ No incluyas el API key de Anthropic en el código — usa `settings.anthropic_api_key` o deja que el cliente lo lea del entorno automáticamente.

---

## Criterio de éxito de este rol

El trabajo está terminado cuando:
1. `test_llm_extractor.py` toma Markdown real de una plaza y retorna JSON con tiendas estructuradas.
2. El JSON retornado cumple exactamente el schema enviado.
3. El costo calculado en `cost_usd` corresponde a los tokens reales de la respuesta.
4. Un JSON inválido en el primer intento desencadena exactamente un reintento.
5. Después del reintento fallido, el status es `"failed"` con el texto crudo — sin excepción.