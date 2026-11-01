import csv
import io

from app.catalog_export import CSV_COLUMNS, build_catalog_csv, csv_cell


def row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": 1,
        "external_id": "annonce-001",
        "name": "Pikachu",
        "set_name": "Évolutions",
        "card_number": "35/108",
        "language": "fr",
        "condition": "NM",
        "variant": "Holo",
        "edition": "Unlimited",
        "grading_company": None,
        "grade": None,
        "certification_number": None,
        "price_cents": 1290,
        "currency": "EUR",
        "seller": "Collection locale",
        "url": "https://example.com/annonce/1",
        "imported_at": "2026-11-01T10:00:00.000Z",
    }
    base.update(overrides)
    return base


def parse_csv(content: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))


def test_csv_starts_with_bom_and_stable_headers() -> None:
    content = build_catalog_csv([row()])

    assert content.startswith(b"\xef\xbb\xbf")
    lines = parse_csv(content)
    assert lines[0] == [header for _, header in CSV_COLUMNS]


def test_csv_uses_crlf_and_round_trips_special_characters() -> None:
    tricky = row(
        name='Dracaufeu "EX", édition\nspéciale',
        seller="Vendeur ; français",
        url=None,
        card_number=None,
        condition=None,
    )

    content = build_catalog_csv([tricky])
    lines = content.decode("utf-8-sig").split("\r\n")

    assert lines[0].endswith("\n") is False
    parsed = parse_csv(content)
    values = dict(zip((key for key, _ in CSV_COLUMNS), parsed[1], strict=True))
    assert values["name"] == 'Dracaufeu "EX", édition\nspéciale'
    assert values["seller"] == "Vendeur ; français"
    # Valeurs vides exportées comme cellules vides.
    assert values["card_number"] == ""
    assert values["condition"] == ""
    assert values["url"] == ""


def test_csv_escapes_formula_injection() -> None:
    content = build_catalog_csv(
        [
            row(name="=1+1"),
            row(external_id="+cmd"),
            row(seller="-2+3"),
            row(set_name="@Somme(A1)"),
            row(name="Prix : 5 €"),
        ]
    )
    parsed = parse_csv(content)
    keys = [key for key, _ in CSV_COLUMNS]
    data = [dict(zip(keys, values, strict=True)) for values in parsed[1:]]

    assert data[0]["name"] == "'=1+1"
    assert data[1]["external_id"] == "'+cmd"
    assert data[2]["seller"] == "'-2+3"
    assert data[3]["set_name"] == "'@Somme(A1)"
    # Les valeurs sans préfixe dangereux restent inchangées.
    assert data[4]["name"] == "Prix : 5 €"


def test_csv_cell_handles_none_and_non_strings() -> None:
    assert csv_cell(None) == ""
    assert csv_cell(1290) == "1290"
    assert csv_cell("=x") == "'=x"
    assert csv_cell("texte") == "texte"


def test_csv_empty_catalog_exports_header_only() -> None:
    content = build_catalog_csv([])
    parsed = parse_csv(content)

    assert len(parsed) == 1
    assert parsed[0][0] == "Identifiant interne"
