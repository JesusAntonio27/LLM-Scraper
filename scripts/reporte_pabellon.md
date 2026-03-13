## Investigación: Pabellón Polanco
URL: https://www.pabellonpolanco.com.mx/

### Autopsia del intento anterior
- Iteraciones usadas: 11
- Último contenido encontrado: "Server Error 404 - File or directory not found."
- Punto de falla: Claude intentó navegar `/directorio`, `/tiendas`, usar Google e interactuar con scripts directos `.php`, regresando siempre errores 404 del servidor. Al final extrajo ciegamente 1 tienda (Sears) usando su conocimiento base.

### Hallazgos técnicos
- Tipo de sitio: Aplicación PHP en disrupción / dada de baja parcial por reconstrucción física de la plaza.
- Datos pre-cargados: No
- API interna: Múltiples endpoints `.php` (`get_tiendas.php`, `directorio_data.php`) retornan 404 Hard Error.
- robots.txt: `https://pabellonpolanco.com.mx/robots.txt` retorna 404 y redirecciones erráticas (SSL certificate errors también presentes usando dominios `www`).
- Sitemap: No hay sitemap válido activo, dominios rotos.
- Señal de anti-bot: No (los 404 son genuinos de IIS/Apache).

### Categoría
F — Sitio caído o en construcción

### Ruta propuesta
Clasificación: N/A
Cambio: Descartar este sitio de los tests de integración. Documentarlo en el MVP como "Plaza Caída/Reconstrucción".
Archivos afectados: `tests/test_agentic_navigation.py`
Esfuerzo estimado: Muy bajo

### Por qué esta ruta y no otra
El sitio físico está en demolición parcial y su backend digital sufre decaimiento masivo (archivos PHP borrados del servidor). No es un fallo técnico del LLM-Scraper.

### Evidencia que confirma la ruta
`curl -s https://pabellonpolanco.com.mx/robots.txt`
```html
<h2>404 - File or directory not found.</h2>
<h3>The resource you are looking for might have been removed...</h3>
```
