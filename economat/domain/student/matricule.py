"""
domain/student/matricule.py
==============================
Générateur déterministe de matricule élève.

Format : NOM3PRENOM3-AAMMJJ-HHMMSS
  - NOM3    : 3 premières lettres du nom de famille, normalisées
  - PRENOM3 : 3 premières lettres du prénom, normalisées
  - AAMMJJ  : date d'inscription (2 chiffres année + mois + jour)
  - HHMMSS  : heure d'inscription à la seconde (départageur fin)

Normalisation appliquée :
  - Suppression des accents (Unicode NFKD → ASCII)
  - Majuscules
  - Suppression de tout ce qui n'est pas A-Z (espaces, tirets, apostrophes…)
  - Si slug < N lettres → complété par 'X'

Exemples :
  Awa DIALLO    inscrite le 11/09/2026 à 14:30:52  →  DIAAWA-260911-143052
  Aïcha BEN ALI inscrit  le 11/09/2026 à 14:30:52  →  BENAIC-260911-143052
  Ba KONE       inscrit  le 11/09/2026 à 09:01:05  →  KONBAX-260911-090105

Ce module est PARTAGÉ avec le générateur JavaScript (même format, même règles).
Le fichier JS équivalent est : economat/static/economat/js/matricule.js
"""
from __future__ import annotations

import datetime
import unicodedata


def _normalize_slug(text: str, length: int = 3) -> str:
    """
    Normalise un texte en slug alphabétique de longueur fixe.

    1. Décompose les caractères Unicode (NFD) pour séparer les accents
    2. Encode en ASCII strict (ignore ce qui ne passe pas)
    3. Ne garde que les lettres A-Z
    4. Met en majuscules
    5. Tronque ou complète à `length` caractères avec 'X'
    """
    # NFD : sépare "é" en "e" + diacritique combining
    normalized = unicodedata.normalize("NFD", text)
    # encode ASCII en ignorant les diacritiques
    ascii_bytes = normalized.encode("ascii", errors="ignore")
    # ne garde que les lettres, met en majuscules
    letters = "".join(c for c in ascii_bytes.decode("ascii") if c.isalpha()).upper()
    if not letters:
        letters = "X" * length
    # tronque ou complète
    return (letters + "X" * length)[:length]


def generate_matricule(
    last_name: str,
    first_name: str,
    enrolled_at: datetime.datetime | None = None,
) -> str:
    """
    Génère le matricule déterministe d'un élève.

    Args:
        last_name   : nom de famille (ex. "Diallo", "Ben Ali", "N'Diaye")
        first_name  : prénom (ex. "Awa", "Aïcha")
        enrolled_at : date+heure d'inscription (datetime.datetime).
                      Si None → datetime.datetime.now() utilisé.

    Returns:
        Matricule au format NOM3PRENOM3-AAMMJJ-HHMMSS
        Ex. : "DIAAWA-260911-143052"
    """
    if enrolled_at is None:
        enrolled_at = datetime.datetime.now()

    nom_slug    = _normalize_slug(last_name.replace("-", "").replace("'", ""), 3)
    prenom_slug = _normalize_slug(first_name.replace("-", "").replace("'", ""), 3)
    date_part   = enrolled_at.strftime("%y%m%d")  # AAMMJJ
    time_part   = enrolled_at.strftime("%H%M%S")  # HHMMSS

    return f"{nom_slug}{prenom_slug}-{date_part}-{time_part}"


def generate_receipt_number(
    matricule: str,
    class_name: str,
    installment_label: str,
    paid_at: datetime.datetime | None = None,
) -> str:
    """
    Génère le numéro de reçu déterministe à partir du matricule élève.

    Format : MATRICULE/R-AAMMJJ-HHMMSS/TRANCHE/CLASSE
    Ex. : "DIAAWA-260911-143052/R-260915-093012/T1/CM2A"

    Args:
        matricule         : matricule de l'élève (généré par generate_matricule)
        class_name        : nom de la classe (ex. "CM2 A" → "CM2A")
        installment_label : libellé de la tranche (ex. "T1", "T2", "M3")
        paid_at           : datetime du paiement. Si None → now().

    Returns:
        Numéro de reçu unique et lisible.
    """
    if paid_at is None:
        paid_at = datetime.datetime.now()

    # Normalise le nom de classe (supprime espaces)
    class_slug = class_name.replace(" ", "").upper()
    date_part  = paid_at.strftime("%y%m%d")
    time_part  = paid_at.strftime("%H%M%S")

    return f"{matricule}/R-{date_part}-{time_part}/{installment_label}/{class_slug}"
