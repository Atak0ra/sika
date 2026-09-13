# Portail de paiement parent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Une page publique sans compte ni mot de passe où un parent retrouve
son enfant par école + matricule et paie ses frais de scolarité en Mobile
Money (via CinetPay), avec reçu immédiat et historique consultable — et où
ces paiements apparaissent côté école clairement distingués des
encaissements au guichet.

**Architecture:** Nouvelle app Django `economat/interface/parent_portal/`
sans authentification, qui réutilise au maximum l'existant : le
`RecordPaymentUseCase` (étendu de 3 champs additifs rétrocompatibles) pour
la persistance du paiement, les cartes opérateur Mobile Money déjà
construites pour l'écran économe, et le gabarit de reçu existant. Le
paiement réel passe par un port `PaymentGateway` (Orange/Wave/MTN via
CinetPay derrière une seule intégration), avec une implémentation `Fake`
pour le développement/tests et `CinetPay` pour la prod — swap par variable
d'environnement.

**Tech Stack:** Django (vues fonction, forms, templates — suit les
conventions déjà en place dans `economat/interface/`), pytest +
pytest-django, JS vanilla (polling `fetch`), CinetPay API v2.

**Spec:** `docs/superpowers/specs/2026-09-13-parent-payment-portal-design.md`

## Global Constraints

- Aucune vue de `parent_portal` n'a `@login_required` — accès public assumé.
- La recherche élève (école + matricule) est un **match exact uniquement**,
  jamais de recherche floue/partielle ni d'autocomplétion — un message
  d'erreur générique identique que l'école ou le matricule soit invalide.
- Le nouveau format de matricule (`NOM3PRENOM3-XXXXXXX`, suffixe aléatoire
  cryptographique) s'applique **uniquement aux nouvelles inscriptions** —
  aucune migration des matricules existants.
- Tout paiement portail naît `PENDING` et ne doit jamais compter dans un
  solde tant qu'il n'est pas passé à `VALID` par le webhook CinetPay (jamais
  par une action côté parent).
- Un paiement portail est étiqueté `channel=PORTAIL_PARENT`,
  `recorded_by="Portail parent"` — jamais rattaché à un compte utilisateur.
- Aucun webhook n'est traité sans vérification de signature préalable.
- Devise : FCFA (`Currency.XOF`) partout, comme le reste de l'app.

---

## File Structure

**Nouveaux fichiers :**
- `economat/application/ports/payment_gateway.py` — port `PaymentGateway` (ABC) + dataclasses de résultat.
- `economat/infrastructure/payment/__init__.py`
- `economat/infrastructure/payment/fake_gateway.py` — `FakePaymentGateway`.
- `economat/infrastructure/payment/cinetpay_gateway.py` — `CinetPayGateway`.
- `economat/application/use_cases/initiate_online_payment.py` — `InitiateOnlinePaymentUseCase`.
- `economat/application/use_cases/confirm_online_payment.py` — `ConfirmOnlinePaymentUseCase`.
- `economat/interface/parent_portal/__init__.py`
- `economat/interface/parent_portal/urls.py`
- `economat/interface/parent_portal/forms.py` — `SchoolMatriculeForm`, `OnlinePaymentForm`.
- `economat/interface/parent_portal/views.py`
- `economat/templates/economat/parent_portal/search.html`
- `economat/templates/economat/parent_portal/pay.html`
- `economat/templates/economat/parent_portal/waiting.html`
- `economat/templates/economat/parent_portal/receipt.html`
- `economat/templates/economat/parent_portal/history.html`
- `economat/tests/test_matricule.py`
- `economat/tests/test_payment_confirm.py`
- `economat/tests/test_fake_gateway.py`
- `economat/tests/test_initiate_online_payment.py`
- `economat/tests/test_confirm_online_payment.py`

**Fichiers modifiés :**
- `economat/domain/student/matricule.py` — nouveau `generate_matricule()`.
- `economat/static/economat/js/matricule.js` — retire le code mort `generateMatricule`/`_slug`.
- `economat/domain/payment/entities.py` — `PaymentState.PENDING`, `Payment.confirm()`.
- `economat/infrastructure/models.py` — `PaymentModel` : choix `PENDING`, champs `channel`, `gateway_transaction_ref`.
- `economat/application/dto.py` — `RecordPaymentCommand` : `initial_state`, `channel`, `gateway_transaction_ref`.
- `economat/application/use_cases/record_payment.py` — utilise `cmd.initial_state`, propage les 2 nouveaux champs extra.
- `economat/composition.py` — `get_payment_gateway()`, `get_initiate_online_payment_use_case()`, `get_confirm_online_payment_use_case()`.
- `config/settings.py` — variables d'environnement CinetPay + `PAYMENT_GATEWAY`.
- `.env.example` — documente les nouvelles variables.
- `economat/urls.py` — monte `parent_portal.urls` sur `/payer/`.
- `economat/templates/economat/econome/payments_list.html` — badge canal.
- `economat/templates/economat/director/dashboard.html` — badge canal + polling.
- `economat/templates/economat/landing.html` — CTA "Payer les frais de mon enfant".

---

### Task 1: Matricule sécurisé (domaine)

**Files:**
- Modify: `economat/domain/student/matricule.py`
- Test: `economat/tests/test_matricule.py`

**Interfaces:**
- Produces: `generate_matricule(last_name: str, first_name: str, enrolled_at: datetime.datetime | None = None) -> str` — signature inchangée (le paramètre `enrolled_at` n'est plus utilisé dans le nouveau format mais reste accepté pour ne casser aucun appelant existant).

- [ ] **Step 1: Write the failing tests**

```python
# economat/tests/test_matricule.py
"""
tests/test_matricule.py
==========================
Tests du générateur de matricule sécurisé (suffixe aléatoire, pas de
date/heure devinable).
"""
import re

from economat.domain.student.matricule import generate_matricule

MATRICULE_RE = re.compile(r"^[A-Z]{6}-[A-Z0-9]{7}$")
SAFE_ALPHABET = set("23456789ABCDEFGHJKMNPQRSTUVWXYZ")


def test_format_matches_prefix_and_random_suffix():
    mat = generate_matricule("Diallo", "Awa")
    assert MATRICULE_RE.match(mat), f"format inattendu : {mat}"
    assert mat.startswith("DIAAWA-")


def test_suffix_uses_unambiguous_alphabet_only():
    mat = generate_matricule("Kone", "Ba")
    suffix = mat.split("-")[1]
    assert set(suffix) <= SAFE_ALPHABET, f"caractère ambigu dans {suffix}"


def test_suffix_excludes_confusable_characters():
    # 0/O, 1/I/L ne doivent jamais apparaître dans le suffixe
    for _ in range(50):
        mat = generate_matricule("Traore", "Fatou")
        suffix = mat.split("-")[1]
        assert not any(c in suffix for c in "01IOL")


def test_two_generations_for_same_student_differ():
    # Avant : deux inscriptions à la même seconde produisaient le même
    # matricule (collision). Maintenant : le suffixe aléatoire les distingue
    # même sans écart de temps.
    mat1 = generate_matricule("Ben Ali", "Aicha")
    mat2 = generate_matricule("Ben Ali", "Aicha")
    assert mat1 != mat2


def test_enrolled_at_parameter_still_accepted_but_ignored():
    import datetime
    # Ne doit pas lever — compat avec les appelants existants qui passent
    # encore une date (register_student.py).
    mat = generate_matricule("Sall", "Fatou", datetime.datetime(2026, 9, 11, 14, 30, 52))
    assert MATRICULE_RE.match(mat)


def test_no_date_or_time_pattern_leaks_in_output():
    # Le suffixe ne doit jamais ressembler à AAMMJJ ou HHMMSS (régression :
    # l'ancien format encodait la date/heure d'inscription, devinable).
    mat = generate_matricule("Diop", "Moussa")
    suffix = mat.split("-")[1]
    assert not suffix.isdigit()  # un suffixe 100% numérique ressemblerait à une date
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest economat/tests/test_matricule.py -v`
Expected: FAIL (l'ancien générateur produit `NOM3PRENOM3-AAMMJJ-HHMMSS`, ne matche pas `MATRICULE_RE` à un seul groupe de suffixe et échoue `test_two_generations_for_same_student_differ` car déterministe).

- [ ] **Step 3: Implement the new generator**

Remplacer entièrement le contenu de `economat/domain/student/matricule.py` par :

```python
"""
domain/student/matricule.py
==============================
Générateur de matricule élève.

Format : NOM3PRENOM3-XXXXXXX
  - NOM3PRENOM3 : 3 premières lettres du nom + 3 du prénom, normalisées
                  (lisible/reconnaissable par le personnel).
  - XXXXXXX     : 7 caractères aléatoires cryptographiquement sûrs, alphabet
                  restreint aux caractères non ambigus à la lecture/saisie
                  (exclut 0/O et 1/I/L). Espace de recherche : 31⁷ ≈ 2,7×10¹⁰.

Le matricule est utilisé comme identifiant public dans le portail de
paiement parent (aucune authentification) : il ne doit jamais permettre de
retrouver un élève par déduction (nom + période d'inscription). C'est pour
cette raison que l'ancien format (qui encodait la date et l'heure
d'inscription à la seconde près) a été abandonné — il était devinable par
force brute pour qui connaissait déjà le nom de l'élève.

Normalisation du préfixe :
  - Suppression des accents (Unicode NFKD → ASCII)
  - Majuscules
  - Suppression de tout ce qui n'est pas A-Z (espaces, tirets, apostrophes…)
  - Si slug < N lettres → complété par 'X'

Exemples :
  Awa DIALLO    →  DIAAWA-7K9XQPR
  Aïcha BEN ALI →  BENAIC-M4T8HRW

Unicité : protégée par la contrainte `unique=True` sur `StudentModel.matricule`
(economat/infrastructure/models.py). Une collision est astronomiquement
improbable (2,7×10¹⁰ combinaisons pour le suffixe) ; si elle survenait,
l'inscription échoue avec une erreur d'intégrité DB et il suffit de
soumettre à nouveau le formulaire pour obtenir un nouveau suffixe.
"""
from __future__ import annotations

import datetime
import secrets
import unicodedata

# Alphabet sans caractères ambigus à la lecture/saisie : ni 0/O, ni 1/I/L.
_SAFE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_SUFFIX_LENGTH = 7


def _normalize_slug(text: str, length: int = 3) -> str:
    """
    Normalise un texte en slug alphabétique de longueur fixe.

    1. Décompose les caractères Unicode (NFD) pour séparer les accents
    2. Encode en ASCII strict (ignore ce qui ne passe pas)
    3. Ne garde que les lettres A-Z
    4. Met en majuscules
    5. Tronque ou complète à `length` caractères avec 'X'
    """
    normalized = unicodedata.normalize("NFD", text)
    ascii_bytes = normalized.encode("ascii", errors="ignore")
    letters = "".join(c for c in ascii_bytes.decode("ascii") if c.isalpha()).upper()
    if not letters:
        letters = "X" * length
    return (letters + "X" * length)[:length]


def _random_suffix(length: int = _SUFFIX_LENGTH) -> str:
    """Suffixe aléatoire cryptographiquement sûr, alphabet non ambigu."""
    return "".join(secrets.choice(_SAFE_ALPHABET) for _ in range(length))


def generate_matricule(
    last_name: str,
    first_name: str,
    enrolled_at: datetime.datetime | None = None,
) -> str:
    """
    Génère le matricule d'un élève.

    Args:
        last_name   : nom de famille (ex. "Diallo", "Ben Ali", "N'Diaye")
        first_name  : prénom (ex. "Awa", "Aïcha")
        enrolled_at : conservé pour compatibilité de signature avec les
                      appelants existants — n'influence plus le résultat
                      (le nouveau format ne code aucune date/heure).

    Returns:
        Matricule au format NOM3PRENOM3-XXXXXXX
        Ex. : "DIAAWA-7K9XQPR"
    """
    nom_slug    = _normalize_slug(last_name.replace("-", "").replace("'", ""), 3)
    prenom_slug = _normalize_slug(first_name.replace("-", "").replace("'", ""), 3)
    return f"{nom_slug}{prenom_slug}-{_random_suffix()}"


def generate_receipt_number(
    matricule: str,
    class_name: str,
    installment_label: str,
    paid_at: datetime.datetime | None = None,
) -> str:
    """
    Génère le numéro de reçu à partir du matricule élève.

    Format : MATRICULE/R-AAMMJJ-HHMMSS/TRANCHE/CLASSE
    Ex. : "DIAAWA-7K9XQPR/R-260915-093012/T1/CM2A"

    Inchangé : le matricule est traité comme une chaîne opaque ici, son
    format interne n'a aucune incidence sur cette fonction.

    Args:
        matricule         : matricule de l'élève (généré par generate_matricule)
        class_name        : nom de la classe (ex. "CM2 A" → "CM2A")
        installment_label : libellé de la tranche (ex. "T1", "T2", "M3")
        paid_at            : datetime du paiement. Si None → now().

    Returns:
        Numéro de reçu unique et lisible.
    """
    if paid_at is None:
        paid_at = datetime.datetime.now()

    class_slug = class_name.replace(" ", "").upper()
    date_part  = paid_at.strftime("%y%m%d")
    time_part  = paid_at.strftime("%H%M%S")

    return f"{matricule}/R-{date_part}-{time_part}/{installment_label}/{class_slug}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest economat/tests/test_matricule.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Run the full existing test suite to confirm no regression**

Run: `.venv/bin/python -m pytest economat/tests/ -q`
Expected: PASS — `generate_receipt_number` inchangée, `register_student.py` appelle `generate_matricule` avec la même signature.

- [ ] **Step 6: Commit**

```bash
git add economat/domain/student/matricule.py economat/tests/test_matricule.py
git commit -m "fix(security): matricule élève avec suffixe aléatoire (non devinable)

Le format encodait la date/heure d'inscription à la seconde près,
devinable par force brute pour qui connaît le nom de l'élève. Prérequis
au portail de paiement parent (recherche publique par matricule).
Nouvelles inscriptions uniquement, élèves existants non touchés.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012NtEzKCRrnrbk4FfzFuwr9"
```

---

### Task 2: Nettoyage du mirroir JS (code mort)

**Files:**
- Modify: `economat/static/economat/js/matricule.js`

**Interfaces:**
- Consumes: rien de nouveau.
- Produces: `window.SukuluMatricule.generateReceiptNumber(matricule, className, installmentLabel, paidAt)` — inchangé, seule fonction réellement utilisée (par `offline-sync.js`).

`generateMatricule` (génération du matricule élève côté JS) n'est appelée
nulle part dans le code — l'inscription d'élève n'est pas un flux offline,
le matricule est toujours généré côté serveur. La garder maintenant
qu'elle ne correspond plus au format serveur serait trompeur (le
commentaire du fichier dit explicitement "DOIT rester en sync").

- [ ] **Step 1: Vérifier qu'aucun appelant n'existe avant de supprimer**

Run: `grep -rn "generateMatricule" economat/templates economat/static --include="*.html" --include="*.js"`
Expected: seule occurrence = la définition dans `matricule.js` elle-même (aucun appelant).

- [ ] **Step 2: Retirer `generateMatricule` et le code devenu inutile**

Remplacer le contenu de `economat/static/economat/js/matricule.js` par :

```javascript
/**
 * economat/static/economat/js/matricule.js
 * ==========================================
 * Génère le numéro de reçu côté client (mode offline).
 *
 * Le matricule élève, lui, est TOUJOURS généré côté serveur
 * (economat/domain/student/matricule.py) — l'inscription d'élève n'est pas
 * un flux offline. Ce fichier ne fait que formater un numéro de reçu à
 * partir d'un matricule déjà connu (fourni par le serveur au chargement de
 * la page d'encaissement), pour permettre la génération d'un reçu
 * déterministe hors-ligne avant synchronisation.
 *
 * Utilisation :
 *   const rec = generateReceiptNumber('DIAAWA-7K9XQPR', 'CM2 A', 'T1', new Date());
 *   // → "DIAAWA-7K9XQPR/R-260915-093012/T1/CM2A"
 */

/** Formate un nombre sur N chiffres (zéro-padding). */
function _pad(n, digits) {
  return String(n).padStart(digits, '0');
}

/**
 * Génère le numéro de reçu déterministe à partir du matricule.
 *
 * @param {string} matricule        - Matricule élève (chaîne opaque, fournie par le serveur)
 * @param {string} className        - Nom de la classe (ex. "CM2 A" → "CM2A")
 * @param {string} installmentLabel - Tranche visée (ex. "T1", "T2", "M3")
 * @param {Date}   [paidAt]         - Date+heure du paiement (défaut : maintenant)
 * @returns {string}  Ex. "DIAAWA-7K9XQPR/R-260915-093012/T1/CM2A"
 */
function generateReceiptNumber(matricule, className, installmentLabel, paidAt) {
  const dt = paidAt instanceof Date ? paidAt : new Date();
  const classSlug = className.replace(/\s+/g, '').toUpperCase();
  const yy  = _pad(dt.getFullYear() % 100, 2);
  const mm  = _pad(dt.getMonth() + 1, 2);
  const dd  = _pad(dt.getDate(), 2);
  const hh  = _pad(dt.getHours(), 2);
  const min = _pad(dt.getMinutes(), 2);
  const ss  = _pad(dt.getSeconds(), 2);
  return `${matricule}/R-${yy}${mm}${dd}-${hh}${min}${ss}/${installmentLabel}/${classSlug}`;
}

/* ── Exports (ES module + compat script tag) ───────────────────────────────── */
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { generateReceiptNumber };
} else {
  window.SukuluMatricule = { generateReceiptNumber };
}
```

- [ ] **Step 3: Vérifier manuellement que l'écran d'encaissement offline fonctionne toujours**

Run: `grep -n "SukuluMatricule" economat/static/economat/js/offline-sync.js`
Expected: seul `generateReceiptNumber` est appelé — confirmé compatible.

- [ ] **Step 4: Commit**

```bash
git add economat/static/economat/js/matricule.js
git commit -m "chore: retire generateMatricule (JS) devenu obsolète et inutilisé

Le matricule élève est toujours généré côté serveur ; ce code mort
prétendait rester en sync avec le format Python (comme mentionné dans son
propre commentaire) et ne l'était plus depuis le changement de format.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012NtEzKCRrnrbk4FfzFuwr9"
```

---

### Task 3: État `PENDING` sur `Payment` (domaine)

**Files:**
- Modify: `economat/domain/payment/entities.py`
- Test: `economat/tests/test_payment_confirm.py`

**Interfaces:**
- Produces: `PaymentState.PENDING` (nouvelle valeur d'enum) ; `Payment.confirm() -> None` (transition vers `VALID`).

- [ ] **Step 1: Write the failing tests**

```python
# economat/tests/test_payment_confirm.py
"""
tests/test_payment_confirm.py
================================
Tests de l'état PENDING et de la transition confirm() sur Payment.
"""
import datetime

from economat.domain.payment.entities import Payment, PaymentState
from economat.domain.payment.value_objects import PaymentId, PaymentMethod
from economat.domain.enrollment.value_objects import EnrollmentId
from economat.domain.student.value_objects import StudentId
from economat.domain.shared.value_objects import Money


def _make_pending_payment() -> Payment:
    return Payment(
        id=PaymentId.generate(),
        enrollment_id=EnrollmentId.generate(),
        student_id=StudentId.generate(),
        amount=Money.of_xof(25000),
        payment_date=datetime.date.today(),
        method=PaymentMethod.MOBILE_MONEY,
        receipt_number="REC-TEST-0001",
        recorded_by="Portail parent",
        state=PaymentState.PENDING,
    )


def test_payment_can_be_created_pending():
    payment = _make_pending_payment()
    assert payment.state == PaymentState.PENDING
    assert payment.is_valid() is False


def test_confirm_transitions_pending_to_valid():
    payment = _make_pending_payment()
    payment.confirm()
    assert payment.state == PaymentState.VALID
    assert payment.is_valid() is True


def test_cancel_still_works_from_pending():
    # Un paiement en attente refusé par l'opérateur suit le même chemin
    # domaine qu'une annulation classique.
    payment = _make_pending_payment()
    payment.cancel(reason="Refusé par l'opérateur Mobile Money")
    assert payment.state == PaymentState.CANCELLED
    assert "Refusé par l'opérateur" in payment.notes
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest economat/tests/test_payment_confirm.py -v`
Expected: FAIL avec `AttributeError` ou `ValueError: 'PENDING' is not a valid PaymentState` (l'enum n'a pas encore `PENDING`, `confirm()` n'existe pas).

- [ ] **Step 3: Implement**

Dans `economat/domain/payment/entities.py`, modifier :

```python
class PaymentState(str, Enum):
    VALID     = "VALID"
    PENDING   = "PENDING"    # créé côté portail parent, en attente de confirmation du paiement Mobile Money
    CANCELLED = "CANCELLED"
```

Ajouter la méthode `confirm()` juste après `cancel()` :

```python
    def confirm(self) -> None:
        """Transition PENDING → VALID : le paiement en ligne est confirmé par la passerelle."""
        self.state = PaymentState.VALID
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest economat/tests/test_payment_confirm.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full test suite (régression PaymentStatusCalculator)**

Run: `.venv/bin/python -m pytest economat/tests/ -q`
Expected: PASS — `PaymentStatusCalculator.calculate()` ne compte que les paiements `is_valid()` (déjà vrai avant ce changement), donc un paiement `PENDING` est automatiquement exclu du solde sans aucune modification de `payment_status.py`.

- [ ] **Step 6: Commit**

```bash
git add economat/domain/payment/entities.py economat/tests/test_payment_confirm.py
git commit -m "feat(payment): état PENDING + transition confirm() pour les paiements en ligne

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012NtEzKCRrnrbk4FfzFuwr9"
```

---

### Task 4: Migration `PaymentModel` (PENDING, channel, référence passerelle)

**Files:**
- Modify: `economat/infrastructure/models.py`
- Create: migration générée (`economat/migrations/000X_*.py`)

**Interfaces:**
- Produces: `PaymentModel.channel` (`"GUICHET"` / `"PORTAIL_PARENT"`, défaut `"GUICHET"`), `PaymentModel.gateway_transaction_ref` (`CharField`, blank), choix `state` étendus avec `"PENDING"`.

- [ ] **Step 1: Modifier le modèle**

Dans `economat/infrastructure/models.py`, sur `PaymentModel` :

```python
class PaymentModel(models.Model):
    PAYMENT_METHODS = [
        ("ESPECES","Espèces"),("MOBILE_MONEY","Mobile Money"),
        ("VIREMENT","Virement"),("CHEQUE","Chèque"),
    ]
    PAYMENT_STATES = [("VALID","Valide"),("PENDING","En attente"),("CANCELLED","Annulé")]
    PAYMENT_CHANNELS = [("GUICHET","Guichet"),("PORTAIL_PARENT","Portail parent")]
```

Ajouter les deux nouveaux champs juste après `mobile_number` :

```python
    # Canal d'encaissement : au guichet par le personnel, ou en ligne par le
    # parent via le portail de paiement. Distinction affichée partout où les
    # paiements sont listés.
    channel = models.CharField(max_length=20, choices=PAYMENT_CHANNELS, default="GUICHET")
    # Référence de transaction chez la passerelle de paiement (CinetPay) —
    # rempli uniquement pour channel=PORTAIL_PARENT, sert à faire le lien
    # avec le webhook de confirmation.
    gateway_transaction_ref = models.CharField(max_length=100, blank=True, default="")
```

- [ ] **Step 2: Générer la migration**

Run: `.venv/bin/python manage.py makemigrations economat`
Expected: `Migrations for 'economat': + Add field channel to paymentmodel + Add field gateway_transaction_ref to paymentmodel + Alter field state on paymentmodel`

- [ ] **Step 3: Appliquer et vérifier**

Run: `.venv/bin/python manage.py check`
Expected: `System check identified no issues (0 silenced).`

Run: `.venv/bin/python manage.py makemigrations --check --dry-run`
Expected: `No changes detected`

- [ ] **Step 4: Commit**

```bash
git add economat/infrastructure/models.py economat/migrations/
git commit -m "feat(payment): champs channel + gateway_transaction_ref, état PENDING

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012NtEzKCRrnrbk4FfzFuwr9"
```

---

### Task 5: Extension de `RecordPaymentUseCase` (réutilisable pour le portail)

Plutôt que dupliquer toute la logique de résolution d'inscription, de
barème et de numérotation de reçu dans un nouveau use case, on étend
`RecordPaymentCommand`/`RecordPaymentUseCase` de 3 champs additifs à
défaut rétrocompatible — tous les appelants existants (guichet,
synchronisation offline) continuent de produire exactement les mêmes
paiements `VALID`/`GUICHET` qu'avant.

**Files:**
- Modify: `economat/application/dto.py`
- Modify: `economat/application/use_cases/record_payment.py`
- Test: `economat/tests/test_cancel_payment.py` (aucune modif — sert de garde de non-régression), nouveaux cas dans un test dédié.

**Interfaces:**
- Produces (champs ajoutés à `RecordPaymentCommand`) : `initial_state: str = "VALID"`, `channel: str = ""`, `gateway_transaction_ref: str = ""`.

- [ ] **Step 1: Write the failing test**

Créer `economat/tests/test_record_payment_channel.py` :

```python
"""
tests/test_record_payment_channel.py
=======================================
Vérifie que RecordPaymentUseCase peut produire un paiement PENDING/
PORTAIL_PARENT (utilisé par le portail parent) sans changer le
comportement par défaut (VALID/GUICHET) des appelants existants.
"""
import datetime
import pytest
from unittest import mock

from economat.application.dto import RecordPaymentCommand
from economat.application.use_cases.record_payment import RecordPaymentUseCase
from economat.domain.payment.entities import PaymentState


@pytest.mark.django_db
def test_default_command_produces_valid_guichet_payment(
    record_payment_use_case, active_enrollment,
):
    cmd = RecordPaymentCommand(
        student_id=str(active_enrollment.student_id),
        year_id=str(active_enrollment.school_year_id),
        amount_fcfa=10000,
        payment_date=datetime.date.today(),
        method="ESPECES",
        recorded_by="econome-test",
    )
    result = record_payment_use_case.execute(cmd)
    assert result.success, result.error_message

    from economat.infrastructure.models import PaymentModel
    orm = PaymentModel.objects.get(pk=result.payment_id)
    assert orm.state == "VALID"
    assert orm.channel == "GUICHET"
    assert orm.gateway_transaction_ref == ""


@pytest.mark.django_db
def test_initial_state_and_channel_are_applied(
    record_payment_use_case, active_enrollment,
):
    cmd = RecordPaymentCommand(
        student_id=str(active_enrollment.student_id),
        year_id=str(active_enrollment.school_year_id),
        amount_fcfa=10000,
        payment_date=datetime.date.today(),
        method="MOBILE_MONEY",
        recorded_by="Portail parent",
        initial_state="PENDING",
        channel="PORTAIL_PARENT",
        gateway_transaction_ref="cp-txn-abc123",
        mobile_operator="Orange Money",
        mobile_number="0700000000",
    )
    result = record_payment_use_case.execute(cmd)
    assert result.success, result.error_message

    from economat.infrastructure.models import PaymentModel
    orm = PaymentModel.objects.get(pk=result.payment_id)
    assert orm.state == "PENDING"
    assert orm.channel == "PORTAIL_PARENT"
    assert orm.gateway_transaction_ref == "cp-txn-abc123"
    assert orm.mobile_operator == "Orange Money"
```

Ajouter les fixtures partagées dans `economat/tests/conftest.py` (le créer
s'il n'existe pas déjà — vérifier d'abord) :

```python
# economat/tests/conftest.py
import datetime
import pytest

from economat.composition import get_record_payment_use_case


@pytest.fixture
def record_payment_use_case():
    return get_record_payment_use_case()


@pytest.fixture
def active_enrollment(db):
    """Crée école + année active + niveau + classe + élève inscrit, prêt à recevoir un paiement."""
    from economat.infrastructure.models import (
        SchoolModel, SchoolYearModel, LevelModel, ClassModel,
        StudentModel, EnrollmentModel,
    )
    school = SchoolModel.objects.create(name="École Test", city="Lomé", country="Togo")
    year = SchoolYearModel.objects.create(
        school=school, label="2026-2027", status="ACTIVE",
        start_date=datetime.date(2026, 9, 1), end_date=datetime.date(2027, 6, 30),
    )
    level = LevelModel.objects.create(
        school_year=year, name="CM2", annual_fee=150000, payment_mode="UNIQUE",
    )
    klass = ClassModel.objects.create(level=level, name="CM2 A")
    student = StudentModel.objects.create(
        first_name="Awa", last_name="Diallo", school=school, matricule="DIAAWA-7K9XQPR",
    )
    enrollment = EnrollmentModel.objects.create(
        student=student, school_year=year, level=level, klass=klass,
        enrollment_date=datetime.date(2026, 9, 1),
    )
    return enrollment
```

Ces noms de champs (`annual_fee`, `payment_mode` sur `LevelModel`,
`start_date`/`end_date` sur `SchoolYearModel`) ont été vérifiés contre
`economat/infrastructure/models.py` au moment d'écrire ce plan.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest economat/tests/test_record_payment_channel.py -v`
Expected: FAIL — `RecordPaymentCommand` n'a pas encore `initial_state`/`channel`/`gateway_transaction_ref` (`TypeError: unexpected keyword argument`).

- [ ] **Step 3: Étendre `RecordPaymentCommand`**

Dans `economat/application/dto.py`, sur `RecordPaymentCommand` :

```python
    # Opérateur Mobile Money (Orange Money, Wave, MTN…) — pertinent seulement
    # si method == "MOBILE_MONEY".
    mobile_operator:   str = ""
    # Numéro ayant servi à la transaction — pertinent seulement si method == "MOBILE_MONEY".
    mobile_number:     str = ""
    # ── Portail de paiement parent ────────────────────────────────────────
    # État initial du paiement créé. "VALID" (défaut, comportement guichet
    # inchangé) ou "PENDING" (paiement en ligne, en attente de confirmation
    # de la passerelle avant de compter dans un solde).
    initial_state:     str = "VALID"
    # Canal d'encaissement : "" (défaut → GUICHET côté modèle) ou
    # "PORTAIL_PARENT" pour un paiement fait par le parent en ligne.
    channel:           str = ""
    # Référence de transaction chez la passerelle de paiement (CinetPay),
    # pertinent seulement pour un paiement portail.
    gateway_transaction_ref: str = ""
```

- [ ] **Step 4: Utiliser ces champs dans `RecordPaymentUseCase`**

Dans `economat/application/use_cases/record_payment.py`, deux changements :

1. Import `PaymentMethod` est déjà là ; s'assurer que `PaymentState` est importé (déjà le cas via `from economat.domain.payment.entities import Payment, PaymentState`).

2. Remplacer la construction du `Payment` :

```python
        payment = Payment(
            id=self._payments.next_id(),
            enrollment_id=enrollment.id,
            student_id=student_id,
            amount=Money.of_xof(cmd.amount_fcfa),
            payment_date=cmd.payment_date,
            method=PaymentMethod(cmd.method),
            receipt_number=receipt,
            recorded_by=cmd.recorded_by,
            state=PaymentState(cmd.initial_state),
            notes=cmd.notes,
        )
```

3. Ajouter les deux nouveaux champs au dict `extra` (juste après la ligne `mobile_operator`) :

```python
        if cmd.mobile_operator:    extra["mobile_operator"]   = cmd.mobile_operator.strip()
        if cmd.mobile_number:      extra["mobile_number"]     = cmd.mobile_number.strip()
        if cmd.channel:            extra["channel"]           = cmd.channel
        if cmd.gateway_transaction_ref:
            extra["gateway_transaction_ref"] = cmd.gateway_transaction_ref
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest economat/tests/test_record_payment_channel.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Run full suite (non-régression guichet/offline)**

Run: `.venv/bin/python -m pytest economat/tests/ -q`
Expected: PASS — tous les appelants existants de `RecordPaymentCommand` n'utilisent pas ces 3 nouveaux champs, donc conservent `state=VALID`, `channel=GUICHET` (défaut modèle), `gateway_transaction_ref=""`.

- [ ] **Step 7: Commit**

```bash
git add economat/application/dto.py economat/application/use_cases/record_payment.py economat/tests/test_record_payment_channel.py economat/tests/conftest.py
git commit -m "feat(payment): RecordPaymentUseCase réutilisable pour le portail parent

Ajoute initial_state/channel/gateway_transaction_ref à RecordPaymentCommand,
tous à défaut rétrocompatible. Évite de dupliquer la résolution
d'inscription/barème/numérotation de reçu dans un nouveau use case.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012NtEzKCRrnrbk4FfzFuwr9"
```

---

### Task 6: Port `PaymentGateway`

**Files:**
- Create: `economat/application/ports/payment_gateway.py`

**Interfaces:**
- Produces:
  - `GatewayInitiationResult` (dataclass) : `success: bool`, `transaction_ref: str = ""`, `error_message: str = ""`.
  - `GatewayPaymentStatus` (enum str) : `ACCEPTED`, `REFUSED`, `PENDING`.
  - `GatewayWebhookEvent` (dataclass) : `transaction_ref: str`, `status: GatewayPaymentStatus`.
  - `PaymentGateway` (ABC) : `initiate_payment(...)`, `verify_webhook_signature(...)`, `parse_webhook_status(...)`.

- [ ] **Step 1: Write the file**

```python
"""
application/ports/payment_gateway.py
=======================================
Port (interface) pour la passerelle de paiement Mobile Money du portail
parent. Une seule implémentation concrète tourne à la fois, choisie par
economat.composition.get_payment_gateway() :

  - FakePaymentGateway   (economat/infrastructure/payment/fake_gateway.py)
    → développement/tests, confirme automatiquement après un court délai.
  - CinetPayGateway      (economat/infrastructure/payment/cinetpay_gateway.py)
    → production, appelle réellement l'API CinetPay.

Cette abstraction isole tout le reste de l'application (use cases, vues)
du détail exact de l'API du fournisseur — un changement de fournisseur ne
touche qu'un seul fichier d'implémentation.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class GatewayPaymentStatus(str, Enum):
    """Statut d'un paiement côté passerelle."""
    PENDING  = "PENDING"   # en attente de confirmation par le parent
    ACCEPTED = "ACCEPTED"  # confirmé, l'argent a été débité
    REFUSED  = "REFUSED"   # refusé, annulé, ou expiré côté opérateur


@dataclass(frozen=True)
class GatewayInitiationResult:
    """Résultat de l'initiation d'un paiement auprès de la passerelle."""
    success: bool
    transaction_ref: str = ""
    error_message: str = ""


@dataclass(frozen=True)
class GatewayWebhookEvent:
    """Événement décodé depuis un callback webhook de la passerelle."""
    transaction_ref: str
    status: GatewayPaymentStatus


class PaymentGateway(ABC):
    """Port : déclenche un paiement Mobile Money et interprète sa confirmation."""

    @abstractmethod
    def initiate_payment(
        self,
        phone: str,
        operator: str,
        amount_fcfa: int,
        description: str,
        notify_url: str,
    ) -> GatewayInitiationResult:
        """
        Déclenche le paiement : la passerelle pousse une demande de
        confirmation sur le téléphone du parent (USSD/appli opérateur).
        Ne bloque pas jusqu'à la confirmation — celle-ci arrive de façon
        asynchrone via un appel à `notify_url` (voir parse_webhook_status).
        """
        ...

    @abstractmethod
    def verify_webhook_signature(self, raw_body: bytes, headers: dict) -> bool:
        """
        Vérifie l'authenticité d'un callback webhook avant tout traitement.
        Doit retourner False pour tout webhook non authentifié — ne JAMAIS
        faire confiance à un webhook non vérifié pour valider un paiement.
        """
        ...

    @abstractmethod
    def parse_webhook_status(self, raw_body: bytes) -> GatewayWebhookEvent:
        """
        Décode le corps d'un webhook déjà vérifié en un événement exploitable.
        Ne doit être appelé qu'après verify_webhook_signature() == True.
        """
        ...
```

- [ ] **Step 2: Vérifier que le module s'importe sans erreur**

Run: `.venv/bin/python -c "from economat.application.ports.payment_gateway import PaymentGateway, GatewayInitiationResult, GatewayWebhookEvent, GatewayPaymentStatus; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add economat/application/ports/payment_gateway.py
git commit -m "feat(payment): port PaymentGateway pour l'intégration Mobile Money

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012NtEzKCRrnrbk4FfzFuwr9"
```

---

### Task 7: `FakePaymentGateway` (développement/tests)

**Files:**
- Create: `economat/infrastructure/payment/__init__.py` (vide)
- Create: `economat/infrastructure/payment/fake_gateway.py`
- Test: `economat/tests/test_fake_gateway.py`

**Interfaces:**
- Consumes: `PaymentGateway`, `GatewayInitiationResult`, `GatewayWebhookEvent`, `GatewayPaymentStatus` (Task 6).
- Produces: `FakePaymentGateway` — implémentation complète du port, confirme automatiquement toute transaction initiée (utile pour construire et tester tout le parcours parent sans dépendre de CinetPay).

- [ ] **Step 1: Write the failing tests**

```python
# economat/tests/test_fake_gateway.py
"""
tests/test_fake_gateway.py
=============================
FakePaymentGateway : permet de développer/tester tout le portail parent
sans dépendre de CinetPay.
"""
import json

from economat.infrastructure.payment.fake_gateway import FakePaymentGateway
from economat.application.ports.payment_gateway import GatewayPaymentStatus


def test_initiate_payment_always_succeeds_with_a_transaction_ref():
    gateway = FakePaymentGateway()
    result = gateway.initiate_payment(
        phone="0700000000", operator="Orange Money", amount_fcfa=25000,
        description="Frais scolarité", notify_url="http://testserver/payer/webhook/cinetpay/",
    )
    assert result.success
    assert result.transaction_ref.startswith("FAKE-")


def test_webhook_signature_always_valid_for_the_fake_secret():
    gateway = FakePaymentGateway()
    body = json.dumps({"transaction_ref": "FAKE-abc", "status": "ACCEPTED"}).encode()
    headers = {"X-Fake-Signature": gateway.SHARED_SECRET}
    assert gateway.verify_webhook_signature(body, headers) is True


def test_webhook_signature_rejected_without_correct_header():
    gateway = FakePaymentGateway()
    body = json.dumps({"transaction_ref": "FAKE-abc", "status": "ACCEPTED"}).encode()
    assert gateway.verify_webhook_signature(body, headers={}) is False
    assert gateway.verify_webhook_signature(body, headers={"X-Fake-Signature": "wrong"}) is False


def test_parse_webhook_status_accepted():
    gateway = FakePaymentGateway()
    body = json.dumps({"transaction_ref": "FAKE-abc", "status": "ACCEPTED"}).encode()
    event = gateway.parse_webhook_status(body)
    assert event.transaction_ref == "FAKE-abc"
    assert event.status == GatewayPaymentStatus.ACCEPTED


def test_parse_webhook_status_refused():
    gateway = FakePaymentGateway()
    body = json.dumps({"transaction_ref": "FAKE-xyz", "status": "REFUSED"}).encode()
    event = gateway.parse_webhook_status(body)
    assert event.status == GatewayPaymentStatus.REFUSED


def test_simulate_confirmation_helper_builds_a_matching_webhook_body():
    # Utilitaire de test/démo : simule ce que CinetPay enverrait pour
    # confirmer une transaction — utilisé par les tests d'intégration du
    # parcours complet (Task 9/12) sans dépendre d'un vrai webhook HTTP.
    gateway = FakePaymentGateway()
    result = gateway.initiate_payment("0700000000", "Wave", 5000, "desc", "http://x/")
    body, headers = gateway.simulate_confirmation(result.transaction_ref, accepted=True)
    event = gateway.parse_webhook_status(body)
    assert event.transaction_ref == result.transaction_ref
    assert event.status == GatewayPaymentStatus.ACCEPTED
    assert gateway.verify_webhook_signature(body, headers) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest economat/tests/test_fake_gateway.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'economat.infrastructure.payment'`.

- [ ] **Step 3: Implement**

Créer `economat/infrastructure/payment/__init__.py` (fichier vide).

Créer `economat/infrastructure/payment/fake_gateway.py` :

```python
"""
infrastructure/payment/fake_gateway.py
=========================================
Implémentation factice de PaymentGateway — pour le développement et les
tests, sans dépendre d'un compte marchand CinetPay actif.

Toute transaction initiée réussit immédiatement (transaction_ref généré).
La confirmation (webhook) doit être simulée explicitement via
`simulate_confirmation()` — rien ne se confirme tout seul, pour permettre
de tester aussi bien le chemin "accepté" que "refusé" dans les tests
d'intégration du parcours parent.

Activé via la variable d'environnement PAYMENT_GATEWAY=fake (voir
config/settings.py et economat.composition.get_payment_gateway()).
"""
from __future__ import annotations

import json
import uuid

from economat.application.ports.payment_gateway import (
    GatewayInitiationResult,
    GatewayPaymentStatus,
    GatewayWebhookEvent,
    PaymentGateway,
)


class FakePaymentGateway(PaymentGateway):
    """Passerelle factice — aucun appel réseau, aucune dépendance externe."""

    # Secret partagé arbitraire, pour exercer verify_webhook_signature()
    # avec une vraie vérification (et pas un simple "return True").
    SHARED_SECRET = "fake-shared-secret-dev-only"

    def initiate_payment(
        self, phone: str, operator: str, amount_fcfa: int,
        description: str, notify_url: str,
    ) -> GatewayInitiationResult:
        transaction_ref = f"FAKE-{uuid.uuid4().hex[:12]}"
        return GatewayInitiationResult(success=True, transaction_ref=transaction_ref)

    def verify_webhook_signature(self, raw_body: bytes, headers: dict) -> bool:
        return headers.get("X-Fake-Signature") == self.SHARED_SECRET

    def parse_webhook_status(self, raw_body: bytes) -> GatewayWebhookEvent:
        data = json.loads(raw_body)
        return GatewayWebhookEvent(
            transaction_ref=data["transaction_ref"],
            status=GatewayPaymentStatus(data["status"]),
        )

    def simulate_confirmation(
        self, transaction_ref: str, accepted: bool,
    ) -> tuple[bytes, dict]:
        """
        Construit (body, headers) tel que CinetPay les enverrait pour
        confirmer ou refuser une transaction. Réservé aux tests/démo — ne
        fait pas partie du port PaymentGateway (CinetPayGateway n'a pas
        cette méthode, elle n'a pas de sens en production).
        """
        status = GatewayPaymentStatus.ACCEPTED if accepted else GatewayPaymentStatus.REFUSED
        body = json.dumps({"transaction_ref": transaction_ref, "status": status.value}).encode()
        headers = {"X-Fake-Signature": self.SHARED_SECRET}
        return body, headers
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest economat/tests/test_fake_gateway.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add economat/infrastructure/payment/ economat/tests/test_fake_gateway.py
git commit -m "feat(payment): FakePaymentGateway pour développer sans compte CinetPay

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012NtEzKCRrnrbk4FfzFuwr9"
```

---

### Task 8: Câblage `composition.py` + `settings.py`

**Files:**
- Modify: `economat/composition.py`
- Modify: `config/settings.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `FakePaymentGateway` (Task 7), `PaymentGateway` (Task 6).
- Produces: `economat.composition.get_payment_gateway() -> PaymentGateway` — bascule Fake/CinetPay selon `settings.PAYMENT_GATEWAY`.

- [ ] **Step 1: Ajouter les réglages dans `config/settings.py`**

Ajouter, à la suite des autres `os.environ.get(...)` (même style que `DATABASE_URL`) :

```python
# ── Passerelle de paiement Mobile Money (portail parent) ─────────────────────
# "fake" en développement/tests (aucun compte marchand requis),
# "cinetpay" en production (nécessite les 3 variables CINETPAY_* ci-dessous).
PAYMENT_GATEWAY = os.environ.get("PAYMENT_GATEWAY", "fake").strip().lower()

CINETPAY_API_KEY    = os.environ.get("CINETPAY_API_KEY", "").strip()
CINETPAY_SITE_ID    = os.environ.get("CINETPAY_SITE_ID", "").strip()
CINETPAY_SECRET_KEY = os.environ.get("CINETPAY_SECRET_KEY", "").strip()
```

- [ ] **Step 2: Documenter dans `.env.example`**

Ajouter à la fin du fichier :

```bash
# ── Portail de paiement parent (Mobile Money) ────────────────────────────────
# "fake" par défaut : aucun paiement réel, pour développer/tester sans compte
# marchand. Passer à "cinetpay" en production avec les clés ci-dessous.
PAYMENT_GATEWAY=fake
# CINETPAY_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
# CINETPAY_SITE_ID=000000
# CINETPAY_SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

- [ ] **Step 3: Ajouter `get_payment_gateway()` dans `composition.py`**

Ajouter dans `economat/composition.py`, dans une nouvelle section :

```python
# ─ Portail de paiement parent ──────────────────────────────────────────────────

def get_payment_gateway():
    from django.conf import settings
    if settings.PAYMENT_GATEWAY == "cinetpay":
        from economat.infrastructure.payment.cinetpay_gateway import CinetPayGateway
        return CinetPayGateway(
            api_key=settings.CINETPAY_API_KEY,
            site_id=settings.CINETPAY_SITE_ID,
            secret_key=settings.CINETPAY_SECRET_KEY,
        )
    from economat.infrastructure.payment.fake_gateway import FakePaymentGateway
    return FakePaymentGateway()
```

(`CinetPayGateway` sera créé Task 16 — cet import est en aval, dans la
branche `if`, donc ne casse rien tant que `PAYMENT_GATEWAY` reste `fake`.)

- [ ] **Step 4: Vérifier**

Run: `.venv/bin/python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_test')
django.setup()
from economat.composition import get_payment_gateway
g = get_payment_gateway()
print(type(g).__name__)
"`
Expected: `FakePaymentGateway` (le défaut `PAYMENT_GATEWAY=fake` s'applique).

- [ ] **Step 5: Commit**

```bash
git add economat/composition.py config/settings.py .env.example
git commit -m "feat(payment): câble get_payment_gateway() (fake par défaut)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012NtEzKCRrnrbk4FfzFuwr9"
```

---

### Task 9: `InitiateOnlinePaymentUseCase`

**Files:**
- Create: `economat/application/use_cases/initiate_online_payment.py`
- Test: `economat/tests/test_initiate_online_payment.py`

**Interfaces:**
- Consumes: `RecordPaymentUseCase`/`RecordPaymentCommand` (Task 5), `PaymentGateway` (Task 6), `SchoolYearRepository.find_active(school_id)`, `StudentModel` (ORM direct — le matricule n'est pas un champ du domaine `Student`, cf. `register_student.py` qui le traite déjà hors-domaine de la même façon).
- Produces:
  - `InitiateOnlinePaymentCommand` (dataclass) : `school_id: str`, `matricule: str`, `amount_fcfa: int`, `mobile_operator: str`, `mobile_number: str`, `notify_url: str`.
  - `InitiateOnlinePaymentResult` (dataclass) : `success: bool`, `payment_id: str | None`, `error_message: str = ""`.
  - `InitiateOnlinePaymentUseCase.execute(cmd) -> InitiateOnlinePaymentResult`.

- [ ] **Step 1: Write the failing tests**

```python
# economat/tests/test_initiate_online_payment.py
"""
tests/test_initiate_online_payment.py
========================================
InitiateOnlinePaymentUseCase : point d'entrée du paiement en ligne parent.
"""
import pytest

from economat.application.use_cases.initiate_online_payment import (
    InitiateOnlinePaymentCommand,
    InitiateOnlinePaymentUseCase,
)
from economat.infrastructure.payment.fake_gateway import FakePaymentGateway
from economat.composition import get_record_payment_use_case


@pytest.fixture
def use_case():
    return InitiateOnlinePaymentUseCase(
        record_payment_use_case=get_record_payment_use_case(),
        gateway=FakePaymentGateway(),
    )


@pytest.mark.django_db
def test_valid_matricule_creates_a_pending_payment(use_case, active_enrollment):
    student = active_enrollment.student
    cmd = InitiateOnlinePaymentCommand(
        school_id=str(active_enrollment.school_year.school_id),
        matricule=student.matricule,
        amount_fcfa=25000,
        mobile_operator="Orange Money",
        mobile_number="0700000000",
        notify_url="http://testserver/payer/webhook/cinetpay/",
    )
    result = use_case.execute(cmd)
    assert result.success, result.error_message
    assert result.payment_id

    from economat.infrastructure.models import PaymentModel
    orm = PaymentModel.objects.get(pk=result.payment_id)
    assert orm.state == "PENDING"
    assert orm.channel == "PORTAIL_PARENT"
    assert orm.recorded_by == "Portail parent"
    assert orm.gateway_transaction_ref.startswith("FAKE-")


@pytest.mark.django_db
def test_unknown_matricule_fails_with_generic_message(use_case, active_enrollment):
    cmd = InitiateOnlinePaymentCommand(
        school_id=str(active_enrollment.school_year.school_id),
        matricule="INCONNU-0000000",
        amount_fcfa=25000,
        mobile_operator="Orange Money",
        mobile_number="0700000000",
        notify_url="http://testserver/payer/webhook/cinetpay/",
    )
    result = use_case.execute(cmd)
    assert result.success is False
    # Message générique : ne doit jamais confirmer/infirmer si le matricule
    # existe dans une AUTRE école — juste "introuvable" pour cette école.
    assert "introuvable" in result.error_message.lower()


@pytest.mark.django_db
def test_matricule_from_another_school_fails(use_case, active_enrollment):
    from economat.infrastructure.models import SchoolModel
    other_school = SchoolModel.objects.create(name="Autre École", city="Cotonou", country="Bénin")
    student = active_enrollment.student
    cmd = InitiateOnlinePaymentCommand(
        school_id=str(other_school.id),  # bonne matricule, mauvaise école
        matricule=student.matricule,
        amount_fcfa=25000,
        mobile_operator="Orange Money",
        mobile_number="0700000000",
        notify_url="http://testserver/payer/webhook/cinetpay/",
    )
    result = use_case.execute(cmd)
    assert result.success is False


@pytest.mark.django_db
def test_gateway_failure_does_not_create_a_payment_row(active_enrollment):
    class AlwaysFailingGateway(FakePaymentGateway):
        def initiate_payment(self, *a, **kw):
            from economat.application.ports.payment_gateway import GatewayInitiationResult
            return GatewayInitiationResult(success=False, error_message="Service indisponible")

    use_case = InitiateOnlinePaymentUseCase(
        record_payment_use_case=get_record_payment_use_case(),
        gateway=AlwaysFailingGateway(),
    )
    student = active_enrollment.student
    cmd = InitiateOnlinePaymentCommand(
        school_id=str(active_enrollment.school_year.school_id),
        matricule=student.matricule,
        amount_fcfa=25000,
        mobile_operator="Orange Money",
        mobile_number="0700000000",
        notify_url="http://testserver/payer/webhook/cinetpay/",
    )
    result = use_case.execute(cmd)
    assert result.success is False

    from economat.infrastructure.models import PaymentModel
    assert PaymentModel.objects.count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest economat/tests/test_initiate_online_payment.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'economat.application.use_cases.initiate_online_payment'`.

- [ ] **Step 3: Implement**

```python
# economat/application/use_cases/initiate_online_payment.py
"""
application/use_cases/initiate_online_payment.py
====================================================
USE CASE : InitiateOnlinePaymentUseCase — Acteur : parent, sans compte.

Point d'entrée du paiement en ligne. Résout l'élève par (école, matricule)
en match exact, initie le paiement auprès de la passerelle Mobile Money, et
si la passerelle répond favorablement, délègue la création du paiement
PENDING/PORTAIL_PARENT à RecordPaymentUseCase (réutilisation — voir Task 5).

Sécurité : ne renvoie jamais un message différent selon que l'école existe,
le matricule existe, ou appartient à une autre école — toujours le même
message générique, pour ne pas transformer ce endpoint en oracle de
recherche.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from economat.application.dto import RecordPaymentCommand
from economat.application.ports.payment_gateway import PaymentGateway
from economat.application.use_cases.record_payment import RecordPaymentUseCase
from economat.composition import get_school_year_repo

logger = logging.getLogger(__name__)

GENERIC_NOT_FOUND = "École ou matricule introuvable."


@dataclass
class InitiateOnlinePaymentCommand:
    school_id: str
    matricule: str
    amount_fcfa: int
    mobile_operator: str
    mobile_number: str
    notify_url: str


@dataclass
class InitiateOnlinePaymentResult:
    success: bool
    payment_id: str | None = None
    error_message: str = ""


class InitiateOnlinePaymentUseCase:
    def __init__(self, record_payment_use_case: RecordPaymentUseCase, gateway: PaymentGateway) -> None:
        self._record_payment = record_payment_use_case
        self._gateway = gateway

    def execute(self, cmd: InitiateOnlinePaymentCommand) -> InitiateOnlinePaymentResult:
        try:
            return self._execute(cmd)
        except Exception as e:  # noqa: BLE001
            logger.exception("Erreur inattendue dans InitiateOnlinePaymentUseCase")
            return InitiateOnlinePaymentResult(
                success=False, error_message=f"Erreur inattendue : {type(e).__name__} — {e}",
            )

    def _execute(self, cmd: InitiateOnlinePaymentCommand) -> InitiateOnlinePaymentResult:
        if cmd.amount_fcfa <= 0:
            return InitiateOnlinePaymentResult(success=False, error_message="Montant invalide.")

        # ── 1. Résolution élève par matricule (match exact, hors-domaine —
        # matricule n'est pas un champ du domaine Student, cf. register_student.py) ──
        from economat.infrastructure.models import StudentModel
        student_orm = StudentModel.objects.filter(
            school_id=cmd.school_id, matricule=cmd.matricule,
        ).first()
        if student_orm is None:
            return InitiateOnlinePaymentResult(success=False, error_message=GENERIC_NOT_FOUND)

        # ── 2. Année scolaire active de l'école ───────────────────────────────
        from economat.domain.school.value_objects import SchoolId
        year_repo = get_school_year_repo()
        active_year = year_repo.find_active(SchoolId(cmd.school_id))
        if active_year is None:
            return InitiateOnlinePaymentResult(
                success=False,
                error_message="Aucune année scolaire active pour cette école.",
            )

        # ── 3. Initiation auprès de la passerelle ─────────────────────────────
        gateway_result = self._gateway.initiate_payment(
            phone=cmd.mobile_number,
            operator=cmd.mobile_operator,
            amount_fcfa=cmd.amount_fcfa,
            description=f"Frais de scolarité — {student_orm.first_name} {student_orm.last_name}",
            notify_url=cmd.notify_url,
        )
        if not gateway_result.success:
            return InitiateOnlinePaymentResult(
                success=False,
                error_message=gateway_result.error_message or "Le paiement n'a pas pu être initié.",
            )

        # ── 4. Création du paiement PENDING (réutilise RecordPaymentUseCase) ──
        import datetime
        record_cmd = RecordPaymentCommand(
            student_id=str(student_orm.id),
            year_id=str(active_year.id),
            amount_fcfa=cmd.amount_fcfa,
            payment_date=datetime.date.today(),
            method="MOBILE_MONEY",
            recorded_by="Portail parent",
            initial_state="PENDING",
            channel="PORTAIL_PARENT",
            gateway_transaction_ref=gateway_result.transaction_ref,
            mobile_operator=cmd.mobile_operator,
            mobile_number=cmd.mobile_number,
        )
        record_result = self._record_payment.execute(record_cmd)
        if not record_result.success:
            return InitiateOnlinePaymentResult(success=False, error_message=record_result.error_message)

        return InitiateOnlinePaymentResult(success=True, payment_id=record_result.payment_id)
```

`economat/composition.py` n'expose pas encore de `get_school_year_repo()`
public — seul `_repos()["year"]` existe en interne. Ajouter dans
`economat/composition.py`, à la suite de `_repos()` :

```python
def get_school_year_repo():
    return _repos()["year"]
```

et l'importer dans `initiate_online_payment.py` avec
`from economat.composition import get_school_year_repo` (déjà présent dans
le code ci-dessus).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest economat/tests/test_initiate_online_payment.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest economat/tests/ -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add economat/application/use_cases/initiate_online_payment.py economat/tests/test_initiate_online_payment.py
git commit -m "feat(payment): InitiateOnlinePaymentUseCase — entrée du paiement parent

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012NtEzKCRrnrbk4FfzFuwr9"
```

---

### Task 10: `ConfirmOnlinePaymentUseCase` (traitement du webhook)

**Files:**
- Create: `economat/application/use_cases/confirm_online_payment.py`
- Test: `economat/tests/test_confirm_online_payment.py`

**Interfaces:**
- Consumes: `PaymentRepository` (port existant), `GatewayWebhookEvent`/`GatewayPaymentStatus` (Task 6), `Payment.confirm()`/`Payment.cancel()` (Task 3).
- Produces:
  - `ConfirmOnlinePaymentResult` (dataclass) : `success: bool`, `error_message: str = ""`.
  - `ConfirmOnlinePaymentUseCase.execute(event: GatewayWebhookEvent) -> ConfirmOnlinePaymentResult`.

- [ ] **Step 1: Write the failing tests**

```python
# economat/tests/test_confirm_online_payment.py
"""
tests/test_confirm_online_payment.py
=======================================
ConfirmOnlinePaymentUseCase : transition PENDING → VALID/CANCELLED suite
au webhook de la passerelle. Idempotent, ne fait jamais confiance à
l'appelant sans vérification préalable de signature (faite en amont, dans
la vue — ce use case suppose un événement déjà authentifié).
"""
import pytest

from economat.application.ports.payment_gateway import GatewayPaymentStatus, GatewayWebhookEvent
from economat.application.use_cases.confirm_online_payment import ConfirmOnlinePaymentUseCase
from economat.application.use_cases.initiate_online_payment import (
    InitiateOnlinePaymentCommand, InitiateOnlinePaymentUseCase,
)
from economat.infrastructure.payment.fake_gateway import FakePaymentGateway
from economat.composition import get_record_payment_use_case, get_payment_repo


def _initiate(active_enrollment) -> str:
    gateway = FakePaymentGateway()
    use_case = InitiateOnlinePaymentUseCase(
        record_payment_use_case=get_record_payment_use_case(), gateway=gateway,
    )
    result = use_case.execute(InitiateOnlinePaymentCommand(
        school_id=str(active_enrollment.school_year.school_id),
        matricule=active_enrollment.student.matricule,
        amount_fcfa=25000, mobile_operator="Wave", mobile_number="0700000000",
        notify_url="http://testserver/payer/webhook/cinetpay/",
    ))
    assert result.success
    return result.payment_id


@pytest.mark.django_db
def test_accepted_event_confirms_pending_payment(active_enrollment):
    payment_id = _initiate(active_enrollment)
    from economat.infrastructure.models import PaymentModel
    transaction_ref = PaymentModel.objects.get(pk=payment_id).gateway_transaction_ref

    use_case = ConfirmOnlinePaymentUseCase(payment_repo=get_payment_repo())
    result = use_case.execute(GatewayWebhookEvent(
        transaction_ref=transaction_ref, status=GatewayPaymentStatus.ACCEPTED,
    ))
    assert result.success, result.error_message

    orm = PaymentModel.objects.get(pk=payment_id)
    assert orm.state == "VALID"


@pytest.mark.django_db
def test_refused_event_cancels_pending_payment(active_enrollment):
    payment_id = _initiate(active_enrollment)
    from economat.infrastructure.models import PaymentModel
    transaction_ref = PaymentModel.objects.get(pk=payment_id).gateway_transaction_ref

    use_case = ConfirmOnlinePaymentUseCase(payment_repo=get_payment_repo())
    result = use_case.execute(GatewayWebhookEvent(
        transaction_ref=transaction_ref, status=GatewayPaymentStatus.REFUSED,
    ))
    assert result.success, result.error_message

    orm = PaymentModel.objects.get(pk=payment_id)
    assert orm.state == "CANCELLED"


@pytest.mark.django_db
def test_unknown_transaction_ref_fails_gracefully(active_enrollment):
    use_case = ConfirmOnlinePaymentUseCase(payment_repo=get_payment_repo())
    result = use_case.execute(GatewayWebhookEvent(
        transaction_ref="FAKE-does-not-exist", status=GatewayPaymentStatus.ACCEPTED,
    ))
    assert result.success is False


@pytest.mark.django_db
def test_webhook_received_twice_is_idempotent(active_enrollment):
    payment_id = _initiate(active_enrollment)
    from economat.infrastructure.models import PaymentModel
    transaction_ref = PaymentModel.objects.get(pk=payment_id).gateway_transaction_ref

    use_case = ConfirmOnlinePaymentUseCase(payment_repo=get_payment_repo())
    event = GatewayWebhookEvent(transaction_ref=transaction_ref, status=GatewayPaymentStatus.ACCEPTED)

    first = use_case.execute(event)
    second = use_case.execute(event)  # le fournisseur peut renvoyer le même webhook
    assert first.success and second.success

    orm = PaymentModel.objects.get(pk=payment_id)
    assert orm.state == "VALID"  # toujours VALID, pas d'erreur ni de double-traitement
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest economat/tests/test_confirm_online_payment.py -v`
Expected: FAIL — module inexistant, et potentiellement `get_payment_repo` inexistant dans `composition.py`.

- [ ] **Step 3: Implement**

Si `economat/composition.py` n'expose pas déjà un accès direct au
`PaymentRepository` (vérifier — `_repos()` interne en expose peut-être un
sous une clé `"payment"`), ajouter :

```python
def get_payment_repo():
    return _repos()["payment"]
```

Créer `economat/application/use_cases/confirm_online_payment.py` :

```python
"""
application/use_cases/confirm_online_payment.py
====================================================
USE CASE : ConfirmOnlinePaymentUseCase — Acteur : webhook CinetPay.

Applique la confirmation (ou le refus) d'un paiement en ligne PENDING.
Suppose que l'appelant (la vue webhook) a DÉJÀ vérifié l'authenticité de
l'événement via PaymentGateway.verify_webhook_signature() — ce use case ne
refait aucune vérification de signature, il fait confiance à l'événement
qu'on lui passe.

Idempotent : un même transaction_ref reçu plusieurs fois (le fournisseur
peut retenter un webhook) ne déclenche la transition qu'une seule fois.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from economat.application.ports.payment_gateway import GatewayPaymentStatus, GatewayWebhookEvent
from economat.application.ports.repositories import PaymentRepository
from economat.domain.payment.entities import PaymentState
from economat.domain.payment.value_objects import PaymentId

logger = logging.getLogger(__name__)


@dataclass
class ConfirmOnlinePaymentResult:
    success: bool
    error_message: str = ""


class ConfirmOnlinePaymentUseCase:
    def __init__(self, payment_repo: PaymentRepository) -> None:
        self._payments = payment_repo

    def execute(self, event: GatewayWebhookEvent) -> ConfirmOnlinePaymentResult:
        try:
            return self._execute(event)
        except Exception as e:  # noqa: BLE001
            logger.exception("Erreur inattendue dans ConfirmOnlinePaymentUseCase")
            return ConfirmOnlinePaymentResult(
                success=False, error_message=f"Erreur inattendue : {type(e).__name__} — {e}",
            )

    def _execute(self, event: GatewayWebhookEvent) -> ConfirmOnlinePaymentResult:
        from economat.infrastructure.models import PaymentModel as _PM
        orm = _PM.objects.filter(
            gateway_transaction_ref=event.transaction_ref, channel="PORTAIL_PARENT",
        ).first()
        if orm is None:
            return ConfirmOnlinePaymentResult(
                success=False, error_message=f"Transaction inconnue : {event.transaction_ref}",
            )

        # ── Idempotence : déjà traité, ne pas re-transitionner ────────────────
        if orm.state != "PENDING":
            return ConfirmOnlinePaymentResult(success=True)

        payment = self._payments.find_by_id(PaymentId(str(orm.id)))
        if payment is None:
            return ConfirmOnlinePaymentResult(success=False, error_message="Paiement introuvable.")

        if event.status == GatewayPaymentStatus.ACCEPTED:
            payment.confirm()
        else:
            payment.cancel(reason="Paiement Mobile Money refusé ou annulé par l'opérateur.")

        self._payments.save(payment)
        return ConfirmOnlinePaymentResult(success=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest economat/tests/test_confirm_online_payment.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest economat/tests/ -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add economat/application/use_cases/confirm_online_payment.py economat/tests/test_confirm_online_payment.py economat/composition.py
git commit -m "feat(payment): ConfirmOnlinePaymentUseCase — traite le webhook, idempotent

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012NtEzKCRrnrbk4FfzFuwr9"
```

---

### Task 11: Câblage des use cases dans `composition.py`

**Files:**
- Modify: `economat/composition.py`

**Interfaces:**
- Produces: `get_initiate_online_payment_use_case()`, `get_confirm_online_payment_use_case()`.

- [ ] **Step 1: Ajouter les fonctions de composition**

```python
def get_initiate_online_payment_use_case():
    from economat.application.use_cases.initiate_online_payment import InitiateOnlinePaymentUseCase
    return InitiateOnlinePaymentUseCase(
        record_payment_use_case=get_record_payment_use_case(),
        gateway=get_payment_gateway(),
    )


def get_confirm_online_payment_use_case():
    from economat.application.use_cases.confirm_online_payment import ConfirmOnlinePaymentUseCase
    return ConfirmOnlinePaymentUseCase(payment_repo=get_payment_repo())
```

- [ ] **Step 2: Vérifier**

Run: `.venv/bin/python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_test')
django.setup()
from economat.composition import get_initiate_online_payment_use_case, get_confirm_online_payment_use_case
print(type(get_initiate_online_payment_use_case()).__name__)
print(type(get_confirm_online_payment_use_case()).__name__)
"`
Expected:
```
InitiateOnlinePaymentUseCase
ConfirmOnlinePaymentUseCase
```

- [ ] **Step 3: Commit**

```bash
git add economat/composition.py
git commit -m "feat(payment): câble les use cases du portail parent dans composition.py

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012NtEzKCRrnrbk4FfzFuwr9"
```

---

### Task 12: App `parent_portal` — scaffold, forms, recherche élève

**Files:**
- Create: `economat/interface/parent_portal/__init__.py`
- Create: `economat/interface/parent_portal/forms.py`
- Create: `economat/interface/parent_portal/urls.py`
- Create: `economat/interface/parent_portal/views.py`
- Create: `economat/templates/economat/parent_portal/search.html`
- Modify: `economat/urls.py`
- Test: `economat/tests/test_parent_portal_search.py`

**Interfaces:**
- Consumes: `mobile_operators_for_country`/`mobile_operator_style` (déjà existants, `economat/domain/payment/value_objects.py`).
- Produces:
  - `SchoolMatriculeForm` (école + matricule, validation exacte).
  - Vue `search` (`GET`/`POST /payer/`) : rend le formulaire, ou redirige vers `/payer/montant/` (session) si un élève est trouvé.
  - Session : `request.session["parent_portal_student_id"]`, `request.session["parent_portal_school_id"]`.

- [ ] **Step 1: Write the failing tests**

```python
# economat/tests/test_parent_portal_search.py
"""
tests/test_parent_portal_search.py
=====================================
Recherche parent (école + matricule) — aucune authentification, match
exact uniquement, message d'erreur générique.
"""
import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_search_page_loads_without_authentication(client):
    resp = client.get(reverse("economat:parent_portal_search"))
    assert resp.status_code == 200
    assert "matricule" in resp.content.decode().lower()


@pytest.mark.django_db
def test_valid_school_and_matricule_redirects_to_payment_screen(client, active_enrollment):
    student = active_enrollment.student
    resp = client.post(reverse("economat:parent_portal_search"), {
        "school": str(active_enrollment.school_year.school_id),
        "matricule": student.matricule,
    })
    assert resp.status_code == 302
    assert resp.url == reverse("economat:parent_portal_pay")
    session = client.session
    assert session["parent_portal_student_id"] == str(student.id)


@pytest.mark.django_db
def test_unknown_matricule_shows_generic_error(client, active_enrollment):
    resp = client.post(reverse("economat:parent_portal_search"), {
        "school": str(active_enrollment.school_year.school_id),
        "matricule": "INCONNU-0000000",
    })
    assert resp.status_code == 200
    assert "introuvable" in resp.content.decode().lower()


@pytest.mark.django_db
def test_correct_matricule_wrong_school_shows_same_generic_error(client, active_enrollment):
    from economat.infrastructure.models import SchoolModel
    other_school = SchoolModel.objects.create(name="Autre École", city="Cotonou", country="Bénin")
    student = active_enrollment.student
    resp = client.post(reverse("economat:parent_portal_search"), {
        "school": str(other_school.id),
        "matricule": student.matricule,
    })
    assert resp.status_code == 200
    assert "introuvable" in resp.content.decode().lower()


@pytest.mark.django_db
def test_search_does_not_suggest_partial_matches(client, active_enrollment):
    """Aucune autocomplétion : une saisie partielle ne doit renvoyer aucune
    suggestion, seulement l'erreur générique."""
    student = active_enrollment.student
    partial = student.matricule[:6]  # préfixe seulement, pas le matricule complet
    resp = client.post(reverse("economat:parent_portal_search"), {
        "school": str(active_enrollment.school_year.school_id),
        "matricule": partial,
    })
    assert resp.status_code == 200
    assert student.first_name not in resp.content.decode()
    assert "introuvable" in resp.content.decode().lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest economat/tests/test_parent_portal_search.py -v`
Expected: FAIL — `NoReverseMatch` (l'app/les routes n'existent pas encore).

- [ ] **Step 3: Créer l'app**

`economat/interface/parent_portal/__init__.py` (vide).

`economat/interface/parent_portal/forms.py` :

```python
"""
interface/parent_portal/forms.py
===================================
Formulaire de recherche élève par école + matricule.

Sécurité : le matricule est normalisé (majuscules, espaces retirés) mais
JAMAIS recherché en `icontains` — un match partiel ne doit jamais être
possible (voir InitiateOnlinePaymentUseCase / la vue search qui applique
le même principe pour la recherche seule).
"""
from django import forms

from economat.infrastructure.models import SchoolModel


class SchoolMatriculeForm(forms.Form):
    school = forms.ModelChoiceField(
        label="École", queryset=SchoolModel.objects.order_by("name"),
        empty_label="Sélectionnez l'école",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    matricule = forms.CharField(
        label="Matricule de l'élève", max_length=30,
        widget=forms.TextInput(attrs={
            "class": "form-input", "placeholder": "Ex : DIAAWA-7K9XQPR",
            "autocomplete": "off", "autocapitalize": "characters",
        }),
    )

    def clean_matricule(self) -> str:
        return self.cleaned_data["matricule"].strip().upper()
```

`economat/interface/parent_portal/views.py` :

```python
"""
interface/parent_portal/views.py
===================================
Vues du portail de paiement parent — AUCUNE authentification. La session
Django (sans compte) porte l'identité de l'élève confirmé entre les écrans
(recherche → montant → paiement → reçu).
"""
from __future__ import annotations

from django.shortcuts import redirect, render

from .forms import SchoolMatriculeForm

GENERIC_NOT_FOUND = "École ou matricule introuvable. Vérifiez votre saisie."


def search(request):
    """GET : formulaire vide. POST : recherche exacte, redirige si trouvé."""
    if request.method == "POST":
        form = SchoolMatriculeForm(request.POST)
        if form.is_valid():
            school = form.cleaned_data["school"]
            matricule = form.cleaned_data["matricule"]

            from economat.infrastructure.models import StudentModel
            student = StudentModel.objects.filter(
                school_id=school.id, matricule=matricule,
            ).first()

            if student is not None:
                request.session["parent_portal_student_id"] = str(student.id)
                request.session["parent_portal_school_id"] = str(school.id)
                return redirect("economat:parent_portal_pay")

            form.add_error(None, GENERIC_NOT_FOUND)
    else:
        form = SchoolMatriculeForm()

    return render(request, "economat/parent_portal/search.html", {
        "form": form, "page_title": "Payer les frais de scolarité",
    })
```

`economat/interface/parent_portal/urls.py` :

```python
"""
interface/parent_portal/urls.py — Portail de paiement parent, sans authentification.

Pas de `app_name` ici, par cohérence avec les autres sous-apps du projet
(`econome/urls.py`, `director/urls.py`, `accounts/urls.py`) : aucune ne
déclare son propre `app_name` — toutes les routes vivent à plat sous le
seul namespace `economat` déclaré dans `economat/urls.py`. Chaque route
porte donc un nom préfixé `parent_portal_...` pour éviter toute collision
avec les routes des autres sous-apps (même convention que
`econome_dashboard`, `econome_payments`, etc.).
"""
from django.urls import path

from . import views

urlpatterns = [
    path("", views.search, name="parent_portal_search"),
]
```

Créer `economat/templates/economat/parent_portal/search.html` :

```django
{% extends "economat/base.html" %}
{% block title %}Payer les frais de scolarité{% endblock %}
{% block content %}
<div style="max-width:420px;margin:3rem auto;">
  <div class="card" style="padding:1.75rem;">
    <h1 style="font-size:1.125rem;font-weight:700;margin-bottom:.35rem;">Payer les frais de scolarité</h1>
    <p style="font-size:.8375rem;color:#9397a8;margin-bottom:1.5rem;">
      Sélectionnez l'école et saisissez le matricule complet de votre enfant.
    </p>
    {% if form.non_field_errors %}
    <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:.75rem 1rem;margin-bottom:1.25rem;color:#b91c1c;font-size:.84375rem;">
      {{ form.non_field_errors.0 }}
    </div>
    {% endif %}
    <form method="post" style="display:flex;flex-direction:column;gap:1rem;">
      {% csrf_token %}
      <div>
        <label class="field-label">{{ form.school.label }}</label>
        {{ form.school }}
        {% if form.school.errors %}<p class="field-error">{{ form.school.errors.0 }}</p>{% endif %}
      </div>
      <div>
        <label class="field-label">{{ form.matricule.label }}</label>
        {{ form.matricule }}
        {% if form.matricule.errors %}<p class="field-error">{{ form.matricule.errors.0 }}</p>{% endif %}
      </div>
      <button type="submit" class="btn-primary" style="width:100%;padding:.8rem;font-weight:600;">
        Rechercher mon enfant
      </button>
    </form>
  </div>
  <p style="text-align:center;font-size:.78125rem;color:#9397a8;margin-top:1rem;">
    Le matricule vous a été communiqué par l'école lors de l'inscription.
  </p>
</div>
{% endblock %}
```

Monter les routes dans `economat/urls.py` — même style que les 3 `include()`
déjà présents, sans namespace supplémentaire (cf. note ci-dessus sur
`app_name`) :

```python
urlpatterns = [
    path("",        include("economat.interface.accounts.urls")),
    path("econome/",   include("economat.interface.econome.urls")),
    path("directeur/", include("economat.interface.director.urls")),
    # Portail de paiement parent — sans authentification
    path("payer/", include("economat.interface.parent_portal.urls")),
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest economat/tests/test_parent_portal_search.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest economat/tests/ -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add economat/interface/parent_portal/ economat/templates/economat/parent_portal/search.html economat/urls.py economat/tests/test_parent_portal_search.py
git commit -m "feat(parent-portal): écran de recherche élève (école + matricule)

Sans authentification, match exact uniquement, message d'erreur générique
qui ne distingue jamais école/matricule invalide.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012NtEzKCRrnrbk4FfzFuwr9"
```

---

### Task 13: Écran montant + choix opérateur

**Files:**
- Modify: `economat/interface/parent_portal/forms.py`
- Modify: `economat/interface/parent_portal/views.py`
- Modify: `economat/interface/parent_portal/urls.py`
- Create: `economat/templates/economat/parent_portal/pay.html`
- Test: `economat/tests/test_parent_portal_pay.py`

**Interfaces:**
- Consumes: `mobile_operators_for_country`, `mobile_operator_style` (`economat/domain/payment/value_objects.py`, déjà existants) ; `request.session["parent_portal_student_id"]` (Task 12).
- Produces:
  - `OnlinePaymentForm` (montant, opérateur, numéro — mêmes règles que `RecordPaymentForm` pour l'opérateur/numéro).
  - Vue `pay` (`GET`/`POST /payer/montant/`) : affiche l'identité de l'élève confirmée + solde, le formulaire ; redirige vers `/payer/initier/` en POST valide (Task 14, traité dans ce même formulaire pour simplifier — voir note).

- [ ] **Step 1: Write the failing tests**

```python
# economat/tests/test_parent_portal_pay.py
"""
tests/test_parent_portal_pay.py
==================================
Écran montant + opérateur — nécessite un élève déjà confirmé en session
(pas d'accès direct sans être passé par la recherche).
"""
import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_pay_screen_requires_a_confirmed_student_in_session(client):
    resp = client.get(reverse("economat:parent_portal_pay"))
    assert resp.status_code == 302
    assert resp.url == reverse("economat:parent_portal_search")


@pytest.mark.django_db
def test_pay_screen_shows_student_full_name_after_search(client, active_enrollment):
    student = active_enrollment.student
    client.post(reverse("economat:parent_portal_search"), {
        "school": str(active_enrollment.school_year.school_id),
        "matricule": student.matricule,
    })
    resp = client.get(reverse("economat:parent_portal_pay"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert student.first_name in body
    assert student.last_name.upper() in body.upper()


@pytest.mark.django_db
def test_operator_cards_reflect_school_country(client, active_enrollment):
    # active_enrollment fixture crée une école au Togo (voir conftest.py)
    student = active_enrollment.student
    client.post(reverse("economat:parent_portal_search"), {
        "school": str(active_enrollment.school_year.school_id),
        "matricule": student.matricule,
    })
    resp = client.get(reverse("economat:parent_portal_pay"))
    body = resp.content.decode()
    assert "Flooz" in body or "T-Money" in body  # opérateurs Togo
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest economat/tests/test_parent_portal_pay.py -v`
Expected: FAIL — vue `pay` inexistante.

- [ ] **Step 3: Implement**

Ajouter dans `economat/interface/parent_portal/forms.py` (à la suite de `SchoolMatriculeForm`) :

```python
import re

from economat.domain.payment.value_objects import mobile_operator_style, mobile_operators_for_country


class OnlinePaymentForm(forms.Form):
    amount_fcfa = forms.IntegerField(
        label="Montant à payer (FCFA)", min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-input", "placeholder": "Ex : 25000"}),
    )
    mobile_operator = forms.ChoiceField(label="Opérateur Mobile Money", choices=[])
    mobile_number = forms.CharField(
        label="Votre numéro Mobile Money", max_length=20,
        widget=forms.TextInput(attrs={"class": "form-input", "inputmode": "tel",
                                       "placeholder": "Ex : 07 00 00 00 00"}),
    )

    def __init__(self, *args, country: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        operators = mobile_operators_for_country(country)
        self.fields["mobile_operator"].choices = [(op, op) for op in operators]
        self.mobile_operator_options = [
            {"value": op, "style": mobile_operator_style(op)} for op in operators
        ]

    def clean_mobile_number(self) -> str:
        number = self.cleaned_data["mobile_number"]
        digits = re.sub(r"\D", "", number)
        if len(digits) < 8:
            raise forms.ValidationError("Numéro trop court.")
        return number
```

Ajouter dans `economat/interface/parent_portal/views.py` :

```python
def pay(request):
    """Écran montant + opérateur — nécessite un élève confirmé en session."""
    student_id = request.session.get("parent_portal_student_id")
    school_id = request.session.get("parent_portal_school_id")
    if not student_id or not school_id:
        return redirect("economat:parent_portal_search")

    from economat.infrastructure.models import EnrollmentModel, StudentModel
    try:
        student = StudentModel.objects.get(pk=student_id, school_id=school_id)
    except StudentModel.DoesNotExist:
        return redirect("economat:parent_portal_search")

    enrollment = (
        EnrollmentModel.objects
        .select_related("level", "klass", "school_year")
        .filter(student_id=student_id, school_year__status="ACTIVE")
        .first()
    )

    balance = None
    if enrollment is not None:
        from django.db.models import Sum
        paid = (
            enrollment.payments.filter(state="VALID").aggregate(total=Sum("amount"))["total"]
            or 0
        )
        balance = max(enrollment.level.annual_fee - paid, 0)

    if request.method == "POST":
        form = OnlinePaymentForm(request.POST, country=student.school.country)
        if form.is_valid() and enrollment is not None:
            from economat.composition import get_initiate_online_payment_use_case
            from economat.application.use_cases.initiate_online_payment import (
                InitiateOnlinePaymentCommand,
            )
            notify_url = request.build_absolute_uri(
                reverse("economat:parent_portal_webhook_cinetpay")
            )
            result = get_initiate_online_payment_use_case().execute(InitiateOnlinePaymentCommand(
                school_id=str(school_id),
                matricule=student.matricule,
                amount_fcfa=form.cleaned_data["amount_fcfa"],
                mobile_operator=form.cleaned_data["mobile_operator"],
                mobile_number=form.cleaned_data["mobile_number"],
                notify_url=notify_url,
            ))
            if result.success:
                request.session["parent_portal_payment_id"] = result.payment_id
                return redirect("economat:parent_portal_waiting", payment_id=result.payment_id)
            form.add_error(None, result.error_message)
    else:
        form = OnlinePaymentForm(country=student.school.country)

    return render(request, "economat/parent_portal/pay.html", {
        "form": form, "student": student, "enrollment": enrollment, "balance": balance,
        "page_title": "Payer les frais de scolarité",
    })
```

Ajouter les imports nécessaires en tête de `views.py` : `from django.urls import reverse`,
`from .forms import OnlinePaymentForm, SchoolMatriculeForm`.

Ajouter la route dans `economat/interface/parent_portal/urls.py` :

```python
urlpatterns = [
    path("", views.search, name="parent_portal_search"),
    path("montant/", views.pay, name="parent_portal_pay"),
]
```

**Note pour l'implémenteur :** les routes `waiting` et `webhook_cinetpay`
référencées ci-dessus (`reverse("economat:parent_portal_waiting", ...)`,
`reverse("economat:parent_portal_webhook_cinetpay")`) sont créées Task 14 —
cette vue `pay` ne sera pleinement fonctionnelle qu'une fois cette tâche
faite. Les tests de cette Task 13 ne couvrent que le GET (affichage), pas
le POST complet — c'est voulu, le POST est testé Task 14 une fois le
parcours entier câblé.

Créer `economat/templates/economat/parent_portal/pay.html` :

```django
{% extends "economat/base.html" %}
{% block title %}Payer les frais de scolarité{% endblock %}
{% block content %}
<div style="max-width:460px;margin:3rem auto;">
  <div class="card" style="padding:1.75rem;margin-bottom:1rem;background:#eef2ff;border-color:#c7d2fe;">
    <div style="font-size:.75rem;font-weight:600;color:#4338ca;text-transform:uppercase;letter-spacing:.05em;margin-bottom:.35rem;">Vous payez pour</div>
    <div style="font-size:1.0625rem;font-weight:700;color:#1a1d29;">{{ student.first_name }} {{ student.last_name|upper }}</div>
    {% if enrollment %}
    <div style="font-size:.8125rem;color:#52556b;margin-top:.2rem;">
      {{ enrollment.level.name }} &middot; {{ enrollment.klass.name }} &middot; {{ enrollment.school_year.label }}
    </div>
    {% if balance is not None %}
    <div style="font-size:.8125rem;color:#52556b;margin-top:.5rem;">
      Solde restant : <strong>{{ balance }} FCFA</strong>
    </div>
    {% endif %}
    {% else %}
    <div style="font-size:.8125rem;color:#b91c1c;margin-top:.5rem;">
      Aucune inscription active trouvée pour cette année scolaire.
    </div>
    {% endif %}
  </div>

  <div class="card" style="padding:1.75rem;">
    {% if form.non_field_errors %}
    <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:.75rem 1rem;margin-bottom:1.25rem;color:#b91c1c;font-size:.84375rem;">
      {{ form.non_field_errors.0 }}
    </div>
    {% endif %}
    <form method="post" style="display:flex;flex-direction:column;gap:1.25rem;">
      {% csrf_token %}
      <div>
        <label class="field-label">{{ form.amount_fcfa.label }}</label>
        {{ form.amount_fcfa }}
        {% if form.amount_fcfa.errors %}<p class="field-error">{{ form.amount_fcfa.errors.0 }}</p>{% endif %}
      </div>

      <div>
        <label class="field-label">{{ form.mobile_operator.label }}</label>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(6.5rem,1fr));gap:.5rem;">
          {% for opt in form.mobile_operator_options %}
          <label class="method-card">
            <input type="radio" name="mobile_operator" value="{{ opt.value }}"
                   class="operator-radio" style="display:none;"
                   data-fg="{{ opt.style.fg }}" data-bg="{{ opt.style.bg }}">
            <span class="method-icon" style="background:{{ opt.style.bg }};color:{{ opt.style.fg }};font-size:.68rem;font-weight:800;">{{ opt.style.short }}</span>
            <span class="method-label">{{ opt.value }}</span>
          </label>
          {% endfor %}
        </div>
        {% if form.mobile_operator.errors %}<p class="field-error">{{ form.mobile_operator.errors.0 }}</p>{% endif %}
      </div>

      <div>
        <label class="field-label">{{ form.mobile_number.label }}</label>
        {{ form.mobile_number }}
        {% if form.mobile_number.errors %}<p class="field-error">{{ form.mobile_number.errors.0 }}</p>{% endif %}
      </div>

      <button type="submit" class="btn-primary" style="width:100%;padding:.85rem;font-weight:600;">
        Payer maintenant
      </button>
    </form>
  </div>
</div>

<style>
  .method-card {
    display:flex;flex-direction:column;align-items:center;justify-content:center;
    gap:.35rem;padding:.7rem .5rem;border:1.5px solid #ecedf1;border-radius:10px;
    cursor:pointer;text-align:center;transition:border-color .13s,background .13s;
    user-select:none;min-height:4.6rem;
  }
  .method-card:hover { border-color:#c7d2fe;background:#fafbff; }
  .method-icon {
    width:2rem;height:2rem;border-radius:8px;
    display:flex;align-items:center;justify-content:center;flex-shrink:0;
  }
  .method-label { font-size:.75rem;font-weight:500;color:#52556b;white-space:normal;line-height:1.15; }
</style>
<script>
  document.querySelectorAll('.operator-radio').forEach(radio => {
    radio.addEventListener('change', () => {
      document.querySelectorAll('.operator-radio').forEach(r => {
        const lbl = r.closest('.method-card');
        const label = lbl.querySelector('.method-label');
        if (r.checked) {
          lbl.style.borderColor = r.dataset.fg;
          lbl.style.background  = r.dataset.bg;
          label.style.color = r.dataset.fg; label.style.fontWeight = '600';
        } else {
          lbl.style.borderColor = '#ecedf1'; lbl.style.background = '';
          label.style.color = '#52556b'; label.style.fontWeight = '500';
        }
      });
    });
  });
</script>
{% endblock %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest economat/tests/test_parent_portal_pay.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add economat/interface/parent_portal/forms.py economat/interface/parent_portal/views.py economat/interface/parent_portal/urls.py economat/templates/economat/parent_portal/pay.html economat/tests/test_parent_portal_pay.py
git commit -m "feat(parent-portal): écran montant + choix opérateur Mobile Money

Réutilise les cartes opérateur (style/couleurs) déjà construites pour
l'écran économe — homogène, filtré selon le pays de l'école.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012NtEzKCRrnrbk4FfzFuwr9"
```

---

### Task 14: Initiation, écran d'attente, endpoint statut, webhook

**Files:**
- Modify: `economat/interface/parent_portal/views.py`
- Modify: `economat/interface/parent_portal/urls.py`
- Create: `economat/templates/economat/parent_portal/waiting.html`
- Test: `economat/tests/test_parent_portal_flow.py`

**Interfaces:**
- Consumes: `get_initiate_online_payment_use_case()`, `get_confirm_online_payment_use_case()`, `get_payment_gateway()` (Task 11/8), `FakePaymentGateway.simulate_confirmation()` (Task 7, pour les tests).
- Produces:
  - Vue `waiting` (`GET /payer/attente/<payment_id>/`) : écran d'attente, poll JS.
  - Vue `status` (`GET /payer/statut/<payment_id>/`) : JSON `{"state": "PENDING"|"VALID"|"CANCELLED"}`.
  - Vue `webhook_cinetpay` (`POST /payer/webhook/cinetpay/`) : `@csrf_exempt`, vérifie la signature, applique `ConfirmOnlinePaymentUseCase`.

- [ ] **Step 1: Write the failing tests**

```python
# economat/tests/test_parent_portal_flow.py
"""
tests/test_parent_portal_flow.py
===================================
Parcours complet : recherche → montant → initiation → attente → webhook
→ statut → reçu. Utilise FakePaymentGateway (PAYMENT_GATEWAY=fake, défaut
de settings_test).
"""
import pytest
from django.urls import reverse


def _search_and_open_pay(client, active_enrollment):
    student = active_enrollment.student
    client.post(reverse("economat:parent_portal_search"), {
        "school": str(active_enrollment.school_year.school_id),
        "matricule": student.matricule,
    })
    return student


@pytest.mark.django_db
def test_full_flow_from_payment_to_confirmed_receipt(client, active_enrollment):
    student = _search_and_open_pay(client, active_enrollment)

    resp = client.post(reverse("economat:parent_portal_pay"), {
        "amount_fcfa": "25000", "mobile_operator": "Orange Money",
        "mobile_number": "0700000000",
    })
    assert resp.status_code == 302
    payment_id = resp.url.rstrip("/").split("/")[-1]

    # Écran d'attente accessible
    resp = client.get(reverse("economat:parent_portal_waiting", args=[payment_id]))
    assert resp.status_code == 200

    # Statut : toujours PENDING avant webhook
    resp = client.get(reverse("economat:parent_portal_status", args=[payment_id]))
    assert resp.json()["state"] == "PENDING"

    # Simule le webhook CinetPay (via FakePaymentGateway)
    from economat.composition import get_payment_gateway
    from economat.infrastructure.models import PaymentModel
    orm = PaymentModel.objects.get(pk=payment_id)
    gateway = get_payment_gateway()
    body, headers = gateway.simulate_confirmation(orm.gateway_transaction_ref, accepted=True)
    resp = client.post(
        reverse("economat:parent_portal_webhook_cinetpay"),
        data=body, content_type="application/json",
        **{f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items()},
    )
    assert resp.status_code == 200

    # Statut : VALID après webhook
    resp = client.get(reverse("economat:parent_portal_status", args=[payment_id]))
    assert resp.json()["state"] == "VALID"


@pytest.mark.django_db
def test_webhook_without_valid_signature_is_rejected(client, active_enrollment):
    student = _search_and_open_pay(client, active_enrollment)
    resp = client.post(reverse("economat:parent_portal_pay"), {
        "amount_fcfa": "25000", "mobile_operator": "Orange Money",
        "mobile_number": "0700000000",
    })
    payment_id = resp.url.rstrip("/").split("/")[-1]

    from economat.infrastructure.models import PaymentModel
    orm = PaymentModel.objects.get(pk=payment_id)

    import json
    body = json.dumps({"transaction_ref": orm.gateway_transaction_ref, "status": "ACCEPTED"}).encode()
    resp = client.post(
        reverse("economat:parent_portal_webhook_cinetpay"),
        data=body, content_type="application/json",
        # Pas de signature — doit être rejeté
    )
    assert resp.status_code == 403

    orm.refresh_from_db()
    assert orm.state == "PENDING"  # inchangé


@pytest.mark.django_db
def test_refused_webhook_updates_status_to_cancelled(client, active_enrollment):
    student = _search_and_open_pay(client, active_enrollment)
    resp = client.post(reverse("economat:parent_portal_pay"), {
        "amount_fcfa": "25000", "mobile_operator": "Wave", "mobile_number": "0700000000",
    })
    payment_id = resp.url.rstrip("/").split("/")[-1]

    from economat.composition import get_payment_gateway
    from economat.infrastructure.models import PaymentModel
    orm = PaymentModel.objects.get(pk=payment_id)
    gateway = get_payment_gateway()
    body, headers = gateway.simulate_confirmation(orm.gateway_transaction_ref, accepted=False)
    client.post(
        reverse("economat:parent_portal_webhook_cinetpay"),
        data=body, content_type="application/json",
        **{f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items()},
    )

    resp = client.get(reverse("economat:parent_portal_status", args=[payment_id]))
    assert resp.json()["state"] == "CANCELLED"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest economat/tests/test_parent_portal_flow.py -v`
Expected: FAIL — routes `waiting`/`status`/`webhook_cinetpay` inexistantes.

- [ ] **Step 3: Implement**

Ajouter dans `economat/interface/parent_portal/views.py` :

```python
import json

from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST


def waiting(request, payment_id: str):
    """Écran d'attente — poll /payer/statut/<id>/ en JS jusqu'à confirmation."""
    from economat.infrastructure.models import PaymentModel
    payment = PaymentModel.objects.filter(pk=payment_id, channel="PORTAIL_PARENT").first()
    if payment is None:
        return redirect("economat:parent_portal_search")
    if payment.state == "VALID":
        return redirect("economat:parent_portal_receipt", payment_id=payment_id)
    return render(request, "economat/parent_portal/waiting.html", {
        "payment": payment, "page_title": "Confirmation du paiement",
    })


@require_GET
def status(request, payment_id: str):
    """Endpoint pollé en JS toutes les 3s par l'écran d'attente."""
    from economat.infrastructure.models import PaymentModel
    payment = PaymentModel.objects.filter(pk=payment_id, channel="PORTAIL_PARENT").first()
    if payment is None:
        return JsonResponse({"state": "UNKNOWN"}, status=404)
    return JsonResponse({"state": payment.state})


@csrf_exempt
@require_POST
def webhook_cinetpay(request):
    """
    Callback serveur-à-serveur de la passerelle de paiement. Aucune session
    ni authentification utilisateur ici — la sécurité tient entièrement à
    la vérification de signature avant tout traitement.
    """
    from economat.composition import get_confirm_online_payment_use_case, get_payment_gateway

    gateway = get_payment_gateway()
    raw_body = request.body

    if not gateway.verify_webhook_signature(raw_body, dict(request.headers)):
        return HttpResponseForbidden("Signature invalide.")

    try:
        event = gateway.parse_webhook_status(raw_body)
    except (json.JSONDecodeError, KeyError, ValueError):
        return JsonResponse({"error": "Corps de requête invalide."}, status=400)

    result = get_confirm_online_payment_use_case().execute(event)
    if not result.success:
        # 200 quand même : évite que le fournisseur ne retente indéfiniment
        # un webhook pour une transaction qu'on ne reconnaît pas (log côté
        # serveur suffisant pour investiguer).
        return JsonResponse({"status": "ignored", "detail": result.error_message})

    return JsonResponse({"status": "ok"})
```

Ajouter les routes dans `economat/interface/parent_portal/urls.py` :

```python
urlpatterns = [
    path("", views.search, name="parent_portal_search"),
    path("montant/", views.pay, name="parent_portal_pay"),
    path("attente/<uuid:payment_id>/", views.waiting, name="parent_portal_waiting"),
    path("statut/<uuid:payment_id>/", views.status, name="parent_portal_status"),
    path("webhook/cinetpay/", views.webhook_cinetpay, name="parent_portal_webhook_cinetpay"),
]
```

Créer `economat/templates/economat/parent_portal/waiting.html` :

```django
{% extends "economat/base.html" %}
{% block title %}Confirmation du paiement{% endblock %}
{% block content %}
<div style="max-width:420px;margin:4rem auto;text-align:center;">
  <div class="card" style="padding:2.5rem 2rem;">
    <div id="spinner" style="width:2.5rem;height:2.5rem;border:3px solid #ecedf1;border-top-color:#4f46e5;border-radius:50%;margin:0 auto 1.25rem;animation:spin 0.8s linear infinite;"></div>
    <h1 style="font-size:1.0625rem;font-weight:700;margin-bottom:.5rem;">Vérifiez votre téléphone</h1>
    <p id="waitMsg" style="font-size:.875rem;color:#52556b;line-height:1.6;">
      Confirmez le paiement avec votre code Mobile Money.
      Cette page se met à jour automatiquement.
    </p>
  </div>
</div>
<style>@keyframes spin { to { transform: rotate(360deg); } }</style>
<script>
(function () {
  var paymentId = "{{ payment.id }}";
  var statusUrl = "/payer/statut/" + paymentId + "/";
  var receiptUrl = "/payer/recu/" + paymentId + "/";
  var elapsed = 0;
  var poll = setInterval(function () {
    elapsed += 3;
    fetch(statusUrl).then(function (r) { return r.json(); }).then(function (data) {
      if (data.state === "VALID") {
        clearInterval(poll);
        window.location = receiptUrl;
      } else if (data.state === "CANCELLED") {
        clearInterval(poll);
        document.getElementById("spinner").style.display = "none";
        document.getElementById("waitMsg").innerHTML =
          "Le paiement a été refusé ou annulé. <a href=\"/payer/montant/\">Réessayer</a>.";
      } else if (elapsed >= 120) {
        clearInterval(poll);
        document.getElementById("waitMsg").textContent =
          "Ça prend plus de temps que prévu. Vérifiez votre téléphone ou contactez l'école.";
      }
    });
  }, 3000);
})();
</script>
{% endblock %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest economat/tests/test_parent_portal_flow.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest economat/tests/ -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add economat/interface/parent_portal/views.py economat/interface/parent_portal/urls.py economat/templates/economat/parent_portal/waiting.html economat/tests/test_parent_portal_flow.py
git commit -m "feat(parent-portal): initiation, écran d'attente, webhook CinetPay

Le parent reste sur notre page pendant tout le paiement. Webhook rejeté
sans signature valide, idempotent, jamais de confiance aveugle.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012NtEzKCRrnrbk4FfzFuwr9"
```

---

### Task 15: Reçu parent + historique

**Files:**
- Modify: `economat/interface/parent_portal/views.py`
- Modify: `economat/interface/parent_portal/urls.py`
- Create: `economat/templates/economat/parent_portal/receipt.html`
- Create: `economat/templates/economat/parent_portal/history.html`
- Test: `economat/tests/test_parent_portal_receipt_history.py`

**Interfaces:**
- Consumes: `SchoolMatriculeForm` (Task 12, réutilisé tel quel pour l'historique).
- Produces: vue `receipt` (`GET /payer/recu/<payment_id>/`), vue `history` (`GET`/`POST /payer/historique/`).

- [ ] **Step 1: Write the failing tests**

```python
# economat/tests/test_parent_portal_receipt_history.py
"""
tests/test_parent_portal_receipt_history.py
==============================================
Reçu (accessible seulement si VALID) + historique (recherche identique à
l'écran d'accueil, liste les paiements passés VALID de l'élève).
"""
import datetime
import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_receipt_not_accessible_while_pending(client, active_enrollment):
    from economat.composition import get_initiate_online_payment_use_case
    from economat.application.use_cases.initiate_online_payment import InitiateOnlinePaymentCommand

    student = active_enrollment.student
    result = get_initiate_online_payment_use_case().execute(InitiateOnlinePaymentCommand(
        school_id=str(active_enrollment.school_year.school_id), matricule=student.matricule,
        amount_fcfa=25000, mobile_operator="Orange Money", mobile_number="0700000000",
        notify_url="http://testserver/payer/webhook/cinetpay/",
    ))
    resp = client.get(reverse("economat:parent_portal_receipt", args=[result.payment_id]))
    assert resp.status_code == 302  # redirigé vers l'écran d'attente, pas de reçu


@pytest.mark.django_db
def test_receipt_shown_once_valid(client, active_enrollment):
    from economat.infrastructure.models import PaymentModel
    from economat.composition import get_record_payment_use_case
    from economat.application.dto import RecordPaymentCommand

    student = active_enrollment.student
    r = get_record_payment_use_case().execute(RecordPaymentCommand(
        student_id=str(student.id), year_id=str(active_enrollment.school_year_id),
        amount_fcfa=25000, payment_date=datetime.date.today(), method="MOBILE_MONEY",
        recorded_by="Portail parent", initial_state="VALID", channel="PORTAIL_PARENT",
        mobile_operator="Orange Money", mobile_number="0700000000",
    ))
    resp = client.get(reverse("economat:parent_portal_receipt", args=[r.payment_id]))
    assert resp.status_code == 200
    assert "Orange Money" in resp.content.decode()


@pytest.mark.django_db
def test_history_lists_valid_payments_only(client, active_enrollment):
    from economat.composition import get_record_payment_use_case
    from economat.application.dto import RecordPaymentCommand

    student = active_enrollment.student
    get_record_payment_use_case().execute(RecordPaymentCommand(
        student_id=str(student.id), year_id=str(active_enrollment.school_year_id),
        amount_fcfa=15000, payment_date=datetime.date.today(), method="ESPECES",
        recorded_by="econome-test",
    ))
    get_record_payment_use_case().execute(RecordPaymentCommand(
        student_id=str(student.id), year_id=str(active_enrollment.school_year_id),
        amount_fcfa=10000, payment_date=datetime.date.today(), method="MOBILE_MONEY",
        recorded_by="Portail parent", initial_state="PENDING", channel="PORTAIL_PARENT",
        mobile_operator="Wave", mobile_number="0711111111",
    ))

    resp = client.post(reverse("economat:parent_portal_history"), {
        "school": str(active_enrollment.school_year.school_id), "matricule": student.matricule,
    })
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "15" in body  # le paiement guichet VALID apparaît
    assert "10" not in body.split("15")[0]  # le paiement PENDING n'apparaît pas
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest economat/tests/test_parent_portal_receipt_history.py -v`
Expected: FAIL — routes `receipt`/`history` inexistantes.

- [ ] **Step 3: Implement**

Ajouter dans `economat/interface/parent_portal/views.py` :

```python
def receipt(request, payment_id: str):
    """Reçu — uniquement si le paiement est confirmé (VALID)."""
    from economat.infrastructure.models import PaymentModel
    payment = PaymentModel.objects.select_related(
        "student", "enrollment__klass", "enrollment__klass__level", "enrollment__school_year",
    ).filter(pk=payment_id, channel="PORTAIL_PARENT").first()
    if payment is None:
        return redirect("economat:parent_portal_search")
    if payment.state != "VALID":
        return redirect("economat:parent_portal_waiting", payment_id=payment_id)

    return render(request, "economat/parent_portal/receipt.html", {
        "payment": payment, "school": payment.enrollment.school_year.school,
        "student": payment.student, "klass": payment.enrollment.klass,
        "page_title": f"Reçu {payment.receipt_number}",
    })


def history(request):
    """Même recherche que l'accueil, liste les paiements VALID de l'élève (tous canaux)."""
    payments = None
    student = None
    if request.method == "POST":
        form = SchoolMatriculeForm(request.POST)
        if form.is_valid():
            school = form.cleaned_data["school"]
            matricule = form.cleaned_data["matricule"]
            from economat.infrastructure.models import PaymentModel, StudentModel
            student = StudentModel.objects.filter(school_id=school.id, matricule=matricule).first()
            if student is not None:
                payments = (
                    PaymentModel.objects
                    .filter(student_id=student.id, state="VALID")
                    .order_by("-payment_date", "-created_at")
                )
            else:
                form.add_error(None, GENERIC_NOT_FOUND)
    else:
        form = SchoolMatriculeForm()

    return render(request, "economat/parent_portal/history.html", {
        "form": form, "student": student, "payments": payments,
        "page_title": "Historique de mes paiements",
    })
```

Ajouter les routes :

```python
urlpatterns = [
    path("", views.search, name="parent_portal_search"),
    path("montant/", views.pay, name="parent_portal_pay"),
    path("attente/<uuid:payment_id>/", views.waiting, name="parent_portal_waiting"),
    path("statut/<uuid:payment_id>/", views.status, name="parent_portal_status"),
    path("webhook/cinetpay/", views.webhook_cinetpay, name="parent_portal_webhook_cinetpay"),
    path("recu/<uuid:payment_id>/", views.receipt, name="parent_portal_receipt"),
    path("historique/", views.history, name="parent_portal_history"),
]
```

Créer `economat/templates/economat/parent_portal/receipt.html` — adapter
`economat/templates/economat/econome/receipt.html` (déjà existant, gabarit
imprimable avec bouton `window.print()`) : copier ce fichier tel quel puis
remplacer uniquement les données affichées par les variables de contexte
ci-dessus (`payment`, `school`, `student`, `klass`) — la structure visuelle
(bandeau vert, montant en gros, bouton "Imprimer / PDF") reste identique.

Créer `economat/templates/economat/parent_portal/history.html` :

```django
{% extends "economat/base.html" %}
{% block title %}Historique de mes paiements{% endblock %}
{% block content %}
<div style="max-width:520px;margin:3rem auto;">
  <div class="card" style="padding:1.75rem;margin-bottom:1.25rem;">
    <h1 style="font-size:1.125rem;font-weight:700;margin-bottom:1rem;">Historique de mes paiements</h1>
    {% if form.non_field_errors %}
    <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:.75rem 1rem;margin-bottom:1rem;color:#b91c1c;font-size:.84375rem;">
      {{ form.non_field_errors.0 }}
    </div>
    {% endif %}
    <form method="post" style="display:flex;flex-direction:column;gap:1rem;">
      {% csrf_token %}
      <div><label class="field-label">{{ form.school.label }}</label>{{ form.school }}</div>
      <div><label class="field-label">{{ form.matricule.label }}</label>{{ form.matricule }}</div>
      <button type="submit" class="btn-primary" style="width:100%;padding:.75rem;font-weight:600;">Voir mes paiements</button>
    </form>
  </div>

  {% if payments is not None %}
  <div class="card" style="padding:1.5rem;">
    <div style="font-size:.8125rem;color:#9397a8;margin-bottom:1rem;">
      {{ student.first_name }} {{ student.last_name|upper }} &middot; {{ payments|length }} paiement(s)
    </div>
    {% for p in payments %}
    <div style="display:flex;justify-content:space-between;align-items:center;padding:.65rem 0;{% if not forloop.last %}border-bottom:1px solid #f4f5f7;{% endif %}">
      <div>
        <div style="font-size:.84375rem;font-weight:600;">{{ p.amount }} FCFA</div>
        <div style="font-size:.75rem;color:#9397a8;">
          {{ p.payment_date|date:"d/m/Y" }} &middot; {{ p.get_method_display }}
          {% if p.channel == 'PORTAIL_PARENT' %}&middot; <span style="color:#7c3aed;font-weight:600;">Portail parent</span>{% endif %}
        </div>
      </div>
      {% if p.channel == 'PORTAIL_PARENT' %}
      <a href="{% url 'economat:parent_portal_receipt' p.id %}" style="font-size:.75rem;color:#4f46e5;font-weight:600;text-decoration:none;">Reçu</a>
      {% endif %}
    </div>
    {% empty %}
    <p style="font-size:.84375rem;color:#9397a8;">Aucun paiement enregistré pour l'instant.</p>
    {% endfor %}
  </div>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest economat/tests/test_parent_portal_receipt_history.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest economat/tests/ -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add economat/interface/parent_portal/views.py economat/interface/parent_portal/urls.py economat/templates/economat/parent_portal/receipt.html economat/templates/economat/parent_portal/history.html economat/tests/test_parent_portal_receipt_history.py
git commit -m "feat(parent-portal): reçu + historique des paiements

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012NtEzKCRrnrbk4FfzFuwr9"
```

---

### Task 16: Distinction visuelle guichet / portail

**Files:**
- Modify: `economat/templates/economat/econome/payments_list.html`
- Modify: `economat/templates/economat/director/dashboard.html`

**Interfaces:**
- Consumes: `PaymentModel.channel` (Task 4), déjà présent sur chaque `p` de ces listes.

- [ ] **Step 1: Badge dans `payments_list.html` (économe)**

Dans `economat/templates/economat/econome/payments_list.html`, juste après
le bloc `{% if method == 'MOBILE_MONEY' and p.mobile_operator %}` déjà
présent (ajouté en session précédente), ajouter :

```django
            {% if p.channel == 'PORTAIL_PARENT' %}
            <div style="font-size:.68rem;font-weight:700;color:#7c3aed;background:#faf5ff;
                        display:inline-block;padding:.1rem .5rem;border-radius:999px;margin-top:.25rem;">
              Portail parent
            </div>
            {% endif %}
```

- [ ] **Step 2: Vérifier l'emplacement exact du dashboard directeur**

Run: `grep -n "recent_payments\|derniers encaissements\|Derniers encaissements" economat/templates/economat/director/dashboard.html`

**Note pour l'implémenteur :** inspecter le résultat pour localiser la
boucle qui affiche les paiements récents sur le dashboard directeur (le
nom exact de la variable de boucle peut différer de `p` — l'ajuster) et y
ajouter le même badge que ci-dessus.

- [ ] **Step 3: Vérification manuelle**

Run: `.venv/bin/python -m pytest economat/tests/ -q`
Expected: PASS (pas de nouveau test dédié — changement purement visuel,
couvert indirectement par le fait que les templates continuent de
compiler ; vérifier en Task 20 lors du test de bout en bout manuel).

- [ ] **Step 4: Commit**

```bash
git add economat/templates/economat/econome/payments_list.html economat/templates/economat/director/dashboard.html
git commit -m "feat(payment): badge visuel distinguant guichet / portail parent

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012NtEzKCRrnrbk4FfzFuwr9"
```

---

### Task 17: Rafraîchissement auto du dashboard directeur

**Files:**
- Modify: `economat/interface/director/views/dashboard.py`
- Modify: `economat/interface/director/views/__init__.py`
- Modify: `economat/interface/director/urls.py`
- Modify: `economat/templates/economat/director/dashboard.html`

**Interfaces:**
- Produces: `dashboard_refresh(request) -> JsonResponse({"collected_today": int})`, endpoint pollé en JS toutes les 20s.

- [ ] **Step 1: Localiser la vue et ses agrégats actuels**

Run: `grep -n "^def dashboard" -A 5 economat/interface/director/views/dashboard.py`

La vue `dashboard()` (`economat/interface/director/views/dashboard.py`)
calcule déjà `collected_today` (somme des paiements `VALID` du jour) et le
passe au template via `base_context(...)` — vérifié dans le code source :
`ctx = base_context(request, active_school, active_year_orm, "dashboard",
schools=schools, bi=bi_data, ...)`. Il n'y a en revanche **aucun compteur
du nombre de paiements du jour** dans le contexte actuel — le polling
compare donc le **montant total encaissé aujourd'hui** (`collected_today`),
qui augmente dès qu'un nouveau paiement (guichet ou portail) est validé.

- [ ] **Step 2: Ajouter un endpoint JSON de rafraîchissement**

Dans `economat/interface/director/views/dashboard.py`, ajouter :

```python
@login_required
def dashboard_refresh(request):
    """
    Endpoint JSON léger, pollé par le dashboard directeur (JS, toutes les
    20s) pour signaler les nouveaux encaissements sans reload de page.
    Renvoie le même total que `collected_today` calculé par dashboard().
    """
    from django.http import JsonResponse
    from economat.infrastructure.models import PaymentModel
    import datetime
    from django.db.models import Sum

    school_id_p = request.GET.get("school")
    year_id_p = request.GET.get("year")
    if not school_id_p or not year_id_p:
        return JsonResponse({"collected_today": 0})

    today = datetime.date.today()
    collected_today = (
        PaymentModel.objects
        .filter(state="VALID", payment_date=today,
                enrollment__school_year_id=year_id_p,
                enrollment__school_year__school_id=school_id_p)
        .aggregate(t=Sum("amount"))["t"] or 0
    )
    return JsonResponse({"collected_today": collected_today})
```

`economat/interface/director/views/__init__.py` ré-exporte explicitement
chaque vue du package (`from .dashboard import dashboard,
secretary_dashboard, switch_year`, puis `__all__`) pour que
`director/urls.py` (`from . import views; views.dashboard`) fonctionne.
Ajouter `dashboard_refresh` à cette ré-export :

```python
from .dashboard import dashboard, dashboard_refresh, secretary_dashboard, switch_year
```

Et l'ajouter à la liste `__all__` du même fichier :

```python
__all__ = [
    "dashboard", "dashboard_refresh", "secretary_dashboard", "switch_year",
    "manage_years", "activate_year", "close_year",
    "add_level", "add_class", "configure_pricing",
    "students_list", "register_student", "student_detail",
    "class_detail", "promote_class",
    "alerts", "export_renvoyables", "school_settings", "chat",
]
```

Puis monter la route dans `economat/interface/director/urls.py` (même
style que les routes voisines, ex. `director_dashboard`) :

```python
path("actualisation/", views.dashboard_refresh, name="dashboard_refresh"),
```

- [ ] **Step 3: Ajouter le polling JS dans le template**

Dans `economat/templates/economat/director/dashboard.html`, ajouter en
fin de fichier (avant `{% endblock %}`) — `window.showToast` existe déjà
globalement (défini dans `economat/templates/economat/base.html`, déjà
utilisé par `offline-sync.js`) :

```django
<script>
(function () {
  var lastCollectedToday = {{ collected_today|default:0 }};
  var schoolId = "{{ school.id|default:'' }}";
  var yearId = "{{ school_year.id|default:'' }}";
  if (!schoolId || !yearId) return;

  setInterval(function () {
    fetch("{% url 'economat:dashboard_refresh' %}?school=" + schoolId + "&year=" + yearId)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.collected_today > lastCollectedToday) {
          var delta = data.collected_today - lastCollectedToday;
          if (window.showToast) {
            window.showToast("+" + delta.toLocaleString('fr-FR') + " FCFA encaissé", "success");
          }
          lastCollectedToday = data.collected_today;
        }
      });
  }, 20000);
})();
</script>
```

- [ ] **Step 4: Vérification manuelle**

Run: `.venv/bin/python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 5: Commit**

```bash
git add economat/interface/director/views/dashboard.py economat/interface/director/urls.py economat/templates/economat/director/dashboard.html
git commit -m "feat(dashboard): rafraîchissement auto des encaissements du jour (polling 20s)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012NtEzKCRrnrbk4FfzFuwr9"
```

---

### Task 18: CTA landing page

**Files:**
- Modify: `economat/templates/economat/landing.html`

**Interfaces:**
- Consumes: route `economat:parent_portal_search` (Task 12).

- [ ] **Step 1: Ajouter le bouton dans le hero**

Dans `economat/templates/economat/landing.html`, section `.hero-cta`
(actuellement un seul bouton "Accéder à la plateforme"), ajouter un second
bouton à sa suite :

```django
<a href="{% url 'economat:parent_portal_search' %}" class="btn btn-outline"
   style="padding:.8rem 1.75rem;font-size:.9375rem;font-weight:700;
          background:rgba(255,255,255,.1);color:#fff;border-color:rgba(255,255,255,.25);">
  Payer les frais de mon enfant
</a>
```

- [ ] **Step 2: Vérifier le rendu**

Run: `.venv/bin/python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_test')
django.setup()
from django.template.loader import get_template
get_template('economat/landing.html')
print('OK')
"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add economat/templates/economat/landing.html
git commit -m "feat(landing): CTA vers le portail de paiement parent

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012NtEzKCRrnrbk4FfzFuwr9"
```

---

### Task 19: `CinetPayGateway` (implémentation réelle)

**Files:**
- Create: `economat/infrastructure/payment/cinetpay_gateway.py`
- Test: `economat/tests/test_cinetpay_gateway.py`

**Interfaces:**
- Consumes: `PaymentGateway`, `GatewayInitiationResult`, `GatewayWebhookEvent`, `GatewayPaymentStatus` (Task 6).
- Produces: `CinetPayGateway(api_key, site_id, secret_key)` — implémentation complète du port contre l'API CinetPay v2.

CinetPay documente publiquement `POST https://api-checkout.cinetpay.com/v2/payment`
pour initier un paiement (fonctionne en mode Mobile Money direct si
`channels` est restreint et le numéro de téléphone du client fourni — la
plupart des intégrations Mobile Money côté CinetPay poussent alors une
confirmation directement sur le téléphone plutôt que d'exiger une
redirection navigateur), et `POST https://api-checkout.cinetpay.com/v2/payment/check`
pour vérifier le statut d'une transaction par `transaction_id`. Le webhook
(`notify_url`) reçoit un POST avec au minimum `cpm_trans_id` (référence de
transaction) et un statut ; CinetPay recommande de **revérifier le statut
via `/v2/payment/check`** plutôt que de faire confiance au contenu brut du
webhook — c'est ce que cette implémentation fait, ce qui a un avantage de
sécurité supplémentaire par rapport à une simple vérification de
signature : même si le corps du webhook était falsifié, le statut utilisé
est celui renvoyé par un appel serveur-à-serveur authentifié par
`apikey`/`site_id` vers CinetPay lui-même.

**Avant de considérer cette tâche terminée :** tester contre le compte
sandbox CinetPay réel (une fois ouvert) avec une vraie transaction Mobile
Money de test, et ajuster les noms de champs exacts de la réponse JSON
si la documentation live de CinetPay diffère de ce qui est écrit
ci-dessous — c'est le seul point de cette tâche qui ne peut pas être
validé sans un compte marchand actif.

- [ ] **Step 1: Write the tests (avec l'API HTTP mockée)**

```python
# economat/tests/test_cinetpay_gateway.py
"""
tests/test_cinetpay_gateway.py
=================================
CinetPayGateway : les appels HTTP réels sont mockés (requests_mock) — ce
test vérifie le contrat (paramètres envoyés, interprétation de la réponse),
pas la disponibilité réelle de l'API CinetPay.
"""
import json
import pytest
import requests_mock

from economat.infrastructure.payment.cinetpay_gateway import CinetPayGateway
from economat.application.ports.payment_gateway import GatewayPaymentStatus


@pytest.fixture
def gateway():
    return CinetPayGateway(api_key="test-key", site_id="123456", secret_key="test-secret")


def test_initiate_payment_sends_expected_fields(gateway):
    with requests_mock.Mocker() as m:
        m.post("https://api-checkout.cinetpay.com/v2/payment", json={
            "code": "201", "message": "CREATED",
            "data": {"payment_token": "tok_abc", "payment_url": "https://checkout.cinetpay.com/x"},
        })
        result = gateway.initiate_payment(
            phone="0700000000", operator="ORANGE", amount_fcfa=25000,
            description="Frais scolarité", notify_url="https://example.com/webhook/",
        )
        assert result.success
        assert result.transaction_ref  # généré côté nous, envoyé comme transaction_id

        sent = json.loads(m.request_history[0].body)
        assert sent["apikey"] == "test-key"
        assert sent["site_id"] == "123456"
        assert sent["amount"] == 25000
        assert sent["currency"] == "XOF"
        assert sent["customer_phone_number"] == "0700000000"
        assert sent["notify_url"] == "https://example.com/webhook/"
        assert sent["channels"] == "MOBILE_MONEY"


def test_initiate_payment_reports_failure_on_error_code(gateway):
    with requests_mock.Mocker() as m:
        m.post("https://api-checkout.cinetpay.com/v2/payment", json={
            "code": "600", "message": "INVALID_AMOUNT",
        })
        result = gateway.initiate_payment(
            phone="0700000000", operator="ORANGE", amount_fcfa=25000,
            description="Frais scolarité", notify_url="https://example.com/webhook/",
        )
        assert result.success is False
        assert "INVALID_AMOUNT" in result.error_message


def test_initiate_payment_reports_failure_on_network_error(gateway):
    with requests_mock.Mocker() as m:
        m.post("https://api-checkout.cinetpay.com/v2/payment", exc=ConnectionError)
        result = gateway.initiate_payment(
            phone="0700000000", operator="ORANGE", amount_fcfa=25000,
            description="Frais scolarité", notify_url="https://example.com/webhook/",
        )
        assert result.success is False


def test_parse_webhook_status_reverifies_via_check_endpoint(gateway):
    body = json.dumps({"cpm_trans_id": "cp-txn-123"}).encode()
    with requests_mock.Mocker() as m:
        m.post("https://api-checkout.cinetpay.com/v2/payment/check", json={
            "code": "00", "data": {"status": "ACCEPTED"},
        })
        event = gateway.parse_webhook_status(body)
        assert event.transaction_ref == "cp-txn-123"
        assert event.status == GatewayPaymentStatus.ACCEPTED


def test_parse_webhook_status_refused(gateway):
    body = json.dumps({"cpm_trans_id": "cp-txn-456"}).encode()
    with requests_mock.Mocker() as m:
        m.post("https://api-checkout.cinetpay.com/v2/payment/check", json={
            "code": "00", "data": {"status": "REFUSED"},
        })
        event = gateway.parse_webhook_status(body)
        assert event.status == GatewayPaymentStatus.REFUSED


def test_verify_webhook_signature_accepts_known_site_id(gateway):
    body = json.dumps({"cpm_trans_id": "cp-txn-123", "cpm_site_id": "123456"}).encode()
    assert gateway.verify_webhook_signature(body, headers={}) is True


def test_verify_webhook_signature_rejects_mismatched_site_id(gateway):
    body = json.dumps({"cpm_trans_id": "cp-txn-123", "cpm_site_id": "999999"}).encode()
    assert gateway.verify_webhook_signature(body, headers={}) is False
```

**Note pour l'implémenteur :** ajouter `requests` et `requests-mock` à
`requirements.txt` / `requirements-dev.txt` (vérifier lequel des deux
fichiers existe et où `requests` est peut-être déjà une dépendance
transitive — l'installer explicitement si absent : `pip install requests
requests-mock` puis figer la version dans le fichier de requirements
utilisé par le projet).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest economat/tests/test_cinetpay_gateway.py -v`
Expected: FAIL — module inexistant.

- [ ] **Step 3: Implement**

```python
# economat/infrastructure/payment/cinetpay_gateway.py
"""
infrastructure/payment/cinetpay_gateway.py
=============================================
Implémentation de PaymentGateway contre l'API CinetPay v2.

Sécurité du webhook : plutôt que de faire confiance au contenu brut du
POST reçu sur notify_url (qui pourrait être falsifié par un tiers qui
devine l'URL), on ne retient du webhook QUE la référence de transaction
(cpm_trans_id), et on revérifie le statut réel via un appel
serveur-à-serveur authentifié (apikey/site_id) à /v2/payment/check. C'est
cet appel authentifié, et non le contenu du POST entrant, qui fait foi.

⚠️ À valider contre un compte sandbox CinetPay réel avant mise en
production — les noms de champs exacts de la réponse JSON peuvent avoir
évolué depuis la rédaction de ce fichier. Voir le commentaire de la classe
Task 19 dans docs/superpowers/plans/2026-09-13-parent-payment-portal.md.
"""
from __future__ import annotations

import uuid

import requests

from economat.application.ports.payment_gateway import (
    GatewayInitiationResult,
    GatewayPaymentStatus,
    GatewayWebhookEvent,
    PaymentGateway,
)

_BASE_URL = "https://api-checkout.cinetpay.com/v2"

# Statuts renvoyés par CinetPay → notre enum interne.
_STATUS_MAP = {
    "ACCEPTED": GatewayPaymentStatus.ACCEPTED,
    "REFUSED":  GatewayPaymentStatus.REFUSED,
    "PENDING":  GatewayPaymentStatus.PENDING,
}


class CinetPayGateway(PaymentGateway):
    def __init__(self, api_key: str, site_id: str, secret_key: str) -> None:
        self._api_key = api_key
        self._site_id = site_id
        self._secret_key = secret_key

    def initiate_payment(
        self, phone: str, operator: str, amount_fcfa: int,
        description: str, notify_url: str,
    ) -> GatewayInitiationResult:
        transaction_ref = f"SUKULU-{uuid.uuid4().hex[:16]}"
        payload = {
            "apikey": self._api_key,
            "site_id": self._site_id,
            "transaction_id": transaction_ref,
            "amount": amount_fcfa,
            "currency": "XOF",
            "description": description,
            "notify_url": notify_url,
            "channels": "MOBILE_MONEY",
            "customer_phone_number": phone,
        }
        try:
            resp = requests.post(f"{_BASE_URL}/payment", json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as e:
            return GatewayInitiationResult(success=False, error_message=str(e))

        if data.get("code") not in ("201", "00"):
            return GatewayInitiationResult(
                success=False, error_message=data.get("message", "Erreur CinetPay inconnue."),
            )

        return GatewayInitiationResult(success=True, transaction_ref=transaction_ref)

    def verify_webhook_signature(self, raw_body: bytes, headers: dict) -> bool:
        """
        CinetPay identifie l'appelant par cpm_site_id dans le corps du
        webhook. On rejette tout webhook qui ne correspond pas à NOTRE
        site_id — la confirmation réelle du statut vient ensuite de
        l'appel authentifié /v2/payment/check dans parse_webhook_status(),
        jamais du contenu brut de ce POST.
        """
        import json
        try:
            data = json.loads(raw_body)
        except (json.JSONDecodeError, TypeError):
            return False
        return str(data.get("cpm_site_id", "")) == str(self._site_id)

    def parse_webhook_status(self, raw_body: bytes) -> GatewayWebhookEvent:
        import json
        data = json.loads(raw_body)
        transaction_ref = data["cpm_trans_id"]

        check_payload = {
            "apikey": self._api_key, "site_id": self._site_id,
            "transaction_id": transaction_ref,
        }
        resp = requests.post(f"{_BASE_URL}/payment/check", json=check_payload, timeout=15)
        resp.raise_for_status()
        check_data = resp.json()
        status_str = check_data.get("data", {}).get("status", "PENDING")

        return GatewayWebhookEvent(
            transaction_ref=transaction_ref,
            status=_STATUS_MAP.get(status_str, GatewayPaymentStatus.PENDING),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest economat/tests/test_cinetpay_gateway.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest economat/tests/ -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add economat/infrastructure/payment/cinetpay_gateway.py economat/tests/test_cinetpay_gateway.py requirements*.txt
git commit -m "feat(payment): CinetPayGateway — implémentation réelle contre l'API v2

Vérifie le statut via un appel authentifié /v2/payment/check plutôt que
de faire confiance au contenu brut du webhook. À valider contre un compte
sandbox CinetPay réel avant mise en production (voir commentaire du
fichier).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012NtEzKCRrnrbk4FfzFuwr9"
```

---

### Task 20: Vérification de bout en bout

**Files:** aucun nouveau fichier — vérification manuelle du parcours complet avec `FakePaymentGateway`.

- [ ] **Step 1: Lancer le serveur en local**

Run: `.venv/bin/python manage.py runserver`

- [ ] **Step 2: Créer des données de test si nécessaire**

Si aucune école/élève de test n'existe déjà en local, utiliser le shell
Django pour créer une école, une année active, un niveau, une classe et un
élève (mêmes champs que la fixture `active_enrollment` de Task 5), et
noter le matricule généré.

- [ ] **Step 3: Parcourir le parcours parent manuellement**

1. Ouvrir `/` (landing page) → cliquer "Payer les frais de mon enfant".
2. Sélectionner l'école, saisir le matricule → vérifier que le nom complet de l'élève s'affiche à l'écran suivant.
3. Saisir un montant, choisir un opérateur, saisir un numéro → cliquer "Payer maintenant".
4. Vérifier l'écran d'attente (spinner visible).
5. Dans un autre onglet, appeler manuellement le webhook avec `curl` en simulant une confirmation `FakePaymentGateway` (adapter la commande à la structure exacte de `simulate_confirmation()`), ou attendre que l'implémenteur ajoute un bouton de debug temporaire supprimé avant commit final.
6. Vérifier que la page d'attente redirige automatiquement vers le reçu.
7. Cliquer "Imprimer / PDF" → vérifier l'aperçu d'impression du navigateur.
8. Retourner sur `/payer/historique/`, refaire la recherche → vérifier que le paiement apparaît.

- [ ] **Step 4: Vérifier côté école**

1. Se connecter en tant que directeur/économe.
2. Ouvrir la liste des encaissements (`/econome/encaissements/`) → vérifier le badge "Portail parent" sur la ligne correspondante.
3. Ouvrir le dashboard directeur → vérifier que le montant apparaît dans les totaux du jour.

- [ ] **Step 5: Lancer la suite complète une dernière fois**

Run: `.venv/bin/python -m pytest economat/tests/ -v`
Expected: tous les tests PASS (matricule, payment_confirm, fake_gateway,
cinetpay_gateway, initiate_online_payment, confirm_online_payment,
parent_portal_search, parent_portal_pay, parent_portal_flow,
parent_portal_receipt_history, record_payment_channel, + suite existante).

- [ ] **Step 6: Commit final si des ajustements ont été faits pendant la vérification**

```bash
git add -A
git commit -m "fix: ajustements suite à la vérification de bout en bout du portail parent

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012NtEzKCRrnrbk4FfzFuwr9"
```
