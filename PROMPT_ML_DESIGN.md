# Prompt — Conception de la phase Machine Learning du projet Pokebourse

Tu es un architecte machine learning expérimenté, spécialisé en NLP appliqué et en systèmes de récupération d'information (information retrieval), travaillant sur un projet Python en production. Ta mission : réfléchir puis rédiger un **document de conception complet** pour intégrer du machine learning dans l'identification automatique de cartes Pokémon à partir d'annonces de marketplace.

Réponds **exclusivement en français**.

---

## 1. Contexte du projet

**Pokebourse** est un outil de veille de prix de cartes Pokémon sur les marketplaces françaises (Vinted, Leboncoin). Pipeline actuel :

1. **Collecte** : scraping d'annonces (app/collectors/) via navigateur automatisé, normalisation des données brutes.
2. **Identification** : moteur actuel basé sur des règles (app/identification/) qui réconcilie chaque annonce avec un catalogue de référence **TCGdex** (stocké en SQLite localement, via app/tcgdex/).
3. **Rentabilité** : calcul de marge estimée (app/profitability.py) sur les annonces identifiées.
4. **Interface web** : FastAPI + templates Jinja (app/web.py), suivi des statuts d'identification.

### État actuel du moteur d'identification (règles, pas de ML)

Le moteur actuel fonctionne en trois étapes :

- **Extraction** (`detector.py`) : regex sur le titre + la description normalisée (NFKD, sans accents, minuscules). Extrait : numéro de carte (format « 4/102 » prioritaire, sinon « n°4 »), extension via une liste figée `_KNOWN_SETS` (~25 extensions), langue (« VF », « VO », « JAP »), variante (« holo », « VMAX », « secrète », « alt art »…), état (« neuf », « NM »…), gradation (« PSA 10 »), détection de lots. Le nom de carte est extrait via séparateur tiret, une liste de ~30 Pokémon célèbres, ou le premier mot pertinent.
- **Recherche en cascade** (`matcher.py`) : requêtes SQLite sur le catalogue TCGdex (nom + numéro, puis numéro + extension, puis nom seul limité à 20 candidats).
- **Scoring additif pondéré** : nom exact +45, nom partiel +35, numéro local exact +40, extension +20, rareté/variante +10 (plafonné à 100). Décision par seuils : score ≥ 80 → `identified` ; ex æquo au sommet avec score < 90, ou score < 80 → `ambiguous` ; aucun candidat ou aucune info → `unidentified` ; lot détecté → `lot`. Le résultat porte des raisons lisibles (« nom exact ; numéro 4/102 exact »).

### Réalité des données

- **Titre brouillon** : formulations non normalisées (« dracaufeu 1ere ed 4/102 mint psa »), fautes de frappe, mélange franglais, emoji, majuscules.
- **Description parfois absente** ou générique ; parfois riche et discriminante.
- **Photos d'annexes** disponibles mais jamais exploitées (le visuel pourrait distinguer variantes/éditions).
- **Champs fréquemment manquants** : numéro, extension, état → beaucoup d'annonces tombent en `ambiguous`.
- **Aucune donnée d'entraînement labellisée** : les annonces `ambiguous`/`unidentified` ne sont pas corrigées manuellement aujourd'hui, donc pas de boucle de feedback.

### Contraintes techniques et métier

- Python 3.12, FastAPI, SQLite, déploiement via Docker ; pas de GPU en production.
- **Traçabilité exigée** : chaque identification doit rester justifiable (raison lisible, pas une boîte noire). Un système hybride (ML pour ordonner, règles pour décider/expliquer) est acceptable et même souhaitable.
- Le catalogue de référence TCGdex est la source de vérité : l'objectif n'est pas de prédire le prix, mais d'**associer chaque annonce à la bonne carte TCGdex** (problème de matching/ranking, ~15 000 à 40 000 cartes dans le catalogue).
- Budget temps de calcul raisonnable : le worker tourne en tâche de fond, l'identification doit rester de l'ordre de la seconde par annonce au maximum.

---

## 2. Ta mission

Rédige un document de conception structuré pour le développement de la phase ML. **Raisonne avant de proposer** : pour chaque choix, expose les alternatives envisagées, les critères de décision, et le moment où ce choix devient pertinent. Sois honnête : si une approche « classique » (non-ML) suffit pour un sous-problème, dis-le et recommande-la.

Le document doit couvrir, dans cet ordre :

### A. Cadrage et préalable indispensable
- Pourquoi le ML n'est pas la première étape : le problème de l'absence de données labellisées.
- Conception de la **boucle de validation humaine** : mécanisme d'enrichissement (champs `validated_card_id`, `validated_by`, `validated_at`), interface minimale de correction, règles métier (que valide-t-on ? cas `ambiguous` seulement ? `unidentified` ? les `identified` aussi en échantillon pour mesurer le taux d'erreur ?).
- Schéma de la table/jointure et impact sur les migrations SQL existantes.
- Objectifs quantitatifs de collecte : combien de labels pour commencer, seuil de confiance minimal pour auto-étiqueter le reste.

### B. Formulation du problème ML
- Reformuler la tâche précisément : est-ce une classification multi-classes (~15 000+ classes, peu réaliste en l'état) ? Un problème de retrieval/ranking (annonce → top-K candidats du catalogue) ? Un problème d'entity linking ? Justifier le choix retenu.
- Définition formelle de l'entrée, de la sortie, et de la fonction de perte adaptée.
- Ce qu'on entraîne vs ce qu'on garde en règles (décision par seuil, gestion des lots, explication).

### C. Stratégie de données
- Pipeline de dataset : extraction des paires (annonce normalisée, carte TCGdex validée), gestion du déséquilibre (cartes rares vs communes), augmentation de données plausible (paraphrases de titres, suppression de champs), split train/validation/test **sans fuite** (attention aux annonces quasi identiques), gestion des versions du dataset.
- Auto-labellisation à grande échelle : quand et comment utiliser le moteur de règles (score ≥ 90 ?) pour générer du bruit contrôlé, avec quels garde-fous.

### D. Choix des modèles — options comparées
Comparer au moins ces familles, avec critères de choix (données disponibles, CPU-only, explicabilité, coût maintenance) :
1. Baseline améliorée sans ML (Levenshtein, index inversé, BM25) — le point de référence à battre.
2. Embeddings sémantiques (sentence-transformers multilingue) pour encoder annonce et descriptions de cartes, similarité cosinus pour reranker les candidats du moteur de règles.
3. Modèle de ranking supervisé (learning-to-rank, ex. LightGBM LambdaRank) sur features structurées (score règles, similarités, correspondances de champs).
4. Fine-tuning d'un modèle de type cross-encoder sur paires (annonce, candidat) → score de pertinence.
5. (Optionnel, phase ultérieure) Vision : classifier l'édition/variante à partir des photos d'annonce.
Pour chacun : données requises, effort d'implémentation, latence CPU, explicabilité, risques.

### E. Architecture d'intégration cible
- Schéma du flux : collecte → extraction règles → récupération candidats (cascade actuelle) → reranking ML → décision par seuils (règles) → validation humaine → ré-entraînement périodique.
- Où le modèle vit (artefact versionné, chargement, fallback sur règles si le modèle indisponible ou score trop faible).
- Gestion de la dérive : monitoring des distributions d'entrée, déclenchement de ré-entraînement.

### F. Évaluation
- Métriques : précision@1, précision@5, taux d'identification correcte, taux d'escalade vers validation humaine, comparaison avant/après sur un jeu de test figé.
- Protocole d'évaluation humaine (échantillonnage, seuils de confiance).
- Critères de bascule : à quel moment le modèle remplace-t-il (ou non) les règles ?

### G. Roadmap séquencée avec jalons mesurables
- Découper en phases (0 : instrumenter la validation ; 1 : baseline + données ; 2 : première version ML ; 3 : itérations), avec pour chaque phase : livrables, critères de succès chiffrés, estimation d'effort relative, risques et plans B.

### H. Risques et anti-patterns
- Pièges classiques : fuite de données dans le split, auto-labellisation circulaire, survendre la précision sur un dataset déséquilibré, boîte noire incompatible avec la traçabilité métier, GPU requis alors que l'infra est CPU.

---

## 3. Exigences de rédaction

- **Structure** : document Markdown avec titres hiérarchiques, tableaux comparatifs pour les options de modèles, diagrammes en ASCII si utile.
- **Précision** : citer des bibliothèques Python concrètes et compatibles Python 3.12 / CPU (ex. `sentence-transformers`, `lightgbm`, `rapidfuzz`), pas de technologies vagues.
- **Honnêteté** : si une recommandation repose sur une hypothèse incertaine (volume de données, qualité des labels), l'expliciter et proposer un test de validation avant d'engager le développement.
- **Ancrage** : toute proposition doit tenir compte du code existant décrit dans la section 1 (schémas SQLite, statuts `identified`/`ambiguous`/`unidentified`/`lot`, pipeline worker/web), pas repartir d'une feuille blanche.
- Longueur cible : document dense mais actionnable (pas de remplissage), de l'ordre de 3 000 à 5 000 mots.

Commence par une synthèse en 10 lignes maximum de ta recommandation stratégique globale, puis développe le document.
