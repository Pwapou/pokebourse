"""Client REST pour l'API officielle Cardmarket (API 2.0).

Canal contractuel unique autorisé : OAuth 1.0a avec les identifiants du
compte de l'utilisateur. Aucun scraping de cardmarket.eu. Les prix sont
convertis en centimes entiers (jamais de float) avec arrondi demi-supérieur.

Documentation : https://api.cardmarket.com/ws/documentation
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable

logger = logging.getLogger(__name__)

DEFAULT_CARDMARKET_BASE_URL = "https://api.cardmarket.com/ws/v2.0"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_USER_AGENT = "Pokebourse/1.0 (Pokemon Card Arbitrage; Local Fair Use)"
# Identifiant du jeu "Pokémon TCG" dans le référentiel Cardmarket (Magic = 1, Yu-Gi-Oh! = 3).
POKEMON_GAME_ID = 6


class CardmarketError(Exception):
    """Erreur générique Cardmarket."""

    pass


class CardmarketNotConfiguredError(CardmarketError):
    """Identifiants API absents ou incomplets."""

    pass


class CardmarketNetworkError(CardmarketError):
    """Erreur réseau ou indisponibilité de l'API Cardmarket."""

    pass


class CardmarketRateLimitError(CardmarketError):
    """Limite de requêtes atteinte (HTTP 429 / 503)."""

    pass


class CardmarketNotFoundError(CardmarketError):
    """Produit introuvable sur Cardmarket (HTTP 404 ou correspondance vide)."""

    pass


def _quote(value: str) -> str:
    """Encodage percent RFC 3986 compatible avec l'implémentation OAuth de Cardmarket."""
    return urllib.parse.quote(value, safe="~")


def euros_to_cents(raw: object) -> int | None:
    """Convertit une chaîne décimale Cardmarket en centimes entiers (ROUND_HALF_UP)."""
    if raw is None or str(raw).strip() == "":
        return None
    value = (Decimal(str(raw).strip()) * 100).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return int(value)


class CardmarketClient:
    """Client API 2.0 Cardmarket avec authentification OAuth 1.0a (HMAC-SHA1)."""

    def __init__(
        self,
        app_token: str,
        app_secret: str,
        access_token: str,
        access_secret: str,
        *,
        base_url: str = DEFAULT_CARDMARKET_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 3,
        nonce_factory: Callable[[], str] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if not all((app_token, app_secret, access_token, access_secret)):
            raise CardmarketNotConfiguredError(
                "Identifiants Cardmarket incomplets : app token/secret et "
                "access token/secret sont requis."
            )
        self.app_token = app_token
        self.app_secret = app_secret
        self.access_token = access_token
        self.access_secret = access_secret
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._nonce_factory = nonce_factory or (lambda: secrets.token_hex(8))
        self._clock = clock or time.time

    # ------------------------------------------------------------------
    # Authentification OAuth 1.0a
    # ------------------------------------------------------------------
    def _signature_base_url(self, url: str) -> str:
        """Cardmarket exige que la signature soit calculée sans le segment output.json."""
        return url.replace("/output.json", "")

    def _authorization_header(self, method: str, url: str) -> str:
        nonce = self._nonce_factory()
        timestamp = str(int(self._clock()))
        oauth_params = {
            "oauth_consumer_key": self.app_token,
            "oauth_token": self.access_token,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": timestamp,
            "oauth_nonce": nonce,
            "oauth_version": "1.0",
        }
        parsed = urllib.parse.urlsplit(url)
        query_params = dict(urllib.parse.parse_qsl(parsed.query))
        all_params = {**oauth_params, **query_params}
        parameter_string = "&".join(
            f"{_quote(key)}={_quote(value)}"
            for key, value in sorted(all_params.items())
        )
        base_string = "&".join(
            [
                method.upper(),
                _quote(self._signature_base_url(url)),
                _quote(parameter_string),
            ]
        )
        signing_key = f"{_quote(self.app_secret)}&{_quote(self.access_secret)}"
        digest = hmac.new(
            signing_key.encode("utf-8"),
            base_string.encode("utf-8"),
            hashlib.sha1,
        ).digest()
        signature = base64.b64encode(digest).decode("ascii")
        header_params = {**oauth_params, "oauth_signature": signature}
        header = ", ".join(
            f'{key}="{_quote(value)}"'
            for key, value in sorted(header_params.items())
        )
        return f'OAuth realm="{_quote(url)}", {header}'

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------
    def _request(self, method: str, path: str) -> Any:
        url = f"{self.base_url}/output.json{path}"
        request = urllib.request.Request(
            url,
            method=method.upper(),
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "application/json",
                "Authorization": self._authorization_header(method, url),
            },
        )

        attempts = 0
        while attempts < self.max_retries:
            attempts += 1
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    data = response.read()
                    return json.loads(data.decode("utf-8"))
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    raise CardmarketNotFoundError(
                        f"Ressource Cardmarket non trouvée : {url}"
                    ) from error
                if error.code == 429:
                    if attempts >= self.max_retries:
                        raise CardmarketRateLimitError(
                            "Quota de requêtes Cardmarket dépassé (429)."
                        ) from error
                    retry_after = error.headers.get("Retry-After") if error.headers else None
                    delay = float(retry_after) if retry_after else 1.0 * (2 ** attempts)
                    logger.warning(
                        "Cardmarket 429 ; attente de %.1fs avant nouvelle tentative.", delay
                    )
                    time.sleep(delay)
                    continue
                if error.code == 503:
                    if attempts >= self.max_retries:
                        raise CardmarketRateLimitError(
                            "Cardmarket demande de ralentir (503 Slow Down)."
                        ) from error
                    time.sleep(1.0 * attempts)
                    continue
                if error.code >= 500:
                    if attempts >= self.max_retries:
                        raise CardmarketNetworkError(
                            f"Erreur serveur Cardmarket ({error.code}) : {url}"
                        ) from error
                    time.sleep(1.0 * attempts)
                    continue
                raise CardmarketError(
                    f"Erreur HTTP Cardmarket ({error.code}) sur {url}"
                ) from error
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                if attempts >= self.max_retries:
                    raise CardmarketNetworkError(
                        f"Connexion Cardmarket impossible sur {url} : {error}"
                    ) from error
                time.sleep(1.0 * attempts)
            except json.JSONDecodeError as error:
                raise CardmarketError("Réponse Cardmarket JSON invalide.") from error

        raise CardmarketNetworkError(
            f"Échec après {self.max_retries} tentatives sur {url}"
        )

    # ------------------------------------------------------------------
    # Endpoints marketplace utilisés par Pokébourse
    # ------------------------------------------------------------------
    def get_games(self) -> list[dict[str, Any]]:
        """Liste les jeux supportés par Cardmarket."""
        data = self._request("GET", "/games")
        if isinstance(data, dict) and isinstance(data.get("games"), list):
            return [dict(game) for game in data["games"]]
        return []

    def get_expansions(self, game_id: int = POKEMON_GAME_ID) -> list[dict[str, Any]]:
        """Liste les extensions (expansions) d'un jeu."""
        data = self._request("GET", f"/expansions/{game_id}")
        if isinstance(data, dict) and isinstance(data.get("expansions"), list):
            return [dict(expansion) for expansion in data["expansions"]]
        return []

    def find_products(
        self, name: str, game_id: int = POKEMON_GAME_ID
    ) -> list[dict[str, Any]]:
        """Recherche des produits par nom dans le catalogue Cardmarket."""
        encoded_name = urllib.parse.quote(name.strip())
        data = self._request("GET", f"/products/{game_id}/{encoded_name}")
        if isinstance(data, dict) and isinstance(data.get("products"), list):
            return [dict(product) for product in data["products"]]
        return []

    def get_product(self, product_id: int) -> dict[str, Any]:
        """Détail d'un produit, incluant le priceGuide (prix de marché)."""
        data = self._request("GET", f"/products/{product_id}")
        if isinstance(data, dict) and isinstance(data.get("product"), dict):
            return dict(data["product"])
        return {}
