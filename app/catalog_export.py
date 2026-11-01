import csv
import io

# Colonnes exportées, dans un ordre stable et documenté :
# id, external_id, name, set_name, card_number, language, condition,
# variant, edition, grading_company, grade, certification_number,
# price_cents, currency, seller, url, imported_at, source_name.
# Le prix est exporté en centimes (entier) avec sa devise dans une colonne
# dédiée afin de rester indépendant de toute locale.
CSV_COLUMNS: tuple[tuple[str, str], ...] = (
    ("id", "Identifiant interne"),
    ("external_id", "Identifiant externe"),
    ("name", "Nom de la carte"),
    ("set_name", "Extension"),
    ("card_number", "Numéro"),
    ("language", "Langue"),
    ("condition", "État"),
    ("variant", "Variante"),
    ("edition", "Édition"),
    ("grading_company", "Certificateur"),
    ("grade", "Grade"),
    ("certification_number", "Numéro de certificat"),
    ("price_cents", "Prix (centimes)"),
    ("currency", "Devise"),
    ("seller", "Vendeur"),
    ("url", "URL"),
    ("imported_at", "Date d'import"),
    ("source_name", "Source"),
)

CSV_FILENAME = "pokebourse-catalogue.csv"

_DANGEROUS_PREFIXES = ("=", "+", "-", "@")


def csv_cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    # Protection contre l'injection de formules dans Excel/LibreOffice :
    # une cellule commençant par =, +, - ou @ est neutralisée par un
    # apostrophe en tête, interprétée comme du texte par les tableurs.
    if text.startswith(_DANGEROUS_PREFIXES):
        return f"'{text}"
    return text


def build_catalog_csv(rows: list) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([header for _, header in CSV_COLUMNS])
    for row in rows:
        data = dict(row)
        writer.writerow([csv_cell(data.get(key)) for key, _ in CSV_COLUMNS])
    # BOM UTF-8 pour qu'Excel reconnaisse correctement les accents.
    return buffer.getvalue().encode("utf-8-sig")
