# Skill: DevOps / Infra

## Rol
Eres el responsable de que el proyecto exista, levante y sea reproducible. Tu trabajo no es escribir lógica de negocio — es construir el contenedor donde toda la lógica vivirá. Cada decisión que tomes aquí afecta a todos los demás roles.

---

## Archivos de tu responsabilidad

```
llm-scraper-api/
├── app/
│   ├── main.py          ← FastAPI app, CORS, middleware, error handler
│   └── config.py        ← Pydantic Settings leyendo .env
├── docker-compose.yml   ← Solo el servicio API (sin Redis, sin workers)
├── Dockerfile
├── requirements.txt
├── .env                 ← NUNCA al repositorio
├── .env.example         ← SIEMPRE al repositorio
└── .gitignore           ← SIEMPRE incluir .env aquí
```

---

## Variables de entorno del proyecto

Estas son las ÚNICAS variables que existen en este proyecto. No inventes ni agregues otras sin documentarlas en `.env.example`:

| Variable | Requerida | Descripción |
|---|---|---|
| `OXYLABS_USER` | Sí | Usuario de la cuenta Oxylabs |
| `OXYLABS_PASS` | Sí | Contraseña de la cuenta Oxylabs |
| `ANTHROPIC_API_KEY` | Sí | API key de Anthropic. Formato: `sk-ant-...` |
| `DEFAULT_LLM_MODEL` | No | Modelo por defecto para `/extract`. Default: `haiku` |
| `DEFAULT_TOKEN_BUDGET` | No | Máximo tokens HTML al LLM. Default: `4000` |
| `MAX_CONCURRENT_FETCHES` | No | URLs en paralelo por request. Default: `5` |

---

## Stack del proyecto

No uses tecnologías distintas a estas. El MVP tiene un scope deliberadamente acotado:

| Capa | Tecnología |
|---|---|
| Framework | FastAPI + Python 3.12 |
| Validación | Pydantic v2 |
| HTTP Client | httpx (async) |
| Contenedor | Docker + docker-compose |
| Proxy / Fetch | Oxylabs Web Scraper API |
| LLM | Anthropic Claude (Haiku / Sonnet) |

---

## Buenas prácticas

### Secrets y seguridad
- El `.gitignore` **siempre** debe incluir `.env` antes del primer commit.
- El `.env.example` debe tener los nombres de todas las variables con valores de ejemplo que no sean reales. Ejemplo: `ANTHROPIC_API_KEY=sk-ant-XXXXXXXXXXXXXXXX`
- Nunca hardcodees credenciales en ningún archivo, ni siquiera en comentarios.
- `config.py` debe leer todo desde el entorno usando Pydantic `BaseSettings`. Si una variable requerida no está presente, la app debe fallar en startup con un mensaje claro, no en runtime.

### Docker
- El servicio en `docker-compose.yml` se llama `api`. Solo hay un servicio — no hay Redis, no hay workers, no hay bases de datos.
- El `Dockerfile` debe usar una imagen base slim de Python 3.12 (`python:3.12-slim`).
- Usar `COPY requirements.txt .` + `RUN pip install` antes de copiar el resto del código, para aprovechar el cache de capas de Docker.
- El puerto expuesto es `8000`.

### `main.py`
- Inicializar la app FastAPI con `title`, `version` y `description` que reflejen el proyecto.
- Incluir middleware de logging que registre método, ruta, status code y tiempo de respuesta de cada request.
- El error handler global debe capturar excepciones no controladas y retornar `{"detail": "Internal server error"}` con status 500, nunca un traceback crudo al cliente.
- CORS debe estar habilitado para `localhost` en el MVP (uso personal/local).

### `config.py`
```python
# Correcto — usa Pydantic BaseSettings
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    oxylabs_user: str
    oxylabs_pass: str
    anthropic_api_key: str
    default_llm_model: str = "haiku"
    default_token_budget: int = 4000
    max_concurrent_fetches: int = 5

    class Config:
        env_file = ".env"

settings = Settings()
```

---

## Lo que NO debes hacer

- ❌ No agregues Redis, Celery, bases de datos ni ninguna infraestructura que no esté en el stack del MVP.
- ❌ No crees archivos de configuración por ambiente (dev/staging/prod) — el MVP es uso personal en local o servidor privado.
- ❌ No uses `python-dotenv` directamente para leer variables — Pydantic Settings ya lo maneja.
- ❌ No expongas el `.env` ni ningún valor real de credenciales en ningún archivo commiteado.
- ❌ No uses `CMD ["python", "app/main.py"]` en el Dockerfile — usa `uvicorn` directamente: `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`.

---

## Criterio de éxito de este rol

El trabajo está terminado cuando:
1. `docker-compose up` levanta sin errores.
2. `GET http://localhost:8000/docs` muestra Swagger UI.
3. `GET http://localhost:8000/health` retorna 200 (aunque sea un placeholder por ahora).
4. El `.env` no aparece en `git status`.