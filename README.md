# Company Docs Downloader

CLI Python modulaire pour rechercher des entreprises (nom ou SIREN) et telecharger automatiquement :

- l'extrait INPI / RNE depuis Pappers
- le RBE (beneficiaires effectifs) depuis Infogreffe

Le projet fonctionne en mode entreprise unique ou traitement batch, avec un flux autonome de bout en bout.

## Nouveautes

- traitement batch natif via un fichier `entreprises.txt`
- execution autonome des deux scrapers (Pappers + Infogreffe)
- cache securise des identifiants Infogreffe (gestionnaire d'identifiants Windows)
- sauvegarde/reutilisation de la session navigateur Infogreffe pour eviter les reconnexions inutiles
- journal de traitement batch genere automatiquement

## Architecture

- `prompts`: interaction CLI et validation des saisies
- `services`: orchestration des traitements (single + batch)
- `scrapers`: logique d'automatisation Pappers / Infogreffe
- `utils`: fichiers, logs, session, identifiants securises

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
playwright install chromium
```

## Configuration des identifiants Infogreffe

Enregistrement securise (une seule fois) :

```bash
python -m company_docs_downloader.credential_cli configure
```

ou via script installe :

```bash
company-docs-configure-infogreffe
```

Suppression des identifiants :

```bash
python -m company_docs_downloader.credential_cli clear
```

ou via script installe :

```bash
company-docs-clear-infogreffe
```

Les identifiants ne sont pas stockes dans le code ni dans le depot Git.

## Utilisation

Lancer la CLI :

```bash
python -m company_docs_downloader
```

ou :

```bash
company-docs-downloader
```

Au demarrage, choisissez :

- `Entreprise unique` pour un traitement ponctuel
- `Traitement par lot` pour traiter une liste d'entreprises

## Format du fichier batch

Le mode batch lit un fichier texte (par defaut `entreprises.txt`) :

- une entreprise par ligne
- accepte nom d'entreprise ou SIREN (9 chiffres)
- lignes vides ignorees
- lignes commencant par `#` ignorees (commentaires)

Exemple :

```txt
# Noms
SCI LOOTON
SOFRADOM

# SIREN
534194535
424950459
```

## Sorties

- PDFs ranges par entreprise dans le dossier cible (par defaut `downloads/`)
- fichier log de batch horodate dans le dossier de sortie
- affichage de progression et statut de chaque entreprise (`OK` / `ERREUR`)

## Notes

- Le scraper depend de la structure HTML des sites cibles (Pappers, Infogreffe).
- Certains documents Infogreffe peuvent rester soumis aux regles de compte, d'acces ou de facturation du site.
