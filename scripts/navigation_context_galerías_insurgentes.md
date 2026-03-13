# Contexto de Navegación Activa

## URL actual
https://www.galerias.com/galerias/insurgentes/tiendas

## Objetivo
Schema: {"stores": [{"plaza": "string", "nombre": "string", "categoria": "string | null", "ubicacion": "string | null"}]}
Hint: Directorio de tiendas de Galerías Insurgentes en CDMX México. El contenido puede estar dividido por categorías o letras del alfabeto. Navega por todas las secciones para obtener el listado completo.

## Estado
En progreso

## Iteraciones
| # | Tool | Input | Resultado |
|---|---|---|---|

| 1 | call_api | {'url': 'https://www.galerias.com/api/trpc/cms.getStoresByMall?input={"json":{"l | ejecutado |

| 1 | call_api | {'url': 'https://www.galerias.com/api/trpc/cms.getStoresByMall?input={"json":{"l | API call failed: Client error '400 Bad Request' for url 'https://realtime.oxylab |

| 2 | fetch_page | {'url': 'https://www.galerias.com/galerias/insurgentes/tiendas'} | ejecutado |

| 2 | fetch_page | {'url': 'https://www.galerias.com/galerias/insurgentes/tiendas'} | props:
  pageProps:
    trpcState:
      json:
        mutations:
        querie |

| 3 | call_api | {'url': 'https://www.galerias.com/api/trpc/cms.getStoresByMall?batch=1&input={"0 | ejecutado |

| 3 | call_api | {'url': 'https://www.galerias.com/api/trpc/cms.getStoresByMall?batch=1&input={"0 | API call failed: Client error '400 Bad Request' for url 'https://realtime.oxylab |

| 4 | fetch_page | {'url': 'https://www.galerias.com/api/trpc/cms.getStoresByMall?batch=1&input={"0 | ejecutado |

| 4 | fetch_page | {'url': 'https://www.galerias.com/api/trpc/cms.getStoresByMall?batch=1&input={"0 | TÉRMINOS Y CONDICIONES DE NAVEGACIÓN Y USO DEL SITIO WEB www.galerias.com
TÉRMIN |

| 5 | call_api | {'url': 'https://www.galerias.com/api/trpc/cms.getStoresByMall', 'method': 'POST | ejecutado |

| 5 | call_api | {'url': 'https://www.galerias.com/api/trpc/cms.getStoresByMall', 'method': 'POST | API call failed: Client error '400 Bad Request' for url 'https://realtime.oxylab |

| 5 | fetch_page | {'url': 'https://www.galerias.com/galerias/insurgentes/tiendas#__NEXT_DATA__'} | ejecutado |

| 5 | fetch_page | {'url': 'https://www.galerias.com/galerias/insurgentes/tiendas#__NEXT_DATA__'} | props:
  pageProps:
    trpcState:
      json:
        mutations:
        querie |

| 6 | fetch_page | {'url': 'https://www.galerias.com/sitemap.xml'} | ejecutado |

| 6 | fetch_page | {'url': 'https://www.galerias.com/sitemap.xml'} | This XML file does not appear to have any style information associated with it.  |

| 7 | fetch_page | {'url': 'https://www.galerias.com/tiendas'} | ejecutado |

| 7 | fetch_page | {'url': 'https://www.galerias.com/tiendas'} | props:
  pageProps:
    categories:
      [0]
        restaurantes_y_comida_rapi |

| 8 | fetch_page | {'url': 'https://www.galerias.com/busqueda?mall=insurgentes'} | ejecutado |

| 8 | fetch_page | {'url': 'https://www.galerias.com/busqueda?mall=insurgentes'} | props:
  pageProps:
    trpcState:
      json:
        mutations:
        querie |

| 9 | fetch_page | {'url': 'https://www.galerias.com/_next/data/xdGU803CvGA8fh2RycvUc/galerias/insu | ejecutado |

| 9 | fetch_page | {'url': 'https://www.galerias.com/_next/data/xdGU803CvGA8fh2RycvUc/galerias/insu | Contenido vacío |

| 10 | call_api | {'url': 'https://www.galerias.com/_next/data/xdGU803CvGA8fh2RycvUc/es-MX/galeria | ejecutado |

| 10 | call_api | {'url': 'https://www.galerias.com/_next/data/xdGU803CvGA8fh2RycvUc/es-MX/galeria | API call failed: Client error '400 Bad Request' for url 'https://realtime.oxylab |

| 11 | fetch_page | {'url': 'https://www.galerias.com/_next/data/xdGU803CvGA8fh2RycvUc/es-MX/galeria | ejecutado |

| 11 | fetch_page | {'url': 'https://www.galerias.com/_next/data/xdGU803CvGA8fh2RycvUc/es-MX/galeria | \"http:
Aviso privacidad\"
TÉRMINOS Y CONDICIONES DE NAVEGACIÓN Y USO DEL SITIO  |

| 12 | fetch_page | {'url': 'https://web.archive.org/web/2024/https://www.galerias.com/galerias/insu | ejecutado |

| 12 | fetch_page | {'url': 'https://web.archive.org/web/2024/https://www.galerias.com/galerias/insu | props:
  pageProps:
    trpcState:
      json:
        mutations:
        querie |

| 13 | fetch_page | {'url': 'https://webcache.googleusercontent.com/search?q=cache:galerias.com/gale | ejecutado |

| 13 | fetch_page | {'url': 'https://webcache.googleusercontent.com/search?q=cache:galerias.com/gale | Our systems have detected unusual traffic from your computer network. This page  |

| 14 | fetch_page | {'url': 'https://web.archive.org/web/20241201000000*/galerias.com/galerias/insur | ejecutado |

| 14 | fetch_page | {'url': 'https://web.archive.org/web/20241201000000*/galerias.com/galerias/insur | Close Banner
Open main menu
Archive
Go home
Expand web menu
Expand texts menu
Ex |

## Datos acumulados
0 registros

## Pendiente
Por explorar

## Decisiones tomadas
_Se irán registrando durante la navegación_
