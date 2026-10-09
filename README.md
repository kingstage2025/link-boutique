# LinkBoutik

LinkBoutik permet à un petit commerçant de créer gratuitement une mini-boutique
en ligne et de partager un lien public avec ses clients.

## Fonctionnalités

- inscription et connexion ;
- comptes distincts Client et Commerçant, avec espace client et historique des commandes ;
- panier visiteur, validation de commande, paiement et livraison simulés prêts à intégrer ;
- statuts de commande et blocage/réactivation des boutiques par l'administration ;
- création d'une boutique publique avec un lien unique ;
- ajout et suppression de produits avec prix et stock ;
- page publique mobile-first ;
- commandes avec nom, téléphone et note ;
- recherche publique de boutiques et de produits ;
- upload d'images sécurisé (5 Mo, extensions contrôlées) ;
- gestion des clients, soldes/dettes et factures simples ;
- administration protégée, statistiques, signalements et plans Free/Pro ;
- parrainage, page tarifs, SEO/Open Graph, sitemap et robots.txt ;
- stockage SQLite en local ou PostgreSQL avec `DATABASE_URL` en production.

Le plan Free conserve une limite de 10 produits. Le plan Pro (50 produits) est
préparé dans l'interface, sans paiement réel pour le moment.

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

## Administration

Définir `ADMIN_EMAIL` (par défaut `admin@linkboutik.local`) permet d'ouvrir
`/admin` avec ce compte. Les migrations SQLite sont appliquées au démarrage et
les déploiements PostgreSQL continuent d'utiliser `DATABASE_URL`.
