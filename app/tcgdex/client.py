import json
import logging
import time
from typing import Any
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

DEFAULT_TCGDEX_BASE_URL = "https://api.tcgdex.net/v2/fr"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_USER_AGENT = "Pokebourse/1.0 (Pokemon Card Arbitrage; Local Fair Use)"


class TcgdexError(Exception):
    """Erreur générique TCGdex."""
    pass


class TcgdexNetworkError(TcgdexError):
    """Erreur réseau ou indisponibilité de l'API TCGdex."""
    pass


class TcgdexRateLimitError(TcgdexError):
    """Limite de requêtes atteinte (HTTP 429)."""
    pass


class TcgdexNotFoundError(TcgdexError):
    """Ressource introuvable sur TCGdex (HTTP 404)."""
    pass


class TcgdexClient:
    """Client REST pour l'API officielle TCGdex."""

    def __init__(
        self,
        base_url: str = DEFAULT_TCGDEX_BASE_URL,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    def _request(self, endpoint: str) -> Any:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "application/json",
            },
        )

        attempts = 0
        while attempts < self.max_retries:
            attempts += 1
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    data = response.read()
                    return json.loads(data.decode("utf-8"))
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    raise TcgdexNotFoundError(f"Ressource TCGdex non trouvée : {url}") from error
                if error.code == 429:
                    if attempts >= self.max_retries:
                        raise TcgdexRateLimitError("Quota de requêtes TCGdex dépassé (429).") from error
                    retry_after = error.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 1.0 * (2 ** attempts)
                    logger.warning("TCGdex 429 ; attente de %.1fs avant nouvelle tentative.", delay)
                    time.sleep(delay)
                    continue
                if error.code >= 500:
                    if attempts >= self.max_retries:
                        raise TcgdexNetworkError(f"Erreur serveur TCGdex ({error.code}) : {url}") from error
                    time.sleep(1.0 * attempts)
                    continue
                raise TcgdexError(f"Erreur HTTP TCGdex ({error.code}) sur {url}") from error
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                if attempts >= self.max_retries:
                    raise TcgdexNetworkError(f"Connexion TCGdex impossible sur {url} : {error}") from error
                time.sleep(1.0 * attempts)
            except json.JSONDecodeError as error:
                raise TcgdexError("Réponse TCGdex JSON invalide.") from error

        raise TcgdexNetworkError(f"Échec après {self.max_retries} tentatives sur {url}")

    def get_sets(self) -> list[dict[str, Any]]:
        """Récupère la liste de toutes les extensions (sets)."""
        data = self._request("/sets")
        if isinstance(data, list):
            return data
        return []

    def get_set(self, set_id: str) -> dict[str, Any]:
        """Récupère les détails d'une extension et ses cartes."""
        data = self._request(f"/sets/{set_id}")
        if isinstance(data, dict):
            return data
        return {}

    def get_card(self, card_id: str) -> dict[str, Any]:
        """Récupère une carte par son identifiant TCGdex (ex: 'swsh3-136')."""
        data = self._request(f"/cards/{card_id}")
        if isinstance(data, dict):
            return data
        return {}

    def get_card_by_set_and_number(self, set_id: str, local_id: str) -> dict[str, Any]:
        """Récupère une carte par son extension et son numéro local."""
        data = self._request(f"/sets/{set_id}/{local_id}")
        if isinstance(data, dict):
            return data
        return {}
