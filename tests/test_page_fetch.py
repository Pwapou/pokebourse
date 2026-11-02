"""Récupération serveur bornée : sécurité réseau, aucun appel réel."""
from __future__ import annotations

import socket
from typing import Any

import pytest

from app.collectors.page_fetch import (
    FetchedContent,
    PageFetchError,
    _public_addresses,
    _split_allowed,
    fetch_listing_image,
    fetch_listing_page,
    fetch_policy_for_url,
)


class _FakeResponse:
    def __init__(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.status = status
        self._headers = headers
        self._body = body

    def getheaders(self) -> list[tuple[str, str]]:
        return list(self._headers.items())

    def read(self, n: int) -> bytes:
        if not self._body:
            return b""
        chunk, self._body = self._body[:n], self._body[n:]
        return chunk


class _FakeConnection:
    """Simule http.client.HTTPSConnection selon un script de réponses."""

    script: list[tuple[int, dict[str, str], bytes]] = []
    requests: list[tuple[str, str]] = []
    created_with: list[str] = []

    def __init__(self, host: str, port: int, timeout: float, source_address: Any = None) -> None:
        self.host = host
        type(self).created_with.append(host)

    def request(self, method: str, path: str, headers: dict[str, str] | None = None) -> None:
        type(self).requests.append((self.host, path))

    def getresponse(self) -> _FakeResponse:
        status, headers, body = type(self).script.pop(0)
        return _FakeResponse(status, headers, body)

    def close(self) -> None:
        pass


@pytest.fixture
def fake_transport(monkeypatch: pytest.MonkeyPatch) -> type[_FakeConnection]:
    """Remplace la couche HTTPS et la résolution DNS par des simulations locales."""
    import app.collectors.page_fetch as page_fetch

    _FakeConnection.script = []
    _FakeConnection.requests = []
    _FakeConnection.created_with = []
    monkeypatch.setattr(page_fetch.http.client, "HTTPSConnection", _FakeConnection)
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda host, port, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))],
    )
    return _FakeConnection


ALLOWED = ("boutique-tcg.example",)
PUBLIC = "93.184.216.34"


def test_successful_page_fetch(fake_transport: type[_FakeConnection]) -> None:
    html = b'<html><head><title>OK</title></head></html>'
    fake_transport.script = [(200, {"Content-Type": "text/html; charset=utf-8"}, html)]
    result = fetch_listing_page("https://boutique-tcg.example/carte/1", allowed_hosts=ALLOWED)
    assert result.content == html
    assert result.content_type == "text/html"
    assert result.final_url == "https://boutique-tcg.example/carte/1"
    # Aucun cookie ni identifiant intégré n'est transmis ; seul un GET borné part.
    assert fake_transport.requests == [("boutique-tcg.example", "/carte/1")]


def test_redirect_is_followed_and_reverified(fake_transport: type[_FakeConnection]) -> None:
    fake_transport.script = [
        (302, {"Location": "https://cdn.boutique-tcg.example/carte/2"}, b""),
        (200, {"Content-Type": "text/html"}, b"<html>finale</html>"),
    ]
    result = fetch_listing_page("https://boutique-tcg.example/carte/1", allowed_hosts=ALLOWED)
    assert result.final_url == "https://cdn.boutique-tcg.example/carte/2"
    assert result.content == b"<html>finale</html>"
    assert fake_transport.created_with == ["boutique-tcg.example", "cdn.boutique-tcg.example"]


@pytest.mark.parametrize("location", [
    "https://autre.example/carte",          # domaine hors liste autorisée
    "http://boutique-tcg.example/carte",    # schéma non HTTPS
])
def test_redirect_to_forbidden_destination_is_blocked(fake_transport: type[_FakeConnection], location: str) -> None:
    fake_transport.script = [(302, {"Location": location}, b"")]
    with pytest.raises(PageFetchError):
        fetch_listing_page("https://boutique-tcg.example/carte/1", allowed_hosts=ALLOWED)


def test_too_many_redirects_are_rejected(fake_transport: type[_FakeConnection]) -> None:
    fake_transport.script = [(302, {"Location": "https://boutique-tcg.example/a"}, b"")] * 5
    with pytest.raises(PageFetchError, match="redirect"):
        fetch_listing_page("https://boutique-tcg.example/carte/1", allowed_hosts=ALLOWED)


def test_oversized_response_is_rejected(fake_transport: type[_FakeConnection]) -> None:
    fake_transport.script = [(200, {"Content-Type": "text/html"}, b"x" * (2 * 1024 * 1024 + 1))]
    with pytest.raises(PageFetchError, match="taille"):
        fetch_listing_page("https://boutique-tcg.example/carte/1", allowed_hosts=ALLOWED)


@pytest.mark.parametrize("status,message", [
    (404, "introuvable"),
    (403, "authentification"),
    (500, "inattendu"),
])
def test_http_errors_have_specific_messages(fake_transport: type[_FakeConnection], status: int, message: str) -> None:
    fake_transport.script = [(status, {"Content-Type": "text/html"}, b"erreur")]
    with pytest.raises(PageFetchError, match=message):
        fetch_listing_page("https://boutique-tcg.example/carte/1", allowed_hosts=ALLOWED)


@pytest.mark.parametrize("content_type", ["application/json", "text/plain", ""])
def test_unsupported_content_type_is_rejected(fake_transport: type[_FakeConnection], content_type: str) -> None:
    fake_transport.script = [(200, {"Content-Type": content_type}, b"{}")]
    with pytest.raises(PageFetchError, match="contenu"):
        fetch_listing_page("https://boutique-tcg.example/carte/1", allowed_hosts=ALLOWED)


def test_image_fetch_accepts_only_photo_types(fake_transport: type[_FakeConnection]) -> None:
    fake_transport.script = [
        (200, {"Content-Type": "image/jpeg"}, b"\xff\xd8\xff"),
        (200, {"Content-Type": "application/pdf"}, b"%PDF"),
    ]
    result = fetch_listing_image("https://boutique-tcg.example/photo.jpg", allowed_hosts=ALLOWED)
    assert result.content == b"\xff\xd8\xff"
    with pytest.raises(PageFetchError, match="contenu"):
        fetch_listing_image("https://boutique-tcg.example/photo.jpg", allowed_hosts=ALLOWED)


@pytest.mark.parametrize("url", [
    "http://boutique-tcg.example/carte/1",
    "https://boutique-tcg.example:8443/carte/1",
    "https://user:pass@boutique-tcg.example/carte/1",
    "https://evil.example/carte/1",
    "ftp://boutique-tcg.example/carte/1",
])
def test_split_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(PageFetchError):
        _split_allowed(url, ALLOWED)


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.0.0.8", "192.168.1.1", "169.254.1.1", "::1", "fe80::1", "100.64.0.1",
])
def test_private_and_reserved_addresses_are_rejected(address: str) -> None:
    with pytest.raises(PageFetchError, match="privés|invalide"):
        _public_addresses("x", lambda *a, **k: [(2, 1, 6, "", (address, 443))])


def test_unresolvable_domain_is_rejected() -> None:
    def _fail(*args: Any, **kwargs: Any) -> list[Any]:
        raise OSError("NXDOMAIN")

    with pytest.raises(PageFetchError, match="résolu"):
        _public_addresses("introuvable.example", _fail)


def test_literal_global_ip_host_is_accepted() -> None:
    assert _public_addresses(PUBLIC, lambda *a, **k: []) == [PUBLIC]


def test_literal_private_ip_host_is_rejected() -> None:
    with pytest.raises(PageFetchError):
        _public_addresses("192.168.0.1", lambda *a, **k: [])


def test_policy_requires_explicit_allowlist() -> None:
    denied = fetch_policy_for_url("https://www.vinted.fr/items/1", ())
    assert denied["status"] == "unavailable"
    assert "extension" in denied["message"] and "manuellement" in denied["message"]
    allowed = fetch_policy_for_url("https://www.vinted.fr/items/1", ("vinted.fr",))
    assert allowed["status"] == "allowed"
    assert fetch_policy_for_url("https://www.vinted.fr/items/1", ("boutique-tcg.example",))["status"] == "unavailable"


def test_policy_never_treats_validated_url_as_extracted() -> None:
    """Une URL validée n'est jamais présentée comme une annonce extraite."""
    policy = fetch_policy_for_url("https://www.ebay.fr/itm/123456789012", ())
    assert policy["status"] == "unavailable"


def test_fetched_content_dataclass() -> None:
    fetched = FetchedContent(content=b"x", content_type="text/html", final_url="https://a.example/")
    assert fetched.content == b"x"
