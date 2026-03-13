## Investigación: Antara Fashion Hall
URL: https://www.antara.com.mx/directorio

### Autopsia del intento anterior
- Iteraciones usadas: 15
- Último contenido encontrado: Contenido genérico de footer/header ("Planta Baja / Horario...").
- Punto de falla: El sitio usa un Swiper carousel que oculta los elementos del directorio del viewport inicial. Al no interactuar con el carousel o activar los triggers AJAX, el agente solo veía el primer slide o el layout vacío.

### Hallazgos técnicos
- Tipo de sitio: SPA con carga por fragmentos HTML vía AJAX.
- Datos pre-cargados: No
- API interna: Sí (Endpoint de búsqueda). `POST https://antara.com.mx/busqueda` con el campo `busqueda=` vacío retorna un listado completo (~60KB) de todas las tiendas con sus nombres, logos y links.
- robots.txt: Bloquea `/assets/`, pero permite el resto. Prohíbe bots específicos (python-requests).
- Sitemap: Existe, pero solo lista páginas genéricas (eventos, inicio), no tiendas individuales.
- Señal de anti-bot: Sí (bloquea `python-requests` y otros bots por User-Agent).

### Categoría
B — API interna accesible (aunque retorna fragmentos HTML)

### Ruta propuesta
Clasificación: 🟠
Cambio: Añadir una herramienta al `navigation-agent` llamada `fetch_post(url, data)` o modificar `fetch_page` para soportar POST. Targeting específico al endpoint `/busqueda` para este dominio.
Archivos afectados: `app/services/llm_extractor.py`, `skills/11-navigation-agent.md`
Esfuerzo estimado: Medio

### Por qué esta ruta y no otra
El endpoint `/busqueda` entrega en una sola llamada lo que al agente le tomaría 10-15 clicks en el carousel. Es la ruta de mayor eficiencia y menor costo.

### Evidencia que confirma la ruta
`curl -X POST -d "busqueda=" https://antara.com.mx/busqueda`
```html
<a class='store-title' href='https://antara.com.mx/tienda/zara'>
    <h3>Zara</h3>
</a>
<a class='store-title' href='https://antara.com.mx/tienda/nike'>
    <h3>Nike</h3>
</a>
```
