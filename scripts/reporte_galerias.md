## Investigación: Galerías Insurgentes
URL: https://www.galerias.com/galeriasinsurgentes

### Autopsia del intento anterior
- Iteraciones usadas: 8
- Último contenido encontrado: "`<!DOCTYPE html> <html class=\"js-focus-visible\">`"
- Punto de falla: El agente se estancó pidiendo URLs como `?category=accesorios` pero obtenía siempre la misma estructura base del framework porque los datos se inyectan post-load o están pre-cargados.

### Hallazgos técnicos
- Tipo de sitio: SPA Next.js
- Datos pre-cargados: Sí: `__NEXT_DATA__` contiene `props.pageProps` con el listado exhaustivo de locales, orden, brandLogo y categorías.
- API interna: No encontrada explícita, pero innecesaria (la hidratación trae todo).
- robots.txt: Permite `/`, sitemap listado.
- Sitemap: Encontrado, pero apunta a rutas de sección sin lista individual de tiendas.
- Señal de anti-bot: No

### Categoría
A — Datos pre-cargados en HTML

### Ruta propuesta
Clasificación: 🟡
Cambio: Interceptar `__NEXT_DATA__` en el preprocessor como paso previo/alternativo a la extracción por Trafilatura/BeautifulSoup.
Archivos afectados: `app/services/preprocessor.py`
Esfuerzo estimado: Bajo

### Por qué esta ruta y no otra
Extraer directamente el JSON pre-cargado de un framework React (Next.js config o Redux Initial State) es instantáneo, 100% confiable y consume 0 iteraciones extra del LLM.

### Evidencia que confirma la ruta
Snippet del HTML base:
`...{"url": "https://www.galerias.com/tiendas/zara", "label": "Zara"}, {"url": "https://www.galerias.com/tiendas/innovasport", "label": "Innovasports"}, ...`
