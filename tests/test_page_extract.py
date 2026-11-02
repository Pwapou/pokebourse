"""Extraction locale de pages déjà obtenues, sans réseau."""
import pytest

from app.collectors.page_extract import extract_html, marketplace_fetch_policy


def test_jsonld_product_and_price_as_cents() -> None:
    html = b'''<script type="application/ld+json">{"@type":"Product","name":"Pikachu 173/165","description":"Carte 151","image":"https://i.ebayimg.com/p.jpg","offers":{"price":83.25,"priceCurrency":"EUR"}}</script>'''
    result = extract_html(html, 'https://www.ebay.fr/itm/123')
    assert result['fields']['title']['value'] == 'Pikachu 173/165'
    assert result['fields']['price_cents']['value'] == 8325
    assert result['fields']['currency']['value'] == 'EUR'
    assert result['fields']['image_url']['value'] == 'https://i.ebayimg.com/p.jpg'
    assert result['status'] == 'complete'


def test_opengraph_partial_and_currency() -> None:
    result = extract_html(b'<meta property="og:title" content="Dracaufeu"><meta property="product:price:amount" content="12.50"><meta property="product:price:currency" content="USD">', 'https://www.ebay.fr/')
    assert result['fields']['price_cents']['value'] == 1250
    assert result['fields']['currency']['value'] == 'USD'
    assert 'description' not in result['fields']
    assert result['fields']['title']['source'] == 'opengraph'


def test_unsafe_url_or_untrusted_content_and_unsupported_fetch() -> None:
    result = extract_html(b'<meta property="og:image" content="http://127.0.0.1/a">', 'https://www.ebay.fr/')
    assert 'image_url' not in result['fields']
    with pytest.raises(ValueError):
        extract_html(b'{}', 'https://www.ebay.fr/', 'application/json')
    with pytest.raises(ValueError):
        extract_html(b'x' * (2 * 1024 * 1024 + 1), 'https://www.ebay.fr/')
    assert marketplace_fetch_policy('vinted')['status'] == 'unavailable'
    assert marketplace_fetch_policy('ebay')['status'] == 'unavailable'


def test_shipping_rate_is_only_a_proposal() -> None:
    html = b'''<script type="application/ld+json">{"@type":"Product","name":"Pikachu","offers":{"price":"10.00","priceCurrency":"EUR","shippingDetails":{"shippingRate":{"value":"4.50","currency":"EUR"}}}}</script>'''
    shipping = extract_html(html, 'https://www.ebay.fr/')['fields']['shipping_cents']
    assert shipping['value'] == 450
    assert shipping['status'] == 'propose'
