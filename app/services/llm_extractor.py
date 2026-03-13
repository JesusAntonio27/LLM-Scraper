import json
import logging
import time
from anthropic import AsyncAnthropic

from app.config import settings
from app.services.oxylabs import OxylabsFetcher
from app.services.preprocessor import HtmlPreprocessor

logger = logging.getLogger(__name__)

MODEL_MAP = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6"
}

PRICING = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00}
}

NAVIGATION_TOOLS = [
    {
        "name": "fetch_page",
        "description": "Obtiene el contenido de una URL como Markdown limpio.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL a fetchear"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "click_element",
        "description": "Hace click en un elemento de la página actual.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "selector_type": {
                    "type": "string",
                    "enum": ["css", "xpath", "text"],
                    "default": "css"
                }
            },
            "required": ["selector"]
        }
    },
    {
        "name": "scroll_page",
        "description": "Hace scroll en la página para revelar contenido dinámico.",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["down", "up", "bottom"],
                    "default": "bottom"
                },
                "times": {"type": "integer", "default": 1}
            }
        }
    },
    {
        "name": "wait_and_get",
        "description": "Espera N segundos y retorna el HTML actualizado.",
        "input_schema": {
            "type": "object",
            "properties": {
                "seconds": {"type": "integer", "default": 2}
            }
        }
    },
    {
        "name": "extract_links",
        "description": "Extrae hrefs de la página que coincidan con el patrón.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "String que debe estar en el href. Opcional, si se omite retorna todos los links."
                }
            }
        }
    },
    {
        "name": "get_current_content",
        "description": "Retorna el Markdown del estado actual de la página.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "finish",
        "description": "Termina la navegación y retorna el JSON final con los datos extraídos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "description": "JSON que cumple el schema solicitado"
                }
            },
            "required": ["data"]
        }
    },
    {
        "name": "call_api",
        "description": (
            "Llama directamente a una API interna del sitio. "
            "Usar cuando se conoce o sospecha un endpoint que devuelve "
            "los datos en JSON o HTML sin necesidad de render. "
            "Más eficiente que navegar el DOM cuando el endpoint existe."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL completa del endpoint"
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST"],
                    "default": "GET"
                },
                "payload": {
                    "type": "object",
                    "description": "Form data o JSON para POST (opcional)"
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "give_up",
        "description": (
            "Abandona la extracción de este sitio cuando después de intentar "
            "múltiples estrategias el contenido sigue siendo inaccesible. "
            "Usar solo cuando: (1) el HTML está vacío con y sin JS, "
            "(2) los clicks y scrolls no cambian el contenido, "
            "(3) no hay API ni __NEXT_DATA__ accesibles. "
            "NO usar si aún hay estrategias sin intentar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Por qué no fue posible extraer datos"
                },
                "strategies_tried": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista de tools que se intentaron"
                },
                "partial_data": {
                    "type": "object",
                    "description": "Datos parciales si se encontró algo (puede estar vacío)"
                }
            },
            "required": ["reason", "strategies_tried"]
        }
    }
]

class LLMExtractor:
    def __init__(self):
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    def _build_system_prompt(self) -> str:
        return (
            "Eres un extractor de datos estructurados. Tu tarea es extraer información "
            "de contenido web en formato Markdown y retornar ÚNICAMENTE un objeto JSON "
            "válido que cumpla exactamente el schema proporcionado. No incluyas explicaciones, "
            "no incluyas backticks, no incluyas texto fuera del JSON."
        )

    def _build_user_prompt(self, markdown: str, schema: dict, output_hint: str, content_type: str = "markdown") -> str:
        schema_json = json.dumps(schema, indent=2, ensure_ascii=False)
        
        if content_type == "html":
            content_label = "HTML simplificado a analizar"
            extra_instruction = """
El contenido está en formato HTML simplificado.
Analiza la estructura del DOM para identificar el patrón de los datos.
Busca el texto en atributos aria-label, title, data-*, 
y en elementos h2/h3/h4/span/p dentro de componentes repetidos.
"""
        else:
            content_label = "Contenido a extraer"
            extra_instruction = ""
            
        return (
            f"Contexto: {output_hint}\n\n"
            f"{extra_instruction}\n"
            f"Schema esperado (JSON Schema):\n{schema_json}\n\n"
            f"{content_label}:\n{markdown}\n\n"
            f"Retorna ÚNICAMENTE el JSON. Sin backticks, sin explicaciones."
        )

    def _build_retry_prompt(self, schema: dict) -> str:
        schema_json = json.dumps(schema, indent=2, ensure_ascii=False)
        return (
            "El JSON que retornaste no cumple el schema. Intenta de nuevo.\n\n"
            f"Schema esperado:\n{schema_json}\n\n"
            "Retorna ÚNICAMENTE el JSON válido que cumpla exactamente el schema. Sin backticks, sin texto adicional."
        )

    def _try_parse_json(self, text: str) -> dict | None:
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

    def _validates_schema(self, data: dict, schema: dict) -> bool:
        if not isinstance(data, dict):
            return False
        for key in schema.keys():
            if key not in data:
                return False
        return True

    def _calculate_cost(self, model_id: str, input_tokens: int, output_tokens: int) -> float:
        prices = PRICING.get(model_id, PRICING["claude-haiku-4-5-20251001"])
        cost = (input_tokens * (prices["input"] / 1_000_000)) + (output_tokens * (prices["output"] / 1_000_000))
        return round(cost, 6)

    async def extract(
        self, 
        markdown: str, 
        schema: dict, 
        output_hint: str, 
        model: str = "haiku", 
        token_budget: int = 4000,
        content_type: str = "markdown"
    ) -> dict:
        model_id = MODEL_MAP.get(model, MODEL_MAP["haiku"])
        
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(markdown, schema, output_hint, content_type)
        retry_prompt = self._build_retry_prompt(schema)
        
        start_time = time.monotonic()
        tokens_input = 0
        tokens_output = 0
        cost_usd = 0.0
        
        try:
            # Intento 1
            response = await self.client.messages.create(
                model=model_id,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=token_budget,
            )
            
            tokens_input += response.usage.input_tokens
            tokens_output += response.usage.output_tokens
            cost_usd += self._calculate_cost(model_id, response.usage.input_tokens, response.usage.output_tokens)
            
            raw_text = response.content[0].text
            parsed = self._try_parse_json(raw_text)
            
            if parsed is not None and self._validates_schema(parsed, schema):
                llm_ms = int((time.monotonic() - start_time) * 1000)
                return {
                    "status": "extracted",
                    "data": parsed,
                    "meta": {
                        "tokens_input": tokens_input,
                        "tokens_output": tokens_output,
                        "model_used": model_id,
                        "cost_usd": round(cost_usd, 6),
                        "llm_ms": llm_ms
                    }
                }
            
            # Reintento único
            retry_response = await self.client.messages.create(
                model=model_id,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": raw_text},
                    {"role": "user", "content": retry_prompt}
                ],
                max_tokens=token_budget,
            )
            
            tokens_input += retry_response.usage.input_tokens
            tokens_output += retry_response.usage.output_tokens
            cost_usd += self._calculate_cost(model_id, retry_response.usage.input_tokens, retry_response.usage.output_tokens)
            
            retry_raw_text = retry_response.content[0].text
            retry_parsed = self._try_parse_json(retry_raw_text)
            
            llm_ms = int((time.monotonic() - start_time) * 1000)
            
            if retry_parsed is not None and self._validates_schema(retry_parsed, schema):
                return {
                    "status": "extracted",
                    "data": retry_parsed,
                    "meta": {
                        "tokens_input": tokens_input,
                        "tokens_output": tokens_output,
                        "model_used": model_id,
                        "cost_usd": round(cost_usd, 6),
                        "llm_ms": llm_ms
                    }
                }
                
            # Fallo definitivo
            return {
                "status": "failed",
                "raw_response": retry_raw_text,
                "meta": {
                    "tokens_input": tokens_input,
                    "tokens_output": tokens_output,
                    "model_used": model_id,
                    "cost_usd": round(cost_usd, 6),
                    "llm_ms": llm_ms
                }
            }
            
        except Exception as e:
            llm_ms = int((time.monotonic() - start_time) * 1000)
            return {
                "status": "failed",
                "raw_response": str(e),
                "meta": {
                    "tokens_input": tokens_input,
                    "tokens_output": tokens_output,
                    "model_used": model_id,
                    "cost_usd": round(cost_usd, 6),
                    "llm_ms": llm_ms
                }
            }

    # ── Modo Agentic ──────────────────────────────────────────────

    async def _execute_tool(
        self,
        tool_name: str,
        tool_input: dict,
        current_url: str,
        fetch_options: dict
    ) -> str:
        """
        Ejecuta una tool y retorna el resultado como string para Claude.
        """
        fetcher = OxylabsFetcher()
        preprocessor = HtmlPreprocessor()
        # Limpiar browser_instructions y valores None del dict para evitar
        # conflicto con las instrucciones específicas de cada tool
        clean_opts = {k: v for k, v in fetch_options.items()
                      if k != "browser_instructions" and v is not None}

        if tool_name == "fetch_page":
            url = tool_input.get("url", current_url)
            fetch_result = await fetcher.fetch(url=url, **clean_opts)
            if fetch_result["status"] == "failed":
                return f"Error fetching {url}: {fetch_result['error']}"
            pre = preprocessor.process(fetch_result["html"])
            return pre["markdown"] or "Contenido vacío"

        elif tool_name == "click_element":
            instructions = [{
                "type": "click",
                "selector": {
                    "type": tool_input.get("selector_type", "css"),
                    "value": tool_input["selector"]
                }
            }, {"type": "wait", "wait_time_s": 2}]
            fetch_result = await fetcher.fetch(
                url=current_url,
                browser_instructions=instructions,
                **clean_opts
            )
            if fetch_result["status"] == "failed":
                return f"Click failed: {fetch_result['error']}"
            pre = preprocessor.process(fetch_result["html"])
            return pre["markdown"] or "Sin cambios tras el click"

        elif tool_name == "scroll_page":
            times = tool_input.get("times", 1)
            instructions = []
            for _ in range(times):
                instructions.append({"type": "scroll_to_bottom"})
                instructions.append({"type": "wait", "wait_time_s": 1})
            fetch_result = await fetcher.fetch(
                url=current_url,
                browser_instructions=instructions,
                **clean_opts
            )
            if fetch_result["status"] == "failed":
                return f"Scroll failed: {fetch_result['error']}"
            pre = preprocessor.process(fetch_result["html"])
            return pre["markdown"] or "Sin cambios tras el scroll"

        elif tool_name == "wait_and_get":
            seconds = tool_input.get("seconds", 2)
            instructions = [{"type": "wait", "wait_time_s": seconds}]
            fetch_result = await fetcher.fetch(
                url=current_url,
                browser_instructions=instructions,
                **clean_opts
            )
            pre = preprocessor.process(fetch_result.get("html", ""))
            return pre["markdown"] or "Sin contenido"

        elif tool_name == "extract_links":
            fetch_result = await fetcher.fetch(url=current_url, **clean_opts)
            if fetch_result["status"] == "failed":
                return "[]"
            from bs4 import BeautifulSoup
            from urllib.parse import urljoin, urlparse
            soup = BeautifulSoup(fetch_result["html"], "html.parser")
            pattern = tool_input.get("pattern", "")
            base = f"{urlparse(current_url).scheme}://{urlparse(current_url).netloc}"
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if pattern in href:
                    full = urljoin(base, href)
                    if full not in links:
                        links.append(full)
            return str(links) if links else "[]"

        elif tool_name == "get_current_content":
            fetch_result = await fetcher.fetch(url=current_url, **clean_opts)
            pre = preprocessor.process(fetch_result.get("html", ""))
            return pre["markdown"] or "Sin contenido"

        elif tool_name == "finish":
            return "__FINISH__"

        elif tool_name == "call_api":
            url = tool_input["url"]
            method = tool_input.get("method", "GET")
            payload = tool_input.get("payload", None)

            result = await fetcher.fetch_api(
                url=url,
                method=method,
                payload=payload,
                geo_location=fetch_options.get("geo_location", "Mexico")
            )

            if result["status"] == "failed":
                return f"API call failed: {result['error']}"

            content = result["content"]

            # Intentar parsear como JSON para formatear mejor
            try:
                import json
                parsed = json.loads(content)
                lines = []
                preprocessor._flatten_json(parsed, lines)
                return "\n".join(lines[:500])  # máx 500 líneas al LLM
            except Exception:
                # Si no es JSON, retornar como texto (puede ser HTML con tiendas)
                pre = preprocessor.process(content)
                return pre["markdown"] or content[:3000]

        return "Tool no reconocida"

    async def extract_agentic(
        self,
        url: str,
        markdown: str,
        schema: dict,
        output_hint: str,
        fetch_options: dict = None,
        context_file: str = "navigation_context.md",
        max_iterations: int = 40
    ) -> dict:
        """
        Modo agentic: Claude decide si navegar y qué tools usar.
        Retorna el mismo formato que extract().
        """
        if fetch_options is None:
            fetch_options = {}
        start = time.monotonic()
        model_id = MODEL_MAP["sonnet"]  # Agentic siempre usa Sonnet
        total_input_tokens = 0
        total_output_tokens = 0
        iteration = 0

        self._init_navigation_context(context_file, url, schema, output_hint)

        system = f"""Eres un agente de extracción web especializado en directorios de centros comerciales.
Tienes acceso a tools para navegar páginas web y extraer datos estructurados.

Schema que debes poblar:
{json.dumps(schema, indent=2, ensure_ascii=False)}

Objetivo: {output_hint}

REGLAS DE EXTRACCIÓN:
- Evalúa primero si el contenido que ya tienes es suficiente.
- Si lo es, usa finish() directamente con los datos extraídos.
- Si no, navega usando las tools hasta obtener los datos.
- NUNCA inventes datos — usa null si un campo no existe.
- Cuando tengas suficiente información, llama a finish().

REGLAS DE NORMALIZACIÓN (MUY IMPORTANTE):
- Los nombres de las tiendas deben ser legibles y naturales.
- Ejemplo: "Dairy Queen" es correcto. "dairy-queen" (kebab-case) o "DAIRY QUEEN" (ALL CAPS) NO son correctos.
- Si extraes nombres de URLs o selectores con guiones, conviértelos a mayúsculas iniciales y espacios (ej. "h-and-m" -> "H&M" o "H and M").

CUÁNDO USAR give_up:
Úsalo SOLO si se cumplen las dos condiciones juntas:
  1. Has intentado al menos 4 herramientas distintas.
  2. El contenido retornado en TODAS las iteraciones fue vacío o idéntico (el sitio no cambia sin importar lo que hagas).

NO uses give_up si:
  - El sitio tiene un menú de categorías visible — eso es contenido navegable, no un sitio vacío.
  - Solo has intentado 1 o 2 estrategias.
  - Hay texto en la página aunque sea de navegación.
  - No has probado call_api() todavía.

PATRÓN: Sitio con menú de categorías (ej. Plaza Satélite)
Si detectas un menú con categorías (Restaurantes, Moda, Servicios, etc.) pero el contenido principal está vacío:
1. extract_links("/directorio" o el patrón del menú) -> obtener todas las URLs de categorías.
2. Si no hay URLs separadas, para cada categoría visible en el menú:
   click_element(".categoria-selector" o el texto de la categoría)
   wait_and_get(2)
   get_current_content() -> acumular tiendas encontradas.
3. Repetir para TODAS las categorías antes de llamar finish().
4. finish() con todos los datos acumulados de todas las categorías.
No llames finish() después de la primera categoría — espera a tener todas.
"""

        messages = [{
            "role": "user",
            "content": f"""URL: {url}

Contenido disponible (ya preprocesado):
{markdown}

Evalúa si este contenido es suficiente para extraer los datos del schema.
Si lo es, usa finish() con el JSON. Si no, navega la página para obtenerlos."""
        }]

        try:
            while iteration < max_iterations:
                iteration += 1

                response = await self.client.messages.create(
                    model=model_id,
                    max_tokens=4096,
                    system=system,
                    tools=NAVIGATION_TOOLS,
                    messages=messages
                )

                total_input_tokens += response.usage.input_tokens
                total_output_tokens += response.usage.output_tokens

                messages.append({
                    "role": "assistant",
                    "content": response.content
                })

                # Procesar tool calls
                tool_results = []
                final_data = None

                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    tool_name = block.name
                    tool_input = block.input

                    self._update_navigation_context(
                        context_file, iteration, tool_name, tool_input
                    )

                    if tool_name == "finish":
                        final_data = tool_input.get("data", {})
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "Navegación completada."
                        })
                        break

                    if tool_name == "give_up":
                        reason = tool_input.get("reason", "Sin razón especificada")
                        partial = tool_input.get("partial_data", {})
                        strategies = tool_input.get("strategies_tried", [])

                        self._close_navigation_context(
                            context_file,
                            total_records=len(self._count_records(partial, schema)),
                            status=f"Abandonado ⚠️ — {reason}"
                        )

                        llm_ms = int((time.monotonic() - start) * 1000)
                        cost = self._calculate_cost(
                            model_id, total_input_tokens, total_output_tokens
                        )
                        prices = PRICING.get(model_id, PRICING["claude-haiku-4-5-20251001"])

                        return {
                            "status":   "skipped",
                            "reason":   reason,
                            "data":     partial if partial else {},
                            "meta": {
                                "tokens_input":    total_input_tokens,
                                "tokens_output":   total_output_tokens,
                                "model_used":      model_id,
                                "cost_usd":        cost,
                                "cost_breakdown": {
                                    "input_tokens":  total_input_tokens,
                                    "output_tokens": total_output_tokens,
                                    "input_cost":    (total_input_tokens / 1_000_000) * prices["input"],
                                    "output_cost":   (total_output_tokens / 1_000_000) * prices["output"],
                                    "model":         model_id,
                                    "iterations":    iteration
                                },
                                "llm_ms":          llm_ms,
                                "agentic":         True,
                                "iterations":      iteration,
                                "gave_up":         True,
                                "strategies_tried": strategies
                            }
                        }

                    result = await self._execute_tool(
                        tool_name, tool_input, url, fetch_options
                    )

                    self._update_navigation_context(
                        context_file, iteration, tool_name, tool_input,
                        result_summary=result[:200]
                    )

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })

                # Claude llamó finish()
                if final_data is not None:
                    llm_ms = int((time.monotonic() - start) * 1000)
                    cost = self._calculate_cost(
                        model_id, total_input_tokens, total_output_tokens
                    )
                    prices = PRICING.get(model_id, PRICING["claude-haiku-4-5-20251001"])
                    records = self._count_records(final_data, schema)
                    self._close_navigation_context(context_file, len(records))
                    return {
                        "status": "extracted",
                        "data": final_data,
                        "meta": {
                            "tokens_input": total_input_tokens,
                            "tokens_output": total_output_tokens,
                            "model_used": model_id,
                            "cost_usd": cost,
                            "cost_breakdown": {
                                "input_tokens":  total_input_tokens,
                                "output_tokens": total_output_tokens,
                                "input_cost":    (total_input_tokens / 1_000_000) * prices["input"],
                                "output_cost":   (total_output_tokens / 1_000_000) * prices["output"],
                                "model":         model_id,
                                "iterations":    iteration
                            },
                            "llm_ms": llm_ms,
                            "agentic": True,
                            "iterations": iteration
                        }
                    }

                if response.stop_reason == "end_turn":
                    # Intentar rescatar JSON si no usó finish() pero escribió algo
                    for block in response.content:
                        if hasattr(block, "text"):
                            parsed = self._try_parse_json(block.text)
                            if parsed and self._validates_schema(parsed, schema):
                                llm_ms = int((time.monotonic() - start) * 1000)
                                cost = self._calculate_cost(
                                    model_id, total_input_tokens, total_output_tokens
                                )
                                prices = PRICING.get(model_id, PRICING["claude-haiku-4-5-20251001"])
                                return {
                                    "status": "extracted",
                                    "data": parsed,
                                    "meta": {
                                        "tokens_input": total_input_tokens,
                                        "tokens_output": total_output_tokens,
                                        "model_used": model_id,
                                        "cost_usd": cost,
                                        "cost_breakdown": {
                                            "input_tokens":  total_input_tokens,
                                            "output_tokens": total_output_tokens,
                                            "input_cost":    (total_input_tokens / 1_000_000) * prices["input"],
                                            "output_cost":   (total_output_tokens / 1_000_000) * prices["output"],
                                            "model":         model_id,
                                            "iterations":    iteration
                                        },
                                        "llm_ms": llm_ms,
                                        "agentic": True,
                                        "iterations": iteration
                                    }
                                }
                    break

                if tool_results:
                    messages.append({
                        "role": "user",
                        "content": tool_results
                    })

            # Si salimos por límite de iteraciones, buscar el último JSON válido en el historial
            for msg in reversed(messages):
                if msg["role"] == "assistant":
                    for block in msg["content"]:
                        if block.type == "text":
                            parsed = self._try_parse_json(block.text)
                            if parsed and len(self._count_records(parsed, schema)) > 0:
                                llm_ms = int((time.monotonic() - start) * 1000)
                                cost = self._calculate_cost(model_id, total_input_tokens, total_output_tokens)
                                prices = PRICING.get(model_id, PRICING["claude-haiku-4-5-20251001"])
                                return {
                                    "status": "extracted",
                                    "data": parsed,
                                    "meta": {
                                        "tokens_input": total_input_tokens,
                                        "tokens_output": total_output_tokens,
                                        "model_used": model_id,
                                        "cost_usd": cost,
                                        "cost_breakdown": {
                                            "input_tokens":  total_input_tokens,
                                            "output_tokens": total_output_tokens,
                                            "input_cost":    (total_input_tokens / 1_000_000) * prices["input"],
                                            "output_cost":   (total_output_tokens / 1_000_000) * prices["output"],
                                            "model":         model_id,
                                            "iterations":    iteration
                                        },
                                        "llm_ms": llm_ms,
                                        "agentic": True,
                                        "iterations": iteration,
                                        "hit_limit": True,
                                        "partial": True
                                    }
                                }

        except Exception as e:
            logger.error(f"Agentic extraction error: {e}")

        llm_ms = int((time.monotonic() - start) * 1000)
        cost = self._calculate_cost(model_id, total_input_tokens, total_output_tokens)
        prices = PRICING.get(model_id, PRICING["claude-haiku-4-5-20251001"])
        return {
            "status": "failed",
            "raw_response": "Agente no pudo extraer datos tras navegación",
            "meta": {
                "tokens_input": total_input_tokens,
                "tokens_output": total_output_tokens,
                "model_used": model_id,
                "cost_usd": cost,
                "cost_breakdown": {
                    "input_tokens":  total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "input_cost":    (total_input_tokens / 1_000_000) * prices["input"],
                    "output_cost":   (total_output_tokens / 1_000_000) * prices["output"],
                    "model":         model_id,
                    "iterations":    iteration
                },
                "llm_ms": llm_ms,
                "agentic": True,
                "iterations": iteration
            }
        }

    # ── Helpers de contexto de navegación ──────────────────────────

    def _init_navigation_context(self, filepath, url, schema, output_hint):
        try:
            content = f"""# Contexto de Navegación Activa

## URL actual
{url}

## Objetivo
Schema: {json.dumps(schema, ensure_ascii=False)}
Hint: {output_hint}

## Estado
En progreso

## Iteraciones
| # | Tool | Input | Resultado |
|---|---|---|---|

## Datos acumulados
0 registros

## Pendiente
Por explorar

## Decisiones tomadas
_Se irán registrando durante la navegación_
"""
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            pass

    def _update_navigation_context(
        self, filepath, iteration, tool_name, tool_input,
        result_summary=""
    ):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            input_str = str(tool_input)[:80].replace("|", "/")
            result_str = (result_summary or "ejecutado")[:80].replace("|", "/")
            new_row = f"| {iteration} | {tool_name} | {input_str} | {result_str} |\n"
            content = content.replace(
                "## Datos acumulados",
                new_row + "\n## Datos acumulados"
            )
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            pass

    def _close_navigation_context(
        self, filepath, total_records, status="Completado ✅"
    ):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            content = content.replace("En progreso", status)
            content = content.replace(
                "0 registros",
                f"{total_records} registros extraídos"
            )
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            pass

    def _count_records(self, data: dict, schema: dict) -> list:
        for value in data.values():
            if isinstance(value, list):
                return value
        return []
