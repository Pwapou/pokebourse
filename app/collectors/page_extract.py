"""Extraction bornée de métadonnées HTML déjà obtenues de manière autorisée.

Ce module ne télécharge aucune URL et ne crée aucun enregistrement. Les pages
marketplace soumises à restrictions doivent être lues via le navigateur de
l'utilisateur ou un accès officiel explicitement configuré.
"""
from __future__ import annotations

import json
from decimal import Decimal
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from app.collectors.models import ListingValidationError, parse_price_to_cents

MAX_HTML_BYTES = 2 * 1024 * 1024


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.jsonld: list[str] = []
        self._json: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag.lower() == 'meta':
            key = (attributes.get('property') or attributes.get('name') or '').lower()
            value = attributes.get('content')
            if key and value and key not in self.meta:
                self.meta[key] = value.strip()[:5000]
        elif tag.lower() == 'script' and (attributes.get('type') or '').lower().split(';')[0].strip() == 'application/ld+json':
            self._json = []

    def handle_data(self, data: str) -> None:
        if self._json is not None:
            self._json.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == 'script' and self._json is not None:
            self.jsonld.append(''.join(self._json))
            self._json = None


def _products(value: Any, depth: int = 0) -> list[dict[str, Any]]:
    if depth > 8:
        return []
    if isinstance(value, list):
        return [product for child in value[:100] for product in _products(child, depth + 1)]
    if not isinstance(value, dict):
        return []
    types = value.get('@type', [])
    types = [types] if isinstance(types, str) else types
    found = [value] if isinstance(types, list) and any(str(t).lower().split('/')[-1] == 'product' for t in types) else []
    return found + _products(value.get('@graph'), depth + 1)


def _text(value: Any, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = ' '.join(value.split())[:maximum]
    return value or None


def _image(value: Any, base_url: str) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get('url')
    if not isinstance(value, str):
        return None
    try:
        url = urljoin(base_url, value)
        parts = urlsplit(url)
        if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or len(url) > 2048:
            return None
        return url
    except ValueError:
        return None


def extract_html(html: bytes, base_url: str, content_type: str = 'text/html') -> dict[str, Any]:
    """Retourne des champs et leur provenance, sans inventer les valeurs absentes."""
    if len(html) > MAX_HTML_BYTES:
        raise ValueError('La page dépasse la limite de 2 Mo.')
    if content_type.split(';', 1)[0].strip().lower() not in ('text/html', 'application/xhtml+xml'):
        raise ValueError('La réponse ne contient pas de page HTML.')
    parser = _MetadataParser()
    parser.feed(html.decode('utf-8', errors='replace'))
    product: dict[str, Any] = {}
    for block in parser.jsonld[:20]:
        try:
            found = _products(json.loads(block, parse_float=Decimal))
        except (ValueError, RecursionError):
            continue
        if found:
            product = found[0]
            break
    fields: dict[str, dict[str, Any]] = {}
    def add(key: str, value: Any, source: str) -> None:
        if value is not None:
            fields[key] = {'value': value, 'status': 'trouve', 'source': source}
    for key, prop, meta, limit in [('title', 'name', 'og:title', 300), ('description', 'description', 'og:description', 5000), ('condition', 'itemCondition', '', 100)]:
        value = _text(product.get(prop), limit)
        if value:
            add(key, value, 'jsonld')
        elif meta:
            add(key, _text(parser.meta.get(meta), limit), 'opengraph')
    image = _image(product.get('image'), base_url)
    if image:
        add('image_url', image, 'jsonld')
    else:
        add('image_url', _image(parser.meta.get('og:image'), base_url), 'opengraph')
    offers = product.get('offers')
    if isinstance(offers, list):
        offers = offers[0] if len(offers) == 1 else None
    offers = offers if isinstance(offers, dict) else {}
    if 'condition' not in fields:
        add('condition', _text(offers.get('itemCondition'), 100), 'jsonld')
    add('published_at', _text(product.get('datePublished'), 40), 'jsonld')
    price = offers.get('price')
    source = 'jsonld'
    if price is None:
        price, source = parser.meta.get('product:price:amount'), 'opengraph'
    if price is not None:
        try:
            cents = parse_price_to_cents(price)
            if cents <= 1_000_000_000:
                add('price_cents', cents, source)
        except (ListingValidationError, ValueError):
            pass
    currency = offers.get('priceCurrency') or parser.meta.get('product:price:currency')
    if isinstance(currency, str) and len(currency) == 3 and currency.isascii() and currency.isalpha():
        add('currency', currency.upper(), 'jsonld' if offers.get('priceCurrency') else 'opengraph')
    # Un seul tarif explicite dans la même devise ; plusieurs options ne
    # permettent pas de connaître le coût applicable à l'acheteur.
    shipping = offers.get('shippingDetails')
    if isinstance(shipping, list):
        shipping = shipping[0] if len(shipping) == 1 else None
    rate = shipping.get('shippingRate') if isinstance(shipping, dict) else None
    if isinstance(rate, dict) and currency and str(rate.get('currency', '')).upper() == str(currency).upper():
        try:
            cents = parse_price_to_cents(rate.get('value'), 'port')
            if cents <= 1_000_000_000:
                fields['shipping_cents'] = {'value': cents, 'status': 'propose', 'source': 'jsonld', 'note': 'Tarif extrait, à confirmer selon la destination et le mode de livraison.'}
        except (ListingValidationError, ValueError):
            pass
    return {'status': 'complete' if all(k in fields for k in ('title', 'price_cents', 'currency')) else 'partial', 'fields': fields}


def marketplace_fetch_policy(platform: str) -> dict[str, str]:
    """Interdit le scraping serveur tant qu'un accès officiel n'est pas intégré."""
    return {'status': 'unavailable', 'message': 'Récupération serveur non disponible pour cette plateforme. Utilisez l’extension sur la page ouverte ou complétez les champs manuellement.'}
