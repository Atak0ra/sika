"""
infrastructure/email/resend_email_sender.py
=============================================
Adaptateur Resend — envoie un email transactionnel via l'API HTTP Resend.

Endpoint  : POST https://api.resend.com/emails
Auth      : Authorization: Bearer <RESEND_API_KEY>
Corps     : { from, to, subject, html }

Lit la configuration depuis Django settings :
  RESEND_API_KEY    — clé API Resend (obligatoire en production)
  RESEND_FROM_EMAIL — adresse expéditrice, ex. "Sukulu <no-reply@sukulu.app>"

Lève EmailSendError en cas d'échec (timeout, statut != 200, clé manquante).
Utilise `requests` déjà présent dans requirements.txt — pas de SDK supplémentaire.
"""
from __future__ import annotations

import requests
from django.conf import settings

from economat.application.ports.email_sender import EmailSender, EmailSendError

RESEND_API_URL = "https://api.resend.com/emails"
TIMEOUT_SECONDS = 10


class ResendEmailSender(EmailSender):

    def send(self, *, to: str, subject: str, html: str) -> None:
        api_key   = getattr(settings, "RESEND_API_KEY", "").strip()
        from_addr = getattr(settings, "RESEND_FROM_EMAIL", "Sukulu <no-reply@sukulu.app>")

        if not api_key:
            raise EmailSendError(
                "RESEND_API_KEY n'est pas défini dans les settings. "
                "Ajoutez-le dans votre fichier .env ou les variables d'environnement."
            )

        try:
            response = requests.post(
                RESEND_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type":  "application/json",
                },
                json={
                    "from":    from_addr,
                    "to":      [to],
                    "subject": subject,
                    "html":    html,
                },
                timeout=TIMEOUT_SECONDS,
            )
        except requests.exceptions.Timeout:
            raise EmailSendError(
                f"Délai d'attente dépassé lors de l'envoi de l'email à {to!r}."
            )
        except requests.exceptions.RequestException as exc:
            raise EmailSendError(f"Erreur réseau lors de l'envoi de l'email : {exc}") from exc

        if response.status_code not in (200, 201):
            raise EmailSendError(
                f"Resend a retourné HTTP {response.status_code} : {response.text[:300]}"
            )
