from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Configuración central del proyecto LLM Scraper API.
    Lee todas las variables desde el entorno (o desde .env en desarrollo).
    Las variables sin default son REQUERIDAS — la app falla en startup si faltan.
    """

    # ── Credenciales requeridas ────────────────────────────────────────────────
    oxylabs_user: str
    oxylabs_pass: str
    anthropic_api_key: str

    # ── Variables opcionales con defaults ─────────────────────────────────────
    default_llm_model: str = "haiku"
    default_token_budget: int = 4000
    max_concurrent_fetches: int = 5

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
