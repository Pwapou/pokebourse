"""Détection des annonces identiques entre parcours d'import."""
import sqlite3


def listing_url_identity(source: str, url: str | None) -> tuple[str, str] | None:
    """Renvoie uniquement une identité de plateforme vérifiable par une URL officielle."""
    from app.manual_listing import parse_listing_url
    try:
        requested = parse_listing_url(url or "")
    except ValueError:
        return None
    if source not in (requested["platform"], "extension-chrome", "import-web"):
        return None
    return requested["platform"], requested["external_id"]


def find_existing_listing_url(connection: sqlite3.Connection, platform: str, url: str | None) -> int | None:
    """Compare les URL officiellement reconnues au sein d'une même plateforme.

    Les anciens imports peuvent utiliser des identifiants préfixés ou hachés.
    Une URL non reconnue ou de plateforme discordante n'est jamais assimilée.
    """
    from app.manual_listing import parse_listing_url

    identity = listing_url_identity(platform, url)
    if identity is None:
        return None
    requested_platform, requested_id = identity
    rows = connection.execute(
        "SELECT c.id, c.url FROM catalog_items c JOIN sources s ON s.id = c.source_id "
        "WHERE s.name IN (?, 'extension-chrome', 'import-web') AND c.url IS NOT NULL", (requested_platform,),
    )
    for row in rows:
        try:
            existing = parse_listing_url(row[1])
        except ValueError:
            continue
        if existing["platform"] == requested_platform and existing["external_id"] == requested_id:
            return int(row[0])
    return None
