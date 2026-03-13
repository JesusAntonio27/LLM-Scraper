"""
Integration Engineer — services/oxylabs.py

Wrapper around the Oxylabs Realtime Web Scraper API.
Contract: fetch() always returns one of:
  {"status": "ok",     "html": "...", "fetch_ms": <int>}
  {"status": "failed", "error": "...", "fetch_ms": <int>}
Never raises an exception to the caller.
"""

import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

OXYLABS_URL = "https://realtime.oxylabs.io/v1/queries"


class OxylabsFetcher:
    """Fetches fully-rendered HTML from any URL via Oxylabs Realtime API."""

    async def fetch(
        self,
        url: str,
        render_js: bool = True,
        geo_location: str = None,
        timeout: int = 30,
        user_agent_type: str = "desktop",
        browser_instructions: list[dict] | None = None,
    ) -> dict:
        """
        Fetch the rendered HTML of *url* through Oxylabs.

        Parameters
        ----------
        url : str
        render_js : bool
        geo_location : str | None
        timeout : int
        user_agent_type : str
        browser_instructions : list[dict] | None
            Optional list of JSON instructions (clicks, scrolls, waits).

        Returns
        -------
        dict
            {"status": "ok",     "html": str, "fetch_ms": int}
            {"status": "failed", "error": str, "fetch_ms": int}
        """
        payload: dict = {
            "source": "universal",
            "url": url,
            "render": "html" if (render_js or browser_instructions) else None,
            "geo_location": geo_location,
            "user_agent_type": user_agent_type,
            "browser_instructions": browser_instructions,
        }
        # Remove keys whose value is None before sending
        payload = {k: v for k, v in payload.items() if v is not None}

        start = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=timeout + 5) as client:
                response = await client.post(
                    OXYLABS_URL,
                    auth=(settings.oxylabs_user, settings.oxylabs_pass),
                    json=payload,
                )

            fetch_ms = int((time.monotonic() - start) * 1000)

            if response.status_code != 200:
                error_msg = (
                    f"HTTP {response.status_code}: "
                    f"{response.text[:200]}"  # short excerpt — never log full body
                )
                logger.warning("oxylabs fetch failed | url=%s status=%s fetch_ms=%d",
                               url, response.status_code, fetch_ms)
                return {"status": "failed", "error": error_msg, "fetch_ms": fetch_ms}

            data = response.json()
            html: str = data["results"][0]["content"]

            logger.info("oxylabs fetch ok | url=%s fetch_ms=%d", url, fetch_ms)
            # HTML is returned exactly as received — no modification
            return {"status": "ok", "html": html, "fetch_ms": fetch_ms}

        except httpx.TimeoutException:
            fetch_ms = int((time.monotonic() - start) * 1000)
            logger.warning("oxylabs timeout | url=%s fetch_ms=%d", url, fetch_ms)
            return {
                "status": "failed",
                "error": f"timeout after {timeout}s",
                "fetch_ms": fetch_ms,
            }

        except httpx.ConnectError as exc:
            fetch_ms = int((time.monotonic() - start) * 1000)
            logger.warning("oxylabs connection error | url=%s error=%s fetch_ms=%d",
                           url, exc, fetch_ms)
            return {
                "status": "failed",
                "error": f"connection error: {exc}",
                "fetch_ms": fetch_ms,
            }

        except Exception as exc:  # noqa: BLE001
            fetch_ms = int((time.monotonic() - start) * 1000)
            logger.error("oxylabs unexpected error | url=%s error=%s fetch_ms=%d",
                         url, exc, fetch_ms)
            return {
                "status": "failed",
                "error": str(exc),
                "fetch_ms": fetch_ms,
            }
    async def fetch_api(
        self,
        url: str,
        method: str = "GET",
        payload: dict | str | None = None,
        headers: dict | None = None,
        geo_location: str = "Mexico",
        timeout: int = 30
    ) -> dict:
        """
        Llama directamente a una API interna de un sitio (REST o form POST).
        No usa render_js — retorna el body crudo de la respuesta.
        Útil para endpoints descubiertos en el bundle de JS del sitio.
        """
        import time
        start = time.monotonic()

        # Oxylabs universal scraper soporta POST nativo
        oxylabs_payload = {
            "source":       "universal",
            "url":          url,
            "geo_location": geo_location,
            "parse":        False,   # retornar HTML/JSON crudo sin parsear
        }

        # Para POST con form data
        if method.upper() == "POST":
            oxylabs_payload["http_method"] = "post"
            if isinstance(payload, dict):
                # Form data
                oxylabs_payload["content"] = "&".join(
                    f"{k}={v}" for k, v in payload.items()
                )
            elif isinstance(payload, str):
                oxylabs_payload["content"] = payload

        if headers:
            oxylabs_payload["headers"] = headers

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    OXYLABS_URL,
                    auth=(settings.oxylabs_user, settings.oxylabs_pass),
                    json={"queries": [oxylabs_payload]},
                    timeout=timeout + 5
                )
                response.raise_for_status()
                data = response.json()
                # La API de consultas únicas vs múltiples varía un poco
                # Si se usa queries[], el resultado está en data["results"][0]["content"]
                content = data["results"][0]["content"]
                fetch_ms = int((time.monotonic() - start) * 1000)

                return {
                    "status":   "ok",
                    "content":  content,
                    "fetch_ms": fetch_ms
                }

        except Exception as e:
            logger.error("oxylabs_api failure | url=%s error=%s", url, str(e))
            return {
                "status": "failed",
                "error":  str(e),
                "fetch_ms": int((time.monotonic() - start) * 1000)
            }
