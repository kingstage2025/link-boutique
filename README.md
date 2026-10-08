# LinkBoutik

LinkBoutik permet à un petit commerçant de créer gratuitement une mini-boutique
en ligne et de partager un lien public avec ses clients.

## MVP actuel

- inscription et connexion ;
- création d'une boutique publique avec un lien unique ;
- ajout et suppression de produits avec prix et stock ;
- page publique mobile-first ;
- commandes avec nom, téléphone et note ;
- partage WhatsApp et URL publique ;
- stockage SQLite en local ou PostgreSQL avec `DATABASE_URL` en production.

Le projet est volontairement limité à ce parcours avant d'ajouter les fonctions
Pro. L'objectif est de le tester avec 10 vrais commerçants avant d'investir
dans les abonnements, les paiements ou les fonctionnalités avancées.

## Lancer localement

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SECRET_KEY="change-me"
flask --app app run --debug
```

## Déploiement Render

Le fichier `render.yaml` crée un service web Flask et une base PostgreSQL.
Les variables `SECRET_KEY` et `DATABASE_URL` sont injectées par Render.

## Limites connues du MVP

Les photos utilisent actuellement une URL externe, il n'y a pas encore de
paiement en ligne, de récupération de mot de passe, de QR code ni de formule
Pro. Ces éléments doivent être ajoutés après validation du parcours de vente.
