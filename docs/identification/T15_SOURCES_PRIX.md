# T15 — Capacités réelles des sources de prix

Date de vérification : **3 novembre 2026**. Lot documentaire de `TASKING_IDENTIFICATION_FIABLE.md` : établir la matrice offres actives / ventes conclues / cotes agrégées en distinguant **capacité théorique** (ce qu'une source pourrait fournir selon sa documentation officielle) et **accès réellement configuré sur cette installation** (ce que le code et la configuration actuels obtiennent réellement). Aucune souscription, aucun achat, aucun accès automatique nouveau n'a été déclenché par ce lot ; aucun secret n'est reproduit ici.

Méthode : lecture du code (`app/collectors/`, `app/search/external.py`, `app/cardmarket/`, `app/profitability.py`, `app/purchases.py`, `app/config.py`, `compose.yaml`), de la base locale en lecture seule (compteurs uniquement) et de SOURCES.md. Réseau : aucune requête d'essai vers une marketplace ; les références officielles citées dans le tasking (Browse API, Marketplace Insights, fichiers Cardmarket) restent à revalider avant tout engagement d'implémentation.

## 1. Matrice des capacités

| Source | Offres actives | Ventes conclues individuelles | Cotes agrégées | Accès réellement configuré | Coût / quotas |
|---|---|---|---|---|---|
| **Cardmarket — fichiers publics quotidiens** | Non (le guide agrégé n'est pas une liste d'offres) | Non (moyennes, pas de transactions individuelles) | **Oui** : tendance + moyennes 1/7/30 jours, en centimes, fraîcheur J-1 | **Oui, fonctionnel** : `app/cardmarket/guide.py` synchronise les deux fichiers publics ; 75 082 prix locaux au 2026-11-03 | Gratuit, sans compte ; 2 requêtes/jour ; noms anglais, pas de nom d'extension, **pas de prix par certificateur/note** |
| **Cardmarket — API officielle 2.0** | Théorique (OAuth 1.0a) | Théorique | Théorique | **Non établi** : client dormant `app/cardmarket/client.py` ; vérifié le 2026-11-01, Cardmarket n'accepte plus les demandes d'accès ; aucun identifiant configuré (`CARDMARKET_*` absents de `.env.example` et de Compose) | Gratuit si accès, mais inscriptions fermées |
| **eBay — connecteur actuel** | **Partiel et non contractuel** : `app/collectors/ebay.py` interroge la page de recherche HTML `ebay.fr/sch` sans authentification, avec en-têtes de navigateur émulés ; parsing JSON best-effort d'une page conçue pour le HTML | Non | Non | Présent dans le code, mais sans autorisation établie et sans clé ; fragile (changement de page = silence ou erreur) ; utilisé seulement par la recherche externe explicite `/search?external=1` | Gratuit, sans quota officiel ; risque de blocage ; **ce n'est pas l'API officielle** |
| **eBay — Browse API officielle** | Théorique : recherche d'offres actives avec OAuth 2.0 | Non | Non | **Non configuré** : aucun code Browse API dans le dépôt, aucune clé (`EBAY_*` absent de `app/config.py`, `.env.example`, Compose) | Compte développeur eBay requis ; quotas par jour selon niveau ; à mettre en place avant tout réemploi qualifié |
| **eBay — Marketplace Insights (ventes conclues)** | Non | **Théoriquement indisponible** : documentation consultée lors du recadrage indique l'API restreinte et fermée aux nouveaux utilisateurs | Non | **Absent du code, accès non établi** : aucune clé, aucun appel ; capacité déclarée **indisponible** tant qu'un accès effectif n'est pas prouvé | Soumis à admission eBay ; aucune simulation de ventes à partir des offres n'est autorisée |
| **Vinted** | Capture humaine (extension Chrome, import JSONL, saisie URL bornée aux hôtes configurés) | Non : le statut « vendu » observé sans montant n'est pas une vente documentée | Non | Import manuel uniquement ; scraping serveur non autorisé (CGU) et non activé | Gratuit, manuel |
| **Leboncoin** | Idem : capture/import manuel | Non | Non | Idem (DataDome ; CGU) | Gratuit, manuel |
| **Wallapop** | Idem : capture/import manuel | Non | Non | Idem | Gratuit, manuel |
| **TCGdex** | Non | Non | Non | Référentiel d'identité uniquement ; aucune cote ; aucun contenu d'annonce transmis | Gratuit, Fair Use |
| **Références manuelles locales (`market_references`)** | Partiel (nature « annonces » possible, déclarée par l'utilisateur) | **Oui, si documentées** : 1 660 références locales de nature `ventes_conclues` au 2026-11-03 (import historique), avec prix en centimes, date d'observation et source ; la nature et la date de transaction restent à documenter par l'utilisateur | Non | Disponible immédiatement ; saisie manuelle via l'écran Rentabilité | Gratuit, manuel |
| **Reventes personnelles (`purchases.sale_price_cents`)** | Non | **Oui** : prix de vente réel saisi par l'utilisateur ; colonne ajoutée par la migration 0021 ; 0 enregistrement au 2026-11-03 | Non | Disponible dès le premier achat suivi et revendu documenté | Gratuit, manuel |

## 2. Divergences code / documentation relevées (à corriger dans SOURCES.md)

1. **eBay** : SOURCES.md (tableau de synthèse, section 5) indique « Oui / API officielle » et « Endpoint de recherche / API eBay ». Le code actuel n'utilise **pas** l'API officielle eBay : c'est la page de recherche HTML publique sans authentification. La ligne est corrigée le jour même (section ajoutée en bas de SOURCES.md) pour distinguer la capacité officielle théorique et la méthode réellement implémentée.
2. **eBay / ventes conclues** : aucune capacité d'historique des ventes n'est configurée ni même codée ; la documentation Marketplace Insights indique une API restreinte fermée aux nouveaux utilisateurs. Toute fonctionnalité « ventes eBay automatiques » est donc **indisponible** à ce stade, sans préjudice d'une demande d'accès ultérieure.
3. **Cardmarket** : le guide fournit des cotes agrégées de cartes **non gradées** en anglais ; il ne fournit ni offres, ni transactions, ni prix par certificateur/note. SOURCES.md le disait déjà ; la matrice ci-dessus le fige comme seule source de cote automatique disponible.

## 3. Limites et coûts par catégorie de besoin J3

### Offres actives

- **Automatique** : seul le connecteur eBay HTML existe, sans autorisation établie ; aucune clé d'API officielle n'est configurée. Aucune source d'offres automatique n'est donc « établie » au sens du tasking.
- **Manuel** : captures extension, imports JSONL et recherches marketplace humaines restent la voie autorisée pour Vinted, Leboncoin, Wallapop et en complément eBay.

### Ventes conclues documentées

- **Automatique : indisponible.** Marketplace Insights fermé aux nouveaux utilisateurs ; aucune autre source de transactions n'est configurée. Une annonce retirée, une enchère en cours ou un statut « vendu » sans montant ne sera jamais converti en prix de vente réalisé.
- **Manuel : disponible** via `market_references` (nature `ventes_conclues`, prix, date, source à documenter) et `purchases.sale_price_cents` pour les reventes personnelles.

### Cotes agrégées

- **Cardmarket (fichiers publics)** : disponible, fraîcheur quotidienne, 75 082 prix locaux, pont multilingue via `card_name_aliases` (44 323 alias au 2026-11-03). Limites : non gradé, anglais, pas de nom d'extension, agrégé (moyennes), langue/état non garanties. Utilisable comme **troisième catégorie**, jamais comme liste de transactions ni comme prix d'un exemplaire gradé.

### Cartes gradées PSA / PCA

Aucune source automatique configurée ne fournit des prix par certificateur/note. Cardmarket guide : non gradé uniquement. eBay sold : indisponible. Conséquence : la comparaison qualifiée des gradées exige des **ventes documentées manuelles** ou une source nouvelle soumise à choix produit (budget éventuel). C'est un trou de couverture explicite de J3, pas une fonctionnalité livrée.

## 4. Décisions produit nécessaires avant d'activer un comportement dépendant

| # | Décision | Impact | État |
|---|---|---|---|
| D1 | Zone géographique (France / UE / monde), pays de livraison, devises et importations | Requêtes eBay éventuelles, comparabilité et coût livré T16/T17 | **Ouvert** |
| D2 | Données de prix insuffisantes : estimation indicative, aucune estimation ou scénario saisi | Repli et affichage financier T18 | **Ouvert** |
| D3 | Canal de revente (plateforme choisie ou comparaison des canaux) | Frais et scénario de marge T18 | **Ouvert** |
| D4 | Niveau de comparabilité (même version/langue/finition/état ; gradées : même certificateur et note) | Sélection des preuves T17 | Proposition conservatrice à valider |
| D5 | Source complémentaire éventuellement payante pour les ventes conclues et/ou les gradées | Couvre le trou de ventes automatiques et gradées ; **aucun budget validé, aucune souscription déclenchée** | **Ouvert** |
| D6 | Demande d'accès eBay officiel (Browse API) pour des offres actives contractuelles | Remplace le connecteur HTML non autorisé ; nécessite compte développeur eBay et clés | **Ouvert** ; sans objet si D5 choisit une autre source |

Aucun de ces choix n'a été tranché par ce lot ; aucun comportement produit dépendant n'a été activé. Les contrats, interfaces et tests simulés de T14/T16/T17/T18 peuvent avancer sur des données figées locales indépendamment de ces décisions.

## 5. Ce qui est disponible dès maintenant (sans nouvelle décision)

1. Cotes agrégées Cardmarket synchronisables manuellement, une fois par jour, sans coût.
2. Ventes conclues documentées manuellement (`market_references`, `purchases`) avec prix réels, exploitables dès saisie.
3. Offres locales observées (catalogue Pokébourse) et captures humaines, comparables manuellement.
4. Recherche externe explicite `/search?external=1` existante (TCGdex en file worker, eBay HTML best-effort, sources protégées signalées indisponibles) — son rôle reste explicite et ne devient pas une recherche de marché automatique post-identification (T16).

**Acceptation T15 :** matrice versionnée établie, divergence SOURCES.md corrigée, capacités manquantes visibles avec leur impact J3 explicite (ventes automatiques indisponibles ; gradées sans source automatique), aucune souscription ni accès réel déclenché.
