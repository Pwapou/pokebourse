"""Récupération serveur strictement bornée et explicitement autorisée.

Ce module n'est utilisé que lorsqu'un domaine a été ajouté à la liste
autorisée (``Settings.page_fetch_allowed_hosts``, variable d'environnement
``POKEMON_PAGE_FETCH_ALLOWED_HOSTS``). Aucune plateforme marketplace n'y figure
par défaut : les restrictions documentées dans ``SOURCES.md`` s'appliquent et
le parcours URL explique alors le repli vers l'extension ou la saisie manuelle.

Garde-fous appliqués à chaque requête et à chaque redirection :

- HTTPS uniquement, hôte présent dans la liste autorisée (correspondance de
  suffixe), aucun identifiant intégré, port implicite ou 443 ;
- résolution DNS : toutes les adresses obtenues doivent être publiques
  (jamais de réseau privé, local ou réservé — protection SSRF) ;
- redirections limitées, destination entièrement revérifiée à chaque étape ;
- délais et tailles de réponse bornés, types de contenu contrôlés ;
- aucune exécution de JavaScript, aucun cookie transmis.
"""
from __future__ import annotations

import http.client
import ipaddress
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

MAX_REDIRECTS = 3
FETCH_TIMEOUT_SECONDS = 10.0
USER_AGENT = "Pokébourse/1.0 (usage local personnel; contact local)"
HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")
IMAGE_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp")


class PageFetchError(Exception):
    """Échec de récupération avec un message compréhensible pour l'utilisateur."""


@dataclass(frozen=True)
class FetchedContent:
    content: bytes
    content_type: str
    final_url: str


def _split_allowed(url: str, allowed_hosts: Iterable[str]) -> tuple[str, str]:
    """Valide le schéma, l'hôte et les identifiants ; renvoie (hôte, cible)."""
    try:
        parts = urlsplit(url)
    except ValueError as error:
        raise PageFetchError("Adresse invalide.") from error
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme.lower() != "https" or not host:
        raise PageFetchError("Seules les adresses HTTPS publiques sont acceptées.")
    if parts.username is not None or parts.password is not None:
        raise PageFetchError("Les adresses avec identifiants intégrés sont interdites.")
    if parts.port not in (None, 443):
        raise PageFetchError("Seul le port HTTPS par défaut (443) est accepté.")
    allowed = {entry.lower().lstrip(".") for entry in allowed_hosts if entry.strip()}
    if not any(host == entry or host.endswith("." + entry) for entry in allowed):
        raise PageFetchError("Ce domaine n'est pas dans la liste des accès serveur autorisés.")
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    return host, path


def _public_addresses(host: str, resolve: Callable[..., Any]) -> list[str]:
    """Résout l'hôte et rejette toute adresse non publique (SSRF)."""
    try:
        ipaddress.IPv4Address(host)
        literal = [host]
    except ValueError:
        try:
            ipaddress.IPv6Address(host)
            literal = [host]
        except ValueError:
            literal = []
    if literal:
        addresses = literal
    else:
        try:
            infos = resolve(host, 443, type=socket.SOCK_STREAM)
        except OSError as error:
            raise PageFetchError("Le domaine ne peut pas être résolu ou est injoignable.") from error
        addresses = sorted({str(info[4][0]) for info in infos})
        if not addresses:
            raise PageFetchError("Le domaine ne peut pas être résolu ou est injoignable.")
    for raw in addresses:
        try:
            address = ipaddress.ip_address(raw)
        except ValueError as error:
            raise PageFetchError("Adresse résolue invalide.") from error
        if not address.is_global:
            raise PageFetchError("L'accès aux réseaux privés, locaux ou réservés est interdit.")
    return addresses


def _https_get(host: str, path: str, timeout: float, max_bytes: int) -> tuple[int, dict[str, str], bytes]:
    """Requête HTTPS bornée ; aucun cookie ni état partagé n'est transmis."""
    try:
        addresses = _public_addresses(host, socket.getaddrinfo)
        connection = http.client.HTTPSConnection(
            host, port=443, timeout=timeout, source_address=None,
        )
        # L'empreinte IP est vérifiée via la résolution précédente ; pour un
        # contrôle strict, on se connecte à une adresse résolue vérifiée.
        connection._create_connection = lambda *args, **kwargs: socket.create_connection(  # noqa: SLF001
            (addresses[0], 443), timeout=timeout,
        )
        connection.request(
            "GET", path,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,image/jpeg,image/png,image/webp;q=0.9",
                "Accept-Encoding": "identity",
                "Connection": "close",
            },
        )
        response = connection.getresponse()
        headers = {key.lower(): value for key, value in response.getheaders()}
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(min(64 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                connection.close()
                raise PageFetchError("La réponse dépasse la taille maximale autorisée.")
        connection.close()
        return response.status, headers, b"".join(chunks)
    except PageFetchError:
        raise
    except (OSError, http.client.HTTPException) as error:
        raise PageFetchError("La page est injoignable ou la connexion a échoué.") from error


def fetch_url(
    url: str,
    *,
    allowed_hosts: Iterable[str],
    max_bytes: int,
    content_types: Iterable[str],
    timeout: float = FETCH_TIMEOUT_SECONDS,
    max_redirects: int = MAX_REDIRECTS,
) -> FetchedContent:
    """Récupère une URL après validation complète, en suivant les redirections bornées.

    Lève ``PageFetchError`` avec un message explicite en cas de refus ou d'échec.
    """
    allowed = tuple(allowed_hosts)
    accepted = tuple(ct.lower() for ct in content_types)
    current = url
    for _attempt in range(max_redirects + 1):
        host, path = _split_allowed(current, allowed)
        status, headers, body = _https_get(host, path, timeout, max_bytes)
        if status in (301, 302, 303, 307, 308):
            location = headers.get("location", "")
            if not location:
                raise PageFetchError("La page renvoie une redirection invalide.")
            current = urljoin(current, location)
            continue
        if status == 404:
            raise PageFetchError("Page introuvable (erreur 404).")
        if status == 401 or status == 403:
            raise PageFetchError("La page exige une authentification ou bloque l'accès automatisé.")
        if status != 200:
            raise PageFetchError(f"La page a répondu avec un code inattendu ({status}).")
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type not in accepted:
            raise PageFetchError(f"Le type de contenu « {content_type or 'inconnu'} » n'est pas autorisé.")
        return FetchedContent(content=body, content_type=content_type, final_url=current)
    raise PageFetchError("Trop de redirections : la page n'a pas été suivie au-delà de la limite autorisée.")


def fetch_listing_page(url: str, *, allowed_hosts: Iterable[str], timeout: float = FETCH_TIMEOUT_SECONDS) -> FetchedContent:
    """Récupère une page d'annonce (HTML borné à 2 Mo)."""
    from app.collectors.page_extract import MAX_HTML_BYTES

    return fetch_url(url, allowed_hosts=allowed_hosts, max_bytes=MAX_HTML_BYTES,
                     content_types=HTML_CONTENT_TYPES, timeout=timeout)


def fetch_listing_image(url: str, *, allowed_hosts: Iterable[str], max_bytes: int = 8 * 1024 * 1024,
                        timeout: float = FETCH_TIMEOUT_SECONDS) -> FetchedContent:
    """Récupère l'image principale d'une annonce (formats photo, 8 Mo maximum)."""
    return fetch_url(url, allowed_hosts=allowed_hosts, max_bytes=max_bytes,
                     content_types=IMAGE_CONTENT_TYPES, timeout=timeout)


def fetch_policy_for_url(url: str, allowed_hosts: Iterable[str]) -> dict[str, str]:
    """Politique de récupération serveur pour une adresse d'annonce.

    Par défaut aucun domaine marketplace n'est autorisé : l'accès serveur reste
    interdit et le parcours propose l'extension ou la saisie manuelle.
    """
    allowed = {entry.lower().lstrip(".") for entry in allowed_hosts if entry.strip()}
    try:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        host = ""
    if host and any(host == entry or host.endswith("." + entry) for entry in allowed):
        return {"status": "allowed", "message": ""}
    return {
        "status": "unavailable",
        "message": (
            "La récupération automatique de cette page par le serveur n'est pas autorisée. "
            "Ouvrez l'annonce dans Chrome et utilisez l'extension Pokébourse, "
            "ou complétez les champs manuellement ci-dessous."
        ),
    }
