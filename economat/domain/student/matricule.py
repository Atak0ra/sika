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
