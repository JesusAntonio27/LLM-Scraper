import trafilatura
from bs4 import BeautifulSoup
import logging
import hashlib

logger = logging.getLogger(__name__)

def _is_poor_result(markdown: str, original_size_kb: float) -> bool:
    ratio = len(markdown.encode()) / 1024 / original_size_kb
    ratio_pobre = ratio < 0.005          # Menos del 0.5% del HTML original
    
    lineas_utiles = [
        l for l in markdown.split("\n")
        if l.strip() and len(l.strip()) > 3   # Líneas con más de 3 chars
    ]
    contenido_pobre = len(lineas_utiles) < 10  # Menos de 10 líneas útiles
    
    return ratio_pobre or contenido_pobre  # Se activa si cualquiera de los dos falla

class HtmlPreprocessor:
    def _flatten_json(self, obj, lines, depth=0, max_depth=6):
        """
        Convierte JSON anidado en líneas de texto legibles.
        Preserva la jerarquía con indentación.
        Trunca listas largas para no exceder el token budget.
        """
        if depth > max_depth:
            return

        indent = "  " * depth

        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, (dict, list)):
                    lines.append(f"{indent}{key}:")
                    self._flatten_json(value, lines, depth + 1, max_depth)
                else:
                    if value is not None and str(value).strip():
                        lines.append(f"{indent}{key}: {value}")

        elif isinstance(obj, list):
            # Truncar listas muy largas — tomar máximo 200 items
            items = obj[:200]
            if len(obj) > 200:
                lines.append(f"{indent}[{len(obj)} items, mostrando primeros 200]")
            for i, item in enumerate(items):
                lines.append(f"{indent}[{i}]")
                self._flatten_json(item, lines, depth + 1, max_depth)

        else:
            if obj is not None and str(obj).strip():
                lines.append(f"{indent}{obj}")

    def _extract_next_data(self, html: str) -> str:
        """
        Intercepta __NEXT_DATA__ de sitios Next.js.
        Retorna Markdown con los datos estructurados, o "" si no encuentra nada.
        """
        import re, json

        # Patrón estándar de Next.js
        patterns = [
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            r'__NEXT_DATA__\s*=\s*({.*?})\s*(?:;|</script>)',
        ]

        raw = ""
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                raw = match.group(1)
                break

        if not raw:
            return ""

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return ""

        # Aplanar el JSON en texto legible para el LLM
        lines = []
        self._flatten_json(data, lines, depth=0, max_depth=6)

        result = "\n".join(lines)

        # Solo retornar si tiene contenido sustancial
        if len(result.strip()) < 100:
            return ""

        return result

    def _extract_json_ld(self, html: str) -> str:
        import re, json
        matches = re.findall(
            r'<script type="application/ld\+json">(.*?)</script>',
            html, re.DOTALL
        )
        results = []
        for m in matches:
            try:
                data = json.loads(m)
                # Solo si contiene arrays de items (tiendas, productos, etc.)
                found_bulk = False
                if isinstance(data, dict):
                    for value in data.values():
                        if isinstance(value, list) and len(value) > 3:
                            found_bulk = True
                            break
                elif isinstance(data, list) and len(data) > 3:
                    found_bulk = True

                if found_bulk:
                    lines = []
                    self._flatten_json(data, lines)
                    results.extend(lines)
            except Exception:
                continue
        return "\n".join(results)

    def _strategy_trafilatura(self, html: str) -> str:
        try:
            result = trafilatura.extract(
                html,
                include_tables=True,
                include_links=False,
                include_images=False,
                output_format="markdown",
                favor_recall=True,
                no_fallback=False
            )
            return result or ""
        except Exception as e:
            logger.error(f"Error in Trafilatura extraction: {e}")
            return ""

    def _strategy_structural(self, html: str) -> str:
        try:
            soup = BeautifulSoup(html, "html.parser")

            # Eliminar ruido real — solo lo que no aporta nunca
            for tag in soup(["script", "style", "iframe",
                             "noscript", "svg", "path"]):
                tag.decompose()

            lines = []

            # PASO A: Extraer texto de atributos que suelen contener nombres
            for tag in soup.find_all(True):
                # Caso especial: Imágenes sin alt/title -> intentar extraer del filename
                if tag.name == "img":
                    src = tag.get("src", "")
                    alt = tag.get("alt", "").strip()
                    if not alt and src and "/" in src:
                        # Extraer filename: /path/to/logo-adidas.png -> logo-adidas
                        filename = src.split("/")[-1].split(".")[0].lower()
                        # Solo ignorar si es EXACTAMENTE "logo", "icon", o similares
                        GENERIC_LOGOS = {"logo", "icon", "banner", "spacer", "image"}
                        if len(filename) > 3 and filename not in GENERIC_LOGOS:
                            # Limpiar palabras como "logo-", "-logo" pero conservar el resto
                            clean_name = filename.replace("logo-", "").replace("-logo", "").replace("_", " ").replace("-", " ")
                            if len(clean_name.strip()) > 3:
                                lines.append(clean_name.strip().capitalize())

                # Caso especial: Links sin texto -> intentar extraer slug del href
                if tag.name == "a":
                    href = tag.get("href", "")
                    direct_text = tag.get_text(strip=True)
                    # Si no hay texto, intentar procesar el link
                    if not direct_text and href and "/" in href:
                         path_parts = [p for p in href.split("/") if p and not p.startswith(("http", "www"))]
                         if path_parts:
                             # Extraer el último componente significativo: /tiendas/sushi-itto -> sushi-itto
                             slug = path_parts[-1].split(".")[0].split("?")[0].lower()
                             
                             GENERIC_SLUGS = {"index", "home", "default", "shop", "stores", "tiendas", "view", "details", "product", "item"}
                             if len(slug) > 3 and slug not in GENERIC_SLUGS:
                                 # Limpiar separadores
                                 clean_name = slug.replace("-", " ").replace("_", " ")
                                 if len(clean_name.strip()) > 3:
                                     lines.append(clean_name.strip().capitalize())

                # Atributos estándar
                for attr in ["aria-label", "title", "data-name",
                             "data-title", "data-store", "alt"]:
                    value = tag.get(attr, "").strip()
                    if value and 3 < len(value) < 100:
                        lines.append(value)

            # PASO B: Extraer texto de elementos semánticos preservando jerarquía
            SEMANTIC_TAGS = ["h1","h2","h3","h4","h5","h6",
                             "p","li","td","th","dt","dd",
                             "span","a","label","button"]

            for element in soup.find_all(SEMANTIC_TAGS, limit=3000):
                # get_text(strip=True) es mejor para capturar texto en spans anidados
                direct_text = element.get_text(" ", strip=True)

                if direct_text and 2 < len(direct_text) < 200:
                    if element.name in ["h2", "h3"]:
                        lines.append(f"## {direct_text}")
                    elif element.name in ["h4", "h5"]:
                        lines.append(f"### {direct_text}")
                    else:
                        lines.append(direct_text)

            # PASO C: Deduplicar — eliminar líneas consecutivas idénticas
            deduped = []
            seen_recent = []
            for line in lines:
                if line not in seen_recent:
                    deduped.append(line)
                    seen_recent.append(line)
                    if len(seen_recent) > 5:
                        seen_recent.pop(0)

            return "\n".join(deduped)
        except Exception as e:
            logger.error(f"Error in structural extraction: {e}")
            return ""

    def _strategy_raw_html(self, html: str) -> str:
        try:
            soup = BeautifulSoup(html, "html.parser")

            # Eliminar solo lo que NO aporta información semántica
            for tag in soup(["script", "style", "iframe",
                             "noscript", "svg", "path",
                             "meta", "link", "comment"]):
                tag.decompose()

            # Limpiar atributos irrelevantes pero conservar los semánticos
            ATTRS_A_CONSERVAR = {
                "aria-label", "title", "alt", "href",
                "data-name", "data-title", "data-store",
                "class", "id"
            }
            for tag in soup.find_all(True):
                attrs_originales = dict(tag.attrs)
                tag.attrs = {
                    k: v for k, v in attrs_originales.items()
                    if k in ATTRS_A_CONSERVAR
                }

            return str(soup)
        except Exception as e:
            logger.error(f"Error in raw html extraction: {e}")
            return ""

    def _smart_truncate(self, text: str, token_budget: int) -> str:
        try:
            char_budget = token_budget * 4
            
            if len(text) <= char_budget:
                return text
                
            truncated = text[:char_budget]
            last_break = truncated.rfind("\n\n")
            
            if last_break > char_budget * 0.5:
                return truncated[:last_break]
                
            return truncated
        except Exception as e:
            logger.error(f"Error in smart truncate: {e}")
            return text

    def _compute_hash(self, text: str) -> str:
        try:
            return hashlib.sha256(text.encode("utf-8")).hexdigest()
        except Exception as e:
            logger.error(f"Error computing hash: {e}")
            return ""

    def _empty_result(self, original_size_kb: float, start_time: float) -> dict:
        import time
        return {
            "markdown": "",
            "content_hash": "",
            "original_size_kb": round(float(original_size_kb), 2),
            "processed_size_kb": 0.0,
            "estimated_tokens": 0,
            "preprocess_ms": int((time.monotonic() - start_time) * 1000),
            "strategy_used": None
        }

    def process(self, html: str, token_budget: int = 4000) -> dict:
        import time
        start = time.monotonic()
        
        try:
            original_size_kb = len(html.encode("utf-8")) / 1024 if html else 0.0
            
            # Caso borde: HTML vacío o muy pequeño
            if not html or original_size_kb < 0.5:
                return self._empty_result(original_size_kb, start)
                
            strategy_used = None
            content = ""
            
            # ── PASO 0: __NEXT_DATA__ ──
            content = self._extract_next_data(html)
            if content:
                strategy_used = "next_data"
            else:
                # ── PASO 0b: JSON-LD ──
                content = self._extract_json_ld(html)
                if content and len(content.split("\n")) > 5:
                    strategy_used = "json_ld"

            if not strategy_used:
                # Estrategia 1 — Trafilatura
                content = self._strategy_trafilatura(html)
                strategy_used = "trafilatura"
                
                # ¿Es pobre? → Estrategia 2
                if original_size_kb >= 5 and _is_poor_result(content, original_size_kb):
                    content = self._strategy_structural(html)
                    strategy_used = "structural"
                    
                    # ¿Sigue siendo pobre? → Estrategia 3
                    if _is_poor_result(content, original_size_kb):
                        content = self._strategy_raw_html(html)
                        strategy_used = "raw_html"
                    
            # Aplicar smart_truncate SOLO si no es raw_html
            if strategy_used != "raw_html":
                content = self._smart_truncate(content, token_budget)
                
            content_hash = self._compute_hash(content)
            processed_size_kb = len(content.encode("utf-8")) / 1024
            estimated_tokens = len(content) // 4 if strategy_used != "raw_html" else None
            preprocess_ms = int((time.monotonic() - start) * 1000)
            
            return {
                "markdown":          content,
                "content_hash":      content_hash,
                "original_size_kb":  round(original_size_kb, 2),
                "processed_size_kb": round(processed_size_kb, 2),
                "estimated_tokens":  estimated_tokens,
                "preprocess_ms":     preprocess_ms,
                "strategy_used":     strategy_used
            }
        except Exception as e:
            logger.error(f"Unexpected error in preprocessing: {e}")
            return self._empty_result(0.0, start)
