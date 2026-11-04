BEGIN IMMEDIATE;

-- Périmètre réellement couvert par la synchronisation (T05) : chaque tâche
-- porte la locale de la fiche demandée. La locale « fr » reste la valeur
-- historique par défaut ; les demandes existantes sont reprises sans
-- modification de leur comportement.

ALTER TABLE tcgdex_sync_jobs ADD COLUMN locale TEXT NOT NULL DEFAULT 'fr';

INSERT INTO schema_migrations (version) VALUES ('0026_tcgdex_sync_locale.sql');

COMMIT;
