"""Interface de secours navigateur, désactivée par défaut.

Le worker n'utilise jamais ce module pour les connecteurs spécialisés Vinted et
Leboncoin. Il existe uniquement comme point d'extension explicite : aucun proxy,
rotation d'identité ou contournement CAPTCHA n'y est implémenté.
"""

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from app.collectors.models import CollectorError


@dataclass(frozen=True)
class BrowserSearchRequest:
    platform: str
    query: str
    max_results: int = 25


def build_search_url(request: BrowserSearchRequest) -> str:
    if request.platform == "vinted":
        return f"https://www.vinted.fr/catalog?{urlencode({'search_text': request.query})}"
    if request.platform == "leboncoin":
        return f"https://www.leboncoin.fr/recherche?{urlencode({'text': request.query})}"
    raise CollectorError("Plateforme navigateur inconnue.")


class BrowserCollector:
    """Collecte de secours strictement opt-in, sans contournement de protection."""

    def __init__(self, *, enabled: bool = False) -> None:
        self.enabled = enabled

    async def collect_search_results(self, request: BrowserSearchRequest) -> list[dict[str, Any]]:
        if not self.enabled:
            raise CollectorError(
                "Le collecteur navigateur est désactivé par défaut.",
                retryable=False,
            )
        try:
            from crawlee.crawlers import PlaywrightCrawler
        except ImportError as error:
            raise CollectorError(
                "Crawlee avec l'extra Playwright n'est pas installé."
            ) from error

        results: list[dict[str, Any]] = []

        crawler = PlaywrightCrawler(
            max_requests_per_crawl=1,
            max_crawl_depth=0,
        )

        @crawler.router.default_handler
        async def handler(context: Any) -> None:
            page = context.page
            await page.wait_for_load_state("domcontentloaded")
            if await page.locator("text=/captcha|datadome/i").count():
                context.log.warning("Protection anti-bot détectée ; collecte interrompue.")
                return
            hrefs = await page.locator("a[href]").evaluate_all(
                "elements => elements.map(element => element.href)"
            )
            allowed_host = (
                "https://www.vinted.fr/items/"
                if request.platform == "vinted"
                else "https://www.leboncoin.fr/ad/"
            )
            for href in hrefs:
                if href.startswith(allowed_host):
                    results.append({"url": href})
                if len(results) >= request.max_results:
                    break

        await crawler.run([build_search_url(request)])
        return results
