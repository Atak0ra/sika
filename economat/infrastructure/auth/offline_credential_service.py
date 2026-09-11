"""
infrastructure/auth/offline_credential_service.py
====================================================
Service de gestion du verifier PBKDF2 dédié à l'auth offline PWA.

Principe de sécurité :
  - Le verifier est calculé avec un sel PROPRE (offline_salt), distinct
    du sel du hash Django (auth_user.password).
  - Même compromis du verifier → ne permet PAS de se connecter côté serveur.
  - PBKDF2-HMAC-SHA256 avec 200 000 itérations (OWASP 2024).
  - Expiration 30 jours glissants, renouvelé à chaque connexion en ligne.

Le client JS re-calcule le même PBKDF2 via SubtleCrypto (WebCrypto API)
et compare au verifier stocké dans IndexedDB (jamais envoyé au serveur).

Ce service est appelé UNE SEULE FOIS après une connexion en ligne réussie
(dans accounts/views.py::login_view).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import timedelta

from django.utils import timezone


# Durée de validité du verifier offline (30 jours glissants)
OFFLINE_CREDENTIAL_TTL_DAYS = 30
# Nombre d'itérations PBKDF2 (OWASP 2024 recommande >= 210 000 pour SHA-256)
PBKDF2_ITERATIONS = 210_000
# Longueur du sel en bytes
SALT_BYTES = 16


def generate_offline_verifier(raw_password: str) -> dict:
    """
    Calcule le verifier PBKDF2 dédié à l'usage offline.

    Args:
        raw_password : mot de passe en clair (reçu lors de la connexion en ligne).

    Returns:
        dict avec les champs à stocker en base ET à envoyer au client :
        {
            "verifier":     str,   # hash hex (à stocker en base, NE PAS renvoyer tel quel)
            "offline_salt": str,   # sel base64 (à envoyer au client pour recalcul)
            "iterations":   int,
            "expires_at":   datetime,
        }
    """
    salt_bytes  = secrets.token_bytes(SALT_BYTES)
    offline_salt = base64.b64encode(salt_bytes).decode("ascii")

    verifier_bytes = hashlib.pbkdf2_hmac(
        "sha256",
        raw_password.encode("utf-8"),
        salt_bytes,
        PBKDF2_ITERATIONS,
    )
    verifier_hex = verifier_bytes.hex()

    return {
        "verifier":     verifier_hex,
        "offline_salt": offline_salt,
        "iterations":   PBKDF2_ITERATIONS,
        "expires_at":   timezone.now() + timedelta(days=OFFLINE_CREDENTIAL_TTL_DAYS),
    }


def save_offline_credential(user, raw_password: str) -> dict:
    """
    Génère et persiste le verifier offline pour un utilisateur.
    Appelé après une connexion en ligne réussie.

    Returns:
        dict avec les données à envoyer au client JS (sans le verifier brut) :
        {
            "offline_salt": str,
            "iterations":   int,
            "expires_at":   str (ISO),
            "verifier":     str (hex — à stocker dans IndexedDB côté client)
        }
    """
    from economat.infrastructure.models import OfflineCredentialModel

    cred_data = generate_offline_verifier(raw_password)

    OfflineCredentialModel.objects.update_or_create(
        user=user,
        defaults={
            "verifier":        cred_data["verifier"],
            "offline_salt":    cred_data["offline_salt"],
            "iterations":      cred_data["iterations"],
            "expires_at":      cred_data["expires_at"],
            "failed_attempts": 0,
        },
    )

    # On envoie TOUT au client (y compris le verifier hex) :
    # le client le stocke dans IndexedDB pour recalculer localement.
    # Ce verifier ne permet PAS de se connecter côté serveur.
    return {
        "verifier":     cred_data["verifier"],
        "offline_salt": cred_data["offline_salt"],
        "iterations":   cred_data["iterations"],
        "expires_at":   cred_data["expires_at"].isoformat(),
    }


def reset_failed_attempts(user) -> None:
    """Remet le compteur d'échecs à 0 après connexion en ligne réussie."""
    from economat.infrastructure.models import OfflineCredentialModel
    OfflineCredentialModel.objects.filter(user=user).update(failed_attempts=0)
