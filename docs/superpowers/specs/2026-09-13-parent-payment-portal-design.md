# Portail de paiement parent — design

**Date** : 2026-09-13
**Statut** : validé en brainstorming, prêt pour plan d'implémentation

## Contexte

Aujourd'hui, seul le personnel de l'école (économe/secrétaire/directeur) peut
enregistrer un paiement, depuis l'espace connecté. Les parents n'ont aucun
moyen de payer les frais de scolarité de chez eux : ils doivent se déplacer
au guichet.

Objectif : une page publique, sans compte ni mot de passe, où un parent
retrouve son enfant par matricule et paie ses frais en Mobile Money, avec un
reçu immédiat. Côté école, ces paiements doivent être visibles au même
endroit que les paiements guichet, mais clairement distingués.

## Objectifs

- Zéro friction : pas de compte, pas de mot de passe, pas d'app à installer.
- Le parent confirme qu'il paie pour le bon enfant avant de payer (affichage
  du nom complet après recherche).
- Le parent sait, sans ambiguïté, si son paiement a abouti ou non.
- Le parent peut consulter l'historique de ses paiements passés avec la même
  recherche (école + matricule).
- Le directeur voit les paiements en ligne arriver sans action manuelle, et
  les distingue clairement des encaissements au guichet.
- Le lien vers le portail est visible et invitant depuis la landing page.

## Non-objectifs (hors scope de cette itération)

- Rate-limiting / throttling de la recherche parent — la décision prise est
  de fermer la surface d'attaque en rendant le matricule non devinable
  plutôt qu'en ajoutant de la friction. Un throttling reste une piste de
  durcissement future si le besoin apparaît, mais n'est pas construit ici.
- Migration des matricules déjà attribués (élèves déjà inscrits) — ils
  gardent leur format actuel, potentiellement déjà imprimés sur des
  documents.
- Paiement par carte bancaire, virement, ou tout moyen autre que Mobile
  Money depuis le portail parent (le guichet garde tous les moyens
  existants).
- Notifications SMS/email de confirmation — le reçu à l'écran (+ impression
  PDF via le navigateur) suffit pour cette itération.
- Vrai push temps réel (WebSocket) sur le dashboard directeur — un
  rafraîchissement automatique périodique est jugé suffisant.

## 1. Sécurisation du matricule (prérequis bloquant)

Le format actuel (`domain/student/matricule.py`) encode le nom + la date et
l'heure d'inscription à la seconde près : `NOM3PRENOM3-AAMMJJ-HHMMSS`.
Combiné à une page publique qui affiche le nom complet d'un élève dès qu'un
matricule valide est saisi, ce format est une source de fuite — un
attaquant qui connaît (ou devine) le nom d'un élève et sa période
d'inscription peut retrouver son matricule par force brute (au plus 86 400
combinaisons par jour visé) puis consulter son historique de paiement.

**Nouveau format, pour les inscriptions futures uniquement** :

```
NOM3PRENOM3-XXXXXXX
```

- `NOM3PRENOM3` : inchangé, 3 lettres du nom + 3 lettres du prénom
  (garde le matricule lisible/reconnaissable pour le personnel).
- `XXXXXXX` : 7 caractères aléatoires cryptographiquement sûrs
  (`secrets.choice`), alphabet restreint aux caractères non ambigus à la
  lecture/saisie : `23456789ABCDEFGHJKMNPQRSTUVWXYZ` (exclut `0/O`, `1/I/L`).
  Espace de recherche : 31⁷ ≈ 2,7 × 10¹⁰ combinaisons.

Exemple : `DIAAWA-7K9XQPR`.

Modifications :
- `economat/domain/student/matricule.py` : nouvelle fonction
  `generate_matricule()` (même signature publique) qui produit ce format.
  L'ancienne logique basée sur date/heure est retirée (plus personne n'en a
  besoin — elle n'était qu'un moyen d'obtenir de l'unicité).
- Unicité : boucle de génération avec vérification en base et retry en cas
  de collision (probabilité négligeable, mais coût de vérification nul).
- Élèves déjà inscrits : **non touchés**, aucune migration.
- `economat/static/economat/js/matricule.js` (générateur JS miroir, utilisé
  en mode offline) : mis à jour à l'identique. Si la génération du matricule
  déterministe côté client posait un souci d'unicité en offline (le serveur
  ne peut plus vérifier la collision avant coup), documenté comme point à
  vérifier au moment du plan d'implémentation — impact probablement nul car
  l'inscription d'élève n'est pas un flux offline aujourd'hui (à confirmer
  en lisant `matricule.js`).

## 2. Modèle de données

### `PaymentModel` — nouveaux champs

| Champ | Type | Rôle |
|---|---|---|
| `channel` | `CharField`, choices `GUICHET` / `PORTAIL_PARENT`, défaut `GUICHET` | Distingue un encaissement saisi par le personnel d'un paiement fait par un parent en ligne. |
| `state` | existant, choices étendues : `PENDING` (nouveau) / `VALID` / `CANCELLED` | Un paiement portail naît `PENDING` (CinetPay pas encore confirmé) et ne compte dans aucun solde tant qu'il n'est pas `VALID`. Les paiements guichet restent créés directement en `VALID` comme aujourd'hui (jamais `PENDING`). |
| `gateway_transaction_ref` | `CharField`, blank | Référence de transaction CinetPay, pour retrouver/vérifier un paiement lors du webhook ou d'un contrôle a posteriori. |

Migration Django standard. `PaymentStatusCalculator` (domaine) doit ignorer
les paiements `PENDING` dans le calcul de solde — à vérifier/adapter au
moment du plan (probablement déjà le cas si le calcul filtre sur un état
"compté", sinon un filtre explicite `state == VALID` est ajouté aux requêtes
qui alimentent le calculateur).

### Champs déjà ajoutés cette session (réutilisés tels quels)

`mobile_operator`, `mobile_number` — déjà sur `PaymentModel`, remplis pour
tout paiement Mobile Money, guichet ou portail.

## 3. Nouvelle app `economat/interface/parent_portal/`

Suit la structure des apps existantes (`econome/`, `director/`) : `urls.py`,
`views.py`, `forms.py`. Aucune vue de cette app n'a `@login_required` — accès
public assumé.

Montée dans `economat/urls.py` :

```python
path("payer/", include("economat.interface.parent_portal.urls")),
```

### Routes

| Route | Méthode | Rôle |
|---|---|---|
| `/payer/` | GET | Formulaire école (select) + matricule (texte, saisie exacte, **aucune autocomplétion**). |
| `/payer/rechercher/` | POST | Lookup **exact** école+matricule. Retourne (JSON, appelé en AJAX) : nom complet, niveau, classe, solde actuel — ou une erreur générique ("École ou matricule introuvable") sans jamais préciser lequel des deux est en cause. |
| `/payer/montant/` | GET | Écran montant + choix opérateur (cartes réutilisées de l'écran économe), une fois l'élève confirmé. L'identité de l'élève transite en query param signé ou en session — à trancher au plan (probablement session Django classique, pas de compte requis pour en avoir une). |
| `/payer/initier/` | POST | Valide montant + opérateur + numéro de téléphone, crée le `PaymentModel` en `PENDING` avec `channel=PORTAIL_PARENT`, appelle `CinetPayGateway.initiate_payment(...)`, redirige vers l'écran d'attente. |
| `/payer/statut/<payment_id>/` | GET | Interrogé en JS toutes les 3 secondes par l'écran d'attente. Retourne `{"state": "PENDING"|"VALID"|"FAILED"}`. |
| `/payer/webhook/cinetpay/` | POST | Callback serveur-à-serveur CinetPay. `@csrf_exempt` (nécessaire, source externe) mais **signature vérifiée** avant tout traitement (voir §4). Fait passer le paiement de `PENDING` à `VALID` ou `FAILED`. |
| `/payer/recu/<payment_id>/` | GET | Reçu, uniquement si `state == VALID`. Même gabarit visuel que `econome/receipt.html` (bouton "Imprimer / PDF" via `window.print()`, cohérence totale). |
| `/payer/historique/` | GET/POST | Même formulaire école+matricule que `/payer/`, liste les paiements `VALID` de l'élève (guichet + portail confondus — le parent doit voir tout ce qui a été payé, peu importe le canal). |

### Sécurité de la recherche

- Match **exact** uniquement (`Student.objects.get(matricule=matricule,
  enrollment__school_year__school_id=school_id)`), jamais de `icontains` ou
  de suggestion.
- Message d'erreur générique, identique que l'école existe ou non, que le
  matricule existe ou non dans cette école — pas d'oracle qui confirme
  partiellement une saisie.
- Comme discuté : pas de rate-limiting ajouté dans cette itération (voir
  Non-objectifs).

## 4. Intégration CinetPay (mode seamless)

Le parent choisit son opérateur sur notre page (cartes déjà construites
pour l'écran économe, réutilisées ici) et reste sur notre page pendant tout
le paiement — pas de redirection vers un site tiers.

### Abstraction

```
economat/application/ports/payment_gateway.py
    class PaymentGateway(ABC):
        def initiate_payment(self, phone, operator, amount_fcfa, description, notify_url) -> GatewayInitiationResult
        def verify_webhook_signature(self, raw_body: bytes, headers: dict) -> bool
        def parse_webhook_status(self, raw_body: bytes) -> GatewayWebhookEvent  # transaction_ref, status, ...
```

Implémentation concrète : `economat/infrastructure/payment/cinetpay_gateway.py`.
**Le détail exact des endpoints/paramètres CinetPay (mode seamless mobile
money direct) sera confirmé contre leur documentation officielle au moment
de l'implémentation** — je ne fige pas ici de contrat d'API que je ne peux
pas vérifier avec certitude. L'abstraction ci-dessus isole ce risque à un
seul fichier ; le reste de l'app ne connaît que `PaymentGateway`.

Pour le développement sans compte marchand actif : un
`FakePaymentGateway` (même interface) qui simule une confirmation après
quelques secondes — permet de construire et tester tout le reste du
parcours (recherche, écran montant, attente, reçu, historique, distinction
guichet/portail, dashboard) sans dépendre des clés API CinetPay. Bascule
entre les deux via une variable d'environnement (`PAYMENT_GATEWAY=fake` en
dev, `cinetpay` en prod), suivant le pattern déjà en place pour
`DATABASE_URL` etc. dans `config/settings.py`.

### Webhook

- CinetPay signe ses callbacks (HMAC ou token, à confirmer précisément dans
  leur doc) — `verify_webhook_signature()` doit rejeter (403) tout webhook
  non vérifié avant de toucher à quoi que ce soit en base. Point non
  négociable : ne jamais faire confiance à un webhook non authentifié pour
  valider un paiement.
- Idempotent : un webhook reçu deux fois pour le même
  `gateway_transaction_ref` ne doit pas déclencher deux fois la mise à jour
  (vérifier l'état actuel avant transition).

### Écran d'attente (parent)

Après `/payer/initier/`, le parent voit un écran "Vérifiez votre téléphone
et confirmez le paiement avec votre code {opérateur}" avec un indicateur de
chargement. JS poll `/payer/statut/<id>/` toutes les 3s :
- `VALID` → redirection automatique vers `/payer/recu/<id>/`.
- `FAILED` → message clair ("Paiement refusé ou annulé"), bouton pour
  réessayer.
- Toujours `PENDING` après ~2 minutes → message "Ça prend plus de temps que
  prévu, vérifiez votre téléphone ou contactez l'école", sans faire échouer
  le paiement côté serveur (le webhook peut encore arriver après ce délai
  d'affichage — l'utilisateur n'est pas bloqué mais informé).

## 5. Distinction guichet / portail

- Badge visuel (déjà un pattern établi pour les badges de méthode de
  paiement) partout où une liste de paiements est affichée : liste
  économe (`payments_list.html`), historique parent, dashboard directeur.
  Couleur dédiée (violet, cohérente avec l'identité "Chat IA"/portail déjà
  utilisée ailleurs dans l'app) pour `PORTAIL_PARENT`, distincte des 4
  badges de méthode existants.
- `recorded_by` pour un paiement portail : chaîne fixe `"Portail parent"`
  (pas de compte utilisateur associé).

## 6. Dashboard directeur

Rafraîchissement automatique du bandeau KPI + de la liste des derniers
encaissements toutes les 15-30 secondes (polling JS vers un endpoint déjà
existant ou une variante légère de la vue dashboard). Une notification
toast discrète signale les nouveaux paiements apparus depuis le dernier
rafraîchissement ("+1 encaissement"), sans reload de page.

## 7. Landing page

Nouveau bouton dans le hero, à côté de "Accéder à la plateforme" :
*"Payer les frais de mon enfant"* → `/payer/`. Pas de comptes ni de gate.
Cohérent avec la charte déjà en place (couleur, style de bouton).

## Tests

- Génération de matricule : format, unicité (pas de collision sur N
  générations), absence totale de date/heure dans le résultat.
- Recherche parent : match exact only, message d'erreur identique pour
  "école inconnue" et "matricule inconnu" (pas de fuite d'information par
  différence de réponse).
- `PaymentStatusCalculator` : un paiement `PENDING` n'est jamais compté
  dans le solde.
- Webhook : rejeté si signature absente/invalide ; idempotent si reçu deux
  fois ; transition correcte `PENDING → VALID` / `PENDING → FAILED`.
- `FakePaymentGateway` : permet un test de bout en bout du parcours parent
  sans dépendance externe.

## Risques / points ouverts pour le plan d'implémentation

1. Compte marchand CinetPay pas encore ouvert — le portail est construit et
   testable avec `FakePaymentGateway` ; le branchement réel attend les
   clés API et la confirmation du contrat exact du mode seamless.
2. `matricule.js` (miroir JS du générateur) à vérifier : impact du nouveau
   format sur un éventuel usage offline de la génération de matricule.
3. Format téléphone : pas de validation stricte par pays dans cette
   itération (même tolérance que le champ `mobile_number` déjà ajouté côté
   économe — 8 chiffres minimum après nettoyage).
