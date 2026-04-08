# Company Docs Downloader

CLI Python modulaire pour rechercher une entreprise via son nom ou son numero de SIREN, puis telecharger :

- l'extrait INPI / RNE depuis Pappers
- le RBE / document des beneficiaires effectifs via Infogreffe

## Points clefs

- interface interactive avec `questionary`
- architecture separee entre `prompts`, `services`, `scrapers` et `utils`
- telechargement des PDF sur le poste local dans un dossier dedie
- identifiants Infogreffe saisis au lancement, jamais hardcodes
- passage obligatoire par Infogreffe pour le RBE
- identifiants Infogreffe enregistrables localement dans le gestionnaire d'identifiants Windows

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
playwright install chromium
```

## Memoriser les identifiants Infogreffe

Pour eviter de ressaisir l'identifiant et le mot de passe a chaque lancement, vous pouvez les enregistrer une seule fois dans le gestionnaire d'identifiants Windows :

```bash
python -m company_docs_downloader.credential_cli configure
```

Ensuite, la CLI les reutilisera automatiquement pour le RBE et pourra les proposer pour le repli statuts sans jamais les stocker dans le depot Git.

Ensuite, la CLI les reutilisera automatiquement pour le RBE sans jamais les stocker dans le depot Git.

Pour les supprimer :

```bash
python -m company_docs_downloader.credential_cli clear
```

## Execution

```bash
python -m company_docs_downloader
```

ou :

```bash
company-docs-downloader
```

## Remarques

- Le parcours HTML de Pappers et d'Infogreffe peut evoluer. Les selecteurs ont ete centralises et le code est structure pour etre adaptee rapidement.
- Certains documents sur Infogreffe peuvent requerir un compte, une authentification valide ou un paiement selon le type de document.
- Le telechargement du RBE passe directement par Infogreffe et demande donc des identifiants valides.
- Les identifiants Infogreffe peuvent etre lus depuis le gestionnaire d'identifiants Windows plutot que demandes a chaque execution.
- Si Infogreffe bloque l'automatisation via Cloudflare, la CLI bascule sur une reprise manuelle: vous vous connectez dans la fenetre navigateur ouverte, puis l'automatisation continue.
- Autre solution possible, une seul authentification et on conserve. La solution de session navigateur persistée consiste à ne plus refaire la connexion Infogreffe à chaque exécution, mais à réutiliser une session déjà ouverte et déjà authentifiée. L’idée n’est pas de contourner une protection, mais de conserver un état de connexion valide, exactement comme quand tu fermes puis rouvres un navigateur en gardant tes cookies.

**Principe**
Quand tu te connectes manuellement à un site, le navigateur stocke plusieurs éléments de session :
- cookies d’authentification
- stockage local du site
- parfois des jetons de session temporaires
- parfois un état lié au profil navigateur lui-même

Si ces éléments sont conservés, un script peut rouvrir le navigateur avec ce même état et retrouver une session déjà connectée, sans retaper l’identifiant et le mot de passe. 
Utile pour envoyé un max de requêtes à la suite ( récupérer tous les documents d'une liste d'entreprise )
