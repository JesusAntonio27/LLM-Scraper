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
        # FIX P5: antes se rechazaba si CUALQUIER lista estaba vacía — un schema con
        # "stores" y "promotions" fallaba si no había promociones aunque hubiera tiendas.
        # Correcto: rechazar solo si TODAS las listas están vacías (extracción total fallida).
        list_values = [v for v in data.values() if isinstance(v, list)]
        if list_values and all(len(lst) == 0 for lst in list_values):
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

    # ── Descubrimiento de Schema ───────────────────────────────────

    async def extract_schema_discovery(
        self,
        markdown: str,
        output_hint: str,
        token_budget: int = 4000
    ) -> dict:
        """
        FIX P7: método dedicado para POST /extract/discover.
        Tiene su propio system prompt orientado a GENERAR un JSON Schema,
        no a extraer datos. Antes se abusaba de extract() con schema={},
        lo que generaba una contradicción entre el system prompt ("cumple el schema")
        y el hint ("genera el schema").
        """
        model_id = MODEL_MAP["sonnet"]
        system_prompt = (
            "Eres un analista de estructuras de datos web. "
            "Tu tarea es analizar contenido Markdown de una página y generar "
            "el JSON Schema óptimo para extraer sus datos estructurados. "
            "Retorna ÚNICAMENTE un JSON Schema válido con 'type', 'properties' y sus tipos. "
            "Sin backticks, sin explicaciones, sin texto adicional."
        )
        user_prompt = (
            f"Hint del usuario: {output_hint}\n\n"
            f"Contenido de la página:\n{markdown}\n\n"
            "Genera el JSON Schema para extraer los datos estructurados de esta página."
        )
        retry_prompt = (
            "El JSON que retornaste no es un JSON Schema válido. "
            "Retorna un objeto con 'type': 'object' y 'properties' con los campos detectados. "
            "Sin backticks, sin texto adicional."
        )

        start_time = time.monotonic()
        tokens_input = 0
        tokens_output = 0
        cost_usd = 0.0

        try:
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

            if parsed is not None and isinstance(parsed, dict) and len(parsed) > 0:
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

            # Reintento
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

            retry_raw = retry_response.content[0].text
            retry_parsed = self._try_parse_json(retry_raw)
            llm_ms = int((time.monotonic() - start_time) * 1000)

            if retry_parsed is not None and isinstance(retry_parsed, dict) and len(retry_parsed) > 0:
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

            return {
                "status": "failed",
                "raw_response": retry_raw,
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
            # FIX 9: si ya visitamos esta URL, retornar el contenido cacheado
            if url in self._visited_urls:
                logger.info("fetch_page cache hit | url=%s", url)
                return self._last_page_content or "Contenido vacío (cacheado)"
            fetch_result = await fetcher.fetch(url=url, **clean_opts)
            if fetch_result["status"] == "failed":
                return f"Error fetching {url}: {fetch_result['error']}"
            pre = preprocessor.process(fetch_result["html"])
            content = pre["markdown"] or "Contenido vacío"
            # FIX 3: actualizar caché de contenido y marcar URL como visitada
            self._last_page_content = content
            self._last_page_html = fetch_result["html"]  # FIX C: HTML crudo para extract_links
            self._visited_urls.add(url)
            return content

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
            content = pre["markdown"] or "Sin cambios tras el click"
            self._last_page_content = content  # FIX 3: actualizar caché
            self._last_page_html = fetch_result["html"]  # FIX C
            return content

        elif tool_name == "scroll_page":
            times = tool_input.get("times", 1)
            # FIX 4: respetar el parámetro direction que el agente especificó
            direction = tool_input.get("direction", "down")
            scroll_pages = 10 if direction == "bottom" else 5
            instructions = []
            for _ in range(times):
                instructions.append({
                    "type": "scroll",
                    "coordinate_x": 0,
                    "coordinate_y": 0,
                    "scroll_direction": "down",
                    "scroll_pages": scroll_pages
                })
                instructions.append({"type": "wait", "wait_time_s": 1})
            fetch_result = await fetcher.fetch(
                url=current_url,
                browser_instructions=instructions,
                **clean_opts
            )
            if fetch_result["status"] == "failed":
                return f"Scroll failed: {fetch_result['error']}"
            pre = preprocessor.process(fetch_result["html"])
            content = pre["markdown"] or "Sin cambios tras el scroll"
            self._last_page_content = content  # FIX 3: actualizar caché
            self._last_page_html = fetch_result["html"]  # FIX C
            return content

        elif tool_name == "wait_and_get":
            seconds = tool_input.get("seconds", 2)
            instructions = [{"type": "wait", "wait_time_s": seconds}]
            fetch_result = await fetcher.fetch(
                url=current_url,
                browser_instructions=instructions,
                **clean_opts
            )
            if fetch_result["status"] == "failed":
                return f"wait_and_get failed: {fetch_result['error']}"
            pre = preprocessor.process(fetch_result.get("html", ""))
            content = pre["markdown"] or "Sin contenido"
            self._last_page_content = content  # FIX 3: actualizar caché
            self._last_page_html = fetch_result.get("html", "")  # FIX C
            return content

        elif tool_name == "extract_links":
            # FIX C: si ya tenemos el HTML de esta URL en caché, evitar llamada a Oxylabs
            if current_url in self._visited_urls and self._last_page_html:
                logger.info("extract_links cache hit | url=%s", current_url)
                html_to_parse = self._last_page_html
            else:
                fetch_result = await fetcher.fetch(url=current_url, **clean_opts)
                if fetch_result["status"] == "failed":
                    return "[]"
                html_to_parse = fetch_result["html"]
                self._last_page_html = html_to_parse
                self._visited_urls.add(current_url)
            from bs4 import BeautifulSoup
            from urllib.parse import urljoin, urlparse
            soup = BeautifulSoup(html_to_parse, "html.parser")
            pattern = tool_input.get("pattern", "")
            # FIX 6: si el patrón es URL completa, extraer solo el path para comparar con hrefs relativos
            if pattern.startswith("http"):
                pattern = urlparse(pattern).path
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
            # FIX 3: usar el caché del último fetch — sin llamada extra a Oxylabs
            if self._last_page_content:
                return self._last_page_content
            # Fallback: primer uso antes de cualquier fetch
            fetch_result = await fetcher.fetch(url=current_url, **clean_opts)
            pre = preprocessor.process(fetch_result.get("html", ""))
            content = pre["markdown"] or "Sin contenido"
            self._last_page_content = content
            return content

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
                geo_location=fetch_options.get("geo_location", "Mexico"),
                timeout=fetch_options.get("timeout", 30)  # FIX 8: heredar timeout del request
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
        max_iterations: int = 40,
        initial_html: str = ""
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

        # FIX 3: caché del último contenido fetchado — evita llamadas extra a Oxylabs en get_current_content
        self._last_page_content: str = markdown  # inicializar con el markdown ya disponible
        # FIX P4: inicializar con el HTML crudo del pipeline — extract_links sobre la URL
        # inicial ya no necesita hacer un fetch extra a Oxylabs
        self._last_page_html: str = initial_html
        # FIX 9: URLs ya visitadas — evita re-fetchear la misma página
        self._visited_urls: set = {url}  # la URL inicial ya fue fetchada por el pipeline

        self._init_navigation_context(context_file, url, schema, output_hint)

        system = f"""Eres un agente de extracción web. Tu objetivo es extraer datos estructurados de páginas web usando las tools disponibles.

Contexto del sitio: {output_hint}

Schema que debes poblar:
{json.dumps(schema, indent=2, ensure_ascii=False)}

REGLAS DE EXTRACCIÓN:
- Evalúa primero si el contenido que ya tienes es suficiente.
- Si lo es, usa finish() directamente con los datos extraídos.
- Si no, navega usando las tools hasta obtener los datos.
- NUNCA inventes datos — usa null si un campo no existe.
- Cuando tengas suficiente información, llama a finish().

REGLA DE ACUMULACIÓN — CRÍTICA:
Cada vez que extraes items de una página o categoría, RECUÉRDALOS.
Cuando llames finish(), el JSON debe contener TODOS los items encontrados
en TODAS las páginas/categorías visitadas, no solo los de la última.
Antes de llamar finish(), verifica: ¿Incluí los datos de CADA sección visitada?
Si no → sigue navegando hasta tenerlos todos.
NO llames finish() después de la primera categoría — espera a tener TODAS.

REGLAS DE NORMALIZACIÓN (MUY IMPORTANTE):
- Los nombres deben ser legibles y naturales.
- Ejemplo: "Dairy Queen" es correcto. "dairy-queen" (kebab-case) o "DAIRY QUEEN" (ALL CAPS) NO son correctos.
- Si extraes nombres de URLs o selectores con guiones, conviértelos a mayúsculas iniciales y espacios (ej. "h-and-m" -> "H&M").

CUÁNDO USAR give_up:
Úsalo SOLO si se cumplen las dos condiciones juntas:
  1. Has intentado al menos 4 herramientas distintas.
  2. El contenido retornado en TODAS las iteraciones fue vacío o idéntico (el sitio no cambia sin importar lo que hagas).

NO uses give_up si:
  - El sitio tiene un menú de categorías visible — eso es contenido navegable, no un sitio vacío.
  - Solo has intentado 1 o 2 estrategias.
  - Hay texto en la página aunque sea de navegación.
  - No has probado call_api() todavía.

PATRÓN: Sitio con menú de categorías
Si detectas un menú con categorías pero el contenido principal está vacío:
1. extract_links(patrón del menú) -> obtener todas las URLs de categorías.
2. Si no hay URLs separadas, para cada categoría visible en el menú:
   click_element(selector de la categoría)
   wait_and_get(2)
   get_current_content() -> ACUMULAR items encontrados en memoria.
3. Repetir para TODAS las categorías.
4. finish() con TODOS los datos acumulados de todas las categorías.

NOTA sobre get_current_content():
Retorna el Markdown del último fetch realizado. Es instantáneo y gratuito.
Úsalo para leer el estado actual sin gastar un fetch nuevo.

NOTA sobre click_element vs fetch_page:
Si conoces la URL destino de un link, SIEMPRE usa fetch_page(url) en lugar de click_element().
click_element() no actualiza la URL activa del agente — los tools subsecuentes (scroll, extract_links)
seguirán operando sobre la URL anterior aunque el click haya navegado a otra página.
Usa click_element() SOLO para acciones sin navegación: abrir dropdowns, activar tabs de SPA,
expandir acordeones — donde el contenido cambia pero la URL no."""

        messages = [{
            "role": "user",
            "content": f"""URL: {url}

Contenido disponible (ya preprocesado):
{markdown}

Evalúa si este contenido es suficiente para extraer los datos del schema.
Si lo es, usa finish() con el JSON. Si no, navega la página para obtenerlos."""
        }]

        current_url = url  # rastrear la URL activa durante la navegación

        try:
            while iteration < max_iterations:
                iteration += 1

                response = await self.client.messages.create(
                    model=model_id,
                    max_tokens=16384,  # FIX P2: 4096 cortaba finish() con 60+ registros → JSON malformado
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

                    if tool_name == "finish":
                        candidate = tool_input.get("data", {})
                        # FIX B: validar antes de aceptar — finish() con listas vacías
                        # era silenciosamente devuelto como status="extracted" con data vacía.
                        if self._validates_schema(candidate, schema):
                            final_data = candidate
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": "Navegación completada."
                            })
                            break
                        else:
                            # Identificar qué listas están vacías para dar feedback preciso
                            empty_keys = [
                                k for k, v in candidate.items()
                                if isinstance(v, list) and len(v) == 0
                            ] if isinstance(candidate, dict) else ["data"]
                            feedback = (
                                f"Rechazado: el JSON tiene listas vacías en: {empty_keys}. "
                                "Sigue navegando — extrae los datos reales antes de llamar finish(). "
                                "Si ya intentaste todo y el sitio no tiene datos, usa give_up()."
                            )
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": feedback
                            })
                            # FIX P1: continuar al siguiente bloque — sin continue, el flujo
                            # caía en _execute_tool("finish",...) y agregaba un segundo
                            # tool_result con el mismo tool_use_id → error 400 de Anthropic API
                            continue

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
                        tool_name, tool_input, current_url, fetch_options
                    )

                    # Actualizar current_url si el agente navegó a una nueva página
                    if tool_name == "fetch_page" and tool_input.get("url"):
                        current_url = tool_input["url"]

                    self._update_navigation_context(
                        context_file, iteration, tool_name, tool_input,
                        result_summary=result[:200]
                    )

                    # FIX 2: truncar tool results largos para evitar context explosion
                    # ~2K tokens = ~8000 chars es suficiente para que el agente tome decisiones
                    MAX_TOOL_RESULT_CHARS = 8000
                    truncated_result = result if len(result) <= MAX_TOOL_RESULT_CHARS else (
                        result[:MAX_TOOL_RESULT_CHARS] +
                        f"\n\n[...contenido truncado — {len(result) - MAX_TOOL_RESULT_CHARS} chars omitidos para preservar contexto]"
                    )

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": truncated_result
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
