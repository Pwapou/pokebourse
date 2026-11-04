BEGIN IMMEDIATE;

-- Alias contrôlés du référentiel (T05). Un alias n'est jamais fabriqué
-- automatiquement : il porte une cible vérifiable, une langue/périmètre, une
-- provenance explicite et une version. Les collisions et les correspondances
-- approximatives sont conservées comme suggestions, jamais promues en
-- équivalence d'impression.

CREATE TABLE reference_aliases (
    id INTEGER PRIMARY KEY,
    alias TEXT NOT NULL,
    raw_alias TEXT NOT NULL,
    target_card_id INTEGER NOT NULL REFERENCES pokemon_reference_cards(id),
    locale TEXT CHECK(locale IS NULL OR length(locale) > 0),
    scope TEXT NOT NULL DEFAULT 'card' CHECK(scope IN ('card', 'set')),
    provenance TEXT NOT NULL CHECK(provenance IN ('manual', 'tcgdex', 'cardmarket', 'import')),
    status TEXT NOT NULL CHECK(status IN ('active', 'suggestion')),
    version TEXT NOT NULL,
    note TEXT,
    created_by TEXT NOT NULL DEFAULT 'local',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(alias, target_card_id, locale, scope)
);
CREATE INDEX reference_aliases_lookup ON reference_aliases(alias, status);
CREATE INDEX reference_aliases_target ON reference_aliases(target_card_id);

INSERT INTO schema_migrations (version) VALUES ('0025_reference_aliases.sql');

COMMIT;
