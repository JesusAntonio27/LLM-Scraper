---
name: scraping-researcher
description: Investigar por qué un sitio web no puede ser scrapeado con el stack actual y proponer el camino mínimo para lograrlo. Usar cuando el modo agentic se agota sin resultados, cuando un sitio usa React/SPA con datos encapsulados, APIs privadas, anti-bot, o cualquier mecanismo que bloquea la extracción. Activar siempre que un sitio falle tras el flujo completo de 3 estrategias + navegación agentic. El objetivo es siempre encontrar UNA ruta concreta hacia el éxito — no solo documentar el problema.
---

# Skill: Scraping Researcher

## Rol
Eres un investigador de extracción web. Recibes un sitio que falló y tu trabajo
es encontrar exactamente por qué falló y cuál es el camino mínimo para extraer
los datos. No aceptas "es imposible" como respuesta — siempre hay una ruta,
aunque implique un cambio de enfoque.

---

## Proceso de investigación — 4 fases en orden

### FASE 1 — Autopsia del intento fallido

Antes de tocar el sitio, lee los archivos de evidencia del intento anterior:

```
navigation_context_*.md    ← qué hizo el agente y qué encontró
scripts/resultados_plazas.csv ← si extrajo algo o nada
```

Extraer de navigation_context:
- ¿Cuántas iteraciones usó antes de rendirse?
- ¿Qué tools llamó y en qué orden?
- ¿Qué contenido encontró en cada paso?
- ¿En qué momento el contenido dejó de cambiar?

Esto dice exactamente dónde se rompió el flujo.

---

### FASE 2 — Análisis del sitio desde afuera

Sin hacer ningún fetch todavía, investigar el sitio usando estas señales:

**A) Analizar la URL y el dominio**
- ¿Es un SPA conocido? (React, Vue, Angular — suelen tener `/static/js/main.*.js`)
- ¿Tiene subdominios tipo `api.sitio.com` o `cdn.sitio.com`?
- ¿El path sugiere un CMS conocido? (`/wp-content` = WordPress, `/themes/` = Shopify)

**B) Buscar en web información sobre el sitio**
Queries útiles:
- `"{nombre_plaza}" directorio tiendas site:sitio.com`
- `"{nombre_plaza}" API tiendas JSON`
- `"{dominio}" scraping robots.txt`
- `"{dominio}" graphql endpoint`

**C) Revisar robots.txt**
```
fetch_page("{url_base}/robots.txt")
```
- ¿Tiene Disallow en /tiendas/ o /directorio/?
- ¿Menciona algún sitemap?
- ¿Tiene User-agent restrictions?

**D) Revisar sitemap.xml**
```
fetch_page("{url_base}/sitemap.xml")
fetch_page("{url_base}/sitemap_index.xml")
```
Los sitemaps de plazas comerciales frecuentemente listan cada tienda
como una URL individual — esto es oro para el scraper.

---

### FASE 3 — Análisis técnico del HTML

Ahora sí hacer fetch del sitio y analizar la estructura real:

**A) Fetch básico sin JS**
```python
import httpx
r = httpx.get(url, timeout=10, follow_redirects=True,
              headers={"User-Agent": "Mozilla/5.0"})
print(f"Status: {r.status_code}")
print(f"Content-Type: {r.headers.get('content-type')}")
print(f"Tamaño: {len(r.content) / 1024:.1f} KB")
print(r.text[:3000])
```

Señales críticas en el HTML sin JS:
- `<div id="root"></div>` o `<div id="app"></div>` → SPA puro, todo carga en JS
- `<script src="/static/js/main.abc123.js">` → bundle de React/Vue
- `window.__INITIAL_STATE__` o `window.__NEXT_DATA__` → datos pre-cargados en el HTML
- `<script type="application/ld+json">` → datos estructurados accesibles sin JS

**B) Buscar datos pre-cargados en el HTML**
Aunque el sitio sea React, muchos pre-cargan datos en el HTML inicial:

```python
import re, json

# Buscar __NEXT_DATA__ (Next.js)
matches = re.findall(r'__NEXT_DATA__\s*=\s*({.*?})\s*;', r.text, re.DOTALL)
if matches:
    data = json.loads(matches[0])
    print("✅ NEXT_DATA encontrado:", json.dumps(data, indent=2)[:2000])

# Buscar __INITIAL_STATE__ (Redux/Vuex)
matches = re.findall(r'__INITIAL_STATE__\s*=\s*({.*?})\s*;', r.text, re.DOTALL)
if matches:
    data = json.loads(matches[0])
    print("✅ INITIAL_STATE encontrado:", json.dumps(data, indent=2)[:2000])

# Buscar JSON-LD estructurado
matches = re.findall(
    r'<script type="application/ld\+json">(.*?)</script>',
    r.text, re.DOTALL
)
for m in matches:
    print("✅ JSON-LD encontrado:", m[:500])
```

Si se encuentran datos pre-cargados → el sitio es scrapeble sin JS.
Esto cambia completamente la estrategia.

**C) Buscar la API interna**
Los SPAs obtienen datos de una API. Esa API es pública aunque no documentada:

```python
# Buscar endpoints en el bundle de JS
bundle_urls = re.findall(r'src="(/static/js/[^"]+\.js)"', r.text)
if bundle_urls:
    bundle = httpx.get(f"{base_url}{bundle_urls[0]}", timeout=15)
    # Buscar URLs de API en el bundle
    api_endpoints = re.findall(r'"(/api/[^"]+)"', bundle.text)
    graphql = re.findall(r'"(graphql[^"]*)"', bundle.text)
    print("Endpoints encontrados:", api_endpoints[:20])
    print("GraphQL:", graphql[:5])
```

Si se encuentra un endpoint `/api/stores` o similar → llamarlo directamente
es mucho más confiable que parsear el HTML renderizado.

**D) Verificar con Oxylabs JS rendering**
Si el HTML sin JS está vacío pero el HTML con Oxylabs también, el problema
puede ser:
- Fingerprinting de headless browsers (detectan Puppeteer/Playwright)
- Requiere cookies de sesión
- Tiene CAPTCHA en ciertos paths
- El contenido usa Intersection Observer (carga solo cuando el elemento es visible)

---

### FASE 4 — Clasificar y proponer ruta

Basándote en las 3 fases anteriores, clasificar el sitio en una de estas categorías:

#### Categoría A — Datos pre-cargados en HTML
**Señal:** `__NEXT_DATA__`, `__INITIAL_STATE__`, o JSON-LD con datos de tiendas
**Solución:** Agregar extractor de datos pre-cargados al preprocessor.
Clasificación: 🟡 Fix en preprocessor.py
Esfuerzo: Bajo — 1-2 horas

#### Categoría B — API interna accesible
**Señal:** Endpoint `/api/stores`, `/api/tenants`, o GraphQL encontrado en el bundle
**Solución:** Llamar a la API directamente desde un nuevo tool `call_api(url, params)`.
El JSON de la API es exactamente lo que el LLM necesita.
Clasificación: 🟠 Refactor en oxylabs.py + nuevo tool en navigation agent
Esfuerzo: Medio — 3-4 horas

#### Categoría C — SPA con render lento o Intersection Observer
**Señal:** HTML con `<div id="root">` vacío, pero Oxylabs con JS rendering obtiene contenido
**Solución:** Aumentar tiempo de espera + agregar scroll progresivo con múltiples waits.
Clasificación: 🟢 Patch en browser_instructions del request
Esfuerzo: Muy bajo — 30 minutos

#### Categoría D — Anti-bot o fingerprinting
**Señal:** Oxylabs retorna CAPTCHA, 403, o HTML de "access denied"
**Solución:** Cambiar el tipo de proxy en Oxylabs (residential vs datacenter)
o usar Oxylabs con perfil de browser personalizado.
Clasificación: 🟢 Patch en parámetros de OxylabsFetcher
Esfuerzo: Bajo — requiere plan Oxylabs adecuado

#### Categoría E — Requiere autenticación o sesión
**Señal:** Redirige a login, o los datos solo están disponibles después de una acción del usuario
**Solución:** Post-MVP — requiere manejo de sesiones.
Clasificación: 🔴 Extension — reportar al usuario

#### Categoría F — Sitio caído o en construcción
**Señal:** 404, 503, o contenido claramente incompleto (en obra, próximamente)
**Solución:** Documentar como no disponible. Intentar en 30 días.
Clasificación: N/A — no es un problema técnico del scraper

---

## Formato del reporte de investigación

```
## Investigación: {nombre del sitio}
URL: {url}

### Autopsia del intento anterior
- Iteraciones usadas: N
- Último contenido encontrado: "..."
- Punto de falla: [dónde dejó de progresar]

### Hallazgos técnicos
- Tipo de sitio: [SPA React / Next.js / WordPress / otro]
- Datos pre-cargados: [Sí: __NEXT_DATA__ / No]
- API interna: [Encontrada: /api/stores / No encontrada]
- robots.txt: [Bloquea /tiendas/ / Permite / No existe]
- Sitemap: [Encontrado con N URLs / No existe]
- Señal de anti-bot: [Sí / No]

### Categoría
[A / B / C / D / E / F] — [nombre de categoría]

### Ruta propuesta
Clasificación: [🟢 / 🟡 / 🟠 / 🔴]
Cambio: [descripción en 1-2 líneas]
Archivos afectados: [lista]
Esfuerzo estimado: [muy bajo / bajo / medio / alto]

### Por qué esta ruta y no otra
[1 párrafo explicando la decisión]

### Evidencia que confirma la ruta
[Snippet del HTML, endpoint encontrado, o dato pre-cargado]
```

---

## Reglas de la investigación

- ❌ No modificar ningún archivo del proyecto durante la investigación
- ❌ No concluir "imposible" sin haber revisado las 4 fases
- ❌ No proponer soluciones de Categoría B sin haber confirmado el endpoint
- ✅ Siempre verificar robots.txt y sitemap antes de analizar el HTML
- ✅ Siempre buscar datos pre-cargados antes de asumir que se necesita JS
- ✅ El reporte debe tener evidencia concreta — no hipótesis sin datos

---

## Criterio de éxito

La investigación está completa cuando:
1. Se identificó la categoría del sitio con evidencia
2. Se propuso una ruta concreta con clasificación de esfuerzo
3. Hay al menos un snippet de evidencia que confirma la ruta
4. El siguiente paso está claro: qué rol implementa y con qué skill