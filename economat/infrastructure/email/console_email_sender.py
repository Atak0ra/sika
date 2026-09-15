"""
infrastructure/email/console_email_sender.py
=============================================
Adaptateur de fallback — affiche l'email dans la console (stdout).
Utilisé en développement / tests quand RESEND_API_KEY n'est pas défini.
Aucun appel réseau.
"""
from __future__ import annotations

from economat.application.ports.email_sender import EmailSender


class ConsoleEmailSender(EmailSender):

    def send(self, *, to: str, subject: str, html: str) -> None:
        separator = "─" * 60
        print(f"\n{separator}")
        print(f"[ConsoleEmailSender] Email simulé (pas de RESEND_API_KEY)")
        print(f"  À       : {to}")
        print(f"  Sujet   : {subject}")
        print(f"  Contenu :")
        # Affiche le HTML brut (lisible pour déboguer)
        print(html)
        print(f"{separator}\n")
