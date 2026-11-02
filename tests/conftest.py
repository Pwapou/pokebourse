"""Configuration hermétique des tests, indépendante de l'instance locale."""
import os


def pytest_configure() -> None:
    # Les tests qui exercent la récupération fournissent leurs propres mocks et
    # listes d'hôtes. Une configuration Compose active ne doit jamais leur
    # permettre d'émettre des requêtes marketplace réelles.
    os.environ.pop("POKEMON_PAGE_FETCH_ALLOWED_HOSTS", None)
