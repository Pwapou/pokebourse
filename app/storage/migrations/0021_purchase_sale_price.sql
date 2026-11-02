BEGIN IMMEDIATE;

ALTER TABLE purchases ADD COLUMN sale_price_cents INTEGER CHECK (sale_price_cents IS NULL OR sale_price_cents >= 0);

INSERT INTO schema_migrations (version) VALUES ('0021_purchase_sale_price.sql');
COMMIT;
